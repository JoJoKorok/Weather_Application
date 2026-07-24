from src.main import _parse_history_limit


def test_parse_history_limit_handles_invalid_input():
    assert _parse_history_limit("") == 10
    assert _parse_history_limit("not-a-number") == 10
    assert _parse_history_limit("0") == 1
    assert _parse_history_limit("500") == 200
    assert _parse_history_limit("25") == 25
