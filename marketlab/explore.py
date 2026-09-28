"""Same-snapshot market facts for security search and descriptive rankings."""
import math
from .analytics import adjusted, complete_window, features_at


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def explore_catalog(snapshot, static=True):
    snapshot = snapshot or {}
    day = snapshot.get('as_of')
    rows = []
    for source in snapshot.get('rows', []):
        bars = [b for b in source.get('bars', []) if b.get('date', '') <= (day or '')]
        current = bars[-1] if bars else {}
        info = {k: source.get(k) for k in ('symbol', 'name', 'kind', 'currency')}
        info['data_as_of'] = current.get('date')
        info['detail_url'] = ('./data/details/{}/{}.json'.format(snapshot['id'], source['symbol'])
                              if static else None)
        metrics = {}
        if current.get('date') == day and current.get('valid', True) and finite(current.get('close')):
            feature = features_at(bars, len(bars)-1, snapshot.get('calendar'))
            prev = bars[-2] if len(bars)>1 else {}
            pair_ok = (len(bars)>1 and complete_window(bars[-2:], snapshot.get('calendar'))
                       and not adjusted(current) and finite(prev.get('close')) and prev['close']>0)
            window_ok = feature is not None
            metrics = dict(close=current['close'], turnover=current.get('turnover'), volume=current.get('volume'),
                change_pct=(current['close']/prev['close']-1)*100 if pair_ok else None,
                momentum5_pct=feature['momentum5'] if feature else None,
                momentum20_pct=feature['momentum20'] if feature else None,
                relative_volume=feature['volume_ratio'] if feature else None,
                volatility_pct=feature['volatility'] if feature else None,
                new_high20=current['close']>max(b['high'] for b in bars[-21:-1]) if window_ok else None,
                new_low20=current['close']<min(b['low'] for b in bars[-21:-1]) if window_ok else None)
            metrics = {k: (round(v, 6) if finite(v) else v if isinstance(v, bool) else None) for k,v in metrics.items()}
        info['metrics'] = metrics
        info['trend'] = [dict(date=b['date'], close=b['close']) for b in bars[-20:]
                         if finite(b.get('close'))]
        rows.append(info)
    return dict(id=snapshot.get('id'), as_of=day, rows=rows)
