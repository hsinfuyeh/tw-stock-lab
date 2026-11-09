import unittest
from datetime import datetime

from marketlab.mis_intraday import fetch_batches, market_catalog, normalize_mis, watchlist_symbols


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

    def test_market_catalog_includes_other_listed_etf_types(self):
        companies = [{'公司代號': '2330', '公司簡稱': '台積電'},
                     {'公司代號': '9999', '公司簡稱': '測試-DR'}]
        etfs = {'status': 'success', 'data': [
            {'stockNo': '0050'}, {'stockNo': '00775B'}, {'stockNo': '00631L'},
            {'stockNo': '00632R'}, {'stockNo': '00400A'},
        ]}
        catalog = market_catalog(companies, etfs)
        self.assertEqual({row['symbol']: row['kind'] for row in catalog}, {
            '2330': 'stock', '0050': 'etf', '00775B': 'etf',
            '00631L': 'etf', '00632R': 'etf', '00400A': 'etf',
        })

    def test_batches_cover_more_than_one_page_and_report_partial_failure(self):
        symbols = watchlist_symbols(','.join(str(n) for n in range(1000, 1120)))
        seen = []

        def fetch(batch):
            seen.extend(batch)
            if batch[0] == '1050':
                raise OSError('transient')
            return {'rtcode': '0000', 'msgArray': [{'c': symbol} for symbol in batch]}

        report = fetch_batches(symbols, fetch=fetch, pause=lambda _: None)
        self.assertEqual(seen, list(symbols))
        self.assertEqual((report['batch_count'], report['batches_ok'], len(report['msgArray'])), (3, 2, 70))
