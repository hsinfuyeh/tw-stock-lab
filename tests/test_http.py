import json
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from marketlab.server import make_server
from marketlab.service import ResearchService,DEFAULT_SETTINGS


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.service=ResearchService(self.tmp.name)
        self.server=make_server(self.service,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.tmp.cleanup()
    def test_empty_state_is_honest(self):
        with urlopen(self.base+"/api/state") as response:
            payload=json.load(response)
        self.assertIsNone(payload["latest"])
        self.assertEqual(payload["history"],[])
        self.assertFalse(payload["job"]["running"])
        with urlopen(self.base+'/api/social') as response: social=json.load(response)
        self.assertIsNone(social['collected_at'])
        self.assertEqual(social['sources'],{})
    def test_settings_persist_and_bad_values_do_not_overwrite(self):
        params=dict(DEFAULT_SETTINGS,min_probability=.6)
        req=Request(self.base+"/api/settings",json.dumps(params).encode(),{"Content-Type":"application/json"})
        with urlopen(req) as response:self.assertEqual(json.load(response)["settings"]["min_probability"],.6)
        req=Request(self.base+"/api/settings",json.dumps(dict(params,months=-1)).encode(),{"Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as ctx:urlopen(req)
        self.assertEqual(ctx.exception.code,400)
        self.assertEqual(self.service.settings()["min_probability"],.6)
    def test_market_job_poll_does_not_load_full_snapshot(self):
        from unittest.mock import patch
        with patch.object(self.service,'state',side_effect=AssertionError('full snapshot loaded')):
            with urlopen(self.base+'/api/job') as response: payload=json.load(response)
        self.assertEqual(set(payload),{'job'})
        self.assertFalse(payload['job']['running'])
    def test_explore_uses_latest_snapshot_and_keeps_stale_security_searchable(self):
        self.service.store.save_snapshot(dict(id='old',as_of='2026-09-14',created_at='old',rows=[]))
        self.service.store.save_snapshot(dict(id='new',as_of='2026-09-15',created_at='new',
            rows=[dict(symbol='2330',name='台積電',kind='stock',currency='TWD',
                       bars=[dict(date='2026-09-14',close=100,valid=True)])]))
        with urlopen(self.base+"/api/explore") as response: payload=json.load(response)
        self.assertEqual((payload['id'],payload['as_of']),('new','2026-09-15'))
        self.assertEqual(payload['rows'][0]['symbol'],'2330')
        self.assertIsNone(payload['rows'][0]['detail_url'])
        self.assertEqual(payload['rows'][0]['metrics'],{})
    def test_cross_origin_cannot_change_settings(self):
        req=Request(self.base+"/api/settings",b"{}",{"Content-Type":"application/json","Origin":"https://example.com"})
        with self.assertRaises(HTTPError) as ctx:urlopen(req)
        self.assertEqual(ctx.exception.code,403)

    def test_social_update_uses_real_background_endpoint_and_validates_scope(self):
        from unittest.mock import patch
        payload={'sources':{'ptt':{'status':'partial'},'dcard':{'status':'failed'},'threads':{'status':'unavailable'}}}
        with patch('social_update.update_social',return_value=payload):
            # New server captures the injected collector before starting its job.
            server=make_server(self.service,0)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                request=Request(url+'/api/social/update',b'{"window":"24h"}',{'Content-Type':'application/json'})
                with urlopen(request) as response:
                    self.assertEqual(response.status,202); self.assertEqual(json.load(response)['job']['window'],'24h')
                with urlopen(url+'/api/social/job') as response:self.assertIn('sources',json.load(response)['job'])
                request=Request(url+'/api/social/update',b'{"window":"all"}',{'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as error:urlopen(request)
                self.assertEqual(error.exception.code,400)
                request=Request(url+'/api/social/update',b'{"window":"24h"}',{'Content-Type':'application/json','Origin':'https://example.com'})
                with self.assertRaises(HTTPError) as error:urlopen(request)
                self.assertEqual(error.exception.code,403)
            finally:server.shutdown();server.server_close();worker.join()
    def test_csv_uses_requested_snapshot_and_sorts_return_not_name(self):
        def snap(sid,values):
            return dict(id=sid,as_of="2026-09-15",created_at=sid,rows=[dict(symbol=s,name=s,kind="stock",horizons={"7":dict(expected_return=v,p_positive=.6,p_recovery=.8,q10=-2,q90=3,n=60,eligible=True,reasons=[],target_date="2026-09-22")}) for s,v in values])
        self.service.store.save_snapshot(snap("old",[("2330",1),("2317",3)]))
        self.service.store.save_snapshot(snap("new",[("2330",9)]))
        with urlopen(self.base+"/api/export?horizon=7&sort=expected_return&id=old") as response:text=response.read().decode("utf-8-sig")
        self.assertIn("2317",text.splitlines()[1])
        self.assertEqual(len(text.splitlines()),3)


if __name__=="__main__":unittest.main()
