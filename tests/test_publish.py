import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from marketlab.service import MarketService
from marketlab.data import Store
from marketlab.analytics import features_at
from test_analytics import bars, cal


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
            snap=dict(id='safe-id',as_of='2026-09-18',created_at='2026-09-20T20:00:00+08:00',rows=[row],settings={},calendar=dict(actual=['2026-09-18'],years=[2026],holidays=[],opens=[]),
                two_week=dict(status='insufficient_validation',research_candidates=[dict(symbol='00400A',name='測試股票ETF',score=12)],
                              recommendations=[],scored_universe=[dict(symbol='00400A',score=12)],validation=dict(stock=dict(status='insufficient_validation'))))
            service.store.save_snapshot(snap)
            expected_csv=service.export_csv(14,'p_recovery','safe-id')
            out=Path(root)/'dist'
            with patch.object(service.store,'snapshot',wraps=service.store.snapshot) as read_snapshot:
                export(service,out)
            self.assertLessEqual(read_snapshot.call_count,2,'CSV variants must reuse the loaded snapshot')
            state=json.loads((out/'data/state.json').read_text(encoding='utf-8'))
            home=json.loads((out/'data/home.json').read_text(encoding='utf-8'))
            self.assertEqual(home['latest']['two_week']['research_candidates'][0]['symbol'],'00400A')
            self.assertNotIn('rows',home['latest'])
            self.assertNotIn('scored_universe',home['latest']['two_week'])
            self.assertNotIn('validation',home['latest']['two_week'])
            self.assertLess((out/'data/home.json').stat().st_size,(out/'data/state.json').stat().st_size)
            summary=state['latest']['rows'][0]
            self.assertNotIn('bars',summary)
            self.assertNotIn('samples',summary['horizons']['14'])
            self.assertEqual(json.loads((out/summary['detail_url']).read_text(encoding='utf-8')),row)
            self.assertTrue((out/'data/csv/safe-id-14-p_recovery.csv').exists())
            with (out/'data/csv/safe-id-14-p_recovery.csv').open(encoding='utf-8',newline='') as exported:
                self.assertEqual(exported.read(),expected_csv)
            self.assertFalse(list(out.rglob('*.sqlite3')))
            self.assertIn('name="deployment-mode" content="static"',(out/'index.html').read_text(encoding='utf-8'))
            html=(out/'index.html').read_text(encoding='utf-8')
            self.assertRegex(html,r'\./style\.css\?v=[0-9a-f]{12}')
            self.assertRegex(html,r'\./app\.js\?v=[0-9a-f]{12}')
            self.assertEqual(state['next_session'],'2026-09-21')
            social=json.loads((out/'data/social.json').read_text(encoding='utf-8'))
            self.assertIsNone(social['collected_at'],'no collection must not invent a fresh timestamp')
            self.assertEqual(social['windows']['24h'],[])
            self.assertRegex((out/'app.js').read_text(encoding='utf-8'),r"import\('\./social\.js\?v=[0-9a-f]{12}'\)")

    def test_homepage_enriches_old_archived_candidates_from_same_day_bars(self):
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(Path(root)/'data')
            price_rows=bars(40,start='2026-08-01')
            feature=features_at(price_rows,len(price_rows)-1,cal(price_rows))
            h=dict(target_date=None,expected_return=None,p_positive=None,p_recovery=None,
                   q10=None,q90=None,n=0,eligible=False,reasons=[],score=None)
            candidate=dict(symbol='2330',name='測試股票',kind='stock',score=12,reasons=[])
            snap=dict(id='old-snapshot',as_of=price_rows[-1]['date'],created_at='2026-09-27T20:00:00+08:00',
                rows=[dict(symbol='2330',name='測試股票',kind='stock',bars=price_rows,features=feature,
                           horizons={str(n):h for n in [1,3,5,7,14,30]})],calendar=cal(price_rows),
                two_week=dict(status='insufficient_validation',research_candidates=[candidate],
                              recommendations=[],scored_universe=[candidate]))
            service.store.save_snapshot(snap)
            out=Path(root)/'dist'
            self.publish()(service,out)
            home=json.loads((out/'data/home.json').read_text(encoding='utf-8'))
            explore=json.loads((out/'data/explore.json').read_text(encoding='utf-8'))
            self.assertEqual((explore['id'],explore['as_of']),(snap['id'],snap['as_of']))
            self.assertEqual(explore['rows'][0]['symbol'],snap['rows'][0]['symbol'])
            self.assertEqual(json.loads((out/explore['rows'][0]['detail_url']).read_text(encoding='utf-8')),snap['rows'][0])
            row=home['latest']['two_week']['research_candidates'][0]
            self.assertEqual(row['close'],price_rows[-1]['close'])
            self.assertEqual(len(row['trend']),20)
            self.assertEqual(row['trend'][-1],dict(date=price_rows[-1]['date'],close=price_rows[-1]['close']))
            self.assertAlmostEqual(row['momentum5_pct'],feature['momentum5'],places=2)
            self.assertAlmostEqual(row['relative_volume'],feature['volume_ratio'],places=2)
            self.assertNotIn('close',snap['two_week']['research_candidates'][0], 'archived snapshot must stay unchanged')


if __name__=='__main__': unittest.main()
