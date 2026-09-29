"""Independent local social collection jobs, with one active run per server."""
import copy
import threading
from uuid import uuid4
from .data import now


class SocialJobs:
    def __init__(self,service,runner=None):
        self.service=service
        if runner is None:
            from social_update import update_social
            runner=update_social
        self.runner=runner
        self._guard=threading.RLock(); self._thread=None
        self._job=dict(running=False,status='idle',sources={})

    def state(self):
        with self._guard: return copy.deepcopy(self._job)

    def start(self,window):
        if window not in ('24h','7d'): raise ValueError('統計期間只接受 24h 或 7d')
        with self._guard:
            if self._job['running']: return self.state()
            self._job=dict(id=str(uuid4()),running=True,status='running',window=window,
                started_at=now().isoformat(),finished_at=None,error=None,
                sources={key:dict(status='queued') for key in ('ptt','dcard','threads')})
            self._thread=threading.Thread(target=self._run,args=(window,),daemon=True)
            self._thread.start()
            return self.state()

    def _progress(self,source,status):
        with self._guard: self._job['sources'][source]=copy.deepcopy(status)

    def _run(self,window):
        try:
            report=self.runner(self.service,window=window,local_public=True,progress=self._progress)
            sources=report['sources']
            usable=any(s.get('status') in ('success','partial') for s in sources.values())
            status='success' if all(s.get('status')=='success' for s in sources.values()) else 'partial' if usable else 'failed'
            with self._guard: self._job.update(status=status,sources=copy.deepcopy(sources))
        except Exception:
            # Collector/provider errors never expose secrets or response bodies to the UI.
            with self._guard: self._job.update(status='failed',error='社群收集未完成，保留上一份結果；請確認股票資料與來源狀態。')
        finally:
            with self._guard: self._job.update(running=False,finished_at=now().isoformat())
