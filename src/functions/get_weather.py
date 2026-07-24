import os

import requests
from src.data.client_identity import get_or_create_client_id
from src.data.i18n import TEXT, jp_description_from_weather
from src.data.local_history import init_db, log_weather, fetch_history, search_history


def _t(lang: str, key: str, default: str) -> str:
    # Safe translation getter.
    # Falls back to English, then to the provided default.

    lang = (lang or "en").strip().lower()

    if lang in TEXT and key in TEXT[lang]:
        return TEXT[lang][key]

    if "en" in TEXT and key in TEXT["en"]:
        return TEXT["en"][key]

    return default


def _get_proxy_url() -> str:
    # Pulls the proxy URL from environment variables.
    # This keeps the repo clean (no hardcoded private endpoints).

    DEFAULT_PROXY_URL = "https://weather-application-c7bh.onrender.com/weather"

    proxy_url = os.getenv("WEATHER_PROXY_URL", "").strip()
    return proxy_url if proxy_url else DEFAULT_PROXY_URL


def _get_proxy_headers() -> dict:
    # Optional Bearer token for proxy auth.

    headers = {"X-Weather-Client": get_or_create_client_id()}
    token = os.getenv("WEATHER_PROXY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if os.getenv("WEATHER_FORCE_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}:
        headers["Cache-Control"] = "no-cache"
    return headers


def _print_response_source(response, lang: str) -> None:
    if response.headers.get("X-Weather-Cache") != "HIT":
        return

    age = response.headers.get("X-Weather-Cache-Age", "0")
    print(_t(lang, "cached_result", "Cached result ({seconds} seconds old).").format(seconds=age))


def _print_http_error(response, http_err, lang: str, not_found_message: str) -> None:
    if response.status_code == 404:
        print(not_found_message)
    elif response.status_code == 401:
        print(_t(lang, "unauthorized_proxy", "Error: Unauthorized proxy request. Check proxy token."))
    elif response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            print(
                _t(
                    lang,
                    "rate_limited_retry",
                    "Request limit reached. Try again in about {seconds} seconds.",
                ).format(seconds=retry_after)
            )
        else:
            print(_t(lang, "rate_limited", "Error: Proxy rate limit exceeded. Please try again later."))
    elif response.status_code == 503:
        print(_t(lang, "service_paused", "Live weather is temporarily unavailable."))
    else:
        print(f"{_t(lang, 'http_error', 'HTTP error occurred')}: {http_err}")


def _normalize_lang(lang: str) -> str:
    # Only allow the languages we support.
    # Everything else falls back to English.

    lang = (lang or "en").strip().lower()
    return lang if lang in ("en", "ja") else "en"


def _extract_description(weather_data: dict, lang: str) -> str | None:
    # Grabs a description from the API response.
    # If lang=ja, we prefer our ID->JP map so it's consistent.

    weather0 = (weather_data.get("weather") or [{}])[0] or {}
    desc = weather0.get("description")

    if lang == "ja":
        mapped = jp_description_from_weather(weather0)
        return mapped or desc

    return desc


