"""Deterministic, point-in-time historical analogue research (not calibrated ML)."""
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
import math
import numpy as np

HORIZONS = (1, 3, 5, 7, 14, 30)
MODEL_VERSION = "analogue-v1.0.0"


def iso_date(value):
    parts = str(value).strip().replace("/", "-").split("-")
    if len(parts) != 3:
        raise ValueError("日期格式錯誤")
    y, m, d = map(int, parts)
    return date(y + 1911 if y < 1911 else y, m, d).isoformat()


def number(value):
    try:
        x = float(str(value).replace(",", "").strip())
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def parse_month(payload):
    if str(payload.get("stat", "")).lower() != "ok":
        raise ValueError("TWSE 回應非成功：" + str(payload.get("stat", "missing stat")))
    fields = payload.get("fields", [])
    required = ["日期", "成交股數", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差"]
    if any(key not in fields for key in required):
        raise ValueError("TWSE 欄位與預期不符")
    rows, issues = {}, []
    for values in payload.get("data", []):
        item = dict(zip(fields, values))
        dt = iso_date(item.get("日期"))
        row = dict(date=dt, open=number(item.get("開盤價")), high=number(item.get("最高價")),
                   low=number(item.get("最低價")), close=number(item.get("收盤價")),
                   volume=number(item.get("成交股數")), turnover=number(item.get("成交金額")),
                   mark=str(item.get("註記", item.get("Mark", ""))), change=str(item.get("漲跌價差", "")))
        vals = [row[k] for k in ("open", "high", "low", "close", "volume")]
        valid = all(x is not None for x in vals)
        if valid:
            o,h,l,c,v = vals
            valid = o > 0 and c > 0 and l > 0 and h >= max(o,c) and l <= min(o,c) and h >= l and v >= 0
        row["valid"] = valid
        if not valid:
            issues.append(dt + "：價格或成交量無效，保留日期並排除跨越樣本")
        if dt in rows and rows[dt] != row:
            raise ValueError("重複日期資料衝突：" + dt)
        rows[dt] = row
    return {"rows": [rows[d] for d in sorted(rows)], "issues": issues}


def adjusted(row):
    return "**" in row.get("mark", "") or "X" in row.get("change", "").upper()


def target_date(signal_date, horizon, calendar):
    target = date.fromisoformat(signal_date) + timedelta(days=horizon)
    actual = calendar.get("actual", [])
    value = target.isoformat()
    if actual and actual[0] <= value <= actual[-1]:
        index = bisect_left(actual, value)
        return actual[index] if index < len(actual) else None
    # Do not extrapolate historical sessions from a static holiday calendar.
    if actual and value < actual[0]:
        return None
    for _ in range(40):
        value = target.isoformat()
        if target.year not in calendar.get("years", []):
            return None
        if value in calendar.get("opens", []) or (target.weekday() < 5 and value not in calendar.get("holidays", [])):
            return value
        target += timedelta(days=1)
    return None


def complete_window(window, calendar):
    if not window or any(not r.get("valid", True) for r in window):
        return False
    if calendar and calendar.get("actual"):
        actual = calendar["actual"]
        expected = actual[bisect_left(actual,window[0]["date"]):bisect_right(actual,window[-1]["date"])]
        if expected != [r["date"] for r in window]:
            return False
    return True


def features_at(rows, i, calendar=None):
    if i < 20 or i >= len(rows):
        return None
    window = rows[i-20:i+1]
    if not complete_window(window,calendar) or any(adjusted(r) for r in window[1:]):
        return None
    prev, current = window[:-1], window[-1]
    avg_volume = float(np.mean([r["volume"] for r in prev]))
    if avg_volume <= 0:
        return None
    o,c = current["open"], current["close"]
    body = (c-o)/o
    prev_high = max(r["high"] for r in prev)
    prev_low = min(r["low"] for r in prev)
    volume_ratio = current["volume"]/avg_volume
    labels = []
    if body >= .015 - 1e-12: labels.append("長紅 K")
    if body <= -.015 + 1e-12: labels.append("長黑 K")
    if abs(body) <= .002 + 1e-12: labels.append("小實體／十字線")
    if volume_ratio > 1.5: labels.append("成交量放大")
    if c > prev_high: labels.append("突破前20日高點")
    if c < prev_low: labels.append("跌破前20日低點")
    closes = np.array([r["close"] for r in window],dtype=float)
    volatility = float(np.std(np.diff(np.log(closes))))
    momentum5 = c/rows[i-5]["close"]-1
    momentum20 = c/rows[i-20]["close"]-1
    mean20 = float(np.mean(closes[-20:]))
    turnover = float(np.mean([r.get("turnover") or r["close"]*r["volume"] for r in window[-20:]]))
    return dict(labels=labels,body_pct=body*100,avg_volume_20=avg_volume,volume_ratio=volume_ratio,
                prev_20_high=prev_high,prev_20_low=prev_low,ma20=mean20,momentum5=momentum5*100,
                momentum20=momentum20*100,volatility=volatility*100,avg_turnover_20=turnover,
                vector=[body,momentum5,momentum20,c/mean20-1,math.log(max(volume_ratio,.001)),volatility])


def net_return(entry, close, settings):
    # No unverified day-trade exemption; ordinary stock tax is conservative.
    tax = .001 if settings.get("kind") == "etf" else .003
    fee = settings.get("fee_rate",.001425)
    slip = settings.get("slippage_rate",.0005)
    cost = entry*(1+slip)*(1+fee)
    proceeds = close*(1-slip)*(1-fee-tax)
    return (proceeds/cost-1)*100


def event_outcome(rows, i, horizon, settings, calendar):
    if i+1 >= len(rows):
        return None
    entry_day = target_date(rows[i]["date"],1,calendar)
    end_day = target_date(rows[i]["date"],horizon,calendar)
    if not entry_day or not end_day or end_day > rows[-1]["date"]:
        return None
    dates = [r["date"] for r in rows]
    a,b = bisect_left(dates,entry_day), bisect_left(dates,end_day)
    if a>=len(rows) or b>=len(rows) or dates[a]!=entry_day or dates[b]!=end_day or a>b:
        return None
    window = rows[a:b+1]
    if not complete_window(window,calendar) or any(adjusted(r) for r in window[1:]):
        return None
    if window[0]["high"] == window[0]["low"]:
        return None  # single-price/locked session; cannot assume entry execution
    returns = [net_return(window[0]["open"],r["close"],settings) for r in window]
    first = next((r for r,v in zip(window,returns) if v>0),None)
    return dict(signal_date=rows[i]["date"],entry_date=entry_day,exit_date=end_day,
                return_pct=returns[-1],recovered=first is not None,
                recovery_days=(date.fromisoformat(first["date"])-date.fromisoformat(entry_day)).days if first else None,
                worst_close_return=min(returns))


class ResearchModel:
    """Precompute labels; select only labels matured at each prediction cutoff."""
    def __init__(self,rows,settings,calendar):
        self.rows,self.settings,self.calendar=rows,settings,calendar
        self.features=[features_at(rows,i,calendar) for i in range(len(rows))]
        self.outcomes={h:[event_outcome(rows,i,h,settings,calendar) for i in range(len(rows))] for h in HORIZONS}

    def estimate(self,i,horizon):
        rows,settings,calendar=self.rows,self.settings,self.calendar
        current=self.features[i]
        target=target_date(rows[i]["date"],horizon,calendar)
        result=dict(target_date=target,entry_date=target_date(rows[i]["date"],1,calendar),n=0,
                    expected_return=None,median_return=None,p_positive=None,p_recovery=None,q10=None,q90=None,
                    score=None,eligible=False,reasons=[],samples=[])
        if current is None:
            result["reasons"]=["最近20日資料不足、缺漏或跨價格調整，暫不估計"]
            return result
        indices=[j for j in range(20,i) if self.features[j] is not None and self.outcomes[horizon][j]
                 and self.outcomes[horizon][j]["exit_date"] <= rows[i]["date"]]
        if not indices:
            result["reasons"]=["沒有已成熟且價格可比較的歷史樣本"]
            return result
        vectors=np.array([self.features[j]["vector"] for j in indices])
        scale=np.maximum(np.std(vectors,axis=0),np.array([.003,.01,.02,.01,.2,.003]))
        distances=np.sum(((vectors-np.array(current["vector"]))/scale)**2,axis=1)
        order=np.argsort(distances,kind="stable")[:int(settings.get("neighbors",60))]
        samples=[dict(self.outcomes[horizon][indices[k]],distance=float(distances[k])) for k in order]
        returns=np.array([s["return_pct"] for s in samples])
        p=float(np.mean(returns>0))
        q10,q90=map(float,np.quantile(returns,[.1,.9]))
        mean=float(np.mean(returns))
        reasons=[]
        if len(samples)<settings.get("min_samples",30): reasons.append("有效相近樣本不足")
        if current["avg_turnover_20"]<settings.get("min_turnover",20000000): reasons.append("20日平均成交金額低於門檻")
        if mean<=0: reasons.append("成本後期望值不為正")
        if p<settings.get("min_probability",.55): reasons.append("歷史到期獲利比例低於門檻")
        if q10 < -settings.get("max_downside",8): reasons.append("歷史下檔分位超過風險門檻")
        if target is None: reasons.append("目標年度官方開休市資料尚未取得")
        # Transparent descriptive index, not a probability or an optimized strategy.
        score=max(0,min(100,50+mean*3+(p-.5)*40+min(q10,0)*2))
        result.update(n=len(samples),expected_return=mean,median_return=float(np.median(returns)),
                      p_positive=p,p_recovery=float(np.mean([s["recovered"] for s in samples])),q10=q10,q90=q90,
                      score=round(score,1),eligible=not reasons,reasons=reasons,samples=samples,
                      worst_close_q10=float(np.quantile([s["worst_close_return"] for s in samples],.1)),
                      median_recovery_days=float(np.median([s["recovery_days"] for s in samples if s["recovered"]])) if any(s["recovered"] for s in samples) else None)
        return result

    def validate(self,max_points=36):
        result={}
        for h in HORIZONS:
            eligible=[i for i in range(160,len(self.rows)) if self.features[i] and self.outcomes[h][i]]
            chosen=eligible[-180::5][-max_points:]
            predictions=[]
            for i in chosen:
                p=self.estimate(i,h)
                if p["n"]<self.settings.get("min_samples",30): continue
                outcome=self.outcomes[h][i]
                actual=float(outcome["return_pct"]>0)
                matured=[x for x in self.outcomes[h][:i] if x and x["exit_date"]<=self.rows[i]["date"]]
                baseline=float(np.mean([x["return_pct"]>0 for x in matured])) if matured else .5
                predictions.append(dict(signal_date=self.rows[i]["date"],exit_date=outcome["exit_date"],
                                        expected=p["expected_return"],probability=p["p_positive"],
                                        actual=outcome["return_pct"],positive=actual,baseline=baseline,selected=p["eligible"]))
            if not predictions:
                result[str(h)]=dict(n=0,mae=None,brier=None,baseline_brier=None,mean_return=None,hit_rate=None,
                                    calibration=[],status="驗證樣本不足",predictions=[])
                continue
            calibration=[]
            for low,high in [(0,.4),(.4,.5),(.5,.6),(.6,.7),(.7,1.01)]:
                group=[p for p in predictions if low<=p["probability"]<high]
                if group: calibration.append(dict(n=len(group),predicted=float(np.mean([p["probability"] for p in group])),
                                                   actual=float(np.mean([p["positive"] for p in group]))))
            result[str(h)]=dict(n=len(predictions),mae=float(np.mean([abs(p["expected"]-p["actual"]) for p in predictions])),
                                brier=float(np.mean([(p["probability"]-p["positive"])**2 for p in predictions])),
                                baseline_brier=float(np.mean([(p["baseline"]-p["positive"])**2 for p in predictions])),
                                mean_return=float(np.mean([p["actual"] for p in predictions])),
                                hit_rate=float(np.mean([p["positive"] for p in predictions])),calibration=calibration,
                                status="時間前推抽樣驗證；樣本重疊、未校準，不構成可靠性認證",predictions=predictions)
        return result


def estimate(rows,i,horizon,settings,calendar):
    return ResearchModel(rows,settings,calendar).estimate(i,horizon)


def validate(rows,settings,calendar):
    return ResearchModel(rows,settings,calendar).validate()
