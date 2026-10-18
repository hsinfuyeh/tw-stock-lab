import tempfile
import unittest
from marketlab.data import Store
from marketlab.official import parse_source, T86_FIELDS
from marketlab.official_store import OfficialStore
from marketlab.institution_rankings import institution_rankings


class InstitutionRankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name)
        self.official=OfficialStore(self.store)
        self.days=['2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16']
        self.snapshot=dict(id='current',as_of=self.days[-1],created_at='2026-10-19T00:15:00+08:00',
            calendar={'actual':self.days},rows=[dict(symbol=s,name=s,kind=kind,currency='TWD',
                bars=[dict(date=d,open=100,close=100,high=101,low=99,volume=1000,valid=True) for d in self.days])
                for s,kind in [('2330','stock'),('2317','stock'),('0050','etf')]])
        self.store.save_snapshot(self.snapshot)
    def tearDown(self): self.tmp.cleanup()
    def ingest(self,dt,symbol='2330',multiplier=1,stamp='2026-10-19T00:12:00+08:00'):
        # Foreign dealer is intentionally huge and must never inflate foreign rankings.
        numbers=[100,40,60,10000,0,10000,20,30,-10,12,5,4,1,15,4,11,62]
        payload=dict(stat='OK',date=dt.replace('-',''),hints='單位：股',fields=T86_FIELDS,
                     data=[[symbol,symbol]+[str(n*multiplier) for n in numbers]])
        self.official.ingest('institution',parse_source('institution',payload,dt),
            dict(fetched_at=stamp,url='https://www.twse.com.tw/',file='fixture.json',sha256='a'*64))

    def test_independent_buy_sell_and_official_net(self):
        self.ingest(self.days[-1])
        r=institution_rankings(self.store,self.official)
        row=next(row for row in r['rows'] if row['symbol']=='2330')
        self.assertEqual(row['groups']['foreign'],dict(buy=100,sell=40,net=60))
        self.assertEqual(row['groups']['trust'],dict(buy=20,sell=30,net=-10))
        self.assertEqual(row['groups']['dealer'],dict(buy=20,sell=8,net=12))
        self.assertEqual(r['unit'],'shares')
        self.assertEqual(row['close'],100)
        self.assertEqual(r['dates'],[self.days[-1]])

    def test_five_sessions_complete_only_and_zero_preserved(self):
        for dt in self.days: self.ingest(dt)
        self.ingest(self.days[-1],'2317')
        for dt in self.days: self.ingest(dt,'0050',0)
        report=institution_rankings(self.store,self.official,sessions=5)
        rows={r['symbol']:r for r in report['rows']}
        self.assertEqual(rows['2330']['groups']['foreign']['buy'],500)
        self.assertIsNone(rows['2317']['groups']['foreign']['net'])
        self.assertEqual(rows['0050']['groups']['trust']['net'],0)
        self.assertEqual(report['coverage']['complete_symbols'],2)

    def test_corrections_and_future_date_no_hindsight_label(self):
        self.ingest(self.days[-1]); self.ingest(self.days[-1],multiplier=2,stamp='2026-10-19T01:00:00+08:00')
        self.ingest('2026-10-19',multiplier=100)
        report=institution_rankings(self.store,self.official)
        self.assertEqual(report['rows'][0]['groups']['foreign']['buy'],200)
        self.assertTrue(report['retrospective'])
        self.assertEqual(report['as_of'],'2026-10-16')
        self.assertIn('first_seen_at',report['rows'][0]['evidence'][0])

    def test_wrong_unit_missing_gross_and_readonly(self):
        row=dict(symbol='2330',key=self.days[-1],data_date=self.days[-1],published_at=None,
            period=None,unit='shares',values=dict(foreign_net=3))
        self.official.ingest('institution',[row],dict(fetched_at='2026-10-19T00:12:00+08:00',file='fixture.json'))
        wrong_unit=dict(row,symbol='2317',unit='trading_unit',values=dict(foreign_net=9000))
        self.official.ingest('institution',[wrong_unit],dict(fetched_at='2026-10-19T00:12:00+08:00',file='fixture.json'))
        before=self.store.path.read_bytes()
        report=institution_rankings(self.store,self.official)
        self.assertEqual(self.store.path.read_bytes(),before)
        self.assertEqual(report['rows'][0]['groups']['foreign']['net'],3)
        self.assertIsNone(report['rows'][0]['groups']['foreign']['buy'])
        self.assertIsNone(report['rows'][1]['groups']['foreign']['net'])
        with self.assertRaises(ValueError): institution_rankings(self.store,self.official,sessions=20)
        with self.assertRaises(KeyError): institution_rankings(self.store,self.official,snapshot_id='absent')

    def test_short_calendar_and_stale_source_are_explicit(self):
        self.ingest(self.days[-1]); self.snapshot.update(id='short',calendar={'actual':[self.days[-1]]})
        self.store.save_snapshot(self.snapshot)
        self.store.put('official_health',dict(institution=dict(status='error',error='source unavailable')))
        report=institution_rankings(self.store,self.official,sessions=5)
        self.assertEqual(report['status'],'insufficient_data')
        self.assertEqual(report['health']['status'],'error')
        self.assertIsNone(report['rows'][0]['groups']['foreign']['net'])

if __name__=='__main__': unittest.main()
