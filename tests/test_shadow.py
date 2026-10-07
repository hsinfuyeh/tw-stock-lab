import tempfile
import unittest
from datetime import date, timedelta
from marketlab.data import Store
from marketlab.service import MarketService
from marketlab.shadow import (DEFINITION, DEFINITION_HASH, freeze_definition, select_cohort,
    rolling_splits, paired_summary, shadow_report, archive_signal)


class ShadowTests(unittest.TestCase):
    def test_fixed_selection_common_cohort_and_ties(self):
        rows=[dict(symbol=str(i),rank=i,features=dict(eligible=True,institution_ratio_5=i/100,revenue_yoy_pct=i)) for i in range(1,16)]
        rows.append(dict(symbol='missing',rank=0,features={'eligible':False}))
        baseline,shadow=select_cohort(rows)
        self.assertEqual(len(baseline),10);self.assertEqual(len(shadow),10)
        self.assertEqual(baseline[0]['symbol'],'1')
        self.assertNotIn('missing',[r['symbol'] for r in shadow])
        self.assertEqual(shadow,select_cohort(rows)[1])
        self.assertEqual(DEFINITION['weights'],dict(baseline=.7,institution=.2,revenue=.1))

    def test_purged_rolling_dates_are_disjoint(self):
        days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(75)]
        folds=rolling_splits(days)
        self.assertEqual(len(folds),4)
        self.assertEqual(len(folds[0]['warmup']),30)
        self.assertEqual(len(folds[0]['purge']),10)
        tested=[d for f in folds for d in f['test']]
        self.assertEqual(len(tested),len(set(tested)))
        for f in folds: self.assertLess(max(f['warmup']),min(f['purge']));self.assertLess(max(f['purge']),min(f['test']))

    def test_day_weight_block_bootstrap_and_minimum(self):
        self.assertIsNone(paired_summary([dict(difference_pct=1)]*29)['ci95_pct'])
        result=paired_summary([dict(difference_pct=2)]*30)
        self.assertEqual(result['ci95_pct'],[2,2])
        self.assertEqual(result['mean_difference_pct'],2)
        self.assertEqual(result,paired_summary([dict(difference_pct=2)]*30))

    def test_frozen_conflict_and_insufficient(self):
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root)
            self.assertEqual(shadow_report(service)['status'],'insufficient_data')
            freeze_definition(service.store)
            frozen=service.store.get('shadow_definition:official-shadow-v1')
            self.assertEqual(frozen['sha256'],DEFINITION_HASH)
            frozen['sha256']='changed'; service.store.put('shadow_definition:official-shadow-v1',frozen)
            with self.assertRaises(ValueError): freeze_definition(service.store)

    def test_late_entry_and_maturity_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root)
            service.store.save_snapshot(dict(id='one',as_of='2026-10-06',created_at='2026-10-07T09:01:00+08:00',
                calendar={'actual':['2026-10-06','2026-10-07']},rows=[],two_week={'version':'v','scored_universe':[]}))
            service.store.save_snapshot(dict(id='two',as_of='2026-10-07',created_at='2026-10-07T19:00:00+08:00',
                calendar={'actual':['2026-10-06','2026-10-07']},rows=[],two_week={'version':'v','scored_universe':[]}))
            report=shadow_report(service)
            self.assertEqual(report['days'][0]['status'],'late_entry')
            self.assertIsNone(report['summary']['mean_difference_pct'])

    def test_signal_archive_immutable_after_new_data(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            snap=dict(id='one',as_of='2026-10-07',created_at='2026-10-07T19:00:00+08:00',
                calendar={'actual':['2026-10-07']},rows=[dict(symbol='2330',kind='stock',bars=[])],
                two_week={'scored_universe':[dict(symbol='2330',kind='stock')]})
            archive_signal(store,snap)
            before=store.get('shadow_signal:'+DEFINITION_HASH+':one')
            snap['rows'][0]['bars']=[dict(date='2026-10-07',volume=999)]
            archive_signal(store,snap)
            self.assertEqual(before,store.get('shadow_signal:'+DEFINITION_HASH+':one'))

    def test_only_mature_selected_trades_on_same_cohort(self):
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root)
            frozen=dict(definition=DEFINITION,sha256=DEFINITION_HASH,frozen_at='2025-01-01T00:00:00+08:00')
            service.store.put('shadow_definition:official-shadow-v1',frozen)
            days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(81)]
            tracks=[]
            for i,dt in enumerate(days):
                snap=dict(id=str(i),as_of=dt,created_at=dt+'T19:00:00+08:00',calendar={'actual':days[:i+1]},rows=[],two_week={})
                service.store.save_snapshot(snap)
                inputs=dict(status='saved',rows=[dict(symbol='2330',rank=1,features={'eligible':True})],baseline_symbols=['2330'],shadow_symbols=['2330'])
                service.store.put('shadow_signal:'+DEFINITION_HASH+':'+str(i),inputs)
                tracks.append(dict(signal_date=dt,symbol='2330',status='evaluated' if i<=70 else 'pending',net_return_pct=3))
            service.research_report=lambda identifier: dict(tracking=tracks)
            report=shadow_report(service)
            self.assertEqual(report['summary']['valid_test_days'],31)
            self.assertEqual(report['summary']['ci95_pct'],[0,0])
            self.assertEqual(report['exclusions']['pending'],10)
            tracks[45]['status']='not_filled'
            self.assertEqual(shadow_report(service)['summary']['valid_test_days'],30)

if __name__=='__main__': unittest.main()