def get_weather_by_city_name(city_name, country_code, lang: str = "en"):
    # Gets weather from the proxy by city name.
    # Also logs the result locally so history/search work even if the proxy goes down later.

    init_db()

    BASE_URL = _get_proxy_url()
    lang = _normalize_lang(lang)

    params = {
        "city": city_name,
        "country": country_code.lower(),
        "units": "metric",
        "lang": lang,
    }

    headers = _get_proxy_headers()

    try:
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=120)
        response.raise_for_status()

        weather_data = response.json()
        _print_response_source(response, lang)

        main_data = weather_data.get("main", {}) or {}
        area_name = weather_data.get("name")
        temperature = main_data.get("temp")
        humidity = main_data.get("humidity")
        wind_speed = (weather_data.get("wind") or {}).get("speed")
        description = _extract_description(weather_data, lang)

        # Store the exact description we displayed (JP-mapped if needed).
        log_weather(
            query_type="city",
            city=(city_name or "").strip() or None,
            postal=None,
            country=(country_code or "").strip().upper() or "US",
            units="metric",
            lang=lang,
            description_override=description,
            data=weather_data,
        )

        if temperature is not None and description is not None:
            print(f"\n{_t(lang, 'weather_in', 'Weather in')} {area_name}:")
            print(f"    {_t(lang, 'temp_label', 'Temperature')}: {temperature}°C")
            print(f"    {_t(lang, 'humidity_label', 'Humidity')}: {humidity}%")
            print(f"    {_t(lang, 'wind_label', 'Wind Speed')}: {wind_speed} m/s")
            print(f"    {_t(lang, 'desc_label', 'Description')}: {description.capitalize() if isinstance(description, str) else description}")
        else:
            print(f"{_t(lang, 'incomplete_city', 'Could not retrieve complete weather data for')} {city_name}")

    except requests.exceptions.HTTPError as http_err:
        _print_http_error(
            response,
            http_err,
            lang,
            f"{_t(lang, 'city_not_found', 'Error: City not found')}: '{city_name}'.",
        )
    except requests.exceptions.RequestException as req_err:
        print(f"{_t(lang, 'request_error', 'An error occurred during the API request')}: {req_err}")


def get_weather_by_postal_code(postal_code, country_code="us", lang: str = "en"):
    # Gets weather from the proxy by postal code.
    # Also logs the result locally for history/search.

    init_db()

    BASE_URL = _get_proxy_url()
    lang = _normalize_lang(lang)

    params = {
        "postal": postal_code,
        "country": country_code.lower(),
        "units": "metric",
        "lang": lang,
    }

    headers = _get_proxy_headers()

    try:
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=120)
        response.raise_for_status()

        weather_data = response.json()
        _print_response_source(response, lang)

        main_data = weather_data.get("main", {}) or {}
        area_name = weather_data.get("name")
        temperature = main_data.get("temp")
        humidity = main_data.get("humidity")
        wind_speed = (weather_data.get("wind") or {}).get("speed")
        description = _extract_description(weather_data, lang)

        # Store the exact description we displayed (JP-mapped if needed).
        log_weather(
            query_type="postal",
            city=None,
            postal=(postal_code or "").strip() or None,
            country=(country_code or "").strip().upper() or "US",
            units="metric",
            lang=lang,
            description_override=description,
            data=weather_data,
        )

        if temperature is not None and description is not None:
            print(f"\n\n{_t(lang, 'weather_in', 'Weather in')} {area_name} ({postal_code}, {country_code.upper()}):")
            print(f"    {_t(lang, 'temp_label', 'Temperature')}: {temperature}°C")
            print(f"    {_t(lang, 'humidity_label', 'Humidity')}: {humidity}%")
            print(f"    {_t(lang, 'wind_label', 'Wind Speed')}: {wind_speed} m/s")
            print(f"    {_t(lang, 'desc_label', 'Description')}: {description.capitalize() if isinstance(description, str) else description}")
        else:
            print(f"{_t(lang, 'incomplete_postal', 'Incomplete weather data retrieved for')}: {postal_code}, {country_code.upper()}")

    except requests.exceptions.HTTPError as http_err:
        _print_http_error(
            response,
            http_err,
            lang,
            (
                f"{_t(lang, 'postal_not_found', 'Error: Postal code not found')}: "
                f"'{postal_code}, {country_code.upper()}'."
            ),
        )
    except requests.exceptions.RequestException as req_err:
        print(f"{_t(lang, 'request_error', 'An error occurred during the API request')}: {req_err}")


def get_local_history(limit: int = 25) -> dict:
    # Local history (SQLite in LocalAppData).
    # No network call needed.

    init_db()
    return {"items": fetch_history(limit=limit)}


def search_local_history(q: str, limit: int = 25) -> dict:
    # Local history search (SQLite in LocalAppData).
    # No network call needed.

    init_db()
    return {"items": search_history(q=q, limit=limit)}
