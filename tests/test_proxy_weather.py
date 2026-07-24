import httpx
import pytest
import proxy.server as server
from fastapi.testclient import TestClient
from proxy.server import app as proxy_app


class DummyHTTPXResponse:
    # Mimics httpx response for proxy tests.
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class DummyAsyncClient:
    # Replaces httpx.AsyncClient so we never hit OpenWeather during tests.
    calls = 0

    def __init__(self, timeout=8):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        type(self).calls += 1
        data = {
            "name": "London",
            "sys": {"country": "GB"},
            "main": {"temp": 1.0, "humidity": 90},
            "wind": {"speed": 1.5},
            "weather": [{"description": "few clouds"}],
        }
        return DummyHTTPXResponse(200, data=data)


@pytest.fixture(autouse=True)
def reset_proxy_counters(monkeypatch):
    server._hits.clear()
    server._weather_cache.clear()
    server._query_locks.clear()
    DummyAsyncClient.calls = 0
    monkeypatch.setattr(server, "_usage_day", None)
    monkeypatch.setattr(server, "_usage_count", 0)
    monkeypatch.setattr(server, "DAILY_LIMIT", 1000)
    monkeypatch.setattr(server, "OPENWEATHER_RATE_LIMIT_PER_MIN", 60)
    monkeypatch.setattr(server, "CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(server, "CACHE_MAX_ENTRIES", 500)


def test_proxy_root_ok():
    # Basic sanity check: proxy is alive.
    client = TestClient(proxy_app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_proxy_requires_city_or_postal(monkeypatch):
    # Ensures missing query params return 400 instead of crashing.

    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey", raising=False)
    monkeypatch.setattr(server, "PROXY_TOKENS", set(), raising=False)

    client = TestClient(proxy_app)
    r = client.get("/weather")
    assert r.status_code == 400


def test_proxy_unauthorized_when_tokens_enabled(monkeypatch):
    # Ensures token gating works when PROXY_TOKENS is set.

    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey", raising=False)
    monkeypatch.setattr(server, "PROXY_TOKENS", {"allowedtoken"}, raising=False)

    client = TestClient(proxy_app)
    r = client.get("/weather?city=London&country=gb")
    assert r.status_code == 401


def test_proxy_weather_success(monkeypatch):
    # Ensures proxy returns the fields the client expects.

    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey", raising=False)
    monkeypatch.setattr(server, "PROXY_TOKENS", set(), raising=False)

    # Avoid real network by swapping httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    r = client.get("/weather?city=London&country=gb")

    assert r.status_code == 200
    body = r.json()

    assert "name" in body
    assert "main" in body
    assert "wind" in body
    assert "weather" in body
    assert r.headers["X-Weather-Cache"] == "MISS"


def test_proxy_caches_normalized_duplicate_queries(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    first = client.get("/weather?city=London&country=gb")
    second = client.get("/weather?city=london&country=GB")

    assert first.status_code == 200
    assert first.headers["X-Weather-Cache"] == "MISS"
    assert second.status_code == 200
    assert second.headers["X-Weather-Cache"] == "HIT"
    assert DummyAsyncClient.calls == 1
    assert server._usage_count == 1


def test_proxy_cache_can_be_disabled(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert DummyAsyncClient.calls == 2


def test_proxy_rejects_ambiguous_or_invalid_queries(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())

    client = TestClient(proxy_app)
    assert client.get("/weather?city=London&postal=12345&country=gb").status_code == 400
    assert client.get("/weather?city=London&country=britain").status_code == 400
    assert client.get("/weather?city=London&country=gb&units=kelvin").status_code == 400
    assert client.get("/weather?city=London&country=gb&lang=fr").status_code == 400


def test_proxy_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", {"allowedtoken"})
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    response = client.get(
        "/weather?city=London&country=gb",
        headers={"Authorization": "Bearer allowedtoken"},
    )
    assert response.status_code == 200


def test_invalid_requests_do_not_consume_daily_limit(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "DAILY_LIMIT", 1)
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    assert client.get("/weather").status_code == 400
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert client.get("/weather?city=Paris&country=fr").status_code == 429


def test_proxy_maps_upstream_timeout_to_gateway_timeout(monkeypatch):
    class TimeoutClient(DummyAsyncClient):
        async def get(self, url, params=None):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server.httpx, "AsyncClient", TimeoutClient)

    client = TestClient(proxy_app)
    response = client.get("/weather?city=London&country=gb")
    assert response.status_code == 504
