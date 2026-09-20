import copy
import json
from pathlib import Path
import tempfile
import unittest
import io
from urllib.error import HTTPError
from unittest.mock import patch
from marketlab import data
from test_analytics import bars, cal


class MarketTests(unittest.TestCase):
    def test_invalid_cached_daily_response_is_replaced_with_valid_payload(self):
        import inspect
        self.assertIn('validate',inspect.signature(data.TwseClient.fetch).parameters)
        with tempfile.TemporaryDirectory() as root,patch('marketlab.data.time.sleep'):
            url='https://www.twse.com.tw/example'
            with patch('marketlab.data.urlopen',return_value=io.BytesIO(b'{"stat":"OK","date":"20200101"}')):
                data.TwseClient(root).fetch('day',url)
            def check(payload):
                if payload.get('date')!='20260918': raise ValueError('wrong session')
            with patch('marketlab.data.urlopen',return_value=io.BytesIO(b'{"stat":"OK","date":"20260918"}')) as request:
                self.assertEqual(data.TwseClient(root).fetch('day',url,validate=check)['date'],'20260918')
                self.assertEqual(request.call_count,1)

    def test_stale_calendar_cannot_replace_more_recent_snapshot(self):
        from marketlab.service import MarketService
        fixture=bars(70)
        class Client:
            rows=fixture
            def __init__(self,*args): self.evidence=[]
            def universe(self): return [dict(symbol='2330',name='test',kind='stock')]
            def calendar(self,*args): return cal(self.rows)
            def market_bundles(self,*args): return {'2330':dict(rows=self.rows,issues=[])}
        with tempfile.TemporaryDirectory() as root:
            instance=MarketService(root,client_factory=Client,workers=1)
            old=instance.update();Client.rows=fixture[:-1]
            with self.assertRaises(ValueError): instance.update()
            self.assertEqual(instance.store.snapshot()['id'],old['id'])
    def test_full_market_compacts_old_details_but_preserves_predictions_and_audit(self):
        from marketlab.service import MarketService
        with tempfile.TemporaryDirectory() as root:
            instance=MarketService(root,workers=1)
            self.assertTrue(hasattr(instance,'compact_history'),'long-running state compaction not implemented')
            for n in range(5):
                snapshot=dict(id='s'+str(n),as_of='2026-09-18',created_at=f'2026-09-18T19:0{n}:00',settings={'fee_rate':.001},
                    rows=[dict(symbol='2330',kind='stock',bars=[1]*1000,validation={'large':[1]*1000},horizons={'1':dict(expected_return=2.,p_positive=.6,samples=[1]*1000)})])
                instance.store.save_snapshot(snapshot)
            instance.store.put('reconciled',[{'snapshot_id':'s0','return_pct':1.2}])
            instance.compact_history()
            self.assertEqual(len(instance.store.history(limit=None)),5)
            self.assertNotIn('bars',instance.store.snapshot('s0')['rows'][0])
            self.assertEqual(instance.store.snapshot('s0')['rows'][0]['horizons']['1']['expected_return'],2.)
            self.assertEqual(instance.store.snapshot('s0')['settings'],{'fee_rate':.001})
            self.assertIn('bars',instance.store.snapshot('s4')['rows'][0])
            self.assertEqual(instance.store.get('reconciled')[0]['return_pct'],1.2)
    def test_daily_redirect_falls_back_to_official_canonical_query_and_caches(self):
        original='https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date=20240123&type=ALLBUT0999'
        urls=[]
        def download(request,**kwargs):
            urls.append(request.full_url)
            if request.full_url==original: raise HTTPError(original,308,'redirect',{},None)
            return io.BytesIO(b'{"stat":"OK","date":"20240123"}')
        with tempfile.TemporaryDirectory() as root,patch('marketlab.data.time.sleep'),patch('marketlab.data.urlopen',side_effect=download):
            client=data.TwseClient(root)
            self.assertEqual(client.fetch('test',original)['date'],'20240123')
            self.assertEqual(urls[-1],'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20240123&type=ALLBUT0999&response=json')
            client.fetch('test',original)
            self.assertEqual(len(urls),2)
    def test_foreign_currency_listing_preserved_with_explicit_currency(self):
        result=data.listed_universe([{'公司代號':'2330','公司簡稱':'台積電','上市日期':'19940905'}],
           {'status':'success','data':[{'stockNo':'00625K','stockName':'富邦上証+R(人民幣)','listingDate':'2011.09.26'}]})
        self.assertEqual(next(r for r in result if r['symbol']=='00625K')['currency'],'CNY')
    def test_depositary_receipts_are_not_ordinary_shares(self):
        result=data.listed_universe([{'公司代號':'2330','公司簡稱':'台積電','上市日期':'19940905'},
                {'公司代號':'910322','公司簡稱':'康師傅-DR'}, {'公司代號':'9105','公司簡稱':'泰金寶-DR'}],
                {'status':'success','data':[{'stockNo':'0050','stockName':'台灣50','listingDate':'2003.06.30'}]})
        self.assertEqual({r['symbol'] for r in result},{'2330','0050'})

    def parser(self):
        self.assertTrue(hasattr(data, 'parse_market_day'), 'full-market parser not implemented')
        return data.parse_market_day

    def test_live_daily_table_and_adjustment_marker(self):
        payload=json.loads((Path(__file__).parent/'fixtures/mi-index-live.json').read_text(encoding='utf-8'))
        rows=self.parser()(payload,'2026-09-18')
        self.assertIn('2330',rows)
        self.assertIn('00400A',rows)
        self.assertIn('009800',rows)
        self.assertTrue(rows['2330']['valid'])
        fields=payload['tables'][8]['fields']; values=payload['tables'][8]['data'][0]
        values[fields.index('漲跌(+/-)')]='<p>X</p>'
        self.assertEqual(self.parser()(payload,'2026-09-18')['00400A']['change'][0],'X')

    def test_wrong_date_and_missing_fields_rejected(self):
        parse=self.parser()
        with self.assertRaises(ValueError): parse({'stat':'OK','date':'20260917','tables':[]},'2026-09-18')
        with self.assertRaises(ValueError): parse({'stat':'OK','date':'20260918','tables':[]},'2026-09-18')

    def test_official_universe_includes_new_etfs_and_suspended_company(self):
        self.assertTrue(hasattr(data,'listed_universe'), 'official classification not implemented')
        result=data.listed_universe([{'公司代號':'2330','公司簡稱':'台積电','上市日期':'19940905'},
                                    {'公司代號':'9999','公司簡稱':'停牌股','上市日期':'20000101'}],
            {'status':'success','data':[{'stockNo':'00400A','stockName':'主動股票','listingDate':'2026.04.09'},
              {'stockNo':'009800','stockName':'六碼股票','listingDate':'2025.01.01'}]})
        self.assertEqual({x['symbol'] for x in result},{'2330','9999','00400A','009800'})
        self.assertEqual(next(x for x in result if x['symbol']=='00400A')['kind'],'etf')
        with self.assertRaises(ValueError): data.listed_universe([],{'status':'fail','data':[]})

    def test_unexpected_bond_or_leverage_in_filtered_source_rejected(self):
        self.assertTrue(hasattr(data,'listed_universe'))
        for symbol in ['00679B','00631L','00632R']:
            with self.assertRaises(ValueError):
                data.listed_universe([{'公司代號':'2330','公司簡稱':'台積電','上市日期':'19940905'}],
                    {'status':'success','data':[{'stockNo':symbol,'stockName':'unexpected','listingDate':'2020.01.01'}]})

    def test_whole_universe_keeps_suspended_and_new_listings_excluded(self):
        from marketlab import service
        self.assertTrue(hasattr(service,'MarketService'), 'full market coordinator not implemented')
        fixture=bars(70)
        class Client:
            def __init__(self,*args): self.evidence=[]
            def universe(self): return [dict(symbol=s,name=s,kind='stock',listing_date='2025-01-01') for s in ['2330','9998','9999']]
            def calendar(self,months): return cal(fixture)
            def market_bundles(self,universe,calendar):
                return {'2330':dict(rows=fixture,issues=[]),'9998':dict(rows=fixture[:-1],issues=[]),'9999':dict(rows=[],issues=[])}
        with tempfile.TemporaryDirectory() as root:
            result=service.MarketService(root,client_factory=Client,workers=1).update()
            self.assertEqual(result['coverage']['universe_count'],3)
            self.assertEqual(result['coverage']['unavailable_count'],2)
            for row in result['rows'][1:]:
                self.assertTrue(all(not h['eligible'] and h['expected_return'] is None for h in row['horizons'].values()))
            self.assertEqual(result['rows'][1]['bars'][-1]['date'],fixture[-2]['date'])
            self.assertEqual(result['rows'][1]['data_as_of'],fixture[-2]['date'])

    def test_bulk_failure_keeps_previous_snapshot(self):
        from marketlab import service
        self.assertTrue(hasattr(service,'MarketService'))
        class Client:
            def __init__(self,*args): self.evidence=[]
            def universe(self): return [dict(symbol='2330',name='test',kind='stock')]
            def calendar(self,months): return cal(bars(65))
            def market_bundles(self,*args): raise RuntimeError('missing session')
        with tempfile.TemporaryDirectory() as root:
            instance=service.MarketService(root,client_factory=Client,workers=1)
            old=dict(id='prior',as_of='2025-01-01',created_at='2025-01-01',rows=[])
            instance.store.save_snapshot(old)
            with self.assertRaises(RuntimeError): instance.update()
            self.assertEqual(instance.store.snapshot(),old)


if __name__=='__main__': unittest.main()
