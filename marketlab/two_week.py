"""Ten-session, gross-price target research. Daily bars only bound execution odds."""
from decimal import Decimal, ROUND_CEILING

from .analytics import adjusted, complete_window, features_at

TARGET = Decimal("1.05")
SESSIONS = 10
VERSION = "two-week-v1"


def _tick(price, kind):
    if kind == "etf":
        return Decimal("0.01") if price < 50 else Decimal("0.05")
    if price < 10: return Decimal("0.01") if price < 5 else Decimal("0.05")
    if price < 50: return Decimal("0.05")
    if price < 100: return Decimal("0.1")
    if price < 500: return Decimal("0.5") if price < 150 else Decimal("1")
    return Decimal("1") if price < 1000 else Decimal("5")


def target_price(entry, kind):
    required=Decimal(str(entry))*TARGET
    # The tick is determined at the target price, including a band crossing.
    tick=_tick(required,kind)
    return float((required/tick).to_integral_value(rounding=ROUND_CEILING)*tick)


def outcome(rows, signal_index, kind, calendar=None):
    """Evaluate a signal; entry day is session one. A high-only touch is uncertain."""
    if calendar and calendar.get("actual"):
        actual=calendar["actual"]
        signal_date=rows[signal_index]["date"]
        if signal_date not in actual: return dict(status="not_comparable")
        start=actual.index(signal_date)+1
        if len(actual)-start<SESSIONS: return dict(status="pending")
        expected=actual[start:start+SESSIONS]
        by_date={row["date"]:row for row in rows}
        if expected[0] not in by_date: return dict(status="not_filled",entry_date=expected[0])
        if any(day not in by_date for day in expected): return dict(status="not_comparable")
        window=[by_date[day] for day in expected]
    else:
        if len(rows)-signal_index-1 < SESSIONS:
            return dict(status="pending")
        window=rows[signal_index+1:signal_index+SESSIONS+1]
    if not complete_window(window,calendar) or any(adjusted(r) for r in window):
        return dict(status="not_comparable")
    entry=window[0]
    if entry["high"]==entry["low"] or entry["open"]<=0:
        return dict(status="not_filled",entry_date=entry["date"])
    price=target_price(entry["open"],kind)
    touched=any(r["high"]>=price for r in window)
    # A trade above the limit demonstrates that a sell at the lower target
    # was possible in principle; equal high remains unverified queue priority.
    possible=any(r["high"]>=price+float(_tick(Decimal(str(price)),kind)) for r in window)
    return dict(status="evaluated",entry_date=entry["date"],exit_date=window[-1]["date"],
                entry_price=entry["open"],target_price=price,touched=touched,
                potential_fill=possible,terminal_return_pct=(window[-1]["close"]/entry["open"]-1)*100)


def eligible_asset(info):
    if info.get("currency","TWD")!="TWD": return False
    if info.get("kind")=="stock": return True
    if info.get("kind")!="etf": return False
    name=str(info.get("name", ""))
    index=str(info.get("index_name", ""))
    foreign=("美國","日本","中國","大陸","香港","印度","韓國","全球","世界","越南","歐洲","NASDAQ","標普","S&P")
    if any(term in name or term in index for term in foreign): return False
    return any(term in name or term in index for term in ("台灣","臺灣","台股","臺股","中華民國"))


def _group(item):
    if item.get("kind")=="stock": return "stock"
    return "active_etf" if item.get("etf_style")=="active" else "passive_etf"


