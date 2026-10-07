"""Append-only context observations and conservative point-in-time features."""
from datetime import datetime, date
import hashlib
import math
from .data import json_text, now
from .official import SOURCES, VERSION
import json


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError('時間必須包含時區')
    return parsed


class OfficialStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS official_observations (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, symbol TEXT NOT NULL,
                data_key TEXT NOT NULL, first_seen_at TEXT NOT NULL, payload TEXT NOT NULL)''')
            conn.execute('CREATE INDEX IF NOT EXISTS official_lookup ON official_observations(source,symbol,data_key)')

    def ingest(self, source, rows, evidence):
        if source not in SOURCES: raise ValueError('未知來源')
        acquired = instant(evidence['fetched_at'])
        count = 0
        with self.store.connect() as conn:
            for row in rows:
                digest = hashlib.sha256(json_text(row).encode()).hexdigest()
                previous = conn.execute('SELECT payload FROM official_observations WHERE source=? AND symbol=? AND data_key=? ORDER BY id DESC LIMIT 1',
                    (source, row['symbol'], row['key'])).fetchone()
                if previous:
                    previous = json.loads(previous[0])
                    if previous['content_hash'] == digest or acquired <= instant(previous['first_seen_at']): continue
                published = instant(row['published_at']) if row.get('published_at') else acquired
                record = dict(row, source=source, first_seen_at=acquired.isoformat(),
                    fetched_at=evidence['fetched_at'], available_at=max(acquired, published).isoformat(),
                    content_hash=digest, parser_version=VERSION, evidence=evidence)
                conn.execute('INSERT INTO official_observations(source,symbol,data_key,first_seen_at,payload) VALUES (?,?,?,?,?)',
                    (source,row['symbol'],row['key'],record['first_seen_at'],json_text(record)))
                count += 1
        return count

    def query(self, source=None, symbol=None, cutoff=None, as_of=None, symbols=None):
        limit_time = instant(cutoff) if cutoff else None
        if as_of: date.fromisoformat(as_of)
        clauses, args = [], []
        for column, value in (('source',source),('symbol',symbol)):
            if value is not None: clauses.append(column+'=?'); args.append(value)
        if symbols is not None:
            if not symbols: return []
            clauses.append('symbol IN ('+','.join('?' for _ in symbols)+')');args.extend(sorted(symbols))
        sql = 'SELECT payload FROM official_observations'
        if clauses: sql += ' WHERE '+' AND '.join(clauses)
        sql += ' ORDER BY id'
        latest = {}
        with self.store.connect() as conn:
            for (raw,) in conn.execute(sql,args):
                row = json.loads(raw)
                if limit_time and instant(row['available_at']) > limit_time: continue
                if as_of and row['data_date'] > as_of: continue
                latest[(row['source'],row['symbol'],row['key'])] = row
        return sorted(latest.values(),key=lambda r:(r['data_date'],r['available_at']),reverse=True)

    def health(self): return self.store.get('official_health', {})

    def summary(self, symbols=None):
        health = self.health()
        # Count latest observations, never join source lists into a made-up universe.
        rows = self.query(symbols=symbols)
        result = {}
        for source in SOURCES:
            subset = [r for r in rows if r['source'] == source]
            result[source] = dict(health.get(source, {}), covered_symbols=len({r['symbol'] for r in subset}),
                latest_data_date=max((r['data_date'] for r in subset),default=None),
                observations=len(subset), status=health.get(source,{}).get('status','not_collected'))
            if symbols is not None: result[source]['universe_symbols']=len(symbols)
        return dict(version=VERSION,sources=result,notes=[
            '首次取得時間為保守可用時刻；今日補抓舊資料不納入過去訊號。',
            '法人單位為股；信用交易為交易單位；營收金額單位尚未核對，僅顯示官方增減率。',
            '除權息只是部分公司行動線索，未涵蓋拆併股、減資等全部事件。'])

    def detail(self, symbol, kind, cutoff=None, as_of=None):
        result = {}
        health = self.health()
        for source in SOURCES:
            if source == 'revenue' and kind != 'stock':
                result[source] = dict(status='not_applicable',rows=[]); continue
            # Future announced actions are useful annotations, not features.
            rows = self.query(source,symbol,cutoff,None if source=='action' else as_of)
            status = 'available' if rows else 'missing'
            if rows and health.get(source,{}).get('status') == 'error': status = 'stale'
            result[source] = dict(status=status,rows=rows[:10],error=health.get(source,{}).get('error'))
        return dict(symbol=symbol,cutoff=cutoff,as_of=as_of,sources=result)

    def features(self, symbol, as_of, cutoff, calendar, bars):
        days = sorted({d for d in calendar if d <= as_of})[-5:]
        institution = {r['data_date']:r for r in self.query('institution',symbol,cutoff,as_of)}
        volumes = {r['date']:r.get('volume') for r in bars if isinstance(r,dict) and 'date' in r}
        complete = len(days)==5 and all(d in institution and institution[d]['unit']=='shares'
            and isinstance(volumes.get(d),(int,float)) and math.isfinite(volumes[d]) and volumes[d]>=0 for d in days)
        total = sum(institution[d]['values']['total_net'] for d in days) if complete else None
        denominator = sum(volumes[d] for d in days) if complete else None
        ratio = total / denominator if denominator and total is not None else None
        streak = 0
        if complete:
            for d in reversed(days):
                if institution[d]['values']['total_net'] <= 0: break
                streak += 1
        revenues = self.query('revenue',symbol,cutoff,as_of)
        revenue = revenues[0] if revenues else None
        months_old = None
        if revenue:
            current=date.fromisoformat(as_of); period=date.fromisoformat(revenue['period']+'-01')
            months_old=(current.year-period.year)*12+current.month-period.month
        yoy = revenue['values'].get('yoy_pct') if revenue and 0<=months_old<=3 else None
        refs = [dict(source=r['source'],data_key=r['key'],content_hash=r['content_hash'],
            first_seen_at=r['first_seen_at'],available_at=r['available_at'],evidence=r['evidence'])
            for r in ([institution[d] for d in days if d in institution]+([revenue] if revenue else []))]
        return dict(institution_net_5=total,institution_ratio_5=ratio,buy_streak=streak if complete else None,
            revenue_yoy_pct=yoy,eligible=ratio is not None and yoy is not None,
            window=days,provenance=refs)
