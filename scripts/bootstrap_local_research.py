"""Explicit official-source initialization for local preview (two months only)."""
import argparse,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from marketlab.service import MarketService

class PreviewService(MarketService):
    def settings(self):return dict(super().settings(),months=2)

def bootstrap(destination):
    destination=Path(destination).resolve()
    expected=Path(__file__).resolve().parents[1]/'data/local-research-dev'
    if destination!=expected.resolve():raise ValueError('初始化只允許獨立 data/local-research-dev 目錄')
    service=PreviewService(destination,workers=1)
    snapshot=service.update()
    service.store.put('local_import',dict(source='official-local-bootstrap',history_months=2,missing_snapshots=[],
        note='首次本機初始化只取最近兩個月；完整更新仍使用既有 36 個月設定。'))
    return dict(id=snapshot['id'],as_of=snapshot['as_of'],coverage=snapshot['coverage'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--destination',default='data/local-research-dev');args=parser.parse_args()
    print(json.dumps(bootstrap(args.destination),ensure_ascii=False))
