import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from marketlab.data import Store
from marketlab.social_jobs import SocialJobs


class SocialJobTests(unittest.TestCase):
    def test_job_runs_immediately_reports_progress_and_prevents_duplicates(self):
        entered=threading.Event(); finish=threading.Event()
        def runner(service,**kwargs):
            self.assertEqual(kwargs['window'],'24h')
            self.assertTrue(kwargs['local_public'])
            kwargs['progress']('ptt',{'status':'collecting'})
            entered.set(); finish.wait(2)
            return {'sources':{'ptt':{'status':'partial'},'dcard':{'status':'failed'},'threads':{'status':'not_configured'}}}
        with tempfile.TemporaryDirectory() as directory:
            service=SimpleNamespace(store=Store(directory))
            service.store.save_snapshot({'id':'s','as_of':'2026-09-29','created_at':'now','rows':[{'symbol':'2330','name':'台積電'}]})
            jobs=SocialJobs(service,runner=runner)
            first=jobs.start('24h'); self.assertTrue(entered.wait(1))
            self.assertEqual(jobs.start('7d')['id'],first['id'])
            self.assertEqual(jobs.state()['sources']['ptt']['status'],'collecting')
            finish.set(); jobs._thread.join(2)
            state=jobs.state()
            self.assertFalse(state['running'])
            self.assertEqual(state['status'],'partial')
            self.assertIsNotNone(state['finished_at'])

    def test_failure_does_not_replace_report_and_invalid_input_does_not_start(self):
        with tempfile.TemporaryDirectory() as directory:
            service=SimpleNamespace(store=Store(directory))
            service.store.put('social_report',{'collected_at':'old'})
            jobs=SocialJobs(service,runner=lambda *a,**k:(_ for _ in ()).throw(ValueError('missing snapshot')))
            with self.assertRaises(ValueError): jobs.start('30d')
            jobs.start('7d'); jobs._thread.join(2)
            self.assertEqual(jobs.state()['status'],'failed')
            self.assertEqual(service.store.get('social_report'),{'collected_at':'old'})

    def test_local_collection_uses_selected_period_without_personal_threads_token(self):
        from datetime import datetime,timezone,timedelta
        from social_update import update_social
        current=datetime(2026,9,29,12,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            service=SimpleNamespace(store=Store(directory))
            service.store.save_snapshot({'id':'s','as_of':'2026-09-29','created_at':'now','rows':[{'symbol':'2330','name':'台積電'}]})
            with patch('social_update.collect_ptt',return_value=([],{'status':'partial'})) as ptt, \
                 patch('social_update.collect_dcard',return_value=([],{'status':'failed','error':'HTTP 403'})) as dcard, \
                 patch('social_update.collect_threads') as official, \
                 patch('social_update.collect_threads_public',return_value=([],{'status':'not_configured'})) as public:
                update_social(service,current=current,window='24h',local_public=True)
            self.assertEqual(ptt.call_args.kwargs['since'],current-timedelta(hours=24))
            dcard.assert_called_once(); public.assert_called_once(); official.assert_not_called()

    def test_all_source_failures_keep_previous_report(self):
        from social_update import update_social
        with tempfile.TemporaryDirectory() as directory:
            service=SimpleNamespace(store=Store(directory))
            service.store.save_snapshot({'id':'s','as_of':'2026-09-29','created_at':'now','rows':[{'symbol':'2330','name':'台積電'}]})
            previous={'collected_at':'old','windows':{'24h':[{'symbol':'2330','total':3}]}}
            service.store.put('social_report',previous)
            with patch('social_update.collect_ptt',return_value=([],{'status':'failed'})), \
                 patch('social_update.collect_dcard',return_value=([],{'status':'failed'})), \
                 patch('social_update.collect_threads_public',return_value=([],{'status':'unavailable'})):
                with self.assertRaises(RuntimeError): update_social(service,local_public=True)
            self.assertEqual(service.store.get('social_report'),previous)
