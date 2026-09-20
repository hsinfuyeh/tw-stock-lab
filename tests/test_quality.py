import copy
import tempfile
import unittest

from test_reliability import FixtureClient
from marketlab.service import ResearchService, DEFAULT_SETTINGS


class EvidenceClient(FixtureClient):
    def __init__(self, root, progress=None):
        super().__init__(root, progress)
        self.evidence = [
            dict(url="https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=20250301&stockNo=2330",
                 sha256="a"*64, file="stock-test.json", fetched_at="2026-09-16T20:00:00+08:00"),
            dict(url="https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=20250301&stockNo=2330",
                 sha256="b"*64, file="stock-fallback.json", fetched_at="2026-09-16T20:01:00+08:00")]


class QualityTests(unittest.TestCase):
    def update(self, root, factory=EvidenceClient):
        service = ResearchService(root, client_factory=factory)
        service.save_settings(dict(DEFAULT_SETTINGS, symbols=["2330"], months=3))
        return service, service.update()

    def test_two_official_paths_are_one_upstream_and_not_independent_verification(self):
        with tempfile.TemporaryDirectory() as root:
            service, snapshot = self.update(root)
            quality = snapshot.get("data_quality", {})
            self.assertEqual(quality.get("verification_status"), "single_source")
            self.assertEqual(quality["source_families"], ["TWSE"])
            self.assertFalse(quality["independent_verification"])
            self.assertEqual(quality["source_manifest"][0]["sha256"], "a"*64)
            self.assertIsNone(quality["source_manifest"][0]["published_at"])
            self.assertEqual(quality["data_as_of"], FixtureClient.rows[-1]["date"])
            self.assertNotIn("probability", quality)
            self.assertIn("單一官方來源", service.export_csv())

    def test_no_evidence_is_reported_missing_not_verified(self):
        with tempfile.TemporaryDirectory() as root:
            _, snapshot = self.update(root, FixtureClient)
            self.assertEqual(snapshot.get("data_quality", {}).get("verification_status"), "missing_evidence")

    def test_old_snapshot_is_not_retroactively_marked_as_verified(self):
        with tempfile.TemporaryDirectory() as root:
            service, snapshot = self.update(root)
            old = copy.deepcopy(snapshot)
            old["id"] = "legacy"
            old.pop("data_quality", None)
            service.store.save_snapshot(old)
            self.assertIn("未記錄複查狀態", service.export_csv(snapshot_id="legacy"))


if __name__ == "__main__": unittest.main()
