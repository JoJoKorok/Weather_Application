# Proxy Security and Render Configuration

The desktop client never receives the OpenWeatherMap API key. It calls the
FastAPI proxy, and the proxy reads `OPENWEATHER_API_KEY` from Render.

## Protection layers

The proxy applies all of these controls:

- Normalized successful responses are cached for 10 minutes by default.
- Concurrent requests for the same location share one upstream call.
- Public traffic is limited independently by IP and anonymous installation ID.
- A normalized location has its own cache-miss limit.
- Public traffic cannot consume the reserved owner portion of hourly/daily budgets.
- Global upstream budgets are reserved atomically in SQLite.
- Rate-limit and query-lock registries have hard memory bounds.
- History endpoints are disabled unless explicitly enabled and always require an admin token.
- Aggregate usage statistics require an admin token.
- Emergency switches can stop all traffic or only new upstream calls.

An installation ID is an anonymous fairness mechanism, not authentication.
Attackers can invent IDs, which is why IP, query, cache, and global limits also apply.

## Generate private values

Run these commands locally and save each result in a password manager:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use separate values for:

- `TRUSTED_TOKENS`: your personal testing token.
- `ADMIN_TOKENS`: access to `/admin/stats` and optional history.
- `RATE_LIMIT_SALT`: hashes anonymous installation IDs inside rate-limit keys.

Never put these values in Git, `render.yaml`, documentation, or a distributed executable.

## Render deployment

The included `render.yaml` provides safe baseline values. In the Render dashboard,
configure the three private values above and `OPENWEATHER_API_KEY`.

The proxy remains publicly usable when `PROXY_TOKENS` is empty. Setting
`PROXY_TOKENS` converts it into an allow-list service, but a token embedded in a
public executable should not be considered secret.

### Free Render service

The cache and layered limits work while the instance is running. Render's free
filesystem is ephemeral, so SQLite quota counters reset after a spin-down,
restart, or deployment.

### Persistent Render service

Attach a Render persistent disk at:

```text
/opt/render/project/src/storage
```

Keep:

```text
WEATHER_DB_PATH=/opt/render/project/src/storage/weather_history.sqlite
PERSIST_BUDGETS=true
```

That preserves hourly/daily counters across restarts. A Render Key Value service
can be added later if the proxy needs multiple web-service instances.

## Personal testing

On your private computer only:

```powershell
$env:WEATHER_PROXY_TOKEN = "<value from TRUSTED_TOKENS>"
```

This enables the larger trusted allowance. To deliberately bypass a cached value:

```powershell
$env:WEATHER_FORCE_REFRESH = "true"
```

Cache bypass is ignored unless the Bearer token is in `TRUSTED_TOKENS`.

Clear the variables when finished:

```powershell
Remove-Item Env:WEATHER_PROXY_TOKEN
Remove-Item Env:WEATHER_FORCE_REFRESH
```

## Administration

Retrieve aggregate counters:

```powershell
$headers = @{ Authorization = "Bearer <ADMIN_TOKENS value>" }
Invoke-RestMethod `
  -Uri "https://weather-application-c7bh.onrender.com/admin/stats" `
  -Headers $headers
```

The response contains cache and upstream totals but never API keys, tokens, raw
IP addresses, or installation IDs.

History endpoints default to disabled. If they are genuinely needed, set
`HISTORY_ENDPOINTS_ENABLED=true`; `/history` and `/search` still require an admin token.

## Emergency controls

Stop only new OpenWeatherMap calls while continuing to serve cached results:

```text
UPSTREAM_CALLS_ENABLED=false
```

Put the entire weather endpoint into maintenance mode:

```text
SERVICE_ENABLED=false
```

Both settings are Render environment variables and require a service restart or
redeploy to take effect.

## Recommended production defaults

| Setting | Default |
| --- | ---: |
| `RATE_LIMIT_PER_MIN` | 10 |
| `TRUSTED_RATE_LIMIT_PER_MIN` | 120 |
| `QUERY_RATE_LIMIT_PER_10_MIN` | 2 |
| `TRUSTED_QUERY_RATE_LIMIT_PER_10_MIN` | 30 |
| `CACHE_TTL_SECONDS` | 600 |
| `HOURLY_LIMIT` | 250 |
| `DAILY_LIMIT` | 1000 |
| `RESERVE_PERCENT` | 20 |

Choose hourly and daily limits below the allowance of the configured
OpenWeatherMap plan.
