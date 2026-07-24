import asyncio
import hmac
import json
import os
import sqlite3
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request, Response


"""
Enviroment Pulling Configuration
"""

# My OpeanWeatherMap API Key variable within Working OS Enviroment
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


PROXY_MODE = os.getenv("PROXY_MODE", "production").strip().lower()
if PROXY_MODE not in {"production", "development", "testing"}:
    PROXY_MODE = "production"

SERVICE_ENABLED = _env_bool("SERVICE_ENABLED", True)
UPSTREAM_CALLS_ENABLED = _env_bool("UPSTREAM_CALLS_ENABLED", True)

# Takes env var and turns it into a set of allowed tokens.
PROXY_TOKENS = set(
    t.strip()
    for t in os.getenv("PROXY_TOKENS", "").split(",")
    if t.strip()
)

TRUSTED_TOKENS = set(
    token.strip()
    for token in os.getenv("TRUSTED_TOKENS", "").split(",")
    if token.strip()
)

# Public clients receive conservative limits. A private trusted token gets a
# larger interactive allowance and can use the quota reserve.
default_public_rate = "120" if PROXY_MODE == "development" else "10"
OPENWEATHER_RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", default_public_rate))
TRUSTED_RATE_LIMIT_PER_MIN = int(os.getenv("TRUSTED_RATE_LIMIT_PER_MIN", "120"))
QUERY_RATE_LIMIT_PER_10_MIN = int(os.getenv("QUERY_RATE_LIMIT_PER_10_MIN", "2"))

# Global upstream budgets. The reserve is available only to trusted tokens.
HOURLY_LIMIT = int(os.getenv("HOURLY_LIMIT", "250"))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "1000"))
RESERVE_PERCENT = max(0, min(int(os.getenv("RESERVE_PERCENT", "20")), 90))

# Cache successful upstream responses for repeated normalized queries.
default_cache_ttl = "30" if PROXY_MODE == "development" else "600"
CACHE_TTL_SECONDS = max(0, int(os.getenv("CACHE_TTL_SECONDS", default_cache_ttl)))
CACHE_MAX_ENTRIES = max(1, int(os.getenv("CACHE_MAX_ENTRIES", "500")))

# Tracks upstream usage for the current UTC hour/day.
_usage_hour = None
_usage_hour_count = 0
_usage_day = None          # e.g. "2025-12-31"
_usage_count = 0


def _enforce_upstream_budget(*, trusted: bool) -> None:
    global _usage_hour, _usage_hour_count, _usage_day, _usage_count

    now = datetime.now(timezone.utc)
    current_hour = now.strftime("%Y-%m-%dT%H")
    today = now.date().isoformat()

    if _usage_hour != current_hour:
        _usage_hour = current_hour
        _usage_hour_count = 0
    if _usage_day != today:
        _usage_day = today
        _usage_count = 0

    reserve_multiplier = 1.0 if trusted else (100 - RESERVE_PERCENT) / 100
    allowed_hourly = max(1, int(HOURLY_LIMIT * reserve_multiplier))
    allowed_daily = max(1, int(DAILY_LIMIT * reserve_multiplier))

    if _usage_hour_count >= allowed_hourly:
        raise HTTPException(
            status_code=429,
            detail="Protective hourly upstream allowance reached.",
            headers={"Retry-After": "3600"},
        )
    if _usage_count >= allowed_daily:
        raise HTTPException(
            status_code=429,
            detail="Protective daily upstream allowance reached.",
            headers={"Retry-After": "3600"},
        )

    _usage_hour_count += 1
    _usage_count += 1


# Stores the endpoint of OpenWeatherMap's API
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# Starts an instance of the FastAPI class, registering data routes
# 'univron' requires an object to run, in this case, 'app'
app = FastAPI()

# Maps a key to a deque of timestamps if the key doesn't exist.
_hits = defaultdict(deque)

# LRU-style response cache and per-query locks. Locks collapse simultaneous
# cache misses so only one request reaches OpenWeatherMap for a location.
_weather_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_query_locks: dict[str, asyncio.Lock] = {}


def _cache_key(
    *,
    city: str,
    postal: str,
    country: str,
    units: str,
    lang: str,
) -> str:
    query_type = "city" if city else "postal"
    query = city.casefold() if city else postal.casefold()
    return "|".join((query_type, query, country.casefold(), units, lang))


def _cache_get(key: str) -> tuple[dict, int] | None:
    entry = _weather_cache.get(key)
    if not entry:
        return None

    expires_at, data = entry
    now = time.monotonic()
    if expires_at <= now:
        _weather_cache.pop(key, None)
        return None

    _weather_cache.move_to_end(key)
    age = max(0, CACHE_TTL_SECONDS - int(expires_at - now))
    return data, age


def _cache_put(key: str, data: dict) -> None:
    if CACHE_TTL_SECONDS <= 0:
        return

    _weather_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, data)
    _weather_cache.move_to_end(key)
    while len(_weather_cache) > CACHE_MAX_ENTRIES:
        evicted_key, _ = _weather_cache.popitem(last=False)
        lock = _query_locks.get(evicted_key)
        if lock is not None and not lock.locked():
            _query_locks.pop(evicted_key, None)


