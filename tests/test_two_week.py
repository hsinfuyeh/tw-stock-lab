import unittest
import tempfile

from marketlab.two_week import target_price, outcome, rank_candidates, eligible_asset, validate_ranker
from marketlab.service import MarketService
from marketlab.data import listed_universe
from marketlab.publish import export_site
from pathlib import Path
import json
from test_analytics import bars, cal


def bar(day, open_price=100, high=101, low=99, close=100, volume=1000000, mark="", change=""):
    return dict(date=f"2026-01-{day:02d}", open=open_price, high=high, low=low,
                close=close, volume=volume, turnover=close*volume, mark=mark,
                change=change, valid=True)


class TwoWeekTests(unittest.TestCase):
    def test_target_rounds_up_to_valid_stock_and_etf_prices(self):
        self.assertEqual(target_price(48.01, "stock"), 50.5)
        self.assertEqual(target_price(48.01, "etf"), 50.45)
        self.assertEqual(target_price(100, "stock"), 105)

    def test_entry_is_day_one_and_touch_is_not_automatic_fill(self):
        rows=[bar(1),bar(2, high=105, close=104)]+[bar(i) for i in range(3,12)]
        result=outcome(rows,0,"stock")
        self.assertEqual(result["entry_date"],"2026-01-02")
        self.assertEqual(result["exit_date"],"2026-01-11")
        self.assertTrue(result["touched"])
        self.assertFalse(result["potential_fill"])
        rows[1]["high"]=105.5
        self.assertTrue(outcome(rows,0,"stock")["potential_fill"])

    def test_missing_session_and_adjustment_are_not_success(self):
        rows=[bar(i) for i in range(1,12)]
        self.assertEqual(outcome(rows[:5],0,"stock")["status"],"pending")
        rows[5]["valid"]=False
        self.assertEqual(outcome(rows,0,"stock")["status"],"not_comparable")
        rows[5]["valid"]=True;rows[5]["change"]="X"
        self.assertEqual(outcome(rows,0,"stock")["status"],"not_comparable")

    def test_locked_entry_is_not_assumed_filled(self):
        rows=[bar(i) for i in range(1,12)]
        rows[1].update(open=110,high=110,low=110,close=110)
        self.assertEqual(outcome(rows,0,"stock")["status"],"not_filled")

    def test_missing_next_market_session_never_shifts_entry_to_resumption(self):
        rows=[bar(i) for i in range(1,13) if i!=2]
        calendar=dict(actual=[f"2026-01-{i:02d}" for i in range(1,13)])
        self.assertEqual(outcome(rows,0,"stock",calendar)["status"],"not_filled")

    def test_no_validated_history_means_no_recommendations(self):
        symbols=[dict(symbol="2330",name="甲",kind="stock",rows=[bar(i) for i in range(1,12)])]
        report=rank_candidates(symbols,"2026-01-11",[],[])
        self.assertEqual(report["recommendations"],[])
        self.assertEqual(report["status"],"insufficient_validation")

    def test_walk_forward_validation_can_unlock_only_a_group_with_real_lift(self):
        history=[]
        for day in range(110):
            signal=f"2025-{day//28+1:02d}-{day%28+1:02d}"
            for rank in range(20):
                history.append(dict(signal_date=signal,kind="stock",rank_fraction=1-rank/20,
                    status="evaluated",potential_fill=(rank<2 or rank==8 and day%2==0)))
        report=validate_ranker(history)
        self.assertEqual(report["stock"]["status"],"validated")
        self.assertGreater(report["stock"]["probability"],report["stock"]["baseline"])
        self.assertEqual(report["active_etf"]["status"],"insufficient_validation")
        rows=bars(40)
        for row in rows: row["turnover"]=30_000_000
        ranked=rank_candidates([dict(symbol="2330",name="甲",kind="stock",rows=rows)],
                               rows[-1]["date"],history,cal(rows))
        self.assertEqual(ranked["status"],"validated")
        self.assertEqual(ranked["recommendations"][0]["symbol"],"2330")

    def test_foreign_and_uncertain_etfs_do_not_enter_taiwan_equity_ranking(self):
        self.assertTrue(eligible_asset(dict(kind="stock",currency="TWD")))
        self.assertTrue(eligible_asset(dict(kind="etf",currency="TWD",name="主動統一台股增長",etf_style="active")))
        self.assertFalse(eligible_asset(dict(kind="etf",currency="TWD",name="美國科技ETF")))
        self.assertFalse(eligible_asset(dict(kind="etf",currency="TWD",name="不明主題ETF")))
        self.assertFalse(eligible_asset(dict(kind="etf",currency="USD",name="台股ETF")))

    def test_official_etf_index_hint_is_retained_for_conservative_scope(self):
        universe=listed_universe([dict(公司代號="2330",公司簡稱="台積電",上市日期="19940905")],
            dict(status="success",data=[dict(stockNo="0050",stockName="元大50",listingDate="2003.06.30",indexName="臺灣50指數")]))
        etf=next(x for x in universe if x["kind"]=="etf")
        self.assertEqual(etf["index_name"],"臺灣50指數")
        self.assertTrue(eligible_asset(etf))

    def test_main_score_uses_relative_market_strength(self):
        rows=bars(40)
        for row in rows: row["turnover"]=30_000_000
        base=cal(rows)
        flat=dict(base,index=[dict(date=r["date"],close=100) for r in rows])
        rising=dict(base,index=[dict(date=r["date"],close=100+i) for i,r in enumerate(rows)])
        item=dict(symbol="2330",name="甲",kind="stock",rows=rows)
        one=rank_candidates([item],rows[-1]["date"],[],flat)["research_candidates"][0]["score"]
        two=rank_candidates([item],rows[-1]["date"],[],rising)["research_candidates"][0]["score"]
        self.assertGreater(one,two)

    def test_rank_fraction_is_computed_within_stock_and_etf_groups(self):
        rows=bars(40)
        for row in rows: row["turnover"]=30_000_000
        report=rank_candidates([dict(symbol="2330",name="甲",kind="stock",rows=rows),
            dict(symbol="0050",name="台灣50",kind="etf",etf_style="passive",rows=rows)],
            rows[-1]["date"],[],cal(rows))
        self.assertEqual([r["rank_fraction"] for r in report["scored_universe"]],[1,1])

    def test_main_market_snapshot_carries_daily_two_week_report(self):
        fixture=bars(65)
        class Client:
            def __init__(self,*args): self.evidence=[]
            def universe(self): return [dict(symbol="2330",name="甲",kind="stock",currency="TWD")]
            def calendar(self,*args): return cal(fixture)
            def market_bundles(self,*args): return {"2330":dict(rows=fixture,issues=[])}
        with tempfile.TemporaryDirectory() as root:
            result=MarketService(root,client_factory=Client,workers=1).update()
            self.assertEqual(result["two_week"]["as_of"],result["as_of"])
            self.assertEqual(result["two_week"]["horizon_sessions"],10)
            self.assertEqual(result["two_week"]["recommendations"],[])
            self.assertIn("validation",result["two_week"])
            self.assertEqual(MarketService(root,client_factory=Client,workers=1).store.snapshot()["two_week"],result["two_week"])

    def test_daily_candidates_are_reconciled_without_rewriting_prediction(self):
        all_rows=bars(80)
        for row in all_rows: row["turnover"]=30_000_000
        class Client:
            latest=65
            def __init__(self,*args): self.evidence=[]
            def universe(self): return [dict(symbol="2330",name="甲",kind="stock",currency="TWD")]
            def calendar(self,*args): return cal(all_rows[:self.latest])
            def market_bundles(self,*args): return {"2330":dict(rows=all_rows[:self.latest],issues=[])}
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root,client_factory=Client,workers=1)
            first=service.update()
            self.assertTrue(first["two_week"]["research_candidates"])
            Client.latest=80
            second=service.update()
            self.assertNotEqual(first["id"],second["id"])
            archived=service.store.snapshot(first["id"])
            self.assertEqual(archived["two_week"],first["two_week"])
            outcomes=service.store.get("two_week_outcomes",[])
            self.assertTrue(any(x["snapshot_id"]==first["id"] and x["symbol"]=="2330" for x in outcomes))
            self.assertTrue(all("rank_fraction" in x for x in outcomes))
            self.assertEqual(service.state()["two_week_outcomes"],outcomes)
            export_site(service,Path(root)/"dist")
            public=json.loads((Path(root)/"dist/data/state.json").read_text(encoding="utf-8"))
            self.assertEqual(public["two_week_outcomes"],outcomes)

    def test_delisted_candidate_is_still_collected_for_maturity_check(self):
        fixture=bars(80)
        for row in fixture: row["turnover"]=30_000_000
        class Client:
            latest=65
            seen=[]
            def __init__(self,*args): self.evidence=[]
            def universe(self):
                symbol="2330" if self.latest==65 else "2317"
                return [dict(symbol=symbol,name=symbol,kind="stock",currency="TWD")]
            def calendar(self,*args): return cal(fixture[:self.latest])
            def market_bundles(self,universe,*args):
                type(self).seen=[x["symbol"] for x in universe]
                return {x["symbol"]:dict(rows=fixture[:self.latest],issues=[]) for x in universe}
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root,client_factory=Client,workers=1)
            first=service.update()
            Client.latest=80
            service.update()
            self.assertIn("2330",Client.seen)
            self.assertTrue(any(x["snapshot_id"]==first["id"] for x in service.store.get("two_week_outcomes",[])))


if __name__=="__main__": unittest.main()
