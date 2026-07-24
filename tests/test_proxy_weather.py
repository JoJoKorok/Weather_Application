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
    server._metrics.clear()
    DummyAsyncClient.calls = 0
    monkeypatch.setattr(server, "_usage_hour", None)
    monkeypatch.setattr(server, "_usage_hour_count", 0)
    monkeypatch.setattr(server, "_usage_day", None)
    monkeypatch.setattr(server, "_usage_count", 0)
    monkeypatch.setattr(server, "DAILY_LIMIT", 1000)
    monkeypatch.setattr(server, "HOURLY_LIMIT", 250)
    monkeypatch.setattr(server, "RESERVE_PERCENT", 20)
    monkeypatch.setattr(server, "PERSIST_BUDGETS", False)
    monkeypatch.setattr(server, "OPENWEATHER_RATE_LIMIT_PER_MIN", 60)
    monkeypatch.setattr(server, "TRUSTED_RATE_LIMIT_PER_MIN", 120)
    monkeypatch.setattr(server, "QUERY_RATE_LIMIT_PER_10_MIN", 2)
    monkeypatch.setattr(server, "TRUSTED_QUERY_RATE_LIMIT_PER_10_MIN", 30)
    monkeypatch.setattr(server, "TRUSTED_TOKENS", set())
    monkeypatch.setattr(server, "ADMIN_TOKENS", set())
    monkeypatch.setattr(server, "HISTORY_ENDPOINTS_ENABLED", False)
    monkeypatch.setattr(server, "SERVICE_ENABLED", True)
    monkeypatch.setattr(server, "UPSTREAM_CALLS_ENABLED", True)
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
    monkeypatch.setattr(server, "RESERVE_PERCENT", 0)
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    assert client.get("/weather").status_code == 400
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert client.get("/weather?city=Paris&country=fr").status_code == 429


def test_public_budget_preserves_capacity_for_trusted_token(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "TRUSTED_TOKENS", {"owner-token"})
    monkeypatch.setattr(server, "DAILY_LIMIT", 2)
    monkeypatch.setattr(server, "HOURLY_LIMIT", 2)
    monkeypatch.setattr(server, "RESERVE_PERCENT", 50)
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert client.get("/weather?city=Paris&country=fr").status_code == 429
    trusted = client.get(
        "/weather?city=Paris&country=fr",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert trusted.status_code == 200


def test_persistent_budget_survives_memory_counter_reset(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "DAILY_LIMIT", 1)
    monkeypatch.setattr(server, "HOURLY_LIMIT", 1)
    monkeypatch.setattr(server, "RESERVE_PERCENT", 0)
    monkeypatch.setattr(server, "PERSIST_BUDGETS", True)
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)
    client = TestClient(proxy_app)

    assert client.get("/weather?city=London&country=gb").status_code == 200
    server._usage_hour = None
    server._usage_hour_count = 0
    server._usage_day = None
    server._usage_count = 0
    assert client.get("/weather?city=Paris&country=fr").status_code == 429


def test_service_and_upstream_emergency_switches(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    monkeypatch.setattr(server, "SERVICE_ENABLED", False)
    assert client.get("/").json()["status"] == "maintenance"
    assert client.get("/weather?city=London&country=gb").status_code == 503

    monkeypatch.setattr(server, "SERVICE_ENABLED", True)
    monkeypatch.setattr(server, "UPSTREAM_CALLS_ENABLED", False)
    assert client.get("/weather?city=London&country=gb").status_code == 503


def test_cached_results_remain_available_when_upstream_disabled(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)

    client = TestClient(proxy_app)
    assert client.get("/weather?city=London&country=gb").status_code == 200
    monkeypatch.setattr(server, "UPSTREAM_CALLS_ENABLED", False)
    cached = client.get("/weather?city=London&country=gb")
    assert cached.status_code == 200
    assert cached.headers["X-Weather-Cache"] == "HIT"


def test_only_trusted_token_can_force_refresh(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "TRUSTED_TOKENS", {"owner-token"})
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)
    client = TestClient(proxy_app)

    assert client.get("/weather?city=London&country=gb").status_code == 200
    public = client.get(
        "/weather?city=London&country=gb",
        headers={"Cache-Control": "no-cache"},
    )
    assert public.headers["X-Weather-Cache"] == "HIT"

    trusted = client.get(
        "/weather?city=London&country=gb",
        headers={
            "Authorization": "Bearer owner-token",
            "Cache-Control": "no-cache",
        },
    )
    assert trusted.headers["X-Weather-Cache"] == "MISS"
    assert DummyAsyncClient.calls == 2


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


def test_history_endpoints_are_disabled_by_default(monkeypatch):
    monkeypatch.setattr(server, "ADMIN_TOKENS", {"admin-token"})
    client = TestClient(proxy_app)

    headers = {"Authorization": "Bearer admin-token"}
    assert client.get("/history", headers=headers).status_code == 404
    assert client.get("/search?q=London", headers=headers).status_code == 404


def test_history_endpoints_require_admin_token(monkeypatch):
    monkeypatch.setattr(server, "ADMIN_TOKENS", {"admin-token"})
    monkeypatch.setattr(server, "HISTORY_ENDPOINTS_ENABLED", True)
    client = TestClient(proxy_app)

    assert client.get("/history").status_code == 401
    response = client.get(
        "/history",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_admin_stats_are_private_and_report_aggregate_usage(monkeypatch):
    monkeypatch.setattr(server, "OPENWEATHER_API_KEY", "dummykey")
    monkeypatch.setattr(server, "PROXY_TOKENS", set())
    monkeypatch.setattr(server, "ADMIN_TOKENS", {"admin-token"})
    monkeypatch.setattr(server.httpx, "AsyncClient", DummyAsyncClient)
    client = TestClient(proxy_app)

    assert client.get("/admin/stats").status_code == 401
    assert client.get("/weather?city=London&country=gb").status_code == 200
    assert client.get("/weather?city=London&country=gb").status_code == 200

    response = client.get(
        "/admin/stats",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    stats = response.json()
    assert stats["cache"]["hits"] == 1
    assert stats["cache"]["misses"] == 1
    assert stats["upstream"]["calls"] == 1
    assert "tokens" not in response.text.lower()
    assert "dummykey" not in response.text
