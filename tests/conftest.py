import sys
from pathlib import Path

import pytest



# Adds the repo root to Python's import path so "import src...." works in tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolate_runtime_data(monkeypatch, tmp_path):
    """Keep tests from reading or writing a user's real weather history."""

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("WEATHER_DB_PATH", str(tmp_path / "proxy" / "history.sqlite"))


@pytest.fixture
def set_proxy_env(monkeypatch):
    # Sets proxy URL so client tests don't fail due to missing env vars.
    # This keeps tests self-contained and prevents accidental real network calls.

    monkeypatch.setenv("WEATHER_PROXY_URL", "https://example.com/weather")
    monkeypatch.delenv("WEATHER_PROXY_TOKEN", raising=False)
    yield


@pytest.fixture
def set_proxy_env_with_token(monkeypatch):
    # Same as above, but includes a token so we can test header behavior.

    monkeypatch.setenv("WEATHER_PROXY_URL", "https://example.com/weather")
    monkeypatch.setenv("WEATHER_PROXY_TOKEN", "testtoken123")
    yield
