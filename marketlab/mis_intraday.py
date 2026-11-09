"""Local TWSE MIS rankings for a watchlist or the official listed universe."""
from datetime import datetime
from functools import lru_cache
import json
import re
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .data import TAIPEI, now
from .intraday import MARKET_CLOSE, MARKET_OPEN, IntradayFeed, NoRedirect, empty_report, number, percent

SOURCE = '證交所 MIS · 上市自選清單'
MARKET_SOURCE = '證交所 MIS · 上市全市場'
URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
COMPANIES = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
ETFS = 'https://www.twse.com.tw/zh/ETFortune/ajaxProductsResult'
SYMBOL = re.compile(r'[0-9]{4,6}[A-Z]?')
BATCH_SIZE = 50


def watchlist_symbols(value):
    symbols = tuple(dict.fromkeys(value.upper().replace(',', ' ').split()))
    if not symbols or any(not SYMBOL.fullmatch(s) for s in symbols):
        raise ValueError('請輸入上市證券代號，以空格或逗號分隔')
    return symbols


def get_json(url, headers=None, limit=2 * 1024 * 1024):
    request = Request(url, headers=headers or {'Accept': 'application/json'})
    with build_opener(NoRedirect).open(request, timeout=6) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('TWSE response exceeds size limit')
    return json.loads(body)


def fetch_mis(symbols):
    query = urlencode({'ex_ch': '|'.join(f'tse_{symbol}.tw' for symbol in symbols),
                       'json': 1, 'delay': 0})
    return get_json(f'{URL}?{query}', headers={
        'Accept': 'application/json',
        'Referer': 'https://mis.twse.com.tw/stock/index',
    }, limit=512 * 1024)


def fetch_batches(symbols, *, fetch=fetch_mis, pause=sleep):
    quotes = []
    completed = 0
    error = None
    batch_count = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE
    deadline = monotonic() + 34
    for offset in range(0, len(symbols), BATCH_SIZE):
        if offset:
            pause(0.35)
            if monotonic() >= deadline:
                break
        batch = symbols[offset:offset+BATCH_SIZE]
        try:
            payload = fetch(batch)
            rows = payload.get('msgArray') if isinstance(payload, dict) else None
            if not isinstance(rows, list) or payload.get('rtcode') != '0000':
                raise ValueError('MIS did not return a successful batch')
            requested = set(batch)
            quotes.extend(row for row in rows if isinstance(row, dict)
                          and isinstance(row.get('c'), str) and row['c'] in requested)
            completed += 1
        except (OSError, ValueError) as exc:
            error = exc
            if isinstance(exc, HTTPError) and exc.code in (401, 403, 429):
                break
    if not completed:
        raise error or ValueError('MIS did not return any successful batches')
    return dict(rtcode='0000', msgArray=quotes, batch_count=batch_count, batches_ok=completed)


def market_catalog(companies, etfs):
    if (not isinstance(companies, list) or not companies or not isinstance(etfs, dict)
            or etfs.get('status') != 'success' or not isinstance(etfs.get('data'), list) or not etfs['data']):
        raise ValueError('上市股票／ETF 官方名錄不完整')
    kinds = {}
    for row in companies:
        if str(row.get('公司簡稱', '')).upper().endswith('-DR'):
            continue
        symbol = str(row.get('公司代號', '')).strip()
        if not re.fullmatch(r'[1-9][0-9]{3}', symbol) or symbol in kinds:
            raise ValueError('上市公司代號格式異常')
        kinds[symbol] = 'stock'
    for row in etfs['data']:
        symbol = str(row.get('stockNo', '')).strip()
        if not SYMBOL.fullmatch(symbol) or symbol in kinds:
            raise ValueError('上市 ETF 代號格式異常')
        kinds[symbol] = 'etf'
    return [dict(symbol=symbol, kind=kind) for symbol, kind in sorted(kinds.items())]


def positive(value):
    try:
        result = number(float(value))
    except (TypeError, ValueError):
        return None
    return result if result and result > 0 else None


def normalize_mis(payload, universe, current, *, source=SOURCE):
    if not isinstance(payload, dict) or payload.get('rtcode') != '0000':
        raise ValueError('MIS did not return a successful quote response')
    quotes = payload.get('msgArray')
    if not isinstance(quotes, list):
        raise ValueError('MIS quote list missing')
    catalog = {item['symbol']: item['kind'] for item in universe}
    if not any(catalog.values()):
        return empty_report('no_catalog', source=source)
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
    coverage = dict(coverage=len(rows), universe_count=len(catalog))
    if 'batch_count' in payload:
        returned = {quote['c'] for quote in quotes if isinstance(quote,dict)
                    and isinstance(quote.get('c'),str) and catalog.get(quote['c'])}
        coverage.update(batch_count=payload['batch_count'], batches_ok=payload['batches_ok'],
                        returned_count=len(returned))
    if latest is None:
        return empty_report('stale' if saw_old else 'no_trades', source=source, **coverage)
    if trading_hours and (current - latest).total_seconds() > 90:
        return empty_report('stale', source=source, snapshot_at=latest.isoformat(), **coverage)
    return dict(status='live' if trading_hours else 'closed', source=source,
                snapshot_at=latest.isoformat(), rows=list(rows.values()), **coverage)


def mis_feed(value, universe):
    symbols = watchlist_symbols(value)

    def selected_catalog():
        kinds = {item['symbol']: item['kind'] for item in universe()
                 if item.get('kind') in ('stock', 'etf')}
        return [dict(symbol=symbol, kind=kinds.get(symbol)) for symbol in symbols]

    return IntradayFeed(symbols, selected_catalog, fetch=fetch_batches, normalize=normalize_mis,
                        source=SOURCE, live_ttl=30)


def market_feed():
    @lru_cache(maxsize=1)
    def catalog_for_day(day):
        return market_catalog(get_json(COMPANIES), get_json(ETFS))

    def universe():
        return catalog_for_day(now().date())

    def fetch(_):
        return fetch_batches(tuple(row['symbol'] for row in universe()))

    def normalize(payload, catalog, current):
        return normalize_mis(payload, catalog, current, source=MARKET_SOURCE)

    return IntradayFeed(True, universe, fetch=fetch, normalize=normalize,
                        source=MARKET_SOURCE, live_ttl=50)
