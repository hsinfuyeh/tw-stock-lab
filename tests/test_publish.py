import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from marketlab.service import MarketService
from marketlab.data import Store


class PublishTests(unittest.TestCase):
    def publish(self):
        self.assertIsNotNone(importlib.util.find_spec('marketlab.publish'),'static exporter not implemented')
        from marketlab.publish import export_site
        return export_site

    def test_empty_snapshot_refuses_publish(self):
        export=self.publish()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError): export(MarketService(Path(root)/'data'),Path(root)/'dist')

    def test_separate_detail_and_csv_and_no_database_in_public_site(self):
        export=self.publish()
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(Path(root)/'data')
            h=dict(target_date='2026-10-02',expected_return=2.,p_positive=.6,p_recovery=.8,q10=-2.,q90=5.,n=40,eligible=True,reasons=[],score=60,samples=[{'signal_date':'2025-01-01'}])
            row=dict(symbol='00400A',name='測試股票ETF',kind='etf',bars=[{'date':'2026-09-18'}],horizons={str(n):h for n in [1,3,5,7,14,30]},validation={})
            snap=dict(id='safe-id',as_of='2026-09-18',created_at='2026-09-20T20:00:00+08:00',rows=[row],settings={},calendar=dict(actual=['2026-09-18'],years=[2026],holidays=[],opens=[]))
            service.store.save_snapshot(snap)
            out=Path(root)/'dist';export(service,out)
            state=json.loads((out/'data/state.json').read_text(encoding='utf-8'))
            summary=state['latest']['rows'][0]
            self.assertNotIn('bars',summary)
            self.assertNotIn('samples',summary['horizons']['14'])
            self.assertEqual(json.loads((out/summary['detail_url']).read_text(encoding='utf-8')),row)
            self.assertTrue((out/'data/csv/safe-id-14-p_recovery.csv').exists())
            self.assertFalse(list(out.rglob('*.sqlite3')))
            self.assertIn('name="deployment-mode" content="static"',(out/'index.html').read_text(encoding='utf-8'))
            self.assertEqual(state['next_session'],'2026-09-21')


if __name__=='__main__': unittest.main()
