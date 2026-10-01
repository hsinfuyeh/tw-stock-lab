"""Collect independent public social observations; credentials stay in environment."""
import argparse
from datetime import datetime, timedelta, timezone
from marketlab.service import MarketService
from marketlab.social import build_social, timestamp, IDENTIFIER_VERSION
from marketlab.social_collect import collect_ptt, collect_dcard, collect_threads, collect_threads_public
from marketlab.data import atomic_json


def update_social(service, current=None, skip_dcard=False,window='7d',local_public=False,progress=None):
    if window not in ('24h','7d'): raise ValueError('統計期間只接受 24h 或 7d')
    current=current or datetime.now(timezone.utc)
    # Both report windows are built from this collection, regardless of which
    # window the user is currently viewing.
    since=current-timedelta(days=7)
    snapshot=service.store.snapshot() or {}
    stocks=snapshot.get('rows',[])
    if not stocks: raise ValueError('需要股票母集合才能辨識社群提及')
    state=service.store.get('social_observations') or {}
    previous=state.get('posts',[])
    rebuild_at=state.get('rebuild_at') or current.isoformat()
    if state.get('identifier_version')!=IDENTIFIER_VERSION:
        previous=[]
        rebuild_at=current.isoformat()
    posts=[p for p in previous if timestamp(p.get('published_at')) and current-timedelta(days=7)<=timestamp(p['published_at'])<=current]
    statuses={}
    for source,collector in [('ptt',collect_ptt),('dcard',collect_dcard),('threads',collect_threads_public if local_public else collect_threads)]:
        if progress: progress(source,dict(status='collecting'))
        if source=='dcard' and skip_dcard:
            new,status=[],dict(status='disabled',scanned=0,scope='依設定暫緩 Dcard 收集。')
        else: new,status=collector(stocks,current,since=since)
        status['checked_at']=current.isoformat()
        status['window_start']=since.isoformat()
        status['window_end']=current.isoformat()
        statuses[source]=status
        if progress: progress(source,status)
        posts.extend(new)
        print(f'{source}: {status["status"]}, scanned={status.get("scanned",0)}')
    if not any(status.get('status') in ('success','partial') for status in statuses.values()):
        raise RuntimeError('所有社群來源均未取得有效資料，保留上一份結果')
    posts=list({(p['source'],p['id']):p for p in posts}.values())
    # Version and observations commit together, so interrupted migrations cannot reset twice.
    service.store.put('social_observations',dict(identifier_version=IDENTIFIER_VERSION,posts=posts,rebuild_at=rebuild_at))
    report=build_social(posts,stocks,statuses,current)
    report['requested_window']=window
    report['coverage_note']=f"辨識規則更新後自 {rebuild_at} 重新收集；七天統計僅含實際取得的貼文。"
    service.store.put('social_report',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='data')
    parser.add_argument('--output',default='dist/data/social.json')
    parser.add_argument('--skip-dcard',action='store_true',help='暫緩 Dcard 收集並顯示停用狀態')
    parser.add_argument('--window',choices=['24h','7d'],default='7d')
    parser.add_argument('--public-threads',action='store_true',help='只使用未登入公開路線，不使用 Threads Token')
    args=parser.parse_args()
    report=update_social(MarketService(args.data_dir),skip_dcard=args.skip_dcard,window=args.window,local_public=args.public_threads)
    atomic_json(args.output,report)


if __name__=='__main__': main()
