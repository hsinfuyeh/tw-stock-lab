import unittest,tempfile,copy,threading,json
from urllib.request import urlopen
from urllib.error import HTTPError
from marketlab.service import MarketService
from marketlab.server import make_server

class ResearchReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.service=MarketService(self.temp.name,workers=1)
        self.dates=[f'2026-01-{i:02d}' for i in range(1,13)]
    def tearDown(self):self.temp.cleanup()
    def snap(self,id,day,version='two-week-v2',symbols=('2330',)):
        return dict(id=id,as_of=self.dates[day],created_at=f'2026-02-{len(self.service.store.history())+1:02d}',
            calendar={'actual':self.dates[:day+1]},rows=[dict(symbol=s,kind='stock',bars=[dict(date=d,open=100,high=104,low=99,close=100,valid=True,volume=1) for d in self.dates[:day+1]]) for s in symbols],
            two_week=dict(version=version,scored_universe=[dict(symbol=s,kind='stock',name=s,reasons=['原理由']) for s in symbols],research_candidates=[]))
    def test_dedup_first_original_and_read_only(self):
        original=self.snap('a',0);self.service.store.save_snapshot(original)
        corrected=self.snap('b',0,symbols=('9999','2330'));self.service.store.save_snapshot(corrected)
        self.service.store.save_snapshot(self.snap('c',11))
        before=copy.deepcopy(self.service.store.snapshot('a'))
        r=self.service.research_report()
        old=[x for x in r['tracking'] if x['signal_date']==self.dates[0]]
        self.assertEqual(len(old),1);self.assertEqual(old[0]['snapshot_id'],'a')
        self.assertEqual(old[0]['rank'],1);self.assertEqual(old[0]['reasons'],['原理由'])
        self.assertEqual(old[0]['status'],'evaluated')
        self.assertEqual(self.service.store.snapshot('a'),before)
    def test_asof_cap_version_isolation_and_pending(self):
        self.service.store.save_snapshot(self.snap('old',0,'old-version'))
        self.service.store.save_snapshot(self.snap('a',1))
        self.service.store.save_snapshot(self.snap('b',5))
        self.service.store.save_snapshot(self.snap('future',11))
        r=self.service.research_report('b')
        self.assertEqual(r['as_of'],self.dates[5])
        self.assertEqual(len(r['tracking']),2)
        row=next(x for x in r['tracking'] if x['snapshot_id']=='a')
        self.assertEqual(row['elapsed_sessions'],4);self.assertEqual(row['status'],'pending')
        self.assertIsNone(row['net_return_pct'])
    def test_missing_bars_and_empty(self):
        self.assertEqual(self.service.research_report()['status'],'insufficient_data')
        s=self.snap('a',11);s['as_of']=self.dates[0];s['rows']=[];self.service.store.save_snapshot(s)
        self.service.store.save_snapshot(dict(self.snap('b',11),rows=[]))
        row=next(r for r in self.service.research_report()['tracking'] if r['snapshot_id']=='a')
        self.assertEqual(row['status'],'not_comparable')
        with self.assertRaises(KeyError):self.service.research_report('absent')
    def test_http_read_only_report_and_missing_id(self):
        self.service.store.save_snapshot(self.snap('a',0))
        server=make_server(self.service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_address[1]}/api/research'
            with urlopen(url+'?id=a') as response:payload=json.load(response)
            self.assertEqual(payload['snapshot_id'],'a')
            with self.assertRaises(HTTPError) as e:urlopen(url+'?id=absent')
            self.assertEqual(e.exception.code,404)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
