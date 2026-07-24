import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def _local_appdata_dir() -> Path:
    # Windows Local AppData location.
    # If LOCALAPPDATA isn't set for some reason, fall back to user home.

    base = os.getenv("LOCALAPPDATA", "").strip()
    if base:
        return Path(base) / "weather_application"

    return Path.home() / ".weather_application"


def db_path() -> Path:
    # Full DB path for local history.

    return _local_appdata_dir() / "weather_history.sqlite"


def _connect() -> sqlite3.Connection:
    # Opens SQLite connection, ensures folder exists.

    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    # Creates the table if it doesn't exist yet.

    conn = _connect()
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
                lang TEXT NOT NULL,
                name TEXT,
                description TEXT,
                temp REAL,
                humidity INTEGER,
                wind_speed REAL,
                raw_json TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_created ON weather_history(created_utc);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_name ON weather_history(name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_desc ON weather_history(description);")
        conn.commit()
    finally:
        conn.close()


def log_weather(
    *,
    query_type: str,
    city: str | None,
    postal: str | None,
    country: str,
    units: str,
    lang: str,
    description_override: str | None = None,
    data: dict,
) -> None:
    # Inserts one successful weather call into local SQLite.

    created_utc = datetime.now(timezone.utc).isoformat()

    main = data.get("main", {}) or {}
    weather0 = (data.get("weather") or [{}])[0] or {}

    name = data.get("name")

    # If the caller gives an override, use it.
    # This lets us store JP-mapped descriptions even if OpenWeather returns English.
    description = (description_override or weather0.get("description"))

    temp = main.get("temp")
    humidity = main.get("humidity")
    wind_speed = (data.get("wind") or {}).get("speed")

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO weather_history (
                created_utc, query_type, city, postal, country, units, lang,
                name, description, temp, humidity, wind_speed, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                created_utc,
                query_type,
                city,
                postal,
                country,
                units,
                (lang or "en").strip().lower(),
                name,
                description,
                temp,
                humidity,
                wind_speed,
                # We wrap the response so we can store a little bit of metadata too.
                json.dumps({"lang": (lang or "en").strip().lower(), "data": data}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_history(limit: int = 25) -> list[dict]:
    # Returns last N entries.

    limit = max(1, min(int(limit), 200))

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT created_utc, query_type, city, postal, country, units, lang,
                   name, description, temp, humidity, wind_speed
            FROM weather_history
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_history(q: str, limit: int = 25) -> list[dict]:
    # Simple LIKE search on city/name/description.

    limit = max(1, min(int(limit), 200))
    query = (q or "").strip().lower()
    if not query:
        return []

    needle = f"%{query}%"

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT created_utc, query_type, city, postal, country, units, lang,
                   name, description, temp, humidity, wind_speed
            FROM weather_history
            WHERE
                lower(coalesce(city, '')) LIKE ?
                OR lower(coalesce(name, '')) LIKE ?
                OR lower(coalesce(description, '')) LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (needle, needle, needle, limit),
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()