def validate_ranker(history):
    """Fixed top-decile rule, trained before a ten-session gap and date holdout."""
    result={}
    records=[r for r in history if r.get("status")=="evaluated" and r.get("rank_fraction") is not None]
    for group in ("stock","passive_etf","active_etf"):
        pool=[r for r in records if _group(r)==group]
        dates=sorted({r["signal_date"] for r in pool})
        report=dict(status="insufficient_validation",probability=None,baseline=None,
                    train_dates=0,test_dates=0,train_n=0,test_n=0)
        if len(dates)<80:
            result[group]=report;continue
        train_dates=set(dates[:-30]);test_dates=set(dates[-20:])
        train=[r for r in pool if r["signal_date"] in train_dates]
        test=[r for r in pool if r["signal_date"] in test_dates]
        train_top=[r for r in train if r["rank_fraction"]>=.9]
        test_top=[r for r in test if r["rank_fraction"]>=.9]
        report.update(train_dates=len(train_dates),test_dates=len(test_dates),train_n=len(train),test_n=len(test))
        if len(train)<400 or len(test)<100 or len(train_top)<40 or len(test_top)<20:
            result[group]=report;continue
        baseline=sum(bool(r["potential_fill"]) for r in train)/len(train)
        probability=(sum(bool(r["potential_fill"]) for r in train_top)+1)/(len(train_top)+2)
        holdout_base=sum(bool(r["potential_fill"]) for r in test)/len(test)
        holdout_top=sum(bool(r["potential_fill"]) for r in test_top)/len(test_top)
        brier_top=sum((probability-int(bool(r["potential_fill"])))**2 for r in test_top)/len(test_top)
        brier_base=sum((baseline-int(bool(r["potential_fill"])))**2 for r in test_top)/len(test_top)
        report.update(probability=probability,baseline=baseline,holdout_base=holdout_base,
                      holdout_top=holdout_top,holdout_top_n=len(test_top),brier=brier_top,baseline_brier=brier_base)
        if (probability>=baseline+.05 and holdout_top>=holdout_base+.05 and brier_top<brier_base):
            report["status"]="validated"
        result[group]=report
    return result


def rank_candidates(symbols, as_of, history, calendar):
    """Rank today; unlock recommendations only after forward archived validation."""
    candidates=[]
    for item in symbols:
        rows=item["rows"]
        if not rows or rows[-1]["date"]!=as_of or not eligible_asset(item): continue
        feature=features_at(rows,len(rows)-1,calendar if isinstance(calendar,dict) else None)
        if feature and feature["avg_turnover_20"]>=20_000_000:
            index={r["date"]:r.get("close") for r in calendar.get("index",[])} if isinstance(calendar,dict) else {}
            old,new=index.get(rows[-21]["date"]),index.get(as_of)
            market20=(new/old-1)*100 if old and new else 0
            breakout=2 if "突破前20日高點" in feature["labels"] else 0
            candidates.append(dict(symbol=item["symbol"],name=item.get("name",item["symbol"]),
                kind=item["kind"],etf_style=item.get("etf_style"),score=round(feature["momentum5"]+feature["momentum20"]
                -market20+min(feature["volume_ratio"],3)*2+breakout-feature["volatility"],2),
                reasons=feature["labels"],probability=None))
    candidates.sort(key=lambda r:(-r["score"],r["symbol"]))
    group_counts={group:sum(_group(row)==group for row in candidates)
                  for group in ("stock","passive_etf","active_etf")}
    group_positions={group:0 for group in group_counts}
    for item in candidates:
        group=_group(item)
        item["rank_fraction"]=1-group_positions[group]/group_counts[group]
        group_positions[group]+=1
    validation=validate_ranker(history)
    recommendations=[]
    for item in candidates:
        group=validation[_group(item)]
        if item["rank_fraction"]>=.9 and group["status"]=="validated":
            recommendations.append(dict(item,probability=group["probability"]))
    recommendations.sort(key=lambda r:(-r["probability"],-r["score"],r["symbol"]))
    recommendations=recommendations[:10]
    status="validated" if recommendations else "insufficient_validation"
    return dict(version=VERSION,as_of=as_of,horizon_sessions=SESSIONS,
                target_gross_pct=5,cutoff="19:00 Asia/Taipei",status=status,
                recommendations=recommendations,research_candidates=candidates[:10],scored_universe=candidates,
                validation=validation,note=("已用每日封存訊號做時間向前驗證；所示機率為排名組別的歷史頻率，日線仍無法確認實際成交。"
                    if recommendations else "候選僅依量價排序；尚無足夠的樣本外校準，不提供達標機率或正式推薦。無法確認投資區域的 ETF 暫不列入。"))
