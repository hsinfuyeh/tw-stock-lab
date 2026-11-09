import unittest
from datetime import datetime

from marketlab.mis_intraday import normalize_mis


class MisTests(unittest.TestCase):
    current = datetime.fromisoformat('2026-11-10T09:10:10+08:00')
    catalog = [
        {'symbol': '2330', 'kind': 'stock'},
        {'symbol': '0050', 'kind': 'etf'},
    ]

    def row(self, **changes):
        tick = int((self.current.timestamp() - 5) * 1000)
        row = dict(ex='tse', ch='2330.tw', c='2330', n='台積電', d='20261110',
                   t='09:10:05', tlong=str(tick), z='102.00', y='100.00',
                   o='98.00', v='999', tv='2')
        return dict(row, **changes)

    def test_normalizes_only_requested_formal_trades(self):
        rows = [
            self.row(),
            self.row(c='0050', ch='0050.tw', n='元大台灣50', z='-'),
            self.row(c='9999', ch='9999.tw'),
        ]
        report = normalize_mis(dict(rtcode='0000', msgArray=rows), self.catalog, self.current)
        self.assertEqual(report['status'], 'live')
        self.assertEqual(report['coverage'], 1)
        self.assertEqual(report['universe_count'], 2)
        quote, = report['rows']
        self.assertEqual((quote['symbol'], quote['day_pct'], quote['gap_pct'], quote['volume']),
                         ('2330', 2, -2, 999))
        self.assertIsNone(quote['amount'])

    def test_previous_session_is_not_live(self):
        row = self.row(d='20261109', t='13:30:00', tlong='1794205800000')
        report = normalize_mis(dict(rtcode='0000', msgArray=[row]), self.catalog, self.current)
        self.assertEqual(report['status'], 'stale')
        self.assertEqual(report['rows'], [])
