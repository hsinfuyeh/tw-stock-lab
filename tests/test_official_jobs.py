import tempfile
import unittest
import threading
import json
from urllib.request import urlopen, Request
from marketlab.service import MarketService
from marketlab.official_jobs import OfficialJobs, collect_for_market
from marketlab.official import T86_FIELDS, MARGIN_FIELDS
from marketlab.server import make_server


class FakeClient:
    def __init__(self,root): self.evidence=[]
    def fetch(self,key,url,max_age=None,validate=None):
        if 'margin' in key: raise RuntimeError('single source failure')
        if 'institution' in key:
            p=dict(stat='OK',date='20261007',fields=T86_FIELDS,hints='單位：股',data=[['2330','台積電']+['1']*17])
        elif 'revenue' in key:
            p=[{'公司代號':'2330','資料年月':'11508','出表日期':'1150917','營業收入-去年當月營收':'100','營業收入-去年同月增減(%)':'10'}]
        elif 'announcement' in key:
            p=[{'公司代號':'2330','發言日期':'1151007','發言時間':'70004','事實發生日':'1151007','主旨 ':'hello'}]
        else: p=[dict(Code='2330',Date='1151008',Exdividend='息')]
        if validate: validate(p)
        self.evidence.append(dict(fetched_at='2026-10-08T08:00:00+08:00',sha256='a'*64,file=key+'.json',url=url))
        return p


class OfficialJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.service=MarketService(self.tmp.name)
        self.service.store.save_snapshot(dict(id='one',as_of='2026-10-07',created_at='2026-10-07T19:00:00+08:00',
            calendar={'actual':['2026-10-07']},rows=[dict(symbol='2330',kind='stock',bars=[])],two_week={'scored_universe':[]}))
        self.jobs=OfficialJobs(self.service,FakeClient)
    def tearDown(self): self.tmp.cleanup()

    def test_failure_isolation_and_readonly_report(self):
        job=self.jobs.start(); self.jobs._thread.join(5)
        self.assertFalse(self.jobs.state()['running'])
        self.assertEqual(self.jobs.state()['status'],'partial')
        report=self.jobs.report(symbol='2330',snapshot_id='one')
        self.assertEqual(report['summary']['sources']['institution']['covered_symbols'],1)
        self.assertEqual(report['summary']['sources']['margin']['status'],'error')
        self.assertEqual(report['detail']['sources']['revenue']['status'],'available')
        self.assertEqual(report['signal_detail']['sources']['revenue']['status'],'missing')
        before=self.service.store.path.read_bytes()
        self.jobs.report(); self.jobs.report(symbol='2330')
        self.assertEqual(before,self.service.store.path.read_bytes())

    def test_concurrent_lock_and_recovery(self):
        from marketlab.service import update_lock
        with update_lock(self.service.root):
            with self.assertRaises(ValueError): self.jobs.start()
        self.service.store.put('official_job',{'running':True,'status':'running'})
        recovered=OfficialJobs(self.service,FakeClient)
        self.assertEqual(recovered.state()['status'],'interrupted')

    def test_local_enabled_market_collection(self):
        self.service.store.put('official_enabled',True)
        collect_for_market(self.service,self.service.store.snapshot()['calendar'],FakeClient)
        self.assertEqual(self.jobs.state()['status'],'partial')
        self.assertEqual(len(self.jobs.official.query('institution')),1)

    def test_archived_feature_availability_survives_compaction(self):
        from marketlab.shadow import archive_signal
        from marketlab.data import json_text
        days=['2026-10-01','2026-10-02','2026-10-05','2026-10-06','2026-10-07']
        snapshot=dict(id='full',as_of=days[-1],created_at='2026-10-07T19:01:00+08:00',
            calendar={'actual':days},rows=[dict(symbol='2330',kind='stock',bars=[dict(date=d,volume=100) for d in days])],
            two_week={'scored_universe':[dict(symbol='2330',kind='stock')]})
        evidence=dict(fetched_at='2026-10-07T18:00:00+08:00',sha256='a'*64,file='fixture.json',url='https://www.twse.com.tw/')
        institution=[dict(symbol='2330',key=d,data_date=d,period=None,published_at=None,unit='shares',values={'total_net':10}) for d in days]
        revenue=dict(symbol='2330',key='2026-08',data_date='2026-08-01',period='2026-08',published_at=None,
            unit='amount_unverified',values={'yoy_pct':5})
        self.jobs.official.ingest('institution',institution,evidence)
        self.jobs.official.ingest('revenue',[revenue],evidence)
        self.service.store.save_snapshot(snapshot);archive_signal(self.service.store,snapshot)
        snapshot['rows'][0].pop('bars');snapshot['detail_retention']='forecast_only'
        with self.service.store.connect() as conn:
            conn.execute('UPDATE snapshots SET payload=? WHERE id=?',(json_text(snapshot),'full'))
        report=self.jobs.report('2330','full')
        self.assertTrue(report['features']['eligible'])
        self.assertEqual(report['features_status'],'archived')
        self.assertEqual(report['features']['institution_ratio_5'],.1)
        self.service.store.put('shadow_signal:unrelated',{})
        # A compacted non-candidate has no retained feature evidence, not evidence of missing features.
        snapshot['rows'].append(dict(symbol='2317',kind='stock'))
        with self.service.store.connect() as conn:
            conn.execute('UPDATE snapshots SET payload=? WHERE id=?',(json_text(snapshot),'full'))
        unknown=self.jobs.report('2317','full')
        self.assertIsNone(unknown['features']);self.assertEqual(unknown['features_status'],'unavailable_inputs')

    def test_get_and_post_guards(self):
        server=make_server(self.service,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/official') as response: self.assertIn('summary',json.load(response))
            with urlopen(base+'/api/shadow') as response: self.assertEqual(json.load(response)['status'],'insufficient_data')
            from urllib.error import HTTPError
            request=Request(base+'/api/official/update',data=b'{"bad":1}',headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as err: urlopen(request)
            self.assertEqual(err.exception.code,400)
            request=Request(base+'/api/official',headers={'Host':'evil.example'})
            with self.assertRaises(HTTPError) as err: urlopen(request)
            self.assertEqual(err.exception.code,403)
        finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
