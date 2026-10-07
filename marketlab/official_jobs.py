"""Explicit local collection; source failures are independent and GETs never fetch."""
import copy
import threading
from .data import TwseClient, now
from .official import SOURCES, parse_source
from .official_store import OfficialStore
from .service import update_lock

URLS = dict(revenue='https://openapi.twse.com.tw/v1/opendata/t187ap05_L',
    announcement='https://openapi.twse.com.tw/v1/opendata/t187ap04_L',
    action='https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL')


class OfficialJobs:
    def __init__(self, service, client_factory=TwseClient):
        self.service=service; self.official=OfficialStore(service.store)
        self.client_factory=client_factory; self._guard=threading.RLock(); self._thread=None
        if self.state().get('running'):
            try:
                with update_lock(service.root):
                    job=self.state()
                    if job.get('running'):
                        job.update(running=False,status='interrupted',error='前次資料更新中斷，保留已取得觀測，可重新更新。')
                        service.store.put('official_job',job)
            except RuntimeError: pass

    def state(self):
        return self.service.store.get('official_job',dict(running=False,status='idle',sources={}))

    def start(self):
        with self._guard:
            if self.state().get('running'): return self.state()
            snapshot=self.service.store.snapshot()
            if not snapshot: raise ValueError('請先更新本機行情，再收集研究資料')
            lock=update_lock(self.service.root)
            try: lock.__enter__()
            except RuntimeError as exc: raise ValueError(str(exc)) from exc
            try:
                # Freeze the definition before collecting any experiment data.
                from .shadow import freeze_definition
                freeze_definition(self.service.store)
                job=dict(running=True,status='running',started_at=now().isoformat(),sources={},
                    as_of=snapshot['as_of'],error=None)
                self.service.store.put('official_job',job)
                self._thread=threading.Thread(target=self._run,args=(snapshot,lock),daemon=True)
                self._thread.start()
                return self.state()
            except Exception:
                lock.__exit__(None,None,None); raise

    def _run(self, snapshot, lock):
        job=self.state(); health=self.official.health()
        try:
            client=self.client_factory(self.service.root)
            dates=sorted({d for d in snapshot.get('calendar',{}).get('actual',[]) if d<=snapshot['as_of']})[-5:]
            for source in SOURCES:
                failures=[]; new_count=0; batches=0
                for dt in (dates if source in ('institution','margin') else [None]):
                    compact=dt.replace('-','') if dt else None
                    url=(f'https://www.twse.com.tw/rwd/zh/fund/T86?date={compact}&selectType=ALL&response=json'
                        if source=='institution' else
                        f'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={compact}&selectType=ALL&response=json'
                        if source=='margin' else URLS[source])
                    key='official-'+source+('-'+compact if compact else '')
                    try:
                        payload=client.fetch(key,url,max_age=3600,
                            validate=lambda p,s=source,d=dt: parse_source(s,p,d))
                        rows=parse_source(source,payload,dt)
                        new_count+=self.official.ingest(source,rows,copy.deepcopy(client.evidence[-1]))
                        batches+=1
                    except Exception as exc:
                        failures.append(str(exc)[:300])
                previous=health.get(source,{})
                status=dict(status='error' if failures else 'success',checked_at=now().isoformat(),
                    successful_batches=batches,expected_batches=len(dates) if source in ('institution','margin') else 1,
                    new_observations=new_count,error='；'.join(failures) if failures else None,
                    last_success_at=previous.get('last_success_at'))
                if batches: status['last_success_at']=now().isoformat()
                health[source]=status; job['sources'][source]=status
                self.service.store.put('official_health',health)
                self.service.store.put('official_job',job)
            success=sum(s['status']=='success' for s in job['sources'].values())
            job['status']='success' if success==len(SOURCES) else 'partial' if any(s['successful_batches'] for s in job['sources'].values()) else 'failed'
        except Exception as exc:
            job.update(status='failed',error=str(exc)[:300])
        finally:
            job.update(running=False,finished_at=now().isoformat())
            try: self.service.store.put('official_job',job)
            finally: lock.__exit__(None,None,None)

    def report(self, symbol=None, snapshot_id=None):
        snap=self.service.store.snapshot(snapshot_id)
        if snapshot_id and not snap: raise KeyError('找不到快照')
        report=dict(summary=self.official.summary(),job=self.state(),snapshot_id=snap['id'] if snap else None,
            as_of=snap['as_of'] if snap else None)
        if symbol:
            rows={r['symbol']:r for r in (snap or {}).get('rows',[])}
            if symbol not in rows: raise KeyError('快照沒有此代號')
            kind=rows[symbol]['kind']
            report['detail']=self.official.detail(symbol,kind,as_of=snap['as_of'])
            report['signal_detail']=self.official.detail(symbol,kind,cutoff=snap['created_at'],as_of=snap['as_of'])
            report['signal_cutoff']=snap['created_at']
            report['features']=self.official.features(symbol,snap['as_of'],snap['created_at'],
                snap.get('calendar',{}).get('actual',[]),rows[symbol].get('bars',[])) if kind=='stock' else None
        return report
