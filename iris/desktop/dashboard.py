"""Small, cached public-data widgets for the personal desktop dashboard.

Only rounded browser coordinates leave the computer. Market prices are completed
daily closes for four fixed ETFs, never a live trading feed. Nothing is persisted.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
import threading
import time
import urllib.request
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo


MAX_RESPONSE_BYTES = 96 * 1024
TIMEOUT_SECONDS = 8
WATCHLIST = (
    ('SPY', 'S&P 500 ETF'),
    ('QQQ', 'Nasdaq-100 ETF'),
    ('DIA', 'Dow Jones ETF'),
    ('IWM', 'Russell 2000 ETF'),
)
_ALLOWED_PATHS = {
    ('api.open-meteo.com', '/v1/forecast'),
    *(('query1.finance.yahoo.com', '/v8/finance/chart/' + symbol)
      for symbol, _ in WATCHLIST),
}
_NY = ZoneInfo('America/New_York')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError('Unexpected data-source redirect.')


def _utcnow():
    return datetime.now(timezone.utc)


def _fetch_json(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment
            or (parsed.hostname, parsed.path) not in _ALLOWED_PATHS):
        raise ValueError('Unsupported data source.')
    request = urllib.request.Request(url, headers={
        'User-Agent': 'IRIS-personal-desktop/3.0', 'Accept': 'application/json',
    })
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError('Data-source response is too large.')
    return json.loads(data)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Expected a number.')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Expected a finite number.')
    return value


def _coordinates(latitude, longitude):
    try:
        latitude, longitude = _number(latitude), _number(longitude)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Please allow a valid location for the weather widget.') from None
    return round(latitude, 2), round(longitude, 2)


class _Cache:
    """A separate lock per widget prevents refresh storms without cross-blocking."""
    def __init__(self, max_entries=1):
        self.lock = threading.Lock()
        self.entries = {}
        self.max_entries = max_entries

    def get(self, key, load, unavailable, ttl, stale_for):
        with self.lock:
            now = time.monotonic()
            previous = self.entries.get(key)
            if previous and now < previous['expires']:
                return deepcopy(previous['data'])
            try:
                data = load()
                good_at = now
                expires = now + ttl
            except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError):
                if (previous and previous['good_at'] is not None
                        and now - previous['good_at'] <= stale_for):
                    data = deepcopy(previous['data'])
                    data.update(status='stale', stale=True,
                                message='Refresh unavailable. Showing the last saved reading.')
                    for item in data.get('items', []):
                        if item.get('value') is not None:
                            item['status'] = 'stale'
                    good_at = previous['good_at']
                else:
                    data = unavailable()
                    good_at = None
                expires = now + 60
            self.entries.pop(key, None)
            if len(self.entries) >= self.max_entries:
                self.entries.pop(next(iter(self.entries)))
            self.entries[key] = dict(data=data, expires=expires, good_at=good_at)
            return deepcopy(data)


_weather_cache = _Cache(max_entries=8)
_market_cache = _Cache()


def _condition(code):
    descriptions = {
        0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
        45: 'Fog', 48: 'Freezing fog', 51: 'Light drizzle', 53: 'Drizzle',
        55: 'Heavy drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle',
        61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
        66: 'Freezing rain', 67: 'Freezing rain', 71: 'Light snow',
        73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains',
        80: 'Rain showers', 81: 'Rain showers', 82: 'Heavy rain showers',
        85: 'Snow showers', 86: 'Heavy snow showers',
        95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with hail',
    }
    return descriptions.get(code, 'Conditions unavailable')


def _weather_base():
    return dict(source='Open-Meteo', source_url='https://open-meteo.com/',
                location='Near you', status='unavailable', stale=False,
                fetched_at=None, observed_at=None, timezone=None,
                temperature_c=None, feels_like_c=None, wind_kph=None,
                weather_code=None, condition='Unavailable',
                message='Weather is temporarily unavailable.')


def _load_weather(latitude, longitude):
    query = urlencode(dict(latitude=latitude, longitude=longitude, timezone='auto',
                           current='temperature_2m,apparent_temperature,weather_code,wind_speed_10m',
                           temperature_unit='celsius', wind_speed_unit='kmh', forecast_days=1))
    payload = _fetch_json('https://api.open-meteo.com/v1/forecast?' + query)
    current = payload['current']
    offset = _number(payload['utc_offset_seconds'])
    if abs(offset) > 14 * 3600:
        raise ValueError('Invalid time offset.')
    observed = datetime.fromisoformat(current['time']).replace(
        tzinfo=timezone(timedelta(seconds=offset)))
    zone_name = str(payload['timezone'])
    ZoneInfo(zone_name)
    now = _utcnow()
    age = (now - observed).total_seconds()
    if age < -1800 or age > 6 * 3600:
        raise ValueError('Weather observation is out of date.')
    code = _number(current['weather_code'])
    if not code.is_integer():
        raise ValueError('Invalid weather code.')
    result = _weather_base()
    result.update(status='stale' if age > 3600 else 'ok', stale=age > 3600,
                  fetched_at=now.isoformat(), observed_at=observed.isoformat(),
                  timezone=zone_name, temperature_c=_number(current['temperature_2m']),
                  feels_like_c=_number(current['apparent_temperature']),
                  wind_kph=_number(current['wind_speed_10m']), weather_code=int(code),
                  condition=_condition(int(code)),
                  message='Older weather reading.' if age > 3600 else '')
    return result


def dashboard_weather(latitude, longitude):
    """Validate and round browser coordinates before a cached Open-Meteo request."""
    location = _coordinates(latitude, longitude)
    return _weather_cache.get(location, lambda: _load_weather(*location),
                              _weather_base, ttl=900, stale_for=6 * 3600)


def _market_item(symbol, name):
    return dict(symbol=symbol, name=name, currency='USD', value=None,
                change_percent=None, as_of=None, status='unavailable',
                source_url='https://finance.yahoo.com/quote/' + symbol + '/')


def _parse_market(payload, symbol, name):
    result = payload['chart']['result'][0]
    metadata = result['meta']
    if metadata['symbol'] != symbol or metadata['currency'] != 'USD':
        raise ValueError('Unexpected market instrument.')
    now = _utcnow()
    today = now.astimezone(_NY).date()
    market_end = _number(metadata['currentTradingPeriod']['regular']['end'])
    close_confirmed = (datetime.fromtimestamp(market_end, _NY).date() == today
                       and now.timestamp() >= market_end + 30 * 60)
    prices = result['indicators']['quote'][0]['close']
    timestamps = result['timestamp']
    if len(prices) != len(timestamps) or len(prices) > 60:
        raise ValueError('Unexpected market history.')
    daily = {}
    for stamp, price in zip(timestamps, prices):
        if price is None:
            continue
        day = datetime.fromtimestamp(_number(stamp), _NY).date()
        if day > today or (day == today and not close_confirmed):
            continue
        number = _number(price)
        if number <= 0:
            raise ValueError('Invalid market price.')
        daily[day] = number
    days = sorted(daily)
    if len(days) < 2 or (today - days[-1]).days > 14:
        raise ValueError('No recent completed trading sessions.')
    latest, previous = daily[days[-1]], daily[days[-2]]
    item = _market_item(symbol, name)
    item.update(value=round(latest, 2), change_percent=round((latest / previous - 1) * 100, 2),
                as_of=days[-1].isoformat(),
                status='stale' if (today - days[-1]).days > 5 else 'ok')
    return item


def _load_market_item(pair):
    symbol, name = pair
    try:
        payload = _fetch_json('https://query1.finance.yahoo.com/v8/finance/chart/'
                              + symbol + '?range=1mo&interval=1d')
        return _parse_market(payload, symbol, name)
    except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError):
        return _market_item(symbol, name)


def _markets_base():
    return dict(source='Yahoo Finance', source_url='https://finance.yahoo.com/',
                label='Latest daily closes · not live', currency='USD',
                status='unavailable', stale=False, fetched_at=None,
                items=[_market_item(*pair) for pair in WATCHLIST],
                message='Market data is temporarily unavailable.')


def _load_markets():
    with ThreadPoolExecutor(max_workers=4) as pool:
        items = list(pool.map(_load_market_item, WATCHLIST))
    if all(item['status'] == 'unavailable' for item in items):
        raise ValueError('Market data is unavailable.')
    stale = any(item['status'] != 'ok' for item in items)
    result = _markets_base()
    result.update(items=items, status='stale' if stale else 'ok', stale=stale,
                  fetched_at=_utcnow().isoformat(),
                  message='Some market readings are older or unavailable.' if stale else '')
    return result


def dashboard_markets():
    """Return fixed broad-market ETF proxies with individual close dates."""
    return _market_cache.get('watchlist', _load_markets, _markets_base,
                             ttl=900, stale_for=24 * 3600)
