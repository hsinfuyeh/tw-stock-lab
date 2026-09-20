"""Build a static, credential-free Pages artifact from a committed snapshot."""
import copy
from pathlib import Path
import re
import shutil
from .analytics import HORIZONS,target_date
from .data import atomic_json,now


def export_site(service,output):
    latest=service.store.snapshot()
    if not latest or not latest.get('rows'): raise ValueError('沒有完整研究快照，不發布空站')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for source in (Path(__file__).resolve().parents[1]/'web').iterdir():
        if source.is_file(): shutil.copyfile(source,output/source.name)
    html=(output/'index.html').read_text(encoding='utf-8')
    html=html.replace('<head>','<head>\n  <meta name="deployment-mode" content="static">',1)
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
                path.write_text(service.export_csv(h,metric,identifier),encoding='utf-8')
        summaries[identifier]=summary
    state=dict(latest=summaries[latest['id']],history=histories,settings=latest.get('settings',{}),universe=[],
        job=dict(running=False,phase='完成',message='雲端盤後研究已發布',finished_at=latest['created_at'],progress=len(latest['rows']),total=len(latest['rows'])),
        checked_at=service.store.get('checked_at',now().isoformat()),schedule='每日台灣時間19:15啟動；完成後發布，GitHub排程可能延遲',
        next_session=target_date(latest['as_of'],1,latest.get('calendar',{})))
    atomic_json(output/'data/state.json',state)
    return dict(as_of=latest['as_of'],count=len(latest['rows']),files=sum(p.is_file() for p in output.rglob('*')))
