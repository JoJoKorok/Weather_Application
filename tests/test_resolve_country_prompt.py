import builtins

from src.data.country_codes import prompt_country_code, resolve_country



def test_resolve_country_alpha2():
    # Checks alpha-2 direct match (ex: "US")
    best, candidates = resolve_country("US")
    assert best is not None
    assert best.alpha_2 == "US"
    assert len(candidates) >= 1


def test_resolve_country_alpha3():
    # Checks alpha-3 direct match (ex: "USA")
    best, candidates = resolve_country("USA")
    assert best is not None
    assert best.alpha_2 == "US"


def test_resolve_country_exact_name():
    # Checks exact country name match (case-insensitive)
    best, candidates = resolve_country("japan")
    assert best is not None
    assert best.alpha_2 == "JP"


def test_resolve_country_invalid_no_fuzzy():
    # If fuzzy is off, nonsense should return (None, [])
    best, candidates = resolve_country("NOT_A_REAL_COUNTRY_12345", allow_fuzzy=False)
    assert best is None
    assert candidates == []


def test_prompt_country_code_happy_path(monkeypatch):
    # Simulates: user types "United States" then confirms "y"
    inputs = iter(["United States", "y"])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))

    code = prompt_country_code(confirm=True, allow_fuzzy=True)
    assert code == "US"


def test_prompt_country_code_reject_then_accept(monkeypatch, capsys):
    # Simulates: user rejects first choice, then accepts second
    inputs = iter(["United States", "n", "Japan", "y"])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))

    code = prompt_country_code(confirm=True, allow_fuzzy=True)
    assert code == "JP"

    out = capsys.readouterr().out
    assert "Okay" in out
