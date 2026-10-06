import unittest
from datetime import date, timedelta
from marketlab.analytics import net_return
from marketlab.performance import simulate_trade, summarize_performance


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.dates = [(date(2026, 1, 1)+timedelta(days=i)).isoformat() for i in range(11)]
        self.calendar = {'actual': self.dates}
        self.rows = [dict(date=d, open=100, high=104, low=97, close=98, valid=True) for d in self.dates]

    def trade(self, **kwargs):
        return simulate_trade(self.rows, self.dates[0], kwargs.get('kind','stock'), self.calendar, kwargs.get('as_of',self.dates[-1]))

    def test_touch_is_not_fill_and_expiry_cost_once(self):
        self.rows[1]['high']=105
        r=self.trade()
        self.assertFalse(r['target_filled']); self.assertTrue(r['touched'])
        self.assertEqual(r['exit_price'],98)
        self.assertAlmostEqual(r['net_return_pct'],net_return(100,98,{'kind':'stock'}))

    def test_conservative_fill_excludes_exit_low(self):
        self.rows[2].update(high=105.5,low=80)
        r=self.trade()
        self.assertEqual(r['exit_price'],105)
        self.assertAlmostEqual(r['adverse_before_exit_pct'],-3)
        self.rows[1]['high']=105.5
        self.assertIsNone(self.trade()['adverse_before_exit_pct'])

    def test_gap_open_and_etf_cost(self):
        self.rows[2].update(open=107,high=108,close=107)
        r=self.trade(kind='etf')
        self.assertEqual(r['exit_price'],107)
        self.assertAlmostEqual(r['net_return_pct'],net_return(100,107,{'kind':'etf'}))

    def test_pending_even_if_early_target(self):
        self.rows[1]['high']=106
        r=self.trade(as_of=self.dates[4])
        self.assertEqual(r['status'],'pending');self.assertEqual(r['elapsed_sessions'],4)
        self.assertIsNone(r['net_return_pct'])

    def test_missing_locked_and_adjusted(self):
        saved=self.rows.pop(4)
        self.assertEqual(self.trade()['status'],'not_comparable')
        self.rows.insert(4,saved)
        self.rows[1].update(high=100,low=100,close=100)
        self.assertEqual(self.trade()['status'],'not_filled')
        self.rows[1].update(high=104,low=97)
        self.rows[3]['change']='X'
        self.assertEqual(self.trade()['status'],'not_comparable')

    def test_daily_weighting_and_undefined_profit_factor(self):
        records=[dict(signal_date=d,kind='stock',rank=1,status='evaluated',net_return_pct=v,target_filled=v>0,policy_version='trade-policy-v1')
                 for d,v in [('a',10),('a',10),('b',-10)]]
        report=summarize_performance(records)['stock']
        self.assertEqual(report['top10']['mean_net_return_pct'],0)
        self.assertEqual(report['paired_difference_pct'],0)
        self.assertIsNone(summarize_performance(records[:2])['stock']['top10']['profit_factor'])
        records.append(dict(signal_date='c',kind='stock',rank=1,status='pending',net_return_pct=None))
        self.assertEqual(summarize_performance(records)['stock']['top10']['counts']['pending'],1)

if __name__=='__main__': unittest.main()
