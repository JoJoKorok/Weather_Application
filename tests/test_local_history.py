from src.data import local_history


def _weather(name: str, description: str, temp: float) -> dict:
    return {
        "name": name,
        "main": {"temp": temp, "humidity": 55},
        "wind": {"speed": 2.0},
        "weather": [{"description": description}],
    }


def test_history_round_trip_and_search(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    local_history.init_db()

    local_history.log_weather(
        query_type="city",
        city="Tokyo",
        postal=None,
        country="JP",
        units="metric",
        lang="ja",
        description_override="晴天",
        data=_weather("Tokyo", "clear sky", 24.0),
    )

    items = local_history.fetch_history()
    assert len(items) == 1
    assert items[0]["name"] == "Tokyo"
    assert items[0]["description"] == "晴天"
    assert local_history.search_history("tokyo")[0]["country"] == "JP"
    assert local_history.search_history("晴天")[0]["city"] == "Tokyo"


def test_history_limits_and_blank_search(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    local_history.init_db()

    assert local_history.fetch_history(limit=500) == []
    assert local_history.search_history("   ") == []
