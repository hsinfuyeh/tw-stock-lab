import unittest
from datetime import date,timedelta
from marketlab.market_summary import build_market_summary
from marketlab.data import listed_universe

class MarketSummaryTests(unittest.TestCase):
    def snapshot(self):
        dates=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(21)]
        rows=[]
        for symbol,close in [('a',110),('b',90),('c',100),('etf',1000)]:
            bars=[dict(date=d,open=100,high=max(100,close),low=min(100,close),close=100,volume=100,turnover=10000,valid=True) for d in dates]
            bars[-1].update(close=close,turnover=20000)
            rows.append(dict(symbol=symbol,kind='etf' if symbol=='etf' else 'stock',industry='01',bars=bars))
        return dict(as_of=dates[-1],rows=rows,calendar={'actual':dates},two_week={'research_candidates':[{'symbol':'a'}]})

    def test_breadth_median_and_cohort(self):
        r=build_market_summary(self.snapshot())
        self.assertEqual(r['market']['advancers'],1);self.assertEqual(r['market']['decliners'],1)
        self.assertEqual(r['market']['unchanged'],1)
        self.assertAlmostEqual(r['market']['equal_weight_return_pct'],0)
        self.assertEqual(r['market']['turnover_ratio_20'],2)
        self.assertEqual(r['coverage']['daily_return']['eligible'],3)
        self.assertEqual(r['industries'][0]['median_return_pct'],0)
        self.assertTrue(r['industries'][0]['small_sample'])
        self.assertEqual(r['industries'][0]['turnover_share'],1)

    def test_independent_missing_windows_unknown_industry(self):
        s=self.snapshot();s['rows'][0].pop('industry');s['rows'][0]['bars']=s['rows'][0]['bars'][-1:]
        r=build_market_summary(s)
        self.assertEqual(r['coverage']['daily_return']['eligible'],2)
        self.assertEqual(r['coverage']['turnover']['eligible'],3)
        self.assertEqual(r['coverage']['ma20']['eligible'],2)
        self.assertIn('未記錄',[x['industry'] for x in r['industries']])

    def test_adjustment_and_wrong_date(self):
        s=self.snapshot();s['rows'][0]['bars'][-1]['change']='X';s['rows'][1]['bars'].pop()
        r=build_market_summary(s)
        self.assertEqual(r['coverage']['daily_return']['eligible'],1)
        self.assertEqual(r['coverage']['ma20']['eligible'],1)
        self.assertEqual(r['coverage']['turnover']['eligible'],2)

    def test_official_industry_is_retained(self):
        result=listed_universe([{'公司代號':'2330','公司簡稱':'台積電','產業別':'24'}],{'status':'success','data':[{'stockNo':'0050','stockName':'台灣50','listingDate':'2003.06.30'}]})
        self.assertEqual(next(r for r in result if r['symbol']=='2330')['industry'],'24')
    def test_industry_windows_have_separate_small_samples_and_provenance(self):
        s=self.snapshot();s['rows'][0]['bars']=s['rows'][0]['bars'][-2:]
        s['rows'][0].update(industry_source='official-company-master',industry_retrieved_at='2026-01-21T20:00:00')
        r=build_market_summary(s);industry=r['industries'][0]
        self.assertTrue(industry['momentum20_small_sample'])
        self.assertEqual(industry['momentum20_count'],2)
        self.assertEqual(r['classification_sources'][0]['retrieved_at'],'2026-01-21T20:00:00')

if __name__=='__main__':unittest.main()
