from src.functions.det_questions import location_data
from src.functions.get_weather import (
    get_weather_by_city_name,
    get_weather_by_postal_code,
    get_local_history,
    search_local_history,
)
from src.data.local_history import init_db
from src.data.i18n import TEXT


def _t(lang: str, key: str, default: str) -> str:
    # Small helper so main doesn't crash if a key is missing.

    lang = (lang or "en").strip().lower()

    if lang in TEXT and key in TEXT[lang]:
        return TEXT[lang][key]

    if "en" in TEXT and key in TEXT["en"]:
        return TEXT["en"][key]

    return default


def _print_history(items: list[dict], lang: str) -> None:
    # Prints history in a readable format (not raw JSON).

    if not items:
        print(_t(lang, "no_history", "\nNo history found yet.\n"))
        return

    print(_t(lang, "history_title", "\n--- Local History ---"))

    for row in items:
        created = row.get("created_utc")
        query_type = row.get("query_type")
        city = row.get("city")
        postal = row.get("postal")
        country = row.get("country")
        name = row.get("name")
        desc = row.get("description")
        temp = row.get("temp")

        # Keeps the query display simple.
        query = city or postal or "?"

        print(f"[{created}] {query_type}:{query} ({country}) -> {name} | {temp}° | {desc}")

    print(_t(lang, "history_footer", "---------------------\n"))


def _parse_history_limit(raw: str, default: int = 10) -> int:
    value = (raw or "").strip()
    if not value:
        return default

    try:
        return max(1, min(int(value), 200))
    except ValueError:
        return default


def main() -> int:
    """Run the interactive weather client."""

    # Pick a language for prompts/output.
    # Default is English if the user types something unexpected.
    lang = input(_t("en", "language_prompt", "Language? [en/ja] (default en): ")).strip().lower()
    if lang not in ("en", "ja"):
        lang = "en"

    # Ensure our local history DB exists before we do anything.
    # This DB is stored in LocalAppData so it's free + works offline.
    init_db()

    # Location prompts should match the selected language.
    city, postal, country = location_data(interactive=True, lang=lang)

    # Fetch weather from the proxy (still metric).
    if postal:
        get_weather_by_postal_code(postal, country_code=country, lang=lang)
    else:
        get_weather_by_city_name(city, country_code=country, lang=lang)

    # History/search menu is local-only (no proxy needed).
    while True:
        choice = input(_t(lang, "history_prompt", "\n[h]istory, [s]earch, or press Enter to quit: ")).strip().lower()

        if not choice:
            break

        if choice in ("h", "history"):
            limit_raw = input(_t(lang, "history_count", "How many entries? (default 10): ")).strip()
            limit = _parse_history_limit(limit_raw)

            result = get_local_history(limit=limit)
            _print_history(result.get("items", []), lang=lang)

        elif choice in ("s", "search"):
            q = input(_t(lang, "search_prompt", "Search text (ex: 'rain', 'Tokyo'): ")).strip()
            if not q:
                print(_t(lang, "search_blank", "Search text can't be blank."))
                continue

            result = search_local_history(q=q, limit=25)
            _print_history(result.get("items", []), lang=lang)

        else:
            print(_t(lang, "unknown_option", "Unknown option. Use 'h', 's', or Enter."))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
