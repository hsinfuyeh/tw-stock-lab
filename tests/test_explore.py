import unittest
from datetime import date, timedelta
import importlib


class ExploreTests(unittest.TestCase):
    def catalog(self, rows, actual=None):
        module = importlib.import_module('marketlab.explore')
        return module.explore_catalog(dict(id='sample', as_of='2026-09-24', rows=rows,
            calendar=dict(actual=actual or [b['date'] for b in rows[0]['bars'] if b['date'] <= '2026-09-24'])))

    def bars(self):
        return [dict(date=(date(2026,9,4)+timedelta(days=i)).isoformat(), open=100,
            high=101 if i<20 else 111, low=99, close=100 if i<20 else 110,
            volume=1000 if i<20 else 2000, turnover=100000 if i<20 else 220000,
            valid=True, mark='', change='0') for i in range(21)]

    def test_current_prices_volume_and_breakout_are_derived_from_same_snapshot(self):
        out=self.catalog([dict(symbol='2330',name='台積電',kind='stock',bars=self.bars())])
        row=out['rows'][0]
        self.assertEqual(out['as_of'],'2026-09-24')
        self.assertEqual(row['metrics']['close'],110)
        self.assertAlmostEqual(row['metrics']['change_pct'],10)
        self.assertEqual(row['metrics']['turnover'],220000)
        self.assertEqual(row['metrics']['relative_volume'],2)
        self.assertTrue(row['metrics']['new_high20'])
        self.assertFalse(row['metrics']['new_low20'])
        self.assertEqual(row['detail_url'],'./data/details/sample/2330.json')

    def test_stale_symbol_remains_searchable_without_current_metrics(self):
        row=self.catalog([dict(symbol='2330',name='台積電',kind='stock',bars=self.bars()[:-1])])['rows'][0]
        self.assertEqual(row['data_as_of'],'2026-09-23')
        self.assertEqual(row['metrics'],{})

    def test_missing_market_session_and_adjustments_do_not_create_false_ranks(self):
        bars=self.bars(); actual=[b['date'] for b in bars]
        bars.pop(10)
        row=self.catalog([dict(symbol='2330',kind='stock',bars=bars)],actual)['rows'][0]
        self.assertIsNone(row['metrics']['relative_volume'])
        self.assertIsNone(row['metrics']['new_high20'])
        bars=self.bars(); bars[-1]['change']='X0.00'
        row=self.catalog([dict(symbol='2330',kind='stock',bars=bars)])['rows'][0]
        self.assertIsNone(row['metrics']['change_pct'])
        self.assertIsNone(row['metrics']['volatility_pct'])


if __name__=='__main__': unittest.main()
