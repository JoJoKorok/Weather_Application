import requests
from src.functions.get_weather import get_weather_by_city_name, get_weather_by_postal_code



class DummyResponse:
    # Mimics a basic requests.Response for tests (no network involved).
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


def test_city_success_prints_weather(monkeypatch, capsys, set_proxy_env):
    # Mocks a successful proxy response for a city search.

    payload = {
        "name": "London",
        "main": {"temp": 10.0, "humidity": 50},
        "wind": {"speed": 2.5},
        "weather": [{"description": "overcast clouds"}],
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        # Confirms client sends expected proxy params.
        assert params["city"] == "London"
        assert params["country"] == "gb"
        assert params["units"] == "metric"
        return DummyResponse(200, payload)

    monkeypatch.setattr("src.functions.get_weather.requests.get", fake_get)

    get_weather_by_city_name("London", "GB")
    out = capsys.readouterr().out

    assert "Weather in London" in out
    assert "Temperature" in out
    assert "Humidity" in out
    assert "Wind Speed" in out
    assert "Description" in out


def test_postal_success_prints_weather(monkeypatch, capsys, set_proxy_env):
    # Mocks a successful proxy response for a postal search.

    payload = {
        "name": "Alexandria",
        "main": {"temp": 5.0, "humidity": 60},
        "wind": {"speed": 1.2},
        "weather": [{"description": "clear sky"}],
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        assert params["postal"] == "22304"
        assert params["country"] == "us"
        assert params["units"] == "metric"
        return DummyResponse(200, payload)

    monkeypatch.setattr("src.functions.get_weather.requests.get", fake_get)

    get_weather_by_postal_code("22304", country_code="us")
    out = capsys.readouterr().out

    assert "Weather in Alexandria" in out


def test_city_404_prints_not_found(monkeypatch, capsys, set_proxy_env):
    # Ensures client handles 404 responses without crashing.

    def fake_get(url, params=None, headers=None, timeout=None):
        return DummyResponse(404, {"detail": "not found"})

    monkeypatch.setattr("src.functions.get_weather.requests.get", fake_get)

    get_weather_by_city_name("NopeTown", "US")
    out = capsys.readouterr().out.lower()

    assert "error" in out or "not found" in out


def test_timeout_prints_request_error(monkeypatch, capsys, set_proxy_env):
    # Ensures timeouts are handled gracefully.

    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("src.functions.get_weather.requests.get", fake_get)

    get_weather_by_city_name("London", "GB")
    out = capsys.readouterr().out.lower()

    assert "timed out" in out or "error" in out


def test_client_sends_anonymous_id_and_force_refresh(monkeypatch, set_proxy_env):
    payload = {
        "name": "London",
        "main": {"temp": 10.0, "humidity": 50},
        "wind": {"speed": 2.5},
        "weather": [{"description": "clear sky"}],
    }
    monkeypatch.setenv("WEATHER_FORCE_REFRESH", "true")

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers["X-Weather-Client"]
        assert headers["Cache-Control"] == "no-cache"
        return DummyResponse(200, payload)

    monkeypatch.setattr("src.functions.get_weather.requests.get", fake_get)
    get_weather_by_city_name("London", "GB")


def test_client_prints_cache_age(monkeypatch, capsys, set_proxy_env):
    payload = {
        "name": "London",
        "main": {"temp": 10.0, "humidity": 50},
        "wind": {"speed": 2.5},
        "weather": [{"description": "clear sky"}],
    }
    response = DummyResponse(200, payload)
    response.headers = {
        "X-Weather-Cache": "HIT",
        "X-Weather-Cache-Age": "42",
    }
    monkeypatch.setattr(
        "src.functions.get_weather.requests.get",
        lambda *args, **kwargs: response,
    )

    get_weather_by_city_name("London", "GB")
    assert "42 seconds old" in capsys.readouterr().out
