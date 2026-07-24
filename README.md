# Weather Application

A multilingual command-line weather application that retrieves current conditions through a secure proxy, supports city or postal-code searches, and keeps a private local history.

The project separates the user-facing client from a lightweight FastAPI proxy so OpenWeatherMap credentials never need to ship with the application.

## Features

- Current weather by city and country
- Current weather by postal/ZIP code and country
- ISO 3166 country resolution with fuzzy matching
- English and Japanese output
- Searchable local SQLite history
- Optional proxy Bearer-token authentication
- Cached and coalesced weather requests
- Layered per-IP, installation, query, hourly, and daily limits
- Reserved capacity and trusted personal testing
- Installable Python command and standalone Windows executable

## Documentation

See [Weather Application Documentation](./DOCUMENTATION.md) for the architecture, request flow, environment variables, storage, and deployment model.

See [Proxy Security and Render Configuration](./SECURITY.md) before publishing
the executable or deploying proxy changes.

## Run from source

```powershell
.\setup.ps1
.\run.ps1
```

The client uses the hosted proxy by default. To run the proxy locally:

```powershell
$env:OPENWEATHER_API_KEY = "your-key"
.\.venv\Scripts\uvicorn proxy.server:app --host 127.0.0.1 --port 8000
$env:WEATHER_PROXY_URL = "http://127.0.0.1:8000/weather"
.\run.ps1
```

## Install as a command

```powershell
.\.venv\Scripts\pip install -e .
weather-app
```

## Build a Windows application

```powershell
.\.venv\Scripts\pip install -r requirements-dev.txt
.\build.ps1 -Clean
```

The standalone executable is created at `dist\WeatherApplication.exe`. It remains a console application; a graphical interface can later reuse the tested weather and history modules.

## Test

```powershell
.\tests\run_test.ps1 -q
```

## Configuration

| Variable | Used by | Purpose |
| --- | --- | --- |
| `WEATHER_PROXY_URL` | Client | Override the hosted `/weather` endpoint |
| `WEATHER_PROXY_TOKEN` | Client | Optional Bearer token sent to the proxy |
| `WEATHER_FORCE_REFRESH` | Client | Trusted-only cache bypass for development |
| `OPENWEATHER_API_KEY` | Proxy | Private OpenWeatherMap API key |
| `PROXY_TOKENS` | Proxy | Optional comma-separated allowed tokens |
| `TRUSTED_TOKENS` | Proxy | Private owner tokens with a larger allowance |
| `ADMIN_TOKENS` | Proxy | Private tokens for statistics and optional history |
| `RATE_LIMIT_PER_MIN` | Proxy | Requests allowed per client each minute |
| `HOURLY_LIMIT` | Proxy | Global upstream calls allowed per UTC hour |
| `DAILY_LIMIT` | Proxy | Global requests allowed per UTC day |
| `RESERVE_PERCENT` | Proxy | Capacity reserved for trusted owner tokens |
| `CACHE_TTL_SECONDS` | Proxy | Successful weather response cache lifetime |
| `WEATHER_DB_PATH` | Proxy | Override proxy history database location |
| `SERVICE_ENABLED` | Proxy | Emergency switch for the weather endpoint |
| `UPSTREAM_CALLS_ENABLED` | Proxy | Stop refreshes while retaining cached results |

## License

GPL-3.0-or-later. See [LICENSE](./LICENSE).
