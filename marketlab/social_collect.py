"""Bounded public-source adapters. Never bypass access restrictions."""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .social import identify, timestamp

TAIPEI=timezone(timedelta(hours=8))


def fetch_public(url, headers=None):
    request=Request(url,headers={'User-Agent':'tw-stock-lab/1.0 public-stock-research',**(headers or {})})
    with urlopen(request,timeout=15) as response:
        body=response.read(5_000_001)
        if len(body)>5_000_000: raise ValueError('Response exceeds size limit')
        return body.decode('utf-8')


class PttHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[];self.meta=[];self.parts=[];self.stack=[];self.link=None;self.value=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);classes=attrs.get('class','').split()
        self.stack.append((tag,attrs.get('id'),classes))
        if tag=='a': self.link=[attrs.get('href',''),'']
        if tag=='span' and 'article-meta-value' in classes: self.value=''
    def handle_endtag(self,tag):
        if tag=='a' and self.link is not None: self.links.append(self.link);self.link=None
        if tag=='span' and self.value is not None: self.meta.append(self.value.strip());self.value=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag: self.stack=self.stack[:i];break
    def handle_data(self,text):
        if self.link is not None: self.link[1]+=text
        if self.value is not None: self.value+=text
        if any(x[1]=='main-content' for x in self.stack) and not any('push' in x[2] or 'article-meta-value' in x[2] or 'article-metaline' in x[2] or 'article-metaline-right' in x[2] or x[0] in ('script','style') for x in self.stack): self.parts.append(text)


def parse_ptt_index(html):
    parser=PttHTML();parser.feed(html)
    links=[urljoin('https://www.ptt.cc',href) for href,_ in parser.links if re.fullmatch(r'/bbs/Stock/M\.[A-Za-z0-9.]+\.html',href)]
    prev=next((urljoin('https://www.ptt.cc',href) for href,text in parser.links if '上頁' in text and re.fullmatch(r'/bbs/Stock/index\d+\.html',href)),None)
    return list(dict.fromkeys(links)),prev


def parse_ptt_article(html,url,stocks):
    parser=PttHTML();parser.feed(html)
    if len(parser.meta)<4: raise ValueError('missing publication metadata')
    published=datetime.strptime(parser.meta[3],'%a %b %d %H:%M:%S %Y').replace(tzinfo=TAIPEI)
    title=parser.meta[2]
    text=''.join(parser.parts).split('※ 發信站:')[0]
    text='\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('>','※ 引述',': ')))
    return dict(source='ptt',id=url.rsplit('/',1)[-1],url=url,title=title[:160],
        published_at=published.isoformat(),symbols=identify(title+'\n'+text,stocks))


def reason(exc):
    # Do not expose provider response bodies, URLs containing tokens, or credentials.
    return f'HTTP {exc.code}' if isinstance(exc,HTTPError) else type(exc).__name__


def collect_ptt(stocks,current,fetch=fetch_public,max_pages=12,max_posts=150,since=None):
    since=since or current-timedelta(days=7)
    posts=[];seen=set();url='https://www.ptt.cc/bbs/Stock/index.html';errors=0;pages=0;start=time.monotonic()
    try:
        while url and pages<max_pages and len(seen)<max_posts and time.monotonic()-start<300:
            links,url=parse_ptt_index(fetch(url));pages+=1
            for link in reversed(links):
                if link in seen: continue
                if len(seen)>=max_posts or time.monotonic()-start>=300: break
                seen.add(link)
                try:
                    post=parse_ptt_article(fetch(link),link,stocks)
                    if since<=timestamp(post['published_at'])<=current: posts.append(post)
                except Exception: errors+=1
                time.sleep(.15)
        status='partial' if posts else 'failed' if errors else 'partial'
        return posts,dict(status=status,scanned=len(seen),pages=pages,errors=errors,
            scope=f'PTT Stock 主文；最近至多 {max_pages} 頁／{max_posts} 篇，最多 5 分鐘，不含推文；屬有限取樣。')
    except Exception as exc:
        return posts,dict(status='partial' if posts else 'failed',scanned=len(seen),pages=pages,error=reason(exc),scope='PTT Stock；收集未完成')


