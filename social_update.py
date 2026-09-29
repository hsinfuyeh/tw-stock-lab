"""Collect independent public social observations; credentials stay in environment."""
import argparse
from datetime import datetime, timedelta, timezone
from marketlab.service import MarketService
from marketlab.social import build_social, timestamp, IDENTIFIER_VERSION
from marketlab.social_collect import collect_ptt, collect_dcard, collect_threads
from marketlab.data import atomic_json


def update_social(service, current=None, skip_dcard=False):
    current=current or datetime.now(timezone.utc)
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
    for source,collector in [('ptt',collect_ptt),('dcard',collect_dcard),('threads',collect_threads)]:
        if source=='dcard' and skip_dcard:
            new,status=[],dict(status='disabled',scanned=0,scope='依設定暫緩 Dcard 收集。')
        else: new,status=collector(stocks,current)
        status['checked_at']=current.isoformat()
        statuses[source]=status
        posts.extend(new)
        print(f'{source}: {status["status"]}, scanned={status.get("scanned",0)}')
    posts=list({(p['source'],p['id']):p for p in posts}.values())
    # Version and observations commit together, so interrupted migrations cannot reset twice.
    service.store.put('social_observations',dict(identifier_version=IDENTIFIER_VERSION,posts=posts,rebuild_at=rebuild_at))
    report=build_social(posts,stocks,statuses,current)
    report['coverage_note']=f"辨識規則更新後自 {rebuild_at} 重新收集；七天統計僅含實際取得的貼文。"
    service.store.put('social_report',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='data')
    parser.add_argument('--output',default='dist/data/social.json')
    parser.add_argument('--skip-dcard',action='store_true',help='暫緩 Dcard 收集並顯示停用狀態')
    args=parser.parse_args()
    report=update_social(MarketService(args.data_dir),skip_dcard=args.skip_dcard)
    atomic_json(args.output,report)


if __name__=='__main__': main()
