import tempfile
import unittest
from marketlab.data import Store
from marketlab.official_store import OfficialStore


def obs(dt='2026-10-07', value=10, source='institution'):
    return dict(symbol='2330', key=dt, data_date=dt, period=None,
                published_at=None, unit='shares', values={'total_net':value})

def evidence(stamp='2026-10-08T08:00:00+08:00'):
    return dict(fetched_at=stamp, sha256='a'*64, file='raw.json', url='https://www.twse.com.tw/')


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.official = OfficialStore(self.store)
    def tearDown(self): self.temp.cleanup()

    def test_dedup_correction_and_old_cutoff(self):
        self.assertEqual(self.official.ingest('institution', [obs()], evidence()), 1)
        self.assertEqual(self.official.ingest('institution', [obs()], evidence('2026-10-09T08:00:00+08:00')), 0)
        self.assertEqual(self.official.query(cutoff='2026-10-07T19:00:00+08:00'), [])
        self.assertEqual(self.official.ingest('institution', [obs(value=20)], evidence('2026-10-09T09:00:00+08:00')), 1)
        before = self.official.query(cutoff='2026-10-08T19:00:00+08:00')[0]
        self.assertEqual(before['values']['total_net'], 10)
        self.assertEqual(before['first_seen_at'], evidence()['fetched_at'])
        self.assertEqual(before['evidence']['file'], 'raw.json')
        self.assertEqual(self.official.query()[0]['values']['total_net'], 20)

    def test_reversion_is_new_version(self):
        for day, val in ((8,10),(9,20),(10,10)):
            self.official.ingest('institution',[obs(value=val)],evidence(f'2026-10-{day:02d}T08:00:00+08:00'))
        self.assertEqual(self.official.query()[0]['values']['total_net'],10)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM official_observations').fetchone()[0],3)

    def test_published_and_data_dates_exclude_future(self):
        row = obs('2026-10-09'); row['published_at']='2026-10-10T09:00:00+08:00'
        self.official.ingest('institution',[row],evidence())
        self.assertEqual(self.official.query(cutoff='2026-10-09T19:00:00+08:00'),[])
        self.assertEqual(self.official.query(as_of='2026-10-07'),[])
        with self.assertRaises(ValueError): self.official.query(cutoff='2026-10-08T08:00:00')

    def test_complete_five_days_ratio_and_no_zero_fill(self):
        days=[f'2026-10-{d:02d}' for d in (1,2,5,6,7)]
        rows=[obs(dt,10) for dt in days]
        revenue=obs('2026-08-01'); revenue.update(key='2026-08',period='2026-08',unit='amount_unverified',values={'yoy_pct':5,'mom_pct':0})
        self.official.ingest('institution',rows,evidence('2026-10-07T18:00:00+08:00'))
        self.official.ingest('revenue',[revenue],evidence('2026-10-07T18:00:00+08:00'))
        bars=[dict(date=d,volume=100) for d in days]
        f=self.official.features('2330',days[-1],'2026-10-07T19:00:00+08:00',days,bars)
        self.assertEqual(f['institution_ratio_5'],.1)
        self.assertEqual(f['buy_streak'],5)
        self.assertEqual(f['revenue_yoy_pct'],5)
        bars.pop()
        self.assertIsNone(self.official.features('2330',days[-1],'2026-10-07T19:00:00+08:00',days,bars)['institution_ratio_5'])
        self.assertEqual(self.official.detail('0050','etf')['sources']['revenue']['status'],'not_applicable')
        self.assertEqual(self.official.detail('2317','stock')['sources']['institution']['status'],'missing')

if __name__ == '__main__': unittest.main()
