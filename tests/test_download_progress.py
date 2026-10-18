"""Real coordinator callbacks must reach the persisted job consumed by the UI."""
import tempfile
import unittest
from marketlab.service import MarketService


class InterruptedDownload:
    def __init__(self, root, progress): self.progress=progress
    def universe(self): return [dict(symbol='2330',name='台積電',kind='stock')]
    def calendar(self, months):
        return dict(actual=['2026-10-01','2026-10-02','2026-10-05','2026-10-06','2026-10-07'])
    def market_bundles(self, universe, calendar):
        self.progress('全市場 2/5','2026-10-02')
        raise RuntimeError('fixture: interrupted after second session')


class DownloadProgressTests(unittest.TestCase):
    def test_download_counts_survive_interruption_in_persisted_job(self):
        with tempfile.TemporaryDirectory() as root:
            service=MarketService(root,client_factory=InterruptedDownload,workers=1)
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                service.update()
            job=service.store.get('job')
            self.assertEqual((job['progress'],job['total']),(2,5))
            self.assertFalse(job['running'])
            self.assertIn('interrupted',job['error'])

if __name__=='__main__': unittest.main()
