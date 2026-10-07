"""Version-frozen local shadow experiment definitions."""
import hashlib
import random
from datetime import datetime
from statistics import mean
from .data import json_text, now
from .official_store import OfficialStore, instant
from .data import TAIPEI

DEFINITION = dict(version='official-shadow-v1',policy_version='trade-policy-v1',kind='stock',
    top=10,weights=dict(baseline=.7,institution=.2,revenue=.1),window=5,revenue_max_months=3,
    warmup=30,purge=10,test=10,block=10,minimum_test_days=30,bootstrap=2000,seed=20261008,
    selection='same eligible original candidate cohort; deterministic percentile ranks',
    fitting='none; weights fixed before collection; test dates never used for selection')
DEFINITION_HASH=hashlib.sha256(json_text(DEFINITION).encode()).hexdigest()


def freeze_definition(store):
    key='shadow_definition:'+DEFINITION['version']
    existing=store.get(key)
    if existing and (existing['sha256']!=DEFINITION_HASH or existing['definition']!=DEFINITION):
        raise ValueError('實驗定義改變，請建立新版本')
    if not existing:
        store.put(key,dict(definition=DEFINITION,sha256=DEFINITION_HASH,frozen_at=now().isoformat()))


def percentile(values):
    """Equal values receive equal midpoint percentiles; larger is better."""
    ordered=sorted(values)
    if len(values)==1: return {values[0]:1.0}
    return {value:(ordered.index(value)+len(ordered)-1-ordered[::-1].index(value))/2/(len(ordered)-1)
            for value in set(values)}


def select_cohort(rows):
    eligible=[r for r in rows if r['features'].get('eligible')]
    if not eligible: return [],[]
    base=percentile([-r['rank'] for r in eligible])
    inst=percentile([r['features']['institution_ratio_5'] for r in eligible])
    revenue=percentile([r['features']['revenue_yoy_pct'] for r in eligible])
    weighted=[dict(r,shadow_score=.7*base[-r['rank']]+.2*inst[r['features']['institution_ratio_5']]
        +.1*revenue[r['features']['revenue_yoy_pct']]) for r in eligible]
    baseline=sorted(weighted,key=lambda r:(r['rank'],r['symbol']))[:DEFINITION['top']]
    shadow=sorted(weighted,key=lambda r:(-r['shadow_score'],r['rank'],r['symbol']))[:DEFINITION['top']]
    return baseline,shadow


def signal_inputs(store, snapshot, official=None):
    official=official or OfficialStore(store)
    prices={r['symbol']:r.get('bars',[]) for r in snapshot.get('rows',[])}
    candidates=snapshot.get('two_week',{}).get('scored_universe')
    if candidates is None: return dict(status='missing_universe',rows=[])
    rows=[]
    for rank,row in enumerate(candidates,1):
        if row.get('kind')!='stock': continue
        features=official.features(row['symbol'],snapshot['as_of'],snapshot['created_at'],
            snapshot.get('calendar',{}).get('actual',[]),prices.get(row['symbol'],[]))
        rows.append(dict(symbol=row['symbol'],rank=rank,features=features))
    baseline,shadow=select_cohort(rows)
    return dict(status='saved',snapshot_id=snapshot['id'],signal_date=snapshot['as_of'],
        decision_at=snapshot['created_at'],definition_sha256=DEFINITION_HASH,rows=rows,
        baseline_symbols=[r['symbol'] for r in baseline],shadow_symbols=[r['symbol'] for r in shadow])


def archive_signal(store, snapshot):
    key='shadow_signal:'+DEFINITION_HASH+':'+snapshot['id']
    if store.get(key) is None: store.put(key,signal_inputs(store,snapshot))


def rolling_splits(days):
    days=sorted(set(days)); folds=[]
    start=DEFINITION['warmup']+DEFINITION['purge']
    while start<len(days):
        folds.append(dict(warmup=days[:start-DEFINITION['purge']],
            purge=days[start-DEFINITION['purge']:start],test=days[start:start+DEFINITION['test']]))
        start+=DEFINITION['test']
    return folds


def paired_summary(days):
    values=[r['difference_pct'] for r in days]
    result=dict(valid_test_days=len(values),mean_difference_pct=None,ci95_pct=None,
        block_sessions=DEFINITION['block'],minimum_test_days=DEFINITION['minimum_test_days'],
        conclusion='樣本不足，尚不能判斷新規則是否改善預測。')
    if len(values)<DEFINITION['minimum_test_days']: return result
    rng=random.Random(DEFINITION['seed']); n=len(values); block=DEFINITION['block']; samples=[]
    for _ in range(DEFINITION['bootstrap']):
        sample=[]
        while len(sample)<n:
            start=rng.randrange(n-block+1)
            sample.extend(values[start:start+block])
        samples.append(mean(sample[:n]))
    samples.sort(); ci=[samples[int(.025*len(samples))],samples[int(.975*len(samples))]]
    result.update(mean_difference_pct=mean(values),ci95_pct=ci,
        conclusion='樣本外差值区間高於零，仍需後續獨立觀測確認。' if ci[0]>0 else
        '樣本外差值區間低於零，新規則目前較差。' if ci[1]<0 else '差值區間包含零，尚未證明改善。')
    return result


