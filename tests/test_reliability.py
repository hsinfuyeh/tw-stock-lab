"""Regressions for publication failures, lost outcomes and competing updates."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_analytics import bars, cal
from marketlab.data import Store
from marketlab.service import ResearchService, DEFAULT_SETTINGS, update_lock


class FixtureClient:
    rows = bars(65)

    def __init__(self, root, progress=None):
        self.evidence = []

    def universe(self):
        return [dict(symbol="2330", name="fixture", kind="stock")]

    def calendar(self, months):
        return cal(self.rows)

    def stock(self, symbol, months):
        return dict(rows=copy.deepcopy(self.rows), issues=[])


def past_snapshot(identifier="past", symbol="2330", as_of="2025-01-06"):
    return dict(id=identifier, as_of=as_of, created_at=as_of+"T19:00:00+08:00",
                settings=dict(DEFAULT_SETTINGS, symbols=[symbol]),
                rows=[dict(symbol=symbol, kind="stock", horizons={
                    str(h): dict(expected_return=1., p_positive=.6)
                    for h in (1, 3, 5, 7, 14, 30)})])


class ReliabilityTests(unittest.TestCase):
    def service(self, root):
        service = ResearchService(root, client_factory=FixtureClient)
        service.save_settings(dict(DEFAULT_SETTINGS, symbols=["2330"], months=3))
        return service

    def test_artifact_failure_does_not_publish_or_replace_prior_results(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            old = past_snapshot()
            service.store.save_snapshot(old)
            kept = dict(snapshot_id="kept", symbol="2317", horizon=1, return_pct=1.)
            service.store.put("reconciled", [kept])
            with patch("marketlab.service.atomic_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    service.update()
            self.assertEqual(service.store.snapshot(), old)
            self.assertEqual(service.store.get("reconciled"), [kept])
            self.assertEqual(len(service.store.history()), 1)

    def test_reconciliation_failure_does_not_publish(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            old = past_snapshot()
            service.store.save_snapshot(old)
            with patch.object(service, "_reconcile", side_effect=RuntimeError("audit failed")):
                with self.assertRaises(RuntimeError):
                    service.update()
            self.assertEqual(service.store.snapshot(), old)

    def test_same_signature_retry_repairs_missing_artifact_and_reconciles(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            snapshot = service.update()
            artifact = Path(root)/"snapshots"/(snapshot["id"]+".json")
            artifact.unlink()
            old = past_snapshot()
            # Simulate a previously interrupted audit, keeping latest unchanged.
            with service.store.connect() as conn:
                conn.execute("INSERT INTO snapshots VALUES (?,?,?,?)", (
                    old["id"], old["as_of"], old["created_at"], json.dumps(old)))
            again = service.update()
            self.assertEqual(again["id"], snapshot["id"])
            self.assertTrue(artifact.exists())
            self.assertTrue(any(r["snapshot_id"] == "past" for r in service.store.get("reconciled")))

    def test_missing_current_symbols_does_not_delete_old_outcomes(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            old = dict(snapshot_id="past", symbol="2317", horizon=1, return_pct=1.)
            service.store.put("reconciled", [old])
            service._reconcile({}, cal(FixtureClient.rows))
            self.assertEqual(service.store.get("reconciled"), [old])

    def test_reconciliation_visits_snapshots_older_than_ui_history_limit(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            for n in range(102):
                snap = past_snapshot(f"past-{n:03}")
                snap["created_at"] = f"2025-01-06T19:{n//60:02}:{n%60:02}+08:00"
                service.store.save_snapshot(snap)
            self.assertEqual(len(service.store.history()), 100)
            service._reconcile({"2330": dict(rows=FixtureClient.rows)}, cal(FixtureClient.rows))
            ids = {r["snapshot_id"] for r in service.store.get("reconciled")}
            self.assertEqual(len(ids), 102)

    def test_revised_price_keeps_previous_outcome_and_its_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            service.store.save_snapshot(past_snapshot())
            rows = copy.deepcopy(FixtureClient.rows)
            service._reconcile({"2330": dict(rows=rows)}, cal(rows))
            first = copy.deepcopy(service.store.get("reconciled")[0])
            for row in rows:
                if row["date"] == "2025-01-07":
                    row["close"] += .5
            service._reconcile({"2330": dict(rows=rows)}, cal(rows))
            revised = service.store.get("reconciled")[0]
            self.assertNotEqual(first["return_pct"], revised["return_pct"])
            self.assertEqual(len(revised.get("revisions", [])), 1)
            self.assertEqual(revised["revisions"][0]["return_pct"], first["return_pct"])
            self.assertIn("calculation_hash", revised)
            service._reconcile({"2330": dict(rows=rows)}, cal(rows))
            self.assertEqual(len(service.store.get("reconciled")[0]["revisions"]), 1)

    def test_revision_that_introduces_adjustment_invalidates_current_outcome(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            service.store.save_snapshot(past_snapshot())
            rows = copy.deepcopy(FixtureClient.rows)
            service._reconcile({"2330": dict(rows=rows)}, cal(rows), evidence=[{"version": "old"}])
            original = next(r for r in service.store.get("reconciled") if r["horizon"] == 3)
            for row in rows:
                if row["date"] == "2025-01-08": row["change"] = "X0.00"
            service._reconcile({"2330": dict(rows=rows)}, cal(rows), evidence=[{"version": "corrected"}])
            revised = next(r for r in service.store.get("reconciled") if r["horizon"] == 3)
            self.assertIsNone(revised["return_pct"])
            self.assertEqual(revised["outcome_status"], "not_comparable")
            self.assertEqual(revised["revisions"][0]["return_pct"], original["return_pct"])
            self.assertEqual(revised["evidence"], [{"version": "corrected"}])
            service._reconcile({"2330": dict(rows=rows)}, cal(rows))
            revised = next(r for r in service.store.get("reconciled") if r["horizon"] == 3)
            self.assertEqual(len(revised["revisions"]), 1)

    def test_competing_ui_start_cannot_overwrite_active_job(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            active = dict(running=True, phase="active CLI", progress=42)
            service.store.put("job", active)
            with update_lock(root):
                service.start_update()
                if service._thread:
                    service._thread.join(3)
                self.assertEqual(service.store.get("job"), active)

    def test_restart_recovers_orphaned_running_job_but_not_active_owner(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            active = dict(running=True, phase="active", progress=1)
            store.put("job", active)
            with update_lock(root):
                ResearchService(root)
                self.assertEqual(store.get("job"), active)
            restarted = ResearchService(root)
            self.assertFalse(restarted.state()["job"]["running"])
            self.assertTrue(restarted.state()["job"]["error"])

    def test_background_job_releases_lock_and_finishes(self):
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            service.start_update()
            service._thread.join(10)
            self.assertFalse(service.state()["job"]["running"])
            self.assertIsNotNone(service.store.snapshot())
            with update_lock(root):
                pass

    def test_removed_symbol_and_shorter_history_still_matures_old_predictions(self):
        historical = bars(50, "2024-09-02")
        class BackfillClient(FixtureClient):
            def calendar(self, months):
                return cal(historical+self.rows)
            def stock(self, symbol, months):
                if symbol == "2317":
                    return dict(rows=historical, issues=[])
                return super().stock(symbol, months)
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            service.client_factory = BackfillClient
            service.store.save_snapshot(past_snapshot(symbol="2317", as_of="2024-09-02"))
            service.update()
            old_results = [r for r in service.store.get("reconciled", []) if r["symbol"] == "2317"]
            self.assertEqual(len(old_results), 6)
            self.assertEqual(old_results[0]["entry_date"], "2024-09-03")

    def test_optional_backfill_failure_keeps_today_and_reports_pending_symbol(self):
        class OfflineOldSymbol(FixtureClient):
            def stock(self, symbol, months):
                if symbol == "2317": raise RuntimeError("archived symbol unavailable")
                return super().stock(symbol, months)
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            service.client_factory = OfflineOldSymbol
            service.store.save_snapshot(past_snapshot(symbol="2317"))
            latest = service.update()
            self.assertEqual(latest["rows"][0]["symbol"], "2330")
            audit = service.store.get("reconciliation", {})
            self.assertIn("archived symbol unavailable", audit.get("backfill_errors", {}).get("2317", ""))
            self.assertTrue(any(r["symbol"] == "2317" for r in audit["pending"]))


if __name__ == "__main__":
    unittest.main()
