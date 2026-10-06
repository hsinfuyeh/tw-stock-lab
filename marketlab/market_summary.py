"""Snapshot-only breadth, with independent metric denominators."""
from collections import defaultdict
from statistics import mean, median
import math
from .analytics import adjusted, complete_window

VERSION='market-summary-v1'
CLASSIFICATION_VERSION='official-industry-v1'

def _turnover(row):
    v=row.get('turnover')
    return v if isinstance(v,(int,float)) and math.isfinite(v) and v>=0 else None

def build_market_summary(snapshot):
    as_of=snapshot.get('as_of');calendar=snapshot.get('calendar',{})
    actual=sorted(set(d for d in calendar.get('actual',[]) if d<=as_of))
    stocks=[r for r in snapshot.get('rows',[]) if r.get('kind')=='stock']
    groups=defaultdict(list);metrics=[]
    candidates={r['symbol'] for r in snapshot.get('two_week',{}).get('research_candidates',[])}
    for security in stocks:
        lookup={r['date']:r for r in security.get('bars',[]) if r['date']<=as_of}
        current=lookup.get(as_of)
        item=dict(symbol=security['symbol'],industry=security.get('industry') or '未記錄',
                  daily=None,ma20=None,momentum20=None,turnover=None,previous_turnover=None,
                  candidate=security['symbol'] in candidates)
        if current and current.get('valid',True):
            item['turnover']=_turnover(current)
            def window(count):
                dates=actual[-count:]
                if len(dates)!=count or any(d not in lookup for d in dates): return None
                bars=[lookup[d] for d in dates]
                return bars if complete_window(bars,calendar) and not any(adjusted(r) for r in bars[1:]) else None
            pair=window(2)
            if pair and pair[0]['close']>0: item['daily']=(pair[-1]['close']/pair[0]['close']-1)*100
            twenty=window(20)
            if twenty and not adjusted(twenty[0]): item['ma20']=current['close']>mean(r['close'] for r in twenty)
            history=window(21)
            if history:
                item['momentum20']=(current['close']/history[0]['close']-1)*100
                turnovers=[_turnover(r) for r in history[:-1]]
                if all(v is not None for v in turnovers) and mean(turnovers)>0 and item['turnover'] is not None:
                    item['previous_turnover']=mean(turnovers)
        metrics.append(item);groups[item['industry']].append(item)
    sets={name:[r for r in metrics if r[key] is not None] for name,key in
          [('daily_return','daily'),('ma20','ma20'),('turnover','turnover'),('momentum20','momentum20'),('turnover_ratio_20','previous_turnover')]}
    coverage={name:dict(eligible=len(group),excluded=len(stocks)-len(group),total=len(stocks)) for name,group in sets.items()}
    total_turnover=sum(r['turnover'] for r in sets['turnover'])
    daily=sets['daily_return'];cohort=sets['turnover_ratio_20']
    market=dict(advancers=sum(r['daily']>1e-9 for r in daily),decliners=sum(r['daily']< -1e-9 for r in daily),
                unchanged=sum(abs(r['daily'])<=1e-9 for r in daily),
                equal_weight_return_pct=mean(r['daily'] for r in daily) if daily else None,
                above_ma20_ratio=mean(r['ma20'] for r in sets['ma20']) if sets['ma20'] else None,
                turnover=total_turnover if sets['turnover'] else None,
                turnover_ratio_20=sum(r['turnover'] for r in cohort)/sum(r['previous_turnover'] for r in cohort) if cohort else None)
    industries=[]
    for industry,items in sorted(groups.items()):
        valid=[r for r in items if r['daily'] is not None];momentum=[r['momentum20'] for r in items if r['momentum20'] is not None]
        turnover=[r['turnover'] for r in items if r['turnover'] is not None]
        industries.append(dict(industry=industry,total=len(items),valid_count=len(valid),small_sample=len(valid)<5,
            median_return_pct=median(r['daily'] for r in valid) if valid else None,
            advancing_ratio=mean(r['daily']>1e-9 for r in valid) if valid else None,
            turnover_share=sum(turnover)/total_turnover if turnover and total_turnover>0 else None,
            median_20_return_pct=median(momentum) if momentum else None,momentum20_count=len(momentum),
            turnover_count=len(turnover),candidate_count=sum(r['candidate'] for r in items)))
    return dict(as_of=as_of,version=VERSION,coverage=coverage,market=market,industries=industries,
                classification_missing=sum(r['industry']=='未記錄' for r in metrics))
