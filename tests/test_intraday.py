import unittest
from datetime import datetime
from unittest.mock import Mock

from marketlab.intraday import IntradayFeed, normalize_snapshot


class IntradayTests(unittest.TestCase):
    clock = datetime.fromisoformat('2026-11-09T09:10:12+08:00')
    universe = [dict(symbol='2330', kind='stock'), dict(symbol='0050', kind='etf')]

    def snapshot(self):
        tick = int(self.clock.timestamp() - 5) * 1_000_000
        stock = dict(type='EQUITY', symbol='2330', name='台積電', openPrice=98,
                     lastPrice=102, closePrice=102, change=2, tradeVolume=100,
                     tradeValue=10_000_000, lastUpdated=tick)
        etf = dict(stock, symbol='0050', name='台灣50', lastPrice=101, isTrial=True)
        return dict(market='TSE', date='2026-11-09', time='091010',
                    data=[stock, etf, dict(stock, symbol='9999')])

    def test_classification_reference_and_trial(self):
        report = normalize_snapshot(self.snapshot(), self.universe, self.clock)
        self.assertEqual(report['status'], 'live')
        stock, etf = report['rows']
        self.assertEqual((stock['symbol'], stock['kind'], stock['day_pct'], stock['gap_pct']),
                         ('2330', 'stock', 2, -2))
        self.assertEqual(etf['kind'], 'etf')
        self.assertIsNone(etf['day_pct'])
        self.assertEqual(etf['price'], 102)
        self.assertEqual(report['coverage'], 2)

    def test_rejects_stale_or_other_day_snapshots(self):
        for change in ({'time': '090001'}, {'date': '2026-11-06'}):
            report = normalize_snapshot(dict(self.snapshot(), **change), self.universe, self.clock)
            self.assertEqual(report['status'], 'stale')
            self.assertFalse(report['rows'])

    def test_poll_cache_and_provider_failure(self):
        fetch = Mock(return_value=self.snapshot())
        monotonic = Mock(return_value=100)
        feed = IntradayFeed('key', lambda: self.universe, fetch=fetch,
                            clock=lambda: self.clock, timer=monotonic)
        self.assertEqual(feed.report()['status'], 'live')
        self.assertEqual(feed.report()['status'], 'live')
        fetch.assert_called_once_with('key')
        monotonic.return_value += 20
        fetch.side_effect = OSError('do not expose raw errors')
        report = feed.report()
        self.assertEqual(report['status'], 'unavailable')
        self.assertFalse(report['rows'])
        self.assertNotIn('do not expose', str(report))
