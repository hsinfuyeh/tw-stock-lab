import unittest,tempfile,json
from pathlib import Path
from scripts.seed_local_research import seed
from marketlab.data import Store

class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'dist';self.source.mkdir();self.dest=self.root/'dev'
    def tearDown(self):self.temp.cleanup()
    def fixture(self):
        (self.source/'data/details/a').mkdir(parents=True)
        detail={'symbol':'2330','kind':'stock','bars':[{'date':'2026-01-01','open':100,'high':101,'low':99,'close':100,'volume':1,'valid':True}]}
        (self.source/'data/details/a/2330.json').write_text(json.dumps(detail),encoding='utf8')
        (self.source/'data/state.json').write_text(json.dumps({'latest':{'id':'a','as_of':'2026-01-01','created_at':'x','rows':[{'symbol':'2330','kind':'stock','detail_url':'data/details/a/2330.json'}]},'history':[]}),encoding='utf8')
    def test_real_detail_import_and_source_unchanged(self):
        self.fixture();before=(self.source/'data/state.json').read_bytes()
        result=seed(self.source,self.dest)
        self.assertEqual(result['snapshots'],1)
        snap=Store(self.dest).snapshot();self.assertEqual(len(snap['rows'][0]['bars']),1)
        self.assertEqual(snap['calendar']['actual'],['2026-01-01']);self.assertNotIn('industry',snap['rows'][0])
        self.assertEqual((self.source/'data/state.json').read_bytes(),before)
        with self.assertRaises(ValueError):seed(self.source,self.dest)
    def test_invalid_source_leaves_destination_absent(self):
        with self.assertRaises(ValueError):seed(self.source,self.dest)
        self.assertFalse(self.dest.exists())
    def test_missing_history_is_disclosed_and_latest_remains_available(self):
        self.fixture();p=self.source/'data/state.json';s=json.loads(p.read_text());s['history']=[{'id':'absent'}];p.write_text(json.dumps(s))
        r=seed(self.source,self.dest)
        self.assertEqual(r['missing_snapshots'],['absent'])
        self.assertEqual(Store(self.dest).get('local_import')['missing_snapshots'],['absent'])
    def test_detail_path_cannot_escape_source(self):
        self.fixture();p=self.source/'data/state.json';s=json.loads(p.read_text());s['latest']['rows'][0]['detail_url']='../outside.json';p.write_text(json.dumps(s))
        with self.assertRaises(ValueError):seed(self.source,self.dest)
    def test_missing_details_preserve_partial_snapshot_without_inventing_bars(self):
        self.fixture();(self.source/'data/details/a/2330.json').unlink()
        with self.assertRaises(ValueError):seed(self.source,self.dest)

if __name__=='__main__':unittest.main()