def collect_dcard(stocks,current,fetch=fetch_public,max_pages=5,since=None):
    since=since or current-timedelta(days=7)
    posts=[];before=None;scanned=0;pages=0
    try:
        for _ in range(max_pages):
            params={'popular':'false','limit':100}
            if before: params['before']=before
            rows=json.loads(fetch('https://www.dcard.tw/service/api/v2/forums/stock/posts?'+urlencode(params)))
            if not isinstance(rows,list): raise ValueError('invalid Dcard response')
            pages+=1
            if not rows: break
            for row in rows:
                scanned+=1;published=timestamp(row.get('createdAt'))
                if not published or not since<=published<=current: continue
                text=str(row.get('title',''))+' '+str(row.get('excerpt',''))
                posts.append(dict(source='dcard',id=str(row['id']),url=f'https://www.dcard.tw/f/stock/p/{int(row["id"])}',
                    title=str(row.get('title',''))[:160],published_at=published.isoformat(),symbols=identify(text,stocks)))
            cursor=rows[-1].get('id')
            if cursor==before: break
            before=cursor
            if timestamp(rows[-1].get('createdAt')) and timestamp(rows[-1]['createdAt'])<since: break
        return posts,dict(status='partial',scanned=scanned,pages=pages,scope='Dcard 股票板最新貼文標題與摘要；至多 5 頁、每頁 100 篇，不含留言與摘要外內文。')
    except Exception as exc:
        return posts,dict(status='partial' if posts else 'failed',scanned=scanned,pages=pages,error=reason(exc),scope='Dcard 股票板；來源拒絕或尚無可用資料服務，不繞過驗證。')


def collect_threads_public(stocks,current,since=None):
    # Anonymous discovery did not establish a usable search/publication-time source.
    # Never silently fall back to the user's browser cookies or an account token.
    return [],dict(status='unavailable',scanned=0,scope='Threads 未登入公開搜尋尚未接通；未使用個人帳號或登入 Cookie，未取得可核對發布時間的文章。')


def collect_threads(stocks,current,token=None,fetch=fetch_public,max_pages=3,since=None):
    since=since or current-timedelta(days=7)
    token=token if token is not None else os.environ.get('THREADS_ACCESS_TOKEN','')
    if not token: return [],dict(status='not_configured',scanned=0,scope='Threads 官方 API 尚未設定授權。')
    posts=[];scanned=0;pages=0
    try:
        for query in ['台股','股票','ETF']:
            after=None
            for _ in range(max_pages):
                params=dict(q=query,search_type='RECENT',limit=50,fields='id,text,timestamp,permalink',
                    since=int(since.timestamp()),until=int(current.timestamp()))
                if after: params['after']=after
                data=json.loads(fetch('https://graph.threads.net/v1.0/keyword_search?'+urlencode(params),headers={'Authorization':'Bearer '+token}))
                if 'error' in data or not isinstance(data.get('data'),list): raise ValueError('invalid Threads response')
                pages+=1
                for row in data['data']:
                    scanned+=1;published=timestamp(row.get('timestamp'))
                    link=row.get('permalink','')
                    if not published or not since<=published<=current: continue
                    if urlparse(link).hostname not in ('www.threads.net','www.threads.com','threads.net','threads.com'): continue
                    text=row.get('text','')
                    posts.append(dict(source='threads',id=str(row['id']),url=link,title=str(text)[:120],published_at=published.isoformat(),symbols=identify(text,stocks)))
                next_cursor=data.get('paging',{}).get('cursors',{}).get('after')
                if not data.get('paging',{}).get('next') or not next_cursor or next_cursor==after: break
                after=next_cursor
        return posts,dict(status='partial',scanned=scanned,pages=pages,scope='Threads 官方搜尋「台股／股票／ETF」，每詞至多 3 頁、每頁 50 篇；非全平台完整資料。')
    except Exception as exc:
        return posts,dict(status='partial' if posts else 'failed',scanned=scanned,pages=pages,error=reason(exc),scope='Threads 官方搜尋；授權或來源失敗。')
