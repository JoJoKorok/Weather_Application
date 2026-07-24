import json
import os
import sqlite3
import time
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request


"""
Enviroment Pulling Configuration
"""

# My OpeanWeatherMap API Key variable within Working OS Enviroment
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Takes env var and turns it into a set of allowed tokens.
PROXY_TOKENS = set(
    t.strip()
    for t in os.getenv("PROXY_TOKENS", "").split(",")
    if t.strip()
)

# Limits API calls allowed in env var, or defaults to 60 per minute.
OPENWEATHER_RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))

# Global daily limit for ALL users combined
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "1000"))

# Tracks usage for the current UTC day
_usage_day = None          # e.g. "2025-12-31"
_usage_count = 0


def _enforce_daily_limit() -> None:
    global _usage_day, _usage_count

    # Uses UTC date so it’s consistent regardless of server location
    today = datetime.now(timezone.utc).date().isoformat()

    # Resets counter when the date changes
    if _usage_day != today:
        _usage_day = today
        _usage_count = 0

    # Blocks if the global limit is reached
    if _usage_count >= DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached ({DAILY_LIMIT} requests/day). Try again tomorrow."
        )

    # Counts this request
    _usage_count += 1


# Stores the endpoint of OpenWeatherMap's API
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# Starts an instance of the FastAPI class, registering data routes
# 'univron' requires an object to run, in this case, 'app'
app = FastAPI()

# Maps a key to a deque of timestamps if the key doesn't exist.
_hits = defaultdict(deque)


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
def _enforce_rate_limit(key: str, limit: int) -> None:

    # Current UNIX time in seconds as a float
    now = time.time()

    # The earliest starting time within the last minute
    window_start = now - 60

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
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    q.append(now)


"""
API Endpoint
"""

# Basic root endpoint for sanity checks and uptime monitors.
@app.get("/")
async def root():
    return {"status": "ok", "hint": "Use /weather"}


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
    city: str | None = None,
    postal: str | None = None,
    country: str = "us",
    units: str = "metric",
    lang: str = "en",
):
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
        if not token or token not in PROXY_TOKENS:
            raise HTTPException(status_code=401, detail="Unauthorized")

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
    _enforce_rate_limit(rate_key, OPENWEATHER_RATE_LIMIT_PER_MIN)

    # Count only authenticated, valid requests against the global allowance.
    _enforce_daily_limit()

    # Parameters for OpenWeather API request
    params = {
        "appid": OPENWEATHER_API_KEY,
        "units": units,
        "lang": lang,
    }

    # Uses city search if provided
    if city:
        params["q"] = f"{city},{country}"

    # Uses postal search if provided
    elif postal:
        params["zip"] = f"{postal},{country}"
    
    
    # Calls OpenWeatherMap with an async HTTP client with an 8-second timeout.
    try:
        async with httpx.AsyncClient(timeout=8) as client_http:
            response = await client_http.get(OPENWEATHER_URL, params=params)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Weather provider timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Weather provider unavailable") from exc

    # Checks OpenWeatherMap Call response code for failure codes.
    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text

        raise HTTPException(
            status_code=response.status_code,
            detail=detail
        )

    # Parses response body into a dict/list structure.
    data = response.json()

    # Logs the successful call into SQLite history.
    _db_log(
        query_type="city" if city else "postal",
        city=city or None,
        postal=postal or None,
        country=country,
        units=units,
        data=data,
    )

    # Returns a dict with all nessecary fields for client.
    # FastAPI serializes this dict to a JSON for HTTP response automatically.
    return {
        "name": data.get("name"),
        "sys": data.get("sys"),
        "main": data.get("main"),
        "wind": data.get("wind"),
        "weather": data.get("weather"),
    }