def _weather_payload(data: dict) -> dict:
    return {
        "name": data.get("name"),
        "sys": data.get("sys"),
        "main": data.get("main"),
        "wind": data.get("wind"),
        "weather": data.get("weather"),
    }


"""
SQLite History Storage
"""

def _db_path() -> Path:
    # Figures out where the DB file should live.
    # Defaults to proxy/weather_history.sqlite

    raw = os.getenv("WEATHER_DB_PATH", "").strip()
    if raw:
        return Path(raw)

    return Path(__file__).resolve().parent / "weather_history.sqlite"


def _db_connect() -> sqlite3.Connection:
    # Opens a DB connection.
    # check_same_thread=False so it doesn't explode under ASGI threads.

    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _db_init() -> None:
    # Creates the table if it doesn't exist yet.

    conn = _db_connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc TEXT NOT NULL,
                query_type TEXT NOT NULL,
                city TEXT,
                postal TEXT,
                country TEXT NOT NULL,
                units TEXT NOT NULL,
                name TEXT,
                description TEXT,
                temp REAL,
                humidity INTEGER,
                wind_speed REAL,
                raw_json TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_history_created ON weather_history(created_utc);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_history_name ON weather_history(name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_history_desc ON weather_history(description);")
        conn.commit()
    finally:
        conn.close()


def _db_log(*, query_type: str, city: str | None, postal: str | None, country: str, units: str, data: dict) -> None:
    # Inserts one successful weather call into the DB.

    _db_init()
    created_utc = datetime.now(timezone.utc).isoformat()

    main = data.get("main", {}) or {}
    weather0 = (data.get("weather") or [{}])[0] or {}

    name = data.get("name")
    description = weather0.get("description")
    temp = main.get("temp")
    humidity = main.get("humidity")
    wind_speed = (data.get("wind") or {}).get("speed")

    conn = _db_connect()
    try:
        conn.execute(
            """
            INSERT INTO weather_history (
                created_utc, query_type, city, postal, country, units,
                name, description, temp, humidity, wind_speed, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                created_utc, query_type, city, postal, country, units,
                name, description, temp, humidity, wind_speed, json.dumps(data),
            )
        )
        conn.commit()
    finally:
        conn.close()


def _db_fetch_history(limit: int = 25) -> list[dict]:
    # Pulls the most recent N requests.

    _db_init()
    limit = max(1, min(int(limit), 200))

    conn = _db_connect()
    try:
        rows = conn.execute(
            """
            SELECT created_utc, query_type, city, postal, country, units,
                   name, description, temp, humidity, wind_speed
            FROM weather_history
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,)
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def _db_search(q: str, limit: int = 25) -> list[dict]:
    # Searches by city/name/description.
    # Uses LIKE so it's simple and doesn't need full-text extensions.

    _db_init()
    limit = max(1, min(int(limit), 200))
    needle = f"%{(q or '').strip().lower()}%"

    conn = _db_connect()
    try:
        rows = conn.execute(
            """
            SELECT created_utc, query_type, city, postal, country, units,
                   name, description, temp, humidity, wind_speed
            FROM weather_history
            WHERE
                lower(coalesce(city, '')) LIKE ?
                OR lower(coalesce(name, '')) LIKE ?
                OR lower(coalesce(description, '')) LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (needle, needle, needle, limit)
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


"""
Helper Functions
"""

# Function Definition that returns str or None
def _get_bearer_token(request: Request) -> str | None:

    # Looks for Authorization header, defaults to ""
    auth = request.headers.get("authorization", "")

    # Checks if header starts with "bearer ", case insensitive
    if auth.lower().startswith("bearer "):

        # Returns a split into a minimum of 2 parts, token section and removes and extra sections.
        return auth.split(" ", 1)[1].strip()

    # No valid Bearer format, returns None
    return None


# Function Definition that returns None
# key = str; idetifier per token or per IP
# limit = int; max allowed requests per minute
def _enforce_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:

    # Current UNIX time in seconds as a float
    now = time.time()

    # The earliest starting time within the last minute
    window_start = now - window_seconds

    # Retrieves the deque for this key
    # If missing, defaultdict(deque) creates an empty deque
    q = _hits[key]

    # While loop removing timestamps older than 60 from q
    # starts with q[0], oldest timestamp in q
    # Removes from the left of the deque (popleft())
    while q and q[0] < window_start:
        q.popleft()

    # Checks if the length of q is greater than or equal to the set limit.
    if len(q) >= limit:
        # Raises an exception for the standard "Too Many Requests." code number, 429.
        retry_after = max(1, int(q[0] + window_seconds - now))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )

    q.append(now)


def _token_matches(token: str | None, candidates: set[str]) -> bool:
    if not token:
        return False
    return any(hmac.compare_digest(token, candidate) for candidate in candidates)


"""
API Endpoint
"""

# Basic root endpoint for sanity checks and uptime monitors.
@app.get("/")
async def root():
    return {
        "status": "ok" if SERVICE_ENABLED else "maintenance",
        "mode": PROXY_MODE,
        "hint": "Use /weather",
    }


# Returns recent requests from the proxy DB.
# This endpoint uses the same token security rules as /weather.
@app.get("/history")
async def history(request: Request, limit: int = 25):

    token = _get_bearer_token(request)

    if PROXY_TOKENS:
        if not token or token not in PROXY_TOKENS:
            raise HTTPException(status_code=401, detail="Unauthorized")

    return {"items": _db_fetch_history(limit=limit)}


# Searches the history DB for city/name/description matches.
@app.get("/search")
async def search(request: Request, q: str, limit: int = 25):

    token = _get_bearer_token(request)

    if PROXY_TOKENS:
        if not token or token not in PROXY_TOKENS:
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not (q or "").strip():
        raise HTTPException(status_code=400, detail="q is required")

    return {"items": _db_search(q=q, limit=limit)}


# Decorator (function abstraction) for FastAPT to handle GET requests to "/weather".
@app.get("/weather")
async def weather(
    request: Request,
    response: Response,
    city: str | None = None,
    postal: str | None = None,
    country: str = "us",
    units: str = "metric",
    lang: str = "en",
):
    if not SERVICE_ENABLED:
        raise HTTPException(status_code=503, detail="Weather service is temporarily disabled.")

    # Checks if nothing is retrieved for secret key in env vars.
    if not OPENWEATHER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server missing OPENWEATHER_API_KEY",
        )

    # Extracts token from header
    token = _get_bearer_token(request)

    # Checks if an allowed token(s) has been configured
    # Raises 401 Exception, needing valid credentials.
    if PROXY_TOKENS:
        if not _token_matches(token, PROXY_TOKENS | TRUSTED_TOKENS):
            raise HTTPException(status_code=401, detail="Unauthorized")
    trusted = _token_matches(token, TRUSTED_TOKENS)

    city = (city or "").strip()
    postal = (postal or "").strip()
    country = (country or "").strip().upper()
    units = (units or "").strip().lower()
    lang = (lang or "").strip().lower()

    if bool(city) == bool(postal):
        raise HTTPException(status_code=400, detail="Provide exactly one of city or postal")
    if len(country) != 2 or not country.isalpha():
        raise HTTPException(status_code=400, detail="country must be an ISO alpha-2 code")
    if units not in {"standard", "metric", "imperial"}:
        raise HTTPException(status_code=400, detail="units must be standard, metric, or imperial")
    if lang not in {"en", "ja"}:
        raise HTTPException(status_code=400, detail="lang must be en or ja")

    # Assigns current client IP to 'client_ip'
    client_ip = request.client.host if request.client else "unknown"

    # Assigns key for rate limiting
    # If a token exists, it assigns it as rate limit/token
    # Otherwise, it assigns it as rate limit/IP
    rate_key = f"tok:{token}" if token else f"ip:{client_ip}"

    # Enactment of rate limit on current user, prevents spamming
    request_limit = TRUSTED_RATE_LIMIT_PER_MIN if trusted else OPENWEATHER_RATE_LIMIT_PER_MIN
    _enforce_rate_limit(rate_key, request_limit)

    key = _cache_key(city=city, postal=postal, country=country, units=units, lang=lang)
    cached = _cache_get(key)
    if cached:
        data, age = cached
        response.headers["X-Weather-Cache"] = "HIT"
        response.headers["X-Weather-Cache-Age"] = str(age)
        return _weather_payload(data)

    lock = _query_locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Another request might have filled the cache while this one waited.
        cached = _cache_get(key)
        if cached:
            data, age = cached
            response.headers["X-Weather-Cache"] = "HIT"
            response.headers["X-Weather-Cache-Age"] = str(age)
            return _weather_payload(data)

        if not UPSTREAM_CALLS_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Live weather refreshes are temporarily disabled.",
            )

        # Limit cache-miss traffic for one normalized location, then consume
        # the appropriate public or trusted portion of the global budgets.
        _enforce_rate_limit(
            f"query:{key}",
            QUERY_RATE_LIMIT_PER_10_MIN,
            window_seconds=600,
        )
        _enforce_upstream_budget(trusted=trusted)

        params = {
            "appid": OPENWEATHER_API_KEY,
            "units": units,
            "lang": lang,
        }
        if city:
            params["q"] = f"{city},{country}"
        else:
            params["zip"] = f"{postal},{country}"

        try:
            async with httpx.AsyncClient(timeout=8) as client_http:
                upstream_response = await client_http.get(OPENWEATHER_URL, params=params)
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Weather provider timed out") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Weather provider unavailable") from exc

        if upstream_response.status_code != 200:
            try:
                detail = upstream_response.json()
            except Exception:
                detail = upstream_response.text
            raise HTTPException(status_code=upstream_response.status_code, detail=detail)

        data = upstream_response.json()
        _cache_put(key, data)
        _db_log(
            query_type="city" if city else "postal",
            city=city or None,
            postal=postal or None,
            country=country,
            units=units,
            data=data,
        )

        response.headers["X-Weather-Cache"] = "MISS"
        response.headers["X-Weather-Cache-Age"] = "0"
        return _weather_payload(data)
