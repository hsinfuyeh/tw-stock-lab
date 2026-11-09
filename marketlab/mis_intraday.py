"""Small, opt-in local watchlists from the TWSE MIS quote endpoint."""
from datetime import datetime
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .data import TAIPEI
from .intraday import MARKET_CLOSE, MARKET_OPEN, IntradayFeed, NoRedirect, empty_report, number, percent

SOURCE = '證交所 MIS · 上市自選清單'
URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'


def watchlist_symbols(value):
    symbols = tuple(dict.fromkeys(value.upper().replace(',', ' ').split()))
    if not 1 <= len(symbols) <= 20 or any(not re.fullmatch(r'[0-9]{4,6}[A-Z]?', s) for s in symbols):
        raise ValueError('TWSE_MIS_SYMBOLS 需要 1 至 20 檔上市證券代號，以空格或逗號分隔')
    return symbols


def fetch_mis(symbols):
    query = urlencode({'ex_ch': '|'.join(f'tse_{symbol}.tw' for symbol in symbols),
                       'json': 1, 'delay': 0})
    request = Request(f'{URL}?{query}', headers={
        'Accept': 'application/json',
        'Referer': 'https://mis.twse.com.tw/stock/index',
    })
    limit = 512 * 1024
    with build_opener(NoRedirect).open(request, timeout=6) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('MIS response exceeds size limit')
    return json.loads(body)


def positive(value):
    try:
        result = number(float(value))
    except (TypeError, ValueError):
        return None
    return result if result and result > 0 else None


def normalize_mis(payload, universe, current):
    if not isinstance(payload, dict) or payload.get('rtcode') != '0000':
        raise ValueError('MIS did not return a successful quote response')
    quotes = payload.get('msgArray')
    if not isinstance(quotes, list):
        raise ValueError('MIS quote list missing')
    catalog = {item['symbol']: item['kind'] for item in universe}
    if not any(catalog.values()):
        return empty_report('no_catalog', source=SOURCE)
    rows = {}
    latest = None
    saw_old = False
    trading_hours = MARKET_OPEN <= current.time() < MARKET_CLOSE
    for quote in quotes:
        if not isinstance(quote, dict) or quote.get('ex') != 'tse':
            continue
        symbol = quote.get('c')
        if not isinstance(symbol, str) or not catalog.get(symbol) or quote.get('ch') != f'{symbol}.tw':
            continue
        # A closing quote can carry a later update timestamp than the trade.
        try:
            updated = datetime.strptime(f"{quote.get('d')} {quote.get('t')}", '%Y%m%d %H:%M:%S')
        except ValueError:
            continue
        updated = updated.replace(tzinfo=TAIPEI)
        if (updated - current).total_seconds() > 5:
            continue
        if updated.date() != current.date():
            saw_old = True
            continue
        if not MARKET_OPEN <= updated.time() <= MARKET_CLOSE:
            continue
        price, opening, prior = (positive(quote.get(field)) for field in ('z', 'o', 'y'))
        volume = positive(quote.get('v'))
        if price is None or volume is None:
            continue
        if symbol in rows and rows[symbol]['updated_at'] >= updated.isoformat():
            continue
        latest = max(latest, updated) if latest else updated
        name = quote.get('n')
        rows[symbol] = dict(
            symbol=symbol, name=name[:100] if isinstance(name, str) else symbol, kind=catalog[symbol],
            price=price, opening=opening, volume=volume, amount=None, updated_at=updated.isoformat(),
            day_pct=percent(price, prior) if prior else None,
            gap_pct=percent(opening, prior) if prior and opening else None,
            from_open_pct=percent(price, opening) if opening else None,
        )
    if latest is None:
        return empty_report('stale' if saw_old else 'no_trades', source=SOURCE)
    if trading_hours and (current - latest).total_seconds() > 90:
        return empty_report('stale', source=SOURCE, snapshot_at=latest.isoformat())
    return dict(status='live' if trading_hours else 'closed', source=SOURCE, scope='watchlist',
                snapshot_at=latest.isoformat(), rows=list(rows.values()),
                coverage=len(rows), universe_count=len(catalog))


def mis_feed(value, universe):
    symbols = watchlist_symbols(value)

    def selected_catalog():
        kinds = {item['symbol']: item['kind'] for item in universe()
                 if item.get('kind') in ('stock', 'etf')}
        return [dict(symbol=symbol, kind=kinds.get(symbol)) for symbol in symbols]

    return IntradayFeed(symbols, selected_catalog, fetch=fetch_mis, normalize=normalize_mis,
                        source=SOURCE, live_ttl=30)
