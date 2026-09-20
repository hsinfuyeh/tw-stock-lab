"""TWSE retrieval, immutable raw evidence, calendar and SQLite snapshots."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from .analytics import iso_date, parse_month, number

TAIPEI = timezone(timedelta(hours=8))


def now():
    return datetime.now(TAIPEI)


def json_text(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":"))


def atomic_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json_text(value),encoding="utf-8")
    temp.replace(path)


class Store:
    def __init__(self,root):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/"research.sqlite3"
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, as_of TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        conn=sqlite3.connect(self.path,timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self,key,default=None):
        with self.connect() as conn:
            row=conn.execute("SELECT payload FROM kv WHERE key=?",(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self,key,value):
        with self.connect() as conn:
            conn.execute("INSERT INTO kv VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(key,json_text(value)))

    def save_snapshot(self,snapshot,audit=None):
        with self.connect() as conn:
            conn.execute("INSERT INTO snapshots VALUES (?,?,?,?)",(snapshot["id"],snapshot["as_of"],snapshot["created_at"],json_text(snapshot)))
            conn.execute("INSERT INTO kv VALUES ('latest',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(json_text(snapshot["id"]),))
            if audit is not None: self._write_audit(conn,audit)

    def _write_audit(self,conn,audit):
        for key,value in (("reconciled",audit["outcomes"]),
                          ("reconciliation",{k:v for k,v in audit.items() if k!="outcomes"})):
            conn.execute("INSERT INTO kv VALUES (?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(key,json_text(value)))

    def save_audit(self,audit):
        with self.connect() as conn: self._write_audit(conn,audit)

    def snapshot(self,snapshot_id=None):
        snapshot_id=snapshot_id or self.get("latest")
        if not snapshot_id: return None
        with self.connect() as conn:
            row=conn.execute("SELECT payload FROM snapshots WHERE id=?",(snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def history(self,limit=100):
        with self.connect() as conn:
            sql="SELECT id,as_of,created_at FROM snapshots ORDER BY created_at DESC, id DESC"
            rows=conn.execute(sql if limit is None else sql+" LIMIT ?",() if limit is None else (limit,)).fetchall()
        return [dict(zip(("id","as_of","created_at"),r)) for r in rows]


class TwseClient:
    def __init__(self,root,progress=None):
        self.root=Path(root)/"raw"
        self.root.mkdir(parents=True,exist_ok=True)
        self.last_request=0
        self.progress=progress or (lambda *args:None)
        self.evidence=[]

    def fetch(self,key,url,max_age=None,month=None,validate=None):
        from urllib.parse import urlparse,parse_qs
        alternate=url.replace('/exchangeReport/STOCK_DAY?','/rwd/zh/afterTrading/STOCK_DAY?')
        if '/exchangeReport/MI_INDEX?' in url:
            query=parse_qs(urlparse(url).query)
            alternate='https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date='+query['date'][0]+'&type='+query['type'][0]+'&response=json'
        pointer=self.root/(key+".latest.json")
        if pointer.exists():
            try:
                metadata=json.loads(pointer.read_text(encoding="utf-8"))
                if not isinstance(metadata,dict): raise ValueError("Invalid cache metadata")
                digest=metadata["sha256"]
                if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest):
                    raise ValueError("Invalid cache hash")
                if metadata["file"]!=f"{key}-{digest[:16]}.json": raise ValueError("Invalid cache filename")
                source_url=re.sub(r'&_=[0-9]+$','',metadata['url'])
                if source_url not in (url,alternate): raise ValueError("Invalid cache source")
                acquired=datetime.fromisoformat(metadata["fetched_at"])
                timestamp=metadata["timestamp"]
                if (acquired.tzinfo is None or type(timestamp) not in (int,float)
                        or not 0<=timestamp<=time.time() or abs(acquired.timestamp()-timestamp)>5):
                    raise ValueError("Invalid cache acquisition time")
                age=max_age
                if month is not None:
                    start=datetime.strptime(month,"%Y%m%d").date()
                    closed=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
                    # Old month age alone is not evidence that its last sessions were fetched.
                    if acquired.astimezone(TAIPEI).date()<closed:
                        age=600 if age is None else min(age,600)
                if age is not None and time.time()-timestamp>=age: raise ValueError("Expired cache")
                data_path=self.root/metadata["file"]
                text=data_path.read_text(encoding="utf-8")
                if hashlib.sha256(text.encode()).hexdigest()!=digest: raise ValueError("Invalid cache content")
                value=json.loads(text)
                if not isinstance(value,dict if month is not None else (dict,list)):
                    raise ValueError("Invalid cached JSON shape")
                if validate: validate(value)
                self.evidence.append(metadata)
                return value
            except (OSError,ValueError,KeyError,TypeError,OverflowError):
                # A malformed/missing pointer or raw payload is a cache miss, never evidence.
                pass
        last_error=None
        request_url=url
        for attempt in range(3):
            time.sleep(max(0,1.05-(time.monotonic()-self.last_request)))
            self.last_request=time.monotonic()
            try:
                # Some official historical endpoints self-redirect with custom headers.
                # Keep urllib's standard request and validate the returned JSON below.
                req=Request(request_url)
                with urlopen(req,timeout=30) as response:
                    text=response.read().decode("utf-8-sig")
                value=json.loads(text)
                if not isinstance(value,(dict,list)): raise ValueError("官方資料格式不是 JSON 物件或清單")
                if isinstance(value,dict) and "stat" in value and str(value["stat"]).lower()!="ok":
                    if not any(word in str(value["stat"]) for word in ("沒有符合", "查無資料")):
                        raise ValueError("官方回應："+str(value["stat"]))
                if validate: validate(value)
                digest=hashlib.sha256(text.encode()).hexdigest()
                filename=f"{key}-{digest[:16]}.json"
                destination=self.root/filename
                try:
                    intact=hashlib.sha256(destination.read_bytes()).hexdigest()==digest
                except OSError:
                    intact=False
                if not intact:
                    temp=destination.with_suffix(".json.tmp")
                    temp.write_bytes(text.encode("utf-8"))
                    temp.replace(destination)
                metadata=dict(url=request_url,sha256=digest,file=filename,fetched_at=now().isoformat(),timestamp=time.time())
                atomic_json(pointer,metadata)
                self.evidence.append(metadata)
                return value
            except (URLError,HTTPError,ValueError,TimeoutError,OSError) as exc:
                last_error=exc
                request_url=alternate
                if attempt>=1 and '/MI_INDEX?' in alternate:
                    request_url=alternate+'&_='+str(int(time.time()))
                if attempt<2: time.sleep(2**(attempt+1))
        raise RuntimeError(f"TWSE 取得失敗（已重試）：{key}：{last_error}")

    def universe(self):
        payload=self.fetch("universe","https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",3600)
        if not isinstance(payload,list) or not payload: raise ValueError("官方證券清單為空")
        result=[]
        for row in payload:
            code=str(row.get("Code",""))
            if not re.fullmatch(r"(?:[1-9]\d{3}|00\d{2,3})",code): continue
            result.append(dict(symbol=code,name=str(row.get("Name",code)),kind="etf" if code.startswith("00") else "stock"))
        if not result: raise ValueError("官方證券清單欄位不符")
        return result

    def calendar(self,months):
        dates=[]
        index=[]
        for month in months:
            age=600 if month>=month_list(2)[-1] else None
            payload=self.fetch("market-"+month,"https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date="+month,age,month=month)
            if str(payload.get("stat","")).lower()!="ok": raise ValueError("大盤交易日取得失敗："+month)
            for row in payload.get("data",[]):
                dt=iso_date(row[0]); dates.append(dt)
                index.append(dict(date=dt,close=number(row[4])))
        holidays,opens,years=[],[],[]
        for year in [now().year,now().year+1]:
            payload=self.fetch("calendar-"+str(year),f"https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=json&queryYear={year-1911}",86400)
            if str(payload.get("stat","")).lower()!="ok" or not payload.get("data"): continue
            if str(payload.get("date",""))[:4]!=str(year): continue
            years.append(year)
            for row in payload["data"]:
                if "開始交易" in row[1] or "最後交易" in row[1]: opens.append(row[0])
                else: holidays.append(row[0])
        cutoff=now().date().isoformat()
        if now().hour<19: cutoff=(now().date()-timedelta(days=1)).isoformat()
        dates=sorted(set(d for d in dates if d<=cutoff))
        return dict(actual=dates,years=years,holidays=holidays,opens=opens,index=sorted((r for r in index if r["date"]<=cutoff),key=lambda r:r["date"]))

    def stock(self,symbol,months):
        rows={};issues=[]
        for month in months:
            self.progress(symbol,month)
            age=600 if month>=month_list(2)[-1] else None
            payload=self.fetch(f"stock-{symbol}-{month}",f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={month}&stockNo={symbol}",age,month=month)
            if str(payload.get("stat","")).lower()!="ok":
                if any(word in str(payload.get("stat","")) for word in ("沒有符合", "查無資料")):
                    issues.append(month+"：無歷史資料")
                    continue
                raise ValueError("個股資料取得失敗："+symbol+" "+month)
            parsed=parse_month(payload)
            for row in parsed["rows"]: rows[row["date"]]=row
            issues.extend(parsed["issues"])
        return dict(rows=[rows[k] for k in sorted(rows)],issues=issues)


def month_list(count):
    today=now().date()
    value=today.year*12+today.month-1
    return [f"{(value-offset)//12:04d}{(value-offset)%12+1:02d}01" for offset in range(count)]


def listed_universe(companies, etfs):
    """Official company master plus the explicitly filtered Stock/Vanilla ETF feed."""
    if not isinstance(companies,list) or not companies or etfs.get('status')!='success' or not etfs.get('data'):
        raise ValueError('上市股票／股票型ETF官方分類清單不完整')
    catalog={}
    for row in companies:
        symbol=str(row.get('公司代號','')).strip()
        if str(row.get('公司簡稱','')).upper().endswith('-DR'): continue
        if not re.fullmatch(r'[1-9]\d{3}',symbol):
            raise ValueError('上市公司代號格式改變，需檢查分類')
        listed=str(row.get('上市日期','')).strip()
        listing_date=iso_date(listed[:4]+'-'+listed[4:6]+'-'+listed[6:8]) if len(listed)==8 else None
        if symbol in catalog: raise ValueError('上市公司清單重複代號')
        catalog[symbol]=dict(symbol=symbol,name=row.get('公司簡稱') or row.get('公司名稱') or symbol,
                             kind='stock',listing_date=listing_date,currency='TWD')
    for row in etfs['data']:
        symbol=str(row.get('stockNo','')).strip()
        # 004xxA active equity and new six-digit funds are included. B/L/R are not vanilla equity.
        if not re.fullmatch(r'00(?:\d{2,4}|\d{3}[AK])',symbol):
            raise ValueError('股票型原型ETF分類出現不符代號：'+symbol)
        if symbol in catalog: raise ValueError('ETF清單重複代號')
        listing_date=iso_date(str(row['listingDate']).replace('.','-'))
        currency=('CNY' if '人民幣' in row['stockName'] else 'USD' if '美元' in row['stockName'] else 'unknown') if symbol.endswith('K') else 'TWD'
        catalog[symbol]=dict(symbol=symbol,name=row['stockName'],kind='etf',listing_date=listing_date,currency=currency)
    return sorted(catalog.values(),key=lambda r:r['symbol'])


def parse_market_day(payload, session):
    if payload.get('stat')!='OK' or payload.get('date')!=session.replace('-',''):
        raise ValueError('全市場行情日期或狀態不符：'+session)
    required=['證券代號','證券名稱','成交股數','成交金額','開盤價','最高價','最低價','收盤價','漲跌(+/-)','漲跌價差']
    tables=list(payload.get('tables',[]))
    # Older official responses used numbered fields/data keys.
    for key,fields in payload.items():
        if key.startswith('fields') and isinstance(fields,list):
            tables.append(dict(fields=fields,data=payload.get('data'+key[6:],[])))
    matched=[t for t in tables if all(k in t.get('fields',[]) for k in required)]
    if len(matched)!=1 or not matched[0].get('data'): raise ValueError('找不到唯一的每日行情表：'+session)
    table=matched[0];result={}
    for values in table['data']:
        if len(values)!=len(table['fields']): raise ValueError('每日行情欄位數不符')
        row=dict(zip(table['fields'],values));symbol=str(row['證券代號'])
        clean=lambda x: re.sub('<[^>]*>','',str(x)).strip()
        change=clean(row['漲跌(+/-)'])+clean(row['漲跌價差'])
        mini=dict(stat='OK',fields=['日期','成交股數','成交金額','開盤價','最高價','最低價','收盤價','漲跌價差','註記'],
                  data=[[session,row['成交股數'],row['成交金額'],row['開盤價'],row['最高價'],row['最低價'],row['收盤價'],change,clean(row.get('註記',''))]])
        parsed=parse_month(mini)['rows'][0]
        if symbol in result: raise ValueError('每日行情重複代號：'+symbol)
        result[symbol]=parsed
    return result


class MarketClient(TwseClient):
    def universe(self):
        companies=self.fetch('listed-companies','https://openapi.twse.com.tw/v1/opendata/t187ap03_L',3600)
        etfs=self.fetch('equity-etfs','https://www.twse.com.tw/zh/ETFortune/ajaxProductsResult?assetType=Stock&rewardType=Vanilla',3600)
        return listed_universe(companies,etfs)

    def market_bundles(self,universe,calendar):
        bundles={r['symbol']:dict(rows=[],issues=[]) for r in universe}
        sessions=calendar['actual']
        for i,session in enumerate(sessions):
            # Recheck the most recent five sessions for official corrections.
            age=3600 if session in sessions[-5:] else None
            payload=self.fetch('all-'+session,'https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date='+session.replace('-','')+'&type=ALLBUT0999',age,
                               validate=lambda value:parse_market_day(value,session))
            rows=parse_market_day(payload,session)
            for symbol,bundle in bundles.items():
                if symbol in rows: bundle['rows'].append(rows[symbol])
            self.progress('全市場 '+str(i+1)+'/'+str(len(sessions)),session)
        return bundles
