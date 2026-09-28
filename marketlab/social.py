"""Observed public-post counts, independent of price ranking."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

SOURCES = ('ptt','dcard','threads')


def empty_report():
    return dict(collected_at=None,window_start=None,sources={},windows={'24h':[],'7d':[]})


def timestamp(value):
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result if result.tzinfo else None
    except (ValueError,TypeError): return None


def identify(text, stocks):
    text=unicodedata.normalize('NFKC',text).replace('臺','台')
    context=bool(re.search(r'股票|股價|台股|持股|營收|買超|賣超|法人|ETF|標的',text,re.I))
    context=context or any(len(s.get('name',''))>2 and s['name'].replace('臺','台') in text for s in stocks)
    found=[]
    for stock in stocks:
        symbol=str(stock['symbol'])
        name=unicodedata.normalize('NFKC',stock.get('name','')).replace('臺','台')
        named=bool(name and name in text and (len(name)>2 or context))
        code=bool(context and re.search(r'(?<![\dA-Za-z/.$])'+re.escape(symbol)+r'(?![\dA-Za-z/]|\.\d|\s*(?:元|塊|圓|美元|%|張|年|月|日))',text))
        if named or code: found.append(symbol)
    return sorted(set(found))


def build_social(posts, stocks, sources, current=None):
    current=current or datetime.now(timezone.utc)
    available={s for s in SOURCES if sources.get(s,{}).get('status') in ('success','partial')}
    unique={}
    for post in posts:
        time=timestamp(post.get('published_at'))
        if post.get('source') in available and time and current-timedelta(days=7)<=time<=current:
            unique[(post['source'],str(post['id']))]=post
    windows={}
    for key,days in [('24h',1),('7d',7)]:
        by_symbol={}
        for post in unique.values():
            if timestamp(post['published_at'])<current-timedelta(days=days): continue
            for symbol in set(post.get('symbols',[])):
                by_symbol.setdefault(symbol,[]).append(post)
        rows=[]
        for stock in stocks:
            evidence=by_symbol.get(str(stock['symbol']),[])
            if not evidence: continue
            counts={s:sum(p['source']==s for p in evidence) if s in available else None for s in SOURCES}
            rows.append(dict(symbol=stock['symbol'],name=stock.get('name'),kind=stock.get('kind'),
                counts=counts,total=sum(v or 0 for v in counts.values()),
                evidence=sorted(evidence,key=lambda p:p['published_at'],reverse=True)))
        windows[key]=sorted(rows,key=lambda r:(-r['total'],str(r['symbol'])))
    return dict(collected_at=current.isoformat(),window_start=(current-timedelta(days=7)).isoformat(),
        sources=sources,windows=windows,method='觀察到的公開主貼文篇數；同平台同篇同股票一次，不含留言或圖片文字。搜尋／頁數上限可能造成不完整涵蓋。')
