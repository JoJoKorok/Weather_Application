import builtins

from src.functions.det_questions import location_data



def test_location_data_city_path(monkeypatch):
    # Simulates picking the city path and selecting a country.

    inputs = iter([
        "London",   # city prompt
        "GB",       # country prompt
        "y"         # confirmation
    ])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))

    city, postal, country = location_data(interactive=True)

    assert city == "London"
    assert not postal
    assert country.upper() == "GB"


def test_location_data_postal_path(monkeypatch):
    # Simulates pressing Enter for city, then entering a postal code.

    inputs = iter([
        "",         # city prompt (blank -> postal flow)
        "22304",    # postal prompt
        "US",       # country prompt
        "y"         # confirmation
    ])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))

    city, postal, country = location_data(interactive=True)

    assert not city
    assert postal == "22304"
    assert country.upper() == "US"
