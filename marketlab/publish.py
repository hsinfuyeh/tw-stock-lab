"""Build a static, credential-free Pages artifact from a committed snapshot."""
import copy
import hashlib
from pathlib import Path
import re
import shutil
from .analytics import HORIZONS,target_date,features_at
from .data import atomic_json,now
from .explore import explore_catalog


def export_site(service,output):
    latest=service.store.snapshot()
    if not latest or not latest.get('rows'): raise ValueError('沒有完整研究快照，不發布空站')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for source in (Path(__file__).resolve().parents[1]/'web').iterdir():
        if source.is_file(): shutil.copyfile(source,output/source.name)
    app=(output/'app.js').read_text(encoding='utf-8')
    for module in ('social.js','cloud.js'):
        version=hashlib.sha256((output/module).read_bytes()).hexdigest()[:12]
        app=app.replace(f"import('./{module}')",f"import('./{module}?v={version}')")
    (output/'app.js').write_text(app,encoding='utf-8')
    html=(output/'index.html').read_text(encoding='utf-8')
    html=html.replace('<head>','<head>\n  <meta name="deployment-mode" content="static">',1)
    for asset in ('style.css','app.js'):
        version=hashlib.sha256((output/asset).read_bytes()).hexdigest()[:12]
        html=html.replace(f'./{asset}',f'./{asset}?v={version}',1)
    (output/'index.html').write_text(html,encoding='utf-8')
    (output/'.nojekyll').write_text('',encoding='utf-8')
    histories=service.store.history(limit=3); summaries={}
    for meta in histories:
        snap=service.store.snapshot(meta['id'])
        identifier=snap['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',identifier): raise ValueError('Invalid snapshot path')
        summary={k:copy.deepcopy(v) for k,v in snap.items() if k not in ('rows','evidence','calendar')}
        summary['rows']=[]
        for row in snap['rows']:
            if not re.fullmatch(r'[A-Za-z0-9]+',row['symbol']): raise ValueError('Invalid security path')
            detail_url=f'data/details/{identifier}/{row["symbol"]}.json'
            atomic_json(output/detail_url,row)
            brief={k:v for k,v in row.items() if k not in ('bars','signals','validation','features','horizons')}
            brief['horizons']={h:{k:v for k,v in values.items() if k!='samples'} for h,values in row['horizons'].items()}
            brief['detail_url']=detail_url
            summary['rows'].append(brief)
        atomic_json(output/f'data/snapshots/{identifier}.json',summary)
        for h in HORIZONS:
            for metric in ('expected_return','p_positive','p_recovery','score'):
                path=output/f'data/csv/{identifier}-{h}-{metric}.csv';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(service.export_csv(h,metric,identifier,snapshot=snap),encoding='utf-8',newline='')
        summaries[identifier]=summary
    state=dict(latest=summaries[latest['id']],history=histories,settings=latest.get('settings',{}),universe=[],
        two_week_outcomes=[row for row in service.store.get('two_week_outcomes',[])
                           if row['snapshot_id'] in summaries],
        job=dict(running=False,phase='已完成',message='盤後分析報告已發布',finished_at=latest['created_at'],progress=len(latest['rows']),total=len(latest['rows'])),
        checked_at=service.store.get('checked_at',now().isoformat()),schedule='每日臺灣時間 19:15 執行資料更新，22:47 補檢；分析完成後發布。GitHub 排程可能延遲。',
        next_session=target_date(latest['as_of'],1,latest.get('calendar',{})))
    atomic_json(output/'data/state.json',state)
    report=latest.get('two_week') or {}
    home_report={key:copy.deepcopy(report[key]) for key in ('status','recommendations','research_candidates') if key in report}
    rows_by_symbol={row['symbol']:row for row in latest['rows']}
    for listing in ('recommendations','research_candidates'):
        for candidate in home_report.get(listing,[]):
            row=rows_by_symbol.get(candidate['symbol'])
            bars=row.get('bars') if row else None
            if not bars or len(bars)<21 or bars[-1].get('date')!=latest['as_of']: continue
            feature=row.get('features') or features_at(bars,len(bars)-1,latest.get('calendar'))
            if not feature: continue
            candidate.setdefault('close',bars[-1]['close'])
            candidate.setdefault('momentum5_pct',round(feature['momentum5'],2))
            candidate.setdefault('momentum20_pct',round(feature['momentum20'],2))
            candidate.setdefault('relative_volume',round(feature['volume_ratio'],2))
            candidate.setdefault('trend',[dict(date=bar['date'],close=bar['close']) for bar in bars[-20:]])
    home=dict(latest=dict(id=latest['id'],as_of=latest['as_of'],created_at=latest['created_at'],
        coverage=latest.get('coverage'),
        two_week=home_report),
        history=histories[:1],checked_at=state['checked_at'],next_session=state['next_session'],
        two_week_outcomes=[row for row in state['two_week_outcomes'] if row['snapshot_id']==latest['id']])
    atomic_json(output/'data/home.json',home)
    atomic_json(output/'data/explore.json',explore_catalog(latest))
    from .social import empty_report
    atomic_json(output/'data/social.json',service.store.get('social_report') or empty_report())
    return dict(as_of=latest['as_of'],count=len(latest['rows']),files=sum(p.is_file() for p in output.rglob('*')))