def shadow_report(service, snapshot_id=None, official=None):
    store=service.store; official=official or OfficialStore(store)
    selected=store.snapshot(snapshot_id)
    if snapshot_id and not selected: raise KeyError('找不到快照')
    frozen=store.get('shadow_definition:'+DEFINITION['version'])
    if frozen and (frozen['sha256']!=DEFINITION_HASH or frozen['definition']!=DEFINITION):
        raise ValueError('實驗定義版本不符')
    report=dict(version=DEFINITION['version'],definition=DEFINITION,definition_sha256=DEFINITION_HASH,
        frozen_at=(frozen or {}).get('frozen_at'),policy_version=DEFINITION['policy_version'],
        status='insufficient_data',as_of=selected['as_of'] if selected else None,
        days=[],folds=[],summary=paired_summary([]),exclusions={},
        notes=['固定權重、不擬合參數、不自動取代正式排名。',
            '同日共同合格母體各取前十；所有入選交易成熟且可比較才納入。',
            '十交易日持有造成重疊；採十日區塊，至少三十有效測試日。',
            '暖機不選參數，測試日期不重複；營收、法人需在原快照決策時已取得。'])
    if not selected: return report
    snapshots=[]; seen=set()
    for meta in reversed(store.history(limit=None)):
        if meta['as_of']>selected['as_of'] or (meta['created_at'],meta['id'])>(selected['created_at'],selected['id']): continue
        snap=store.snapshot(meta['id'])
        if snap['as_of'] in seen: continue
        seen.add(snap['as_of']);snapshots.append(snap)
    calendar=sorted({d for s in snapshots for d in s.get('calendar',{}).get('actual',[]) if d<=selected['as_of']})
    # Stage 1 archived simulations retain outcomes and their exact price inputs across compaction.
    tracking={(r['signal_date'],r['symbol']):r for r in service.research_report(selected['id'])['tracking']}
    valid=[]
    for snap in snapshots:
        signal=snap['as_of']; next_days=[d for d in calendar if d>signal]
        record=dict(signal_date=signal,snapshot_id=snap['id'],decision_at=snap['created_at'],
            status='insufficient_features',candidate_count=0,eligible_count=0,baseline_symbols=[],shadow_symbols=[])
        if next_days and instant(snap['created_at'])>=datetime.fromisoformat(next_days[0]).replace(hour=9,tzinfo=TAIPEI):
            record['status']='late_entry'
        elif not frozen or instant(snap['created_at'])<instant(frozen['frozen_at']):
            record['status']='before_definition'
        else:
            inputs=store.get('shadow_signal:'+DEFINITION_HASH+':'+snap['id']) or signal_inputs(store,snap,official)
            record.update(candidate_count=len(inputs.get('rows',[])),
                eligible_count=sum(r['features'].get('eligible',False) for r in inputs.get('rows',[])),
                baseline_symbols=inputs.get('baseline_symbols',[]),shadow_symbols=inputs.get('shadow_symbols',[]))
            if inputs['status']=='missing_universe': record['status']='missing_universe'
            elif record['eligible_count']:
                symbols=set(record['baseline_symbols']+record['shadow_symbols'])
                trades=[tracking.get((signal,symbol)) for symbol in symbols]
                if len(next_days)<10 or any(r and r['status']=='pending' for r in trades): record['status']='pending'
                elif any(r is None or r['status']!='evaluated' for r in trades): record['status']='not_comparable'
                else:
                    actions=[r for symbol in symbols for r in official.query('action',symbol,selected['created_at'])
                        if next_days[0]<=r['data_date']<=next_days[9]]
                    if actions:
                        record.update(status='corporate_action',annotations=[dict(symbol=r['symbol'],
                            date=r['data_date'],content_hash=r['content_hash'],available_at=r['available_at']) for r in actions])
                    else:
                        lookup={r['symbol']:r for r in trades}
                        base=mean(lookup[s]['net_return_pct'] for s in record['baseline_symbols'])
                        shadow=mean(lookup[s]['net_return_pct'] for s in record['shadow_symbols'])
                        record.update(status='comparable',baseline_return_pct=base,shadow_return_pct=shadow,
                            difference_pct=shadow-base,definition_sha256=DEFINITION_HASH,
                            feature_provenance=[r for r in inputs['rows'] if r['symbol'] in symbols],
                            outcome_provenance=[dict(symbol=r['symbol'],simulation_evidence=r.get('simulation_evidence')) for r in trades])
                        valid.append(record)
        report['days'].append(record)
        report['exclusions'][record['status']]=report['exclusions'].get(record['status'],0)+1
    # Warmup/purge count prospective definition-era signal dates, never hindsight-filled dates.
    prospective=[r['signal_date'] for r in report['days'] if r['status'] not in ('before_definition','late_entry')]
    folds=rolling_splits(prospective); tests={d for f in folds for d in f['test']}
    report['folds']=folds
    report['summary']=paired_summary([r for r in valid if r['signal_date'] in tests])
    if report['summary']['ci95_pct'] is not None: report['status']='ready'
    report['saved_signal_days']=len(snapshots)
    report['prospective_signal_days']=len(prospective)
    return report
