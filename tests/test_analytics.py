import unittest
from datetime import date, timedelta
from marketlab.analytics import parse_month, features_at, target_date, event_outcome, estimate


def bars(count=120, start="2025-01-01"):
    result = []
    day = date.fromisoformat(start)
    while len(result) < count:
        if day.weekday() < 5:
            price = 100 + len(result) * .1
            result.append(dict(date=day.isoformat(), open=price, close=price, high=price+1,
                               low=price-1, volume=10000, turnover=1000000, mark="", change="+0.10", valid=True))
        day += timedelta(days=1)
    return result


def cal(rows):
    return dict(actual=[r["date"] for r in rows], years=[2025, 2026], holidays=[], opens=[])


SETTINGS = dict(fee_rate=.001, slippage_rate=0, kind="stock", min_samples=3, neighbors=10,
                min_turnover=0, min_probability=.5, max_downside=8)


class AnalyticsTests(unittest.TestCase):
    def test_calendar_day_weekend_and_holiday_roll_forward(self):
        calendar = dict(actual=[], years=[2026], holidays=["2026-09-28"], opens=[])
        self.assertEqual(target_date("2026-09-25", 1, calendar), "2026-09-29")

    def test_unknown_calendar_does_not_invent_target(self):
        self.assertIsNone(target_date("2026-12-31", 1, dict(actual=[], years=[2026], holidays=[], opens=[])))

    def test_parse_twse_preserves_noncomparison_and_invalid_dates(self):
        data = dict(stat="OK", fields=["日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數","註記"],
                    data=[["114/06/12","28,661,875","30,064,888,046","1,055","1,060","1,045","1,045","X0.00","40,293",""],
                          ["114/06/13","0","0","--","--","--","--","0","0","**"]])
        parsed = parse_month(data)
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["date"], "2025-06-12")
        self.assertEqual(parsed["rows"][0]["change"], "X0.00")
        self.assertFalse(parsed["rows"][1]["valid"])

    def test_previous_twenty_excludes_current_and_strict_thresholds(self):
        rows = bars(21)
        for r in rows:
            r.update(open=100, close=100, high=101, low=99, volume=10000)
        rows[20].update(close=102, high=103, volume=15000)
        f = features_at(rows,20,cal(rows))
        self.assertIsNotNone(f)
        self.assertIn("長紅 K", f["labels"])
        self.assertIn("突破前20日高點", f["labels"])
        self.assertNotIn("成交量放大", f["labels"])
        self.assertEqual(f["prev_20_high"], 101)
        rows[20]["volume"] = 15001
        self.assertIn("成交量放大", features_at(rows,20,cal(rows))["labels"])

    def test_next_open_not_signal_close_and_same_day_costs(self):
        rows = bars(3, "2025-01-03")
        rows[0].update(close=50,open=50,low=49,high=51)
        rows[1].update(open=100,close=101,high=102,low=99)
        outcome = event_outcome(rows,0,1,SETTINGS,cal(rows))
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["entry_date"], "2025-01-06")
        self.assertEqual(outcome["exit_date"], "2025-01-06")
        # Conservative full tax until daytrade eligibility is verified.
        # buy 100 + .1 fee, sell 101 - .101 fee - .303 tax
        self.assertAlmostEqual(outcome["return_pct"], .4955044955045, places=8)

    def test_recovery_is_distinct_from_terminal_profit(self):
        rows = bars(4,"2025-01-06")
        for r in rows:
            r.update(open=100,close=100,high=105,low=95)
        rows[1]["close"] = 103
        rows[3]["close"] = 98
        outcome = event_outcome(rows,0,3,SETTINGS,cal(rows))
        self.assertIsNotNone(outcome)
        self.assertLess(outcome["return_pct"], 0)
        self.assertTrue(outcome["recovered"])
        self.assertEqual(outcome["recovery_days"], 0)

    def test_adjustment_after_entry_excludes_outcome(self):
        rows = bars(5,"2025-01-06")
        rows[2]["change"] = "X0.00"
        self.assertIsNone(event_outcome(rows,0,3,SETTINGS,cal(rows)))

    def test_adjustment_at_entry_does_not_cross_price_basis(self):
        rows = bars(5,"2025-01-06")
        rows[1]["mark"] = "**"
        self.assertIsNotNone(event_outcome(rows,0,3,SETTINGS,cal(rows)))

    def test_missing_market_session_does_not_shift_exit(self):
        rows = bars(5,"2025-01-06")
        calendar = cal(rows)
        del rows[2]
        self.assertIsNone(event_outcome(rows,0,3,SETTINGS,calendar))

    def test_adjustment_in_feature_window_prevents_false_breakout(self):
        rows = bars(30)
        rows[12]["mark"] = "**"
        self.assertIsNone(features_at(rows,25,cal(rows)))

    def test_only_mature_labels_contribute_and_future_prices_do_not_leak(self):
        rows = bars(120)
        settings = dict(SETTINGS, neighbors=10)
        before = estimate(rows,90,14,settings,cal(rows))
        self.assertEqual(before["n"],10)
        self.assertTrue(all(x["exit_date"] <= rows[90]["date"] for x in before["samples"]))
        for r in rows[91:]:
            r.update(open=500,close=500,high=501,low=499)
        after = estimate(rows,90,14,settings,cal(rows))
        self.assertEqual(before["expected_return"], after["expected_return"])
        self.assertEqual(before["p_positive"], after["p_positive"])

    def test_unmatured_outcome_is_missing_not_zero(self):
        rows=bars(30)
        self.assertIsNone(event_outcome(rows,29,7,SETTINGS,cal(rows)))


if __name__ == "__main__":
    unittest.main()
