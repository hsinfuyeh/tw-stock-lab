import unittest
from marketlab.official import parse_source, T86_FIELDS, MARGIN_FIELDS


class OfficialParserTests(unittest.TestCase):
    def t86(self):
        return dict(stat='OK', date='20261007', hints='單位：股', fields=T86_FIELDS,
                    data=[['2330', '台積電'] + ['1,000'] * 17])

    def test_institution_units_and_separate_official_total(self):
        row = parse_source('institution', self.t86(), '2026-10-07')[0]
        self.assertEqual(row['unit'], 'shares')
        self.assertEqual(row['values']['total_net'], 1000)
        self.assertEqual(row['values']['foreign_dealer_net'], 1000)

    def test_reject_wrong_date_duplicate_or_invalid_number(self):
        for change in ('date', 'duplicate', 'number', 'field'):
            p = self.t86()
            if change == 'date': p['date'] = '20261006'
            if change == 'duplicate': p['data'] *= 2
            if change == 'number': p['data'][0][2] = 'NaN'
            if change == 'field': p['fields'] = T86_FIELDS[:-1] + [T86_FIELDS[2]]
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_source('institution', p, '2026-10-07')

    def test_margin_group_indices_not_duplicate_dict(self):
        table = dict(fields=MARGIN_FIELDS, groups=[dict(title='股票', span=2),
                     dict(title='融資', span=6), dict(title='融券', span=6),
                     dict(title='', span=1), dict(title='', span=1)],
                     data=[['2330', '台積電'] + [str(i) for i in range(2, 15)] + ['X']])
        p = dict(stat='OK', date='20261007', tables=[table])
        row = parse_source('margin', p, '2026-10-07')[0]
        self.assertEqual(row['values']['financing_current'], 6)
        self.assertEqual(row['values']['short_current'], 12)
        self.assertEqual(row['values']['note_applies'], 'next_business_day')
        table['groups'][1]['span'] = 5
        with self.assertRaises(ValueError): parse_source('margin', p, '2026-10-07')

    def test_revenue_period_and_missing_percent(self):
        row = parse_source('revenue', [{'公司代號': '2330', '資料年月': '11508',
            '出表日期': '1150917', '營業收入-當月營收': '100',
            '營業收入-上月比較增減(%)': '--', '營業收入-去年同月增減(%)': '0',
            '營業收入-去年當月營收': '50'}])[0]
        self.assertEqual(row['period'], '2026-08')
        self.assertIsNone(row['published_at'])
        self.assertIsNone(row['values']['mom_pct'])
        self.assertEqual(row['values']['yoy_pct'], 0)

    def test_announcement_time_and_normalization_collision(self):
        p = {'公司代號':'2330','發言日期':'1151006','發言時間':'70004',
             '事實發生日':'1150824','主旨 ':'公告','符合條款':'51','說明':'內容'}
        row = parse_source('announcement', [p])[0]
        self.assertEqual(row['published_at'], '2026-10-06T07:00:04+08:00')
        self.assertEqual(row['values']['fact_date'], '2026-08-24')
        p['發言時間'] = '250000'
        self.assertIsNone(parse_source('announcement', [p])[0]['published_at'])
        p['主旨'] = '衝突'
        with self.assertRaises(ValueError): parse_source('announcement', [p])

    def test_action_date(self):
        row = parse_source('action', [dict(Date='1151008', Code='2330',
                               Exdividend='息', CashDividend='2.5')])[0]
        self.assertEqual(row['data_date'], '2026-10-08')
        self.assertEqual(row['values']['cash_dividend'], 2.5)

if __name__ == '__main__': unittest.main()
