"""Collect independent public social observations; credentials stay in environment."""
import argparse
from datetime import datetime, timedelta, timezone
from marketlab.service import MarketService
from marketlab.social import build_social, timestamp
from marketlab.social_collect import collect_ptt, collect_dcard, collect_threads
from marketlab.data import atomic_json


def update_social(service, current=None):
    current=current or datetime.now(timezone.utc)
    snapshot=service.store.snapshot() or {}
    stocks=snapshot.get('rows',[])
    if not stocks: raise ValueError('需要股票母集合才能辨識社群提及')
    previous=service.store.get('social_posts',[])
    posts=[p for p in previous if timestamp(p.get('published_at')) and current-timedelta(days=7)<=timestamp(p['published_at'])<=current]
    statuses={}
    for source,collector in [('ptt',collect_ptt),('dcard',collect_dcard),('threads',collect_threads)]:
        new,status=collector(stocks,current)
        status['checked_at']=current.isoformat()
        statuses[source]=status
        posts.extend(new)
        print(f'{source}: {status["status"]}, scanned={status.get("scanned",0)}')
    posts=list({(p['source'],p['id']):p for p in posts}.values())
    service.store.put('social_posts',posts)
    report=build_social(posts,stocks,statuses,current)
    service.store.put('social_report',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='data')
    parser.add_argument('--output',default='dist/data/social.json')
    args=parser.parse_args()
    report=update_social(MarketService(args.data_dir))
    atomic_json(args.output,report)


if __name__=='__main__': main()
