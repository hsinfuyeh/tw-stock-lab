"""Descriptive institutional rankings from saved official observations only."""
import math
from .analytics import complete_window, adjusted
from .official import T86_FIELDS

GROUPS=('foreign','trust','dealer')


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def total(values):
    return sum(values) if values and all(finite(v) for v in values) else None


def measures(observation,group):
    if not observation or observation.get('unit')!='shares': return dict(buy=None,sell=None,net=None)
    values=observation['values']; fields=values.get('official_fields',{})
    if group=='foreign':
        buy=fields.get(T86_FIELDS[2]); sell=fields.get(T86_FIELDS[3]); net=values.get('foreign_net')
    elif group=='trust':
        buy=fields.get(T86_FIELDS[8]); sell=fields.get(T86_FIELDS[9]); net=values.get('trust_net')
    else:
        buy=total([fields.get(T86_FIELDS[12]),fields.get(T86_FIELDS[15])])
        sell=total([fields.get(T86_FIELDS[13]),fields.get(T86_FIELDS[16])]); net=values.get('dealer_net')
    return dict(buy=buy if finite(buy) and buy>=0 else None,
        sell=sell if finite(sell) and sell>=0 else None,net=net if finite(net) else None)


def institution_rankings(store,official,snapshot_id=None,sessions=1):
    if type(sessions) is not int or sessions not in (1,5): raise ValueError('法人排行期間只接受 1 或 5 個交易日')
    snapshot=store.snapshot(snapshot_id)
    if snapshot_id and not snapshot: raise KeyError('找不到快照')
    health=official.health().get('institution',{})
    report=dict(version='institution-rankings-v1',snapshot_id=(snapshot or {}).get('id'),
        as_of=(snapshot or {}).get('as_of'),sessions=sessions,unit='shares',retrospective=True,
        status='insufficient_data',health=health,dates=[],rows=[],
        coverage=dict(universe_symbols=0,complete_symbols=0),notes=[
            '回顧排行使用目前保存的官方版本，不代表原訊號當時已知；不加入正式評分。',
            '外資指外陸資（不含外資自營商）；外資自營商不重複併入。',
            '自營商買進／賣出合併自行買賣與避險；淨買賣保留官方自營商合計。',
            '原始單位為股；五日只納入完整的五個實際交易日，缺資料不補零。'])
    if not snapshot: return report
    as_of=snapshot['as_of']
    securities=snapshot.get('rows',[])
    universe={r['symbol'] for r in securities}
    days=sorted({d for d in snapshot.get('calendar',{}).get('actual',[]) if d<=as_of})[-sessions:]
    # Legacy snapshots can still supply a single explicit as_of date.
    if sessions==1: days=[as_of]
    complete_window_dates=len(days)==sessions and days[-1]==as_of
    report['dates']=days; report['coverage']['universe_symbols']=len(universe)
    observations=official.query('institution',as_of=as_of,symbols=universe)
    lookup={(r['symbol'],r['data_date']):r for r in observations if r['data_date'] in days}
    for security in securities:
        symbol=security['symbol']; window=[lookup.get((symbol,d)) for d in days]
        groups={}
        for group in GROUPS:
            daily=[measures(r,group) for r in window]
            groups[group]={metric:total([r[metric] for r in daily]) if complete_window_dates else None
                for metric in ('buy','sell','net')}
        bars=[b for b in security.get('bars',[]) if isinstance(b,dict) and b.get('date','')<=as_of]
        current=bars[-1] if bars else {}; close=None; change=None
        if current.get('date')==as_of and current.get('valid',True) and finite(current.get('close')):
            close=current['close']
            if len(bars)>1 and complete_window(bars[-2:],snapshot.get('calendar')) and not adjusted(current):
                previous=bars[-2].get('close')
                if finite(previous) and previous>0: change=(close/previous-1)*100
        evidence=[{k:r.get(k) for k in ('data_date','first_seen_at','available_at','content_hash','evidence')}
            for r in window if r]
        row=dict(symbol=symbol,name=security.get('name',symbol),kind=security['kind'],
            currency=security.get('currency','TWD'),close=close,change_pct=change,
            price_date=current.get('date'),groups=groups,observed_sessions=sum(r is not None for r in window),evidence=evidence)
        report['rows'].append(row)
        if all(finite(v) for g in groups.values() for v in g.values()): report['coverage']['complete_symbols']+=1
    available=any(finite(v) for row in report['rows'] for g in row['groups'].values() for v in g.values())
    if complete_window_dates and available:
        report['status']='stale' if health.get('status')=='error' else (
            'ready' if report['coverage']['complete_symbols']==len(universe) else 'partial')
    return report
