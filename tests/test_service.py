import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from marketlab.data import Store
from marketlab.service import DEFAULT_SETTINGS,validate_settings,ResearchService


class SettingsTests(unittest.TestCase):
    def test_negative_fee_rejected(self):
        with self.assertRaises(ValueError): validate_settings(dict(DEFAULT_SETTINGS,fee_rate=-.01))
    def test_nan_rejected(self):
        with self.assertRaises(ValueError): validate_settings(dict(DEFAULT_SETTINGS,max_downside=float("nan")))
    def test_bool_is_not_number(self):
        with self.assertRaises(ValueError): validate_settings(dict(DEFAULT_SETTINGS,months=True))
    def test_insufficient_neighbors_rejected(self):
        with self.assertRaises(ValueError): validate_settings(dict(DEFAULT_SETTINGS,min_samples=90,neighbors=60))
    def test_symbol_cannot_be_path_or_unknown_instrument(self):
        with self.assertRaises(ValueError): validate_settings(dict(DEFAULT_SETTINGS,symbols=["../2330"]))
    def test_duplicate_symbols_normalized_preserving_leading_zero(self):
        self.assertEqual(validate_settings(dict(DEFAULT_SETTINGS,symbols=["0050","2330","0050"]))["symbols"],["0050","2330"])


class StoreTests(unittest.TestCase):
    def test_snapshot_immutable_and_latest_is_transactional(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            snap=dict(id="original",as_of="2026-09-15",created_at="2026-09-15T19:00:00+08:00",rows=[])
            store.save_snapshot(snap)
            with self.assertRaises(sqlite3.IntegrityError): store.save_snapshot(dict(snap,rows=[1]))
            self.assertEqual(store.snapshot(),snap)
            self.assertEqual(len(store.history()),1)
    def test_update_failure_preserves_existing_snapshot(self):
        class OfflineClient:
            def __init__(self,*args,**kwargs): pass
            def universe(self): raise RuntimeError("upstream unavailable")
        with tempfile.TemporaryDirectory() as root:
            service=ResearchService(root,client_factory=OfflineClient)
            snap=dict(id="yesterday",as_of="2026-09-14",created_at="2026-09-14T19:00:00+08:00",rows=[])
            service.store.save_snapshot(snap)
            with self.assertRaises(RuntimeError): service.update()
            self.assertEqual(service.store.snapshot(),snap)
            self.assertFalse(service.job["running"])
            self.assertIn("upstream unavailable",service.job["error"])


if __name__=="__main__": unittest.main()
