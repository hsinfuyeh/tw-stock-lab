"""Local, read-only Fugle snapshot feed. Quotes are kept in memory."""
from datetime import datetime, time
import json
from math import isfinite
import threading
from time import monotonic
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .data import TAIPEI, now

SOURCE = '富果 Fugle · 上市整股快照'
MARKET_OPEN = time(9)
MARKET_CLOSE = time(13, 30)
URL = 'https://api.fugle.tw/marketdata/v1.0/stock/snapshot/quotes/TSE?type=ALLBUT0999'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_snapshot(key):
    request = Request(URL, headers={'X-API-KEY': key, 'Accept': 'application/json'})
    limit = 4 * 1024 * 1024
    with build_opener(NoRedirect).open(request, timeout=6) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('Snapshot exceeds size limit')
    return json.loads(body)


def number(value):
    if type(value) in (int, float) and abs(value) < 1e18 and isfinite(value):
        return value
    return None


def percent(value, base):
    return round((value - base) / base * 100, 4)


def empty_report(status, **details):
    return {'status': status, 'source': SOURCE, 'rows': [], **details}


def normalize_snapshot(payload, universe, current):
    if not isinstance(payload, dict) or payload.get('market') != 'TSE':
        raise ValueError('Unexpected market')
    quotes = payload.get('data')
    if not isinstance(quotes, list) or not quotes:
        raise ValueError('Missing snapshot rows')
    stamp = datetime.strptime(f"{payload.get('date')} {payload.get('time')}", '%Y-%m-%d %H%M%S')
    stamp = stamp.replace(tzinfo=TAIPEI)
    age = (current - stamp).total_seconds()
    trading_hours = MARKET_OPEN <= current.time() < MARKET_CLOSE
    if (stamp.date() != current.date() or stamp.time() < MARKET_OPEN or age < -5
            or (trading_hours and age > 90)):
        return empty_report('stale', snapshot_at=stamp.isoformat())
    catalog = {item['symbol']: item['kind'] for item in universe
               if item.get('kind') in ('stock', 'etf')}
    if not catalog:
        return empty_report('no_catalog')
    rows = []
    seen = set()
    for quote in quotes:
        if not isinstance(quote, dict) or quote.get('type') != 'EQUITY':
            continue
        symbol = quote.get('symbol')
        if not isinstance(symbol, str) or symbol not in catalog or symbol in seen:
            continue
        volume = number(quote.get('tradeVolume'))
        if not volume or volume < 0:
            continue
        updated = number(quote.get('lastUpdated'))
        if updated is None or not 0 < updated <= (current.timestamp() + 5) * 1_000_000:
            continue
        updated = datetime.fromtimestamp(updated / 1_000_000, TAIPEI)
        if updated.date() != stamp.date() or updated.time() < MARKET_OPEN:
            continue
        price = number(quote.get('closePrice'))
        opening = number(quote.get('openPrice'))
        price = price if price and price > 0 else None
        opening = opening if opening and opening > 0 else None
        # The snapshot's lastPrice can include an indicative auction price.
        # Only use its change to recover the reference when it agrees with
        # the last regular price and the provider has not marked a trial.
        change = number(quote.get('change'))
        reference = None
        if price and price == number(quote.get('lastPrice')) and not quote.get('isTrial') and change is not None:
            candidate = round(price - change, 6)
            if candidate > 0:
                reference = candidate
        amount = number(quote.get('tradeValue'))
        name = quote.get('name')
        rows.append(dict(
            symbol=symbol, name=name[:100] if isinstance(name, str) else symbol, kind=catalog[symbol],
            price=price, opening=opening, volume=volume, amount=amount if amount and amount > 0 else None,
            day_pct=percent(price, reference) if reference else None,
            gap_pct=percent(opening, reference) if opening and reference else None,
            from_open_pct=percent(price, opening) if price and opening else None,
            updated_at=updated.isoformat(), trial=bool(quote.get('isTrial')),
        ))
        seen.add(symbol)
    return dict(status=('live' if trading_hours else 'closed') if rows else 'no_trades',
                source=SOURCE, snapshot_at=stamp.isoformat(), rows=rows,
                coverage=len(rows), universe_count=len(catalog))


class IntradayFeed:
    def __init__(self, key, universe, *, fetch=fetch_snapshot, clock=now, timer=monotonic):
        self.key = key
        self.universe = universe
        self.fetch = fetch
        self.clock = clock
        self.timer = timer
        self.lock = threading.Lock()
        self.cached = None
        self.valid_until = 0

    def report(self):
        if not self.key:
            return empty_report('unconfigured', source=None)
        current = self.clock()
        if current.weekday() >= 5 or current.time() < MARKET_OPEN:
            return empty_report('outside_session')
        with self.lock:
            current = self.clock()
            session = (current.date(), current.time() < MARKET_CLOSE)
            if self.cached and self.cached[0] == session and self.timer() < self.valid_until:
                return self.cached[1]
            try:
                payload = self.fetch(self.key)
                current = self.clock()
                result = normalize_snapshot(payload, self.universe(), current)
            except HTTPError as exc:
                status = {401: 'unauthorized', 403: 'unauthorized', 429: 'rate_limited'}
                result = empty_report(status.get(exc.code, 'unavailable'))
            except (ValueError, OSError, OverflowError):
                result = empty_report('unavailable')
            self.cached = ((current.date(), current.time() < MARKET_CLOSE), result)
            ttl = 60
            if result['status'] == 'live':
                age = (current - datetime.fromisoformat(result['snapshot_at'])).total_seconds()
                ttl = min(15, 90 - age)
            self.valid_until = self.timer() + ttl
            return result
