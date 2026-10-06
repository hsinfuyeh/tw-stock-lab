"""Descriptive signal experiments, not a funded portfolio or fill probability."""
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean, median
from .analytics import adjusted, complete_window, net_return
from .two_week import target_price, _tick

POLICY_VERSION = 'trade-policy-v1'
SESSIONS = 10


def simulate_trade(rows, signal_date, kind, calendar, as_of):
    result=dict(policy_version=POLICY_VERSION,status='not_comparable',reason='缺少實際交易日或訊號日',
                net_return_pct=None,target_filled=False,touched=False,elapsed_sessions=0,
                entry_date=None,entry_price=None,exit_date=None,exit_price=None,
                target_price=None,adverse_before_exit_pct=None)
    actual=sorted(set(d for d in (calendar or {}).get('actual',[]) if d<=as_of))
    if signal_date not in actual: return result
    expected=actual[actual.index(signal_date)+1:][:SESSIONS]
    result['elapsed_sessions']=len(expected)
    if not expected:
        result.update(status='pending',reason='等待下一個實際交易日');return result
    result['entry_date']=expected[0]
    lookup={r['date']:r for r in rows if r['date']<=as_of}
    if any(d not in lookup for d in expected):
        result['reason']='持有窗口缺實際交易日行情';return result
    window=[lookup[d] for d in expected]
    if not complete_window(window,calendar) or any(adjusted(r) for r in window):
        result['reason']='價格無效或跨已辨識的公司行動';return result
    entry=window[0]
    if entry['high']==entry['low'] or entry['open']<=0:
        result.update(status='not_filled',reason='進場日鎖價，不能假設買入');return result
    price=entry['open'];target=target_price(price,kind)
    result.update(entry_price=price,target_price=target,touched=any(r['high']>=target for r in window))
    if len(expected)<SESSIONS:
        result.update(status='pending',reason='尚未滿十個實際交易日');return result
    exit_row=window[-1];exit_price=exit_row['close'];reason='expiry_close'
    tick=float(_tick(Decimal(str(target)),kind))
    for i,row in enumerate(window):
        if i and row['open']>=target:
            exit_row=row;exit_price=row['open'];reason='gap_open';break
        if row['high']>=target+tick-1e-10:
            exit_row=row;exit_price=target;reason='conservative_target';break
    before=[r for r in window if r['date']<exit_row['date']]
    result.update(status='evaluated',reason=reason,exit_date=exit_row['date'],exit_price=exit_price,
                  target_filled=reason!='expiry_close',net_return_pct=net_return(price,exit_price,{'kind':kind}),
                  adverse_before_exit_pct=min((r['low']/price-1)*100 for r in before) if before else None)
    return result


def _summary(records):
    counts=Counter(r['status'] for r in records)
    days=defaultdict(list)
    for r in records:
        if r['status']=='evaluated' and r.get('net_return_pct') is not None:
            days[r['signal_date']].append(r)
    daily={d:mean(r['net_return_pct'] for r in group) for d,group in days.items()}
    weighted=[(r['net_return_pct'],1/len(group)) for group in days.values() for r in group]
    gains=[(v,w) for v,w in weighted if v>0];losses=[(v,w) for v,w in weighted if v<0]
    gain_sum=sum(v*w for v,w in gains);loss_sum=-sum(v*w for v,w in losses)
    contributions=sorted((v*w for v,w in gains),reverse=True)
    return dict(counts={k:counts[k] for k in ('evaluated','pending','not_filled','not_comparable')},
        mature_signal_dates=len({r['signal_date'] for r in records if r.get('elapsed_sessions',10)>=10}),
        comparable_signal_dates=len(days),daily_mean=daily,
        mean_net_return_pct=mean(daily.values()) if daily else None,
        median_net_return_pct=median(median(r['net_return_pct'] for r in group) for group in days.values()) if days else None,
        target_fill_rate=mean(mean(bool(r.get('target_filled')) for r in group) for group in days.values()) if days else None,
        average_gain_pct=gain_sum/sum(w for _,w in gains) if gains else None,
        average_loss_pct=-loss_sum/sum(w for _,w in losses) if losses else None,
        profit_factor=gain_sum/loss_sum if losses else None,
        top5_gain_share=sum(contributions[:5])/gain_sum if gain_sum else None)


def summarize_performance(records):
    compatible=[r for r in records if r.get('policy_version',POLICY_VERSION)==POLICY_VERSION]
    result={}
    for name in ('stock','passive_etf','active_etf'):
        pool=[r for r in compatible if ('stock' if r['kind']=='stock' else 'active_etf' if r.get('etf_style')=='active' else 'passive_etf')==name]
        top=_summary([r for r in pool if r.get('rank') is not None and 1<=r['rank']<=10])
        baseline=_summary(pool)
        paired=sorted(set(top['daily_mean']) & set(baseline['daily_mean']))
        result[name]=dict(top10=top,baseline=baseline,paired_dates=len(paired),
                         paired_difference_pct=mean(top['daily_mean'][d]-baseline['daily_mean'][d] for d in paired) if paired else None)
    return result
