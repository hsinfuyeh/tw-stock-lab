"""Application state, settings, and update coordinator."""
import copy
import csv
import hashlib
import io
import math
from pathlib import Path
import re
import threading
from uuid import uuid4
from contextlib import contextmanager
from datetime import date,timedelta
from .analytics import HORIZONS,MODEL_VERSION,ResearchModel,event_outcome
from .data import Store,TwseClient,MarketClient,atomic_json,json_text,month_list,now
from .quality import PIPELINE_VERSION,describe_sources,quality_label
from .two_week import rank_candidates,outcome as two_week_outcome,VERSION as TWO_WEEK_VERSION

DEFAULT_SETTINGS = dict(symbols=["2330","2317","2454","2308","2881","0050","0056","00878"],
                        months=36,min_samples=30,neighbors=60,min_turnover=20000000,min_probability=.55,
                        max_downside=8,fee_rate=.001425,slippage_rate=.0005)

def validate_settings(value):
    if not isinstance(value,dict): raise ValueError("設定必須為 JSON 物件")
    if set(value)-set(DEFAULT_SETTINGS): raise ValueError("包含未知設定欄位")
    merged=copy.deepcopy(DEFAULT_SETTINGS)
    merged.update(value)
    symbols=merged["symbols"]
    if not isinstance(symbols,list) or not 1<=len(symbols)<=100:
        raise ValueError("研究清單需有1至100個代號；第一版採分批研究")
    if any(not isinstance(s,str) or not re.fullmatch(r"(?:[1-9]\d{3}|00\d{2,3})",s) for s in symbols):
        raise ValueError("只接受臺灣上市股票與數字代號原型 ETF；代號需用字串保留開頭0")
    merged["symbols"]=list(dict.fromkeys(symbols))
    ranges=dict(months=(3,120),min_samples=(10,300),neighbors=(10,300),min_turnover=(0,1e12),
                min_probability=(0,1),max_downside=(0,100),fee_rate=(0,.02),slippage_rate=(0,.05))
    for key,(low,high) in ranges.items():
        v=merged[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:
            raise ValueError(f"{key} 必須介於 {low} 與 {high}")
        if key in ("months","min_samples","neighbors"):
            if int(v)!=v: raise ValueError(f"{key} 必須為整數")
            merged[key]=int(v)
    if merged["min_samples"]>merged["neighbors"]: raise ValueError("最少樣本數不能大於近鄰樣本數")
    return merged


@contextmanager
def update_lock(root):
    """OS-owned lock is released even if a process crashes."""
    path=Path(root)/"update.lock"
    handle=path.open("a+b")
    if handle.tell()==0: handle.write(b"0"); handle.flush()
    handle.seek(0)
    import os
    try:
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("另一個更新程序正在執行，請等待完成")
    try: yield
    finally: handle.close()

class ResearchService:
    def __init__(self,root,client_factory=None):
        self.store=Store(root)
        self.root=Path(root)
        self.client_factory=client_factory or TwseClient
        self._thread=None
        self._guard=threading.Lock()
        self.job=self.store.get("job",dict(running=False,phase="idle",progress=0,total=0,message="尚未更新",error=None))
        self._recover_job()

    def _recover_job(self):
        """Only an OS lock owner may clear status left behind by a dead process."""
        if not self.store.get("job",self.job).get("running"): return
        lock=update_lock(self.root)
        try: lock.__enter__()
        except RuntimeError: return
        try:
            self.job=self.store.get("job",self.job)
            if self.job.get("running"):
                self._status(running=False,phase="更新中斷",error="前次更新程序已結束，尚未完成；可重新更新",
                             message="保留上一份完整快照",finished_at=now().isoformat())
        finally: lock.__exit__(None,None,None)

    def settings(self):
        return validate_settings(self.store.get("settings",DEFAULT_SETTINGS))

    def save_settings(self,settings):
        checked=validate_settings(settings)
        self.store.put("settings",checked)
        return checked

    def state(self):
        self._recover_job()
        latest=self.store.snapshot()
        return dict(settings=self.settings(),latest=latest,history=self.store.history(),
                    job=self.store.get("job",self.job),universe=self.store.get("universe",[]),
                    reconciliation=self.store.get("reconciliation",{}))

    def _status(self,**kwargs):
        self.job.update(kwargs)
        self.store.put("job",self.job)

    def start_update(self):
        with self._guard:
            if self._thread and self._thread.is_alive(): return self.job
            lock=update_lock(self.root)
            try: lock.__enter__()
            except RuntimeError:
                return self.store.get("job",self.job)
            try:
                self._status(running=True,phase="queued",progress=0,total=1,message="排入更新",error=None,started_at=now().isoformat(),finished_at=None)
                self._thread=threading.Thread(target=self._background,args=(lock,),daemon=True)
                self._thread.start()
            except Exception:
                lock.__exit__(None,None,None)
                raise
            return self.job

    def _background(self,lock):
        try: self._update_owned()
        except Exception: pass  # persisted with detail; UI polls it
        finally: lock.__exit__(None,None,None)

    def update(self):
        # Lock failure must not overwrite the running process's persisted job.
        with update_lock(self.root):
            return self._update_owned()

    def _update_owned(self):
        self._status(running=True,phase="資料檢查",progress=0,total=1,message="取得 TWSE 清單與大盤交易日",error=None,
                     started_at=now().isoformat(),finished_at=None)
        try:
            snapshot=self._run()
            self._status(running=False,phase="完成",progress=self.job.get("total",1),
                         message=f"研究完成，資料截至 {snapshot['as_of']}",finished_at=now().isoformat())
            return snapshot
        except Exception as exc:
            self._status(running=False,phase="更新失敗",error=str(exc),message="保留上一份完整快照",finished_at=now().isoformat())
            raise

    def _run(self):
        settings=self.settings()
        months=month_list(settings["months"])
        count=0
        total=len(months)*(len(settings["symbols"])+1)+len(settings["symbols"])
        self._status(total=total)
        def progress(symbol,month):
            nonlocal count
            count+=1
            self._status(phase="取得官方行情",progress=count,message=f"{symbol} · {month[:4]}-{month[4:6]}")
        client=self.client_factory(self.root,progress)
        universe=client.universe()
        self.store.put("universe",universe)
        catalog={r["symbol"]:r for r in universe}
        missing=[s for s in settings["symbols"] if s not in catalog]
        if missing: raise ValueError("TWSE 原型股票/ETF清單中找不到："+", ".join(missing))
        calendar=client.calendar(months)
        if not calendar["actual"]: raise ValueError("沒有已完成盤後的大盤交易資料")
        as_of=calendar["actual"][-1]
        count=len(months)
        bundles={}
        for symbol in settings["symbols"]:
            bundle=client.stock(symbol,months)
            rows=[r for r in bundle["rows"] if r["date"]<=as_of]
            if not rows or rows[-1]["date"]!=as_of:
                raise ValueError(f"{symbol} 未取得共同資料日 {as_of}；整批暫不發布，請检查是否停牌或官方資料未完整")
            bundles[symbol]=dict(rows=rows,issues=bundle["issues"])
        signature=hashlib.sha256(json_text(dict(settings=settings,bundles=bundles,calendar=calendar,version=MODEL_VERSION,
                                               pipeline_version=PIPELINE_VERSION)).encode()).hexdigest()
        previous=self.store.snapshot()
        if previous and previous.get("data_signature")==signature:
            audit=self._prepare_audit(client,bundles,calendar)
            atomic_json(self.root/"snapshots"/(previous["id"]+".json"),previous)
            self.store.save_audit(audit)
            return previous
        results=[]
        for symbol in settings["symbols"]:
            count+=1
            self._status(phase="分析與時間前推驗證",progress=count,message=f"{symbol}：六期限、成熟樣本與歷史驗證")
            info=catalog[symbol]
            rows=bundles[symbol]["rows"]
            config=dict(settings,kind=info["kind"])
            model=ResearchModel(rows,config,calendar)
            horizons={str(h):model.estimate(len(rows)-1,h) for h in HORIZONS}
            features=model.features[-1]
            reasons=list(bundles[symbol]["issues"])
            if features is None: reasons.append("最近20日有價格調整、資料缺漏或暖機資料不足")
            result=dict(**info,as_of=as_of,status="研究估計／未校準",reasons=reasons,bars=rows[-60:],
                        signals=[dict(date=rows[i]["date"],labels=f["labels"]) for i,f in enumerate(model.features) if f and i>=len(rows)-60],
                        features=features,horizons=horizons,validation=model.validate(),data_rows=len(rows),
                        first_date=rows[0]["date"])
            if calendar.get("index") and features:
                market=[r for r in calendar["index"] if r["date"]<=as_of and r["close"]]
                if len(market)>20:
                    m20=(market[-1]["close"]/market[-21]["close"]-1)*100
                    result["market_context"]=dict(momentum20=m20,relative_momentum20=features["momentum20"]-m20,
                                                  trend="偏多" if m20>0 else "偏弱",used_in_model=False)
            results.append(result)
        snapshot=dict(id=now().strftime("%Y%m%dT%H%M%S")+"-"+uuid4().hex[:8],as_of=as_of,
                      created_at=now().isoformat(),model_version=MODEL_VERSION,data_signature=signature,
                      methodology="盤後訊號；次一實際交易日開盤模擬進場；1/3/5/7/14/30曆日目標遇休市順延。以同標的已成熟的標準化近鄰樣本估计成本後未還原價格變動；跨不比價、分割或缺漏區間排除。兩側手續費及滑價、股票賣出0.3%／ETF0.1%已計入；不假設當沖優惠、不含個人股利稅。",
                      warnings=["研究清單共 "+str(len(results))+" 檔，非全市場推薦或已驗證投資策略。",
                                "獲利與回正比例為未校準的歷史估計；q10/q90為相近案例分位，不是有覆蓋率保證的預測區間。",
                                "未還原價格、不含息總報酬；跨X／**事件及缺漏的樣本排除，可能產生選樣偏差。",
                                "驗證採時間前推抽樣，期間有重疊；尚未完成獨立保留集及跨市場可靠性驗證。",
                                "第一版為量價研究；基本面、產業、籌碼、ETF折溢價與即時成交條件尚未納入模型。",
                                "期限以本快照資料基準日開始計算；查看舊快照不會將舊預測改成今天。",
                                "分數為未最佳化描述指標：50＋3×期望報酬＋40×(獲利比例−0.5)＋2×min(q10,0)，限制0至100。"],
                      settings=settings,rows=results,summary=dict(count=len(results),eligible={str(h):sum(r["horizons"][str(h)]["eligible"] for r in results) for h in HORIZONS}),
                      evidence=copy.deepcopy(client.evidence),calendar=calendar)
        snapshot["data_quality"]=describe_sources(snapshot["evidence"],as_of,snapshot["created_at"])
        audit=self._prepare_audit(client,bundles,calendar,extra_snapshot=snapshot)
        atomic_json(self.root/"snapshots"/(snapshot["id"]+".json"),snapshot)
        self.store.save_snapshot(snapshot,audit=audit)
        return snapshot

    def _prepare_audit(self,client,bundles,calendar,extra_snapshot=None):
        """Old research remains auditable independently of today's selected universe."""
        completed={(r["snapshot_id"],r["symbol"],r["horizon"]) for r in self.store.get("reconciled",[])}
        required={}
        cutoff=calendar["actual"][-1]
        for meta in self.store.history(limit=None):
            past=self.store.snapshot(meta["id"])
            if past["as_of"]>=cutoff: continue
            end=min(cutoff,(date.fromisoformat(past["as_of"])+timedelta(days=70)).isoformat())
            for row in past["rows"]:
                symbol=row["symbol"]
                if all((past["id"],symbol,h) in completed for h in HORIZONS): continue
                existing=bundles.get(symbol,{}).get("rows",[])
                if existing and existing[0]["date"]<=past["as_of"] and existing[-1]["date"]>=end:
                    continue
                begin=date.fromisoformat(past["as_of"])
                finish=date.fromisoformat(end)
                months={f"{n//12:04d}{n%12+1:02d}01" for n in range(
                    begin.year*12+begin.month-1,finish.year*12+finish.month)}
                required.setdefault(symbol,set()).update(months)
        audit_bundles=copy.deepcopy(bundles)
        audit_calendar=copy.deepcopy(calendar)
        errors={}
        for symbol,months in required.items():
            try:
                self._status(phase="歷史對帳補齊",message=f"補齊 {symbol} 的舊預測資料")
                supplement=client.stock(symbol,sorted(months,reverse=True))
                sessions=client.calendar(sorted(months,reverse=True))
                merged={r["date"]:r for r in audit_bundles.get(symbol,{}).get("rows",[])}
                # Historical requests must never overwrite today's calculation input.
                for row in supplement["rows"]:
                    if row["date"]<=cutoff: merged.setdefault(row["date"],row)
                audit_bundles[symbol]=dict(rows=[merged[d] for d in sorted(merged)])
                audit_calendar["actual"]=sorted(set(audit_calendar["actual"])|{d for d in sessions["actual"] if d<=cutoff})
            except Exception as exc:
                errors[symbol]=str(exc)
        audit=self._reconcile(audit_bundles,audit_calendar,persist=False,evidence=client.evidence,
                              extra_snapshot=extra_snapshot)
        audit["backfill_errors"]=errors
        return audit

    def _reconcile(self,bundles,calendar,persist=True,evidence=None,extra_snapshot=None):
        key=lambda r:(r["snapshot_id"],r["symbol"],r["horizon"])
        reconciled={key(r):r for r in self.store.get("reconciled",[])}
        pending=[]
        from itertools import chain
        snapshots=chain((self.store.snapshot(meta['id']) for meta in self.store.history(limit=None)),
                        [extra_snapshot] if extra_snapshot else [])
        for past in snapshots:
            for row in past["rows"]:
                bars=bundles.get(row["symbol"],{}).get("rows",[])
                i=next((i for i,r in enumerate(bars) if r["date"]==past["as_of"]),None)
                for h in HORIZONS:
                    identity=dict(snapshot_id=past["id"],symbol=row["symbol"],horizon=h)
                    prediction=row.get("horizons",{}).get(str(h),{})
                    outcome=event_outcome(bars,i,h,dict(past["settings"],kind=row["kind"]),calendar) if i is not None else None
                    old=reconciled.get(key(identity))
                    invalidated=(not outcome and old and i is not None and old.get("exit_date")
                                 and bars[-1]["date"]>=old["exit_date"]
                                 and calendar["actual"][0]<=past["as_of"])
                    if outcome or invalidated:
                        if invalidated:
                            outcome=dict(signal_date=past["as_of"],entry_date=old["entry_date"],exit_date=old["exit_date"],
                                         return_pct=None,recovered=None,recovery_days=None,worst_close_return=None)
                        outcome["outcome_status"]="not_comparable" if invalidated else "computed"
                        inputs=dict(bars=[r for r in bars if past["as_of"]<=r["date"]<=outcome["exit_date"]],
                                    sessions=[d for d in calendar["actual"] if past["as_of"]<=d<=outcome["exit_date"]],
                                    settings=past["settings"],kind=row["kind"],outcome_status=outcome["outcome_status"])
                        digest=hashlib.sha256(json_text(inputs).encode()).hexdigest()
                        if old and old.get("calculation_hash")==digest: continue
                        revisions=copy.deepcopy(old.get("revisions",[])) if old else []
                        if old: revisions.append({k:v for k,v in old.items() if k!="revisions"})
                        reconciled[key(identity)]=dict(**identity,predicted=prediction.get("expected_return"),
                            p_positive=prediction.get("p_positive"),**outcome,calculation_hash=digest,
                            calculated_at=now().isoformat(),evidence=copy.deepcopy(evidence or []),revisions=revisions)
                    elif key(identity) not in reconciled:
                        pending.append(dict(**identity,reason="missing_history" if i is None else "not_mature_or_not_comparable"))
        audit=dict(outcomes=list(reconciled.values()),pending=pending,checked_at=now().isoformat())
        if persist: self.store.save_audit(audit)
        return audit

    def export_csv(self,horizon=7,metric="expected_return",snapshot_id=None,*,snapshot=None):
        if horizon not in HORIZONS or metric not in ("expected_return","p_positive","p_recovery","score"):
            raise ValueError("匯出期限或排序欄位錯誤")
        snap=snapshot if snapshot is not None else self.store.snapshot(snapshot_id)
        if not snap: raise ValueError("尚無研究快照")
        key=str(horizon)
        rows=sorted(snap["rows"],key=lambda r:(r["horizons"][key][metric] is not None,r["horizons"][key][metric] or 0),reverse=True)
        stream=io.StringIO(newline="")
        writer=csv.writer(stream)
        writer.writerow(["資料日","代號","名稱","類型","曆日","目標日期","期望淨報酬%","歷史獲利比例","收盤曾回正比例","q10%","q90%","樣本數","符合門檻","排除原因","複查狀態"])
        for r in rows:
            h=r["horizons"][key]
            writer.writerow([snap["as_of"],r["symbol"],r["name"],r["kind"],horizon,h["target_date"],h["expected_return"],h["p_positive"],h["p_recovery"],h["q10"],h["q90"],h["n"],h["eligible"],"；".join(h["reasons"]),quality_label(snap)])
        return "\ufeff"+stream.getvalue()


def analyze_market_symbol(task):
    from .analytics import target_date
    info,bundle,settings,calendar=task
    as_of=calendar['actual'][-1]
    rows=bundle['rows']; reasons=[]
    if info.get('currency','TWD')!='TWD': reasons.append('外幣交易版本：尚未加入匯率與外幣流動性門檻，暫不排行')
    if not rows or rows[-1]['date']!=as_of: reasons.append('當日無行情／停牌或尚未上市，暫不估計')
    if len(rows)<21: reasons.append('歷史資料不足20個交易日暖機')
    config=dict(settings,kind=info['kind'])
    if reasons:
        horizons={str(h):dict(target_date=target_date(as_of,h,calendar),entry_date=target_date(as_of,1,calendar),
            n=0,expected_return=None,median_return=None,p_positive=None,p_recovery=None,q10=None,q90=None,
            score=None,eligible=False,reasons=reasons,samples=[]) for h in HORIZONS}
        features=None;signals=[];validation={}
    else:
        model=ResearchModel(rows,config,calendar)
        horizons={str(h):model.estimate(len(rows)-1,h) for h in HORIZONS}
        features=model.features[-1]
        signals=[dict(date=rows[i]['date'],labels=f['labels']) for i,f in enumerate(model.features) if f and i>=len(rows)-60]
        validation=model.validate()
        if features is None: reasons.append('最近20日有價格調整、缺漏或無效價格，暫不估計')
    return dict(**info,as_of=as_of,data_as_of=rows[-1]['date'] if rows else None,
        status='排除／無法估計' if reasons else '研究估計／未校準',reasons=reasons,
        bars=rows[-60:],features=features,signals=signals,validation=validation,horizons=horizons,
        data_rows=len(rows),first_date=rows[0]['date'] if rows else None)


class MarketService(ResearchService):
    """All listed ordinary shares and officially classified vanilla equity ETFs."""
    def __init__(self,root,client_factory=None,workers=2):
        super().__init__(root,client_factory or MarketClient)
        self.workers=workers

    def settings(self):
        return dict(DEFAULT_SETTINGS,symbols=[],scope='all_listed_equity')

    def state(self):
        state=super().state()
        visible={meta['id'] for meta in self.store.history(limit=3)}
        state['two_week_outcomes']=[row for row in self.store.get('two_week_outcomes',[])
                                    if row['snapshot_id'] in visible]
        return state

    def compact_history(self):
        """Keep all original predictions; retain detailed diagnostics for latest three."""
        changed=False
        for meta in self.store.history(limit=None)[3:]:
            snap=self.store.snapshot(meta['id'])
            if snap.get('detail_retention')=='forecast_only': continue
            snap['rows']=[dict(symbol=r['symbol'],kind=r['kind'],horizons={h:{k:v for k,v in prediction.items()
                if k in ('expected_return','p_positive','p_recovery','target_date','entry_date','eligible','n','score','q10','q90')}
                for h,prediction in r['horizons'].items()}) for r in snap['rows']]
            snap['detail_retention']='forecast_only'
            atomic_json(self.root/'snapshots'/(snap['id']+'.json'),snap)
            with self.store.connect() as conn:
                conn.execute('UPDATE snapshots SET payload=? WHERE id=?',(json_text(snap),snap['id']))
            changed=True
        if changed:
            with self.store.connect() as conn: conn.execute('VACUUM')

    def reconcile_two_week(self,bundles,calendar):
        """Mature saved daily candidates without changing the original signal."""
        existing=self.store.get('two_week_outcomes',[])
        known={(x['snapshot_id'],x['symbol']) for x in existing}
        for meta in self.store.history(limit=None):
            snap=self.store.snapshot(meta['id'])
            archived=snap.get('two_week',{})
            for candidate in archived.get('scored_universe',archived.get('research_candidates',[])):
                key=(snap['id'],candidate['symbol'])
                if key in known: continue
                rows=bundles.get(candidate['symbol'],{}).get('rows',[])
                index=next((i for i,row in enumerate(rows) if row['date']==snap['as_of']),None)
                if index is None: continue
                result=two_week_outcome(rows,index,candidate['kind'],calendar)
                if result['status']=='pending': continue
                existing.append(dict(snapshot_id=snap['id'],signal_date=snap['as_of'],
                                     symbol=candidate['symbol'],kind=candidate['kind'],
                                     etf_style=candidate.get('etf_style'),rank_fraction=candidate.get('rank_fraction'),
                                     score=candidate.get('score'),**result))
                known.add(key)
        self.store.put('two_week_outcomes',existing)

    def _status(self,**kwargs):
        super()._status(**kwargs)
        print(kwargs.get('message',kwargs.get('phase','')),flush=True)

    def _run(self):
        from concurrent.futures import ProcessPoolExecutor
        settings=self.settings()
        client=self.client_factory(self.root,lambda symbol,session:self._status(phase='下載全市場',message=f'{symbol} {session}'))
        universe=client.universe()
        calendar=client.calendar(month_list(settings['months']))
        if not calendar['actual']: raise ValueError('官方尚無可使用的完整盤後資料')
        previous=self.store.snapshot()
        if previous and calendar['actual'][-1]<previous['as_of']:
            raise ValueError('官方資料日期倒退，保留已發布的較新快照')
        self.store.put('universe',universe)
        collection={info['symbol']:info for info in universe}
        for meta in self.store.history(limit=None):
            old=self.store.snapshot(meta['id'])
            archived=old.get('two_week',{})
            for candidate in archived.get('scored_universe',archived.get('research_candidates',[])):
                collection.setdefault(candidate['symbol'],candidate)
        bundles=client.market_bundles(list(collection.values()),calendar)
        as_of=calendar['actual'][-1]
        # Hash content rather than fetch timestamps: a holiday refresh need not recompute.
        signature=hashlib.sha256(json_text(dict(universe=universe,calendar=calendar,settings=settings,
            sources=[(e['url'],e['sha256']) for e in client.evidence],version=MODEL_VERSION,pipeline=TWO_WEEK_VERSION)).encode()).hexdigest()
        previous=self.store.snapshot()
        if previous and previous.get('data_signature')==signature:
            self.store.put('checked_at',now().isoformat())
            return previous
        tasks=((info,bundles[info['symbol']],settings,calendar) for info in universe)
        results=[]
        def consume(iterator):
            for row in iterator:
                results.append(row)
                if len(results)%10==0 or len(results)==len(universe):
                    self._status(phase='全市場分析',progress=len(results),total=len(universe),message=f'已分析 {len(results)} / {len(universe)} 檔')
        if self.workers>1:
            with ProcessPoolExecutor(max_workers=self.workers) as pool: consume(pool.map(analyze_market_symbol,tasks,chunksize=4))
        else: consume(map(analyze_market_symbol,tasks))
        unavailable=sum(bool(r['reasons']) for r in results)
        coverage=dict(universe_count=len(universe),analyzed_count=len(results)-unavailable,
            unavailable_count=unavailable,stocks=sum(r['kind']=='stock' for r in universe),etfs=sum(r['kind']=='etf' for r in universe))
        two_week=rank_candidates([dict(info,rows=bundles[info['symbol']]['rows']) for info in universe],
                                 as_of,self.store.get('two_week_outcomes',[]),calendar)
        snapshot=dict(id=now().strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8],as_of=as_of,created_at=now().isoformat(),
            model_version=MODEL_VERSION,data_signature=signature,scope='all_listed_equity',coverage=coverage,two_week=two_week,
            methodology='上市普通股及官方分類之股票型原型ETF；六期限按資料日起算曆日，休市順延。訊號後下一交易日開盤模擬進場，成本後未還原價格報酬；股票賣出稅0.3%、ETF0.1%，雙邊手續費0.1425%及滑價0.05%。',
            warnings=['涵蓋目前上市普通股及股票型原型ETF，含主動式與海外股票型；排除上櫃、存託憑證、債券、槓桿及反向ETF。',
                '外幣加掛版本保留於母集合；尚未處理匯率與外幣成交金額，因此暫不納入排行。',
                '獲利與收盤回正比例來自相似歷史，未校準，並非保證或已驗證的未來獲利機率。',
                '每日行情未還原且不含息；X調整標記及缺漏區間排除。MI_INDEX未提供所有個股月表註記，仍可能漏掉未標示的公司行動。',
                '目前上市集合具有存續偏差；歷史驗證樣本可能重疊，尚無獨立保留集可靠性證明。',
                '基本面、籌碼、ETF折溢價及盤中成交條件尚未加入模型。'],
            settings=settings,rows=results,summary=dict(count=len(results),eligible={str(h):sum(r['horizons'][str(h)]['eligible'] for r in results) for h in HORIZONS}),
            evidence=client.evidence,calendar=calendar)
        snapshot['data_quality']=describe_sources(snapshot['evidence'],as_of,snapshot['created_at'])
        # Shared evidence is stored once per snapshot; outcomes reference its content hash.
        manifest_hash=hashlib.sha256(json_text(client.evidence).encode()).hexdigest()
        audit=self._reconcile(bundles,calendar,persist=False,evidence=[dict(snapshot_id=snapshot['id'],manifest_sha256=manifest_hash)],extra_snapshot=snapshot)
        atomic_json(self.root/'snapshots'/(snapshot['id']+'.json'),snapshot)
        self.store.save_snapshot(snapshot,audit=audit)
        self.reconcile_two_week(bundles,calendar)
        self.compact_history()
        self.store.put('checked_at',now().isoformat())
        return snapshot
