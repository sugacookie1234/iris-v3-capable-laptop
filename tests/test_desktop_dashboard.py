from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

from iris.desktop import dashboard as module


NOW = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)


def weather():
    return {
        'timezone': 'America/Toronto', 'utc_offset_seconds': -14400,
        'current': {'time': '2026-10-23T09:45', 'temperature_2m': 8.9,
                    'apparent_temperature': 5.9, 'weather_code': 2,
                    'wind_speed_10m': 12.3},
    }


def market(symbol='SPY'):
    def epoch(day, hour=13, minute=30):
        return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc).timestamp()
    return {'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': 'USD',
                 'currentTradingPeriod': {'regular': {'end': epoch(23, 20, 0)}}},
        'timestamp': [epoch(21), epoch(22), epoch(23)],
        'indicators': {'quote': [{'close': [100, 102, 999]}]},
    }]}}


class DashboardTests(unittest.TestCase):
    def setUp(self):
        for target, replacement in (
            ('_utcnow', Mock(return_value=NOW)),
            ('_weather_cache', module._Cache(max_entries=8)),
            ('_market_cache', module._Cache()),
        ):
            patcher = patch.object(module, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rejects_invalid_coordinates_before_network(self):
        with patch.object(module, '_fetch_json') as fetch:
            for latitude, longitude in ((float('nan'), 0), (1, float('inf')),
                                        (91, 0), (0, -181), (True, 0),
                                        ('43.65', 0), (None, 0), ({}, 0)):
                with self.subTest(latitude=latitude, longitude=longitude):
                    with self.assertRaisesRegex(ValueError, 'valid location'):
                        module.dashboard_weather(latitude, longitude)
            fetch.assert_not_called()

    def test_weather_uses_rounded_coordinates_and_source_timestamp(self):
        with patch.object(module, '_fetch_json', return_value=weather()) as fetch:
            result = module.dashboard_weather(43.654321, -79.381234)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['temperature_c'], 8.9)
            self.assertEqual(result['condition'], 'Partly cloudy')
            self.assertEqual(result['observed_at'], '2026-10-23T09:45:00-04:00')
            self.assertEqual(result['location'], 'Near you')
            url = fetch.call_args.args[0]
            self.assertIn('latitude=43.65', url)
            self.assertIn('longitude=-79.38', url)
            self.assertNotIn('43.654321', url)

    def test_cached_return_cannot_mutate_next_response(self):
        with patch.object(module, '_fetch_json', return_value=weather()) as fetch:
            first = module.dashboard_weather(43.65, -79.38)
            first['temperature_c'] = 999
            self.assertEqual(module.dashboard_weather(43.65, -79.38)['temperature_c'], 8.9)
            self.assertEqual(fetch.call_count, 1)

    def test_failure_returns_stale_reading_with_original_time_and_backoff(self):
        with patch.object(module.time, 'monotonic') as clock, \
                patch.object(module, '_fetch_json') as fetch:
            clock.return_value = 0
            fetch.return_value = weather()
            original = module.dashboard_weather(43.65, -79.38)
            clock.return_value = 901
            fetch.side_effect = OSError('private upstream response details')
            stale = module.dashboard_weather(43.65, -79.38)
            self.assertEqual(stale['status'], 'stale')
            self.assertEqual(stale['observed_at'], original['observed_at'])
            self.assertEqual(stale['fetched_at'], original['fetched_at'])
            self.assertNotIn('private', json.dumps(stale))
            module.dashboard_weather(43.65, -79.38)
            self.assertEqual(fetch.call_count, 2)
            clock.return_value = 6 * 3600 + 1
            self.assertEqual(module.dashboard_weather(43.65, -79.38)['status'], 'unavailable')

    def test_unavailable_also_has_retry_backoff(self):
        with patch.object(module, '_fetch_json', side_effect=TimeoutError()) as fetch:
            for _ in range(3):
                result = module.dashboard_weather(0, 0)
                self.assertEqual(result['status'], 'unavailable')
                self.assertIsNone(result['temperature_c'])
            self.assertEqual(fetch.call_count, 1)

    def test_old_and_invalid_weather_not_presented_as_current(self):
        for bad_value in (None, float('nan')):
            payload = weather()
            payload['current']['temperature_2m'] = bad_value
            with patch.object(module, '_fetch_json', return_value=payload):
                self.assertEqual(module.dashboard_weather(0, 0)['status'], 'unavailable')
            module._weather_cache.entries.clear()
        payload = weather()
        payload['current']['time'] = '2026-10-22T09:45'
        with patch.object(module, '_fetch_json', return_value=payload):
            self.assertEqual(module.dashboard_weather(0, 0)['status'], 'unavailable')

    def test_concurrent_refreshes_share_one_network_call(self):
        started = threading.Event()
        finish = threading.Event()

        def response(_url):
            started.set()
            self.assertTrue(finish.wait(2))
            return weather()

        with patch.object(module, '_fetch_json', side_effect=response) as fetch:
            with ThreadPoolExecutor(max_workers=4) as pool:
                first = pool.submit(module.dashboard_weather, 0, 0)
                self.assertTrue(started.wait(2))
                others = [pool.submit(module.dashboard_weather, 0, 0) for _ in range(3)]
                finish.set()
                for result in [first, *others]:
                    self.assertEqual(result.result()['status'], 'ok')
            self.assertEqual(fetch.call_count, 1)
        self.assertIsNot(module._weather_cache.lock, module._market_cache.lock)

    def test_weather_cache_is_bounded(self):
        with patch.object(module, '_fetch_json', return_value=weather()):
            for latitude in range(12):
                module.dashboard_weather(latitude, 0)
        self.assertEqual(len(module._weather_cache.entries), 8)

    def test_market_ignores_unfinished_today_and_compares_completed_sessions(self):
        result = module._parse_market(market(), 'SPY', 'S&P 500 ETF')
        self.assertEqual(result['value'], 102)
        self.assertEqual(result['change_percent'], 2)
        self.assertEqual(result['as_of'], '2026-10-22')
        self.assertEqual(result['currency'], 'USD')

    def test_market_includes_today_only_after_market_close_settlement_window(self):
        with patch.object(module, '_utcnow', return_value=NOW.replace(hour=21)):
            result = module._parse_market(market(), 'SPY', 'S&P 500 ETF')
        self.assertEqual(result['value'], 999)
        self.assertEqual(result['as_of'], '2026-10-23')

    def test_missing_bars_do_not_become_zero_prices(self):
        payload = market()
        payload['chart']['result'][0]['indicators']['quote'][0]['close'][1] = None
        with self.assertRaises(ValueError):
            module._parse_market(payload, 'SPY', 'S&P 500 ETF')

    def test_wrong_symbol_currency_and_nonfinite_prices_rejected(self):
        for field, bad in (('symbol', 'OTHER'), ('currency', 'CAD')):
            payload = market()
            payload['chart']['result'][0]['meta'][field] = bad
            with self.assertRaises(ValueError):
                module._parse_market(payload, 'SPY', 'S&P 500 ETF')
        payload = market()
        payload['chart']['result'][0]['indicators']['quote'][0]['close'][1] = float('nan')
        with self.assertRaises(ValueError):
            module._parse_market(payload, 'SPY', 'S&P 500 ETF')

    def test_partial_market_failure_keeps_working_rows_and_no_fake_price(self):
        def fetch(url):
            symbol = url.split('/chart/')[1].split('?')[0]
            if symbol == 'DIA':
                raise TimeoutError('secret upstream message')
            return market(symbol)
        with patch.object(module, '_fetch_json', side_effect=fetch):
            result = module.dashboard_markets()
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['items'][0]['as_of'], '2026-10-22')
        self.assertEqual(result['items'][2]['status'], 'unavailable')
        self.assertIsNone(result['items'][2]['value'])
        self.assertNotIn('secret', json.dumps(result))

    def test_total_market_failure_keeps_previous_close_with_stale_label(self):
        def fetch(url):
            return market(url.split('/chart/')[1].split('?')[0])
        with patch.object(module.time, 'monotonic') as clock, \
                patch.object(module, '_fetch_json', side_effect=fetch) as request:
            clock.return_value = 0
            first = module.dashboard_markets()
            clock.return_value = 901
            request.side_effect = OSError()
            result = module.dashboard_markets()
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['fetched_at'], first['fetched_at'])
        self.assertTrue(all(item['status'] == 'stale' for item in result['items']))

    def test_network_allowlist_and_redirect_rejection(self):
        with patch.object(module.urllib.request, 'build_opener') as build:
            for url in ('http://api.open-meteo.com/v1/forecast',
                        'https://localhost/v1/forecast',
                        'https://api.open-meteo.com/other',
                        'https://evil@api.open-meteo.com/v1/forecast',
                        'https://query1.finance.yahoo.com/v8/finance/chart/SECRET'):
                with self.assertRaises(ValueError):
                    module._fetch_json(url)
            build.assert_not_called()
        with self.assertRaises(ValueError):
            module._NoRedirect().redirect_request(None, None, 302, '', {}, 'http://localhost')

    def test_network_response_size_and_timeout_are_bounded(self):
        stream = io.BytesIO(b'a' * (module.MAX_RESPONSE_BYTES + 2))
        opener = Mock()
        opener.open.return_value = stream
        with patch.object(module.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'too large'):
                module._fetch_json('https://api.open-meteo.com/v1/forecast')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 8)


if __name__ == '__main__':
    unittest.main()
