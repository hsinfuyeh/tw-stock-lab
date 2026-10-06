"""Import saved static evidence into a fresh, isolated local store. No downloads."""
import argparse,copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from marketlab.data import Store,atomic_json

def seed(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('來源與目標不得重疊')
    if destination.exists() and any(destination.iterdir()):raise ValueError('目標已有資料，拒絕覆蓋')
    def read(path):
        if not path.is_relative_to(source):raise ValueError('來源路徑超出靜態目錄')
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError) as e:raise ValueError('缺少有效靜態快照：'+str(path)) from e
    state=read(source/'data/state.json');latest=state.get('latest')
    if not latest or not latest.get('rows'):raise ValueError('沒有完整已保存快照')
    snapshots={latest['id']:copy.deepcopy(latest)};missing=[]
    for meta in state.get('history',[]):
        if meta['id']==latest['id']:continue
        identifier=meta['id']
        if not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identifier):raise ValueError('快照 ID 不合法')
        path=source/'data/snapshots'/f'{identifier}.json'
        if not path.is_file():missing.append(identifier);continue
        snapshots[identifier]=read(path)
    for snap in snapshots.values():
        dates=set()
        for i,brief in enumerate(snap.get('rows',[])):
            detail=brief
            if brief.get('detail_url'):
                detail=read((source/brief['detail_url']).resolve())
                if detail.get('symbol')!=brief['symbol']:raise ValueError('個股詳情代號不符')
            snap['rows'][i]=dict(brief,**detail)
            dates.update(r['date'] for r in detail.get('bars',[]) if r['date']<=snap['as_of'])
        if not dates:raise ValueError('沒有可核對的日線資料')
        snap.setdefault('calendar',{'actual':sorted(dates)})
        snap['local_import']=dict(source='saved-static-export',calendar_basis='saved official daily bar dates')
    store=Store(destination)
    ordered=sorted(snapshots.values(),key=lambda r:(r['created_at'],r['id']))
    for snap in ordered:
        store.save_snapshot(snap);atomic_json(destination/'snapshots'/f"{snap['id']}.json",snap)
    store.put('latest',latest['id'])
    store.put('two_week_outcomes',state.get('two_week_outcomes',[]))
    store.put('checked_at',state.get('checked_at'))
    store.put('local_import',dict(missing_snapshots=missing,source='saved-static-export'))
    social=source/'data/social.json'
    if social.is_file():store.put('social_report',read(social))
    return dict(snapshots=len(ordered),as_of=latest['as_of'],destination=str(destination),missing_snapshots=missing)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='dist');parser.add_argument('--destination',default='data/local-research-dev')
    args=parser.parse_args();print(json.dumps(seed(args.source,args.destination),ensure_ascii=False))
