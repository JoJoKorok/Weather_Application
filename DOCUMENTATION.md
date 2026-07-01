# Weather Application: How This Project Works

Joseph Bekele

## Introduction

The reason this weather application exists is that it is meant to be a small command-line program that can ask a person for a place, send that place to a weather service, and then return the current weather in a readable format. It is not only a direct OpenWeatherMap script though. The project was built with a separate proxy service, and that proxy is important because it protects the private OpenWeatherMap API key and controls how often requests can be made.

This is the main thing to remember about the project. OpenWeatherMap is where the weather data comes from, but OpenWeatherMap is not the website that is being used to hide the sensitive information or enforce the request limits. The website/service being used for that part is Render. In the client code, the default proxy URL is:

```text
https://weather-application-c7bh.onrender.com/weather
```

That URL is in `src/functions/get_weather.py`. Because it ends in `onrender.com`, it shows that the FastAPI proxy was intended to be hosted on Render. Render is the part that stores sensitive environment variables such as the OpenWeatherMap key and optional proxy tokens. The local Python client sends a request to the Render proxy, and then the Render proxy sends the real request to OpenWeatherMap.

## Background of the Application

This project is a Python weather application with two main parts. The first part is the client, which is the command-line program that a user actually runs. The second part is the proxy, which is the small FastAPI web server that sits between the client and OpenWeatherMap.

The client does the human-facing work. It asks what language to use, asks for either a municipality name or a postal code, asks what country the location is in, and then prints the weather. It also stores the successful weather results in a local SQLite database so that later the user can look at old weather searches or search through them.

The proxy does the private and network-facing work. It receives the city or postal code from the client, adds the OpenWeatherMap API key from its own environment variables, checks whether the request is allowed, and then forwards the request to OpenWeatherMap. This separation matters because if the API key were inside the desktop client, anybody with the source code or executable could see it. By keeping the API key in Render environment variables, the client can still get weather data without exposing the key.

## Project Structure

The main project files are organized like this:

```text
weather_application/
  src/
    main.py
    functions/
      det_questions.py
      get_weather.py
    data/
      country_codes.py
      i18n.py
      local_history.py
  proxy/
    server.py
    requirements.txt
    weather_history.sqlite
  tests/
    conftest.py
    test_dependencies.py
    test_get_weather_client.py
    test_input_flow.py
    test_proxy_weather.py
    test_resolve_country_prompt.py
  requirements.txt
  requirements-dev.txt
  setup.ps1
  run.ps1
  README.md
  WeatherApp.spec
```

The `src` folder is the actual client application. The `proxy` folder is the API proxy. The `tests` folder contains pytest tests for the input flow, country selection, proxy behavior, and client weather behavior. The `.spec` files are for PyInstaller builds, meaning the project had work done toward packaging the app into Windows executables.

## How the Client Starts

The client starts in `src/main.py`. When run normally, the file does the following:

1. It asks for the language, either `en` or `ja`.
2. It initializes the local SQLite history database.
3. It asks the user for a city name or postal code.
4. It asks the user for a country.
5. It calls the proxy to get weather data.
6. It prints the weather information.
7. It gives the user a small history/search menu before quitting.

The application can be run from the project root with:

```powershell
.\setup.ps1
.\run.ps1
```

The setup script creates a `.venv` virtual environment and installs the requirements. The run script uses that virtual environment and runs `src/main.py`.

It can also be run directly after setup with:

```powershell
.\.venv\Scripts\python src\main.py
```

or:

```powershell
.\.venv\Scripts\python -m src.main
```

## Location Input and Country Selection

The location question logic is in `src/functions/det_questions.py`. The function `location_data()` returns three values:

```python
city, postal, country
```

The application first asks for a municipality name. If the user enters a city, it uses the city path. If the user presses Enter without typing a city, the program asks for a postal or ZIP code instead.

The country selection is handled by `src/data/country_codes.py`. This file uses the `pycountry` package so the user does not have to memorize exact country codes. A user can type a country name like `United States`, an alpha-2 code like `US`, or an alpha-3 code like `USA`. If the input is not exact, the code can use fuzzy matching and show possible country matches.

This matters because OpenWeatherMap expects city and postal code searches to include a country code. For example, a postal code by itself can be ambiguous between different countries, so the app stores and sends the country with the search.

## Weather Request Flow

The weather client functions live in `src/functions/get_weather.py`. There are two main functions:

```python
get_weather_by_city_name(city_name, country_code, lang="en")
get_weather_by_postal_code(postal_code, country_code="us", lang="en")
```

Both functions build a request to the proxy, not directly to OpenWeatherMap. The default proxy URL is:

```python
DEFAULT_PROXY_URL = "https://weather-application-c7bh.onrender.com/weather"
```

The user can override that with an environment variable:

```powershell
$env:WEATHER_PROXY_URL = "http://127.0.0.1:8000/weather"
```

This override is useful if the proxy is being run locally during development. The client can also send a proxy token if this environment variable is set:

```powershell
$env:WEATHER_PROXY_TOKEN = "your-token-here"
```

If `WEATHER_PROXY_TOKEN` exists, the client sends it as a Bearer token in the `Authorization` header. If it does not exist, the client sends no token.

For a city search, the client sends parameters like:

```text
city=London
country=gb
units=metric
lang=en
```

For a postal search, it sends parameters like:

```text
postal=22304
country=us
units=metric
lang=en
```

The proxy then converts those into the OpenWeatherMap request format. The important part is that the OpenWeatherMap API key is added by the proxy, not by the client.

## Proxy, Rate Limiting, and Sensitive Information

The proxy is meant to be a FastAPI application in `proxy/server.py`. In the committed version of the project, the proxy has these routes:

```text
GET /
GET /weather
GET /history
GET /search
```

The `/` route is a simple health check. The `/weather` route is the main endpoint used by the client. The `/history` and `/search` routes existed in the committed proxy version for viewing or searching proxy-side request history.

The proxy reads sensitive settings from environment variables:

```text
OPENWEATHER_API_KEY
PROXY_TOKENS
RATE_LIMIT_PER_MIN
DAILY_LIMIT
WEATHER_DB_PATH
```

`OPENWEATHER_API_KEY` is the private OpenWeatherMap key. This should be stored on Render as an environment variable and should not be written into the source code.

`PROXY_TOKENS` is an optional comma-separated list of allowed Bearer tokens. If this variable is empty, the proxy does not require a token. If it has values, then the client must send one of those values through `WEATHER_PROXY_TOKEN`.

`RATE_LIMIT_PER_MIN` controls how many requests are allowed per minute. The proxy uses an in-memory dictionary of timestamp queues, so each token or IP address gets its own recent-request list. When the list becomes too long inside the 60-second window, the proxy returns HTTP 429.

`DAILY_LIMIT` was added to control the total number of requests for all users combined in a UTC day. This is also tracked in memory, which means it can reset if the Render service restarts. It is still useful as a simple protection layer, but it is not the same as a permanent billing-safe counter in a database.

`WEATHER_DB_PATH` was used by the committed proxy version to control where proxy-side SQLite request history is saved. If not set, it defaults to `proxy/weather_history.sqlite`.

So, to answer the question plainly: the website being used for API rate limiting and for keeping sensitive information away from the client is Render, using the `weather-application-c7bh.onrender.com` proxy service. OpenWeatherMap is only the upstream weather data provider.

## OpenWeatherMap's Role

OpenWeatherMap is still important, but its role is narrower than it may first look. It is the external weather API that returns the actual temperature, humidity, wind speed, and weather description.

The OpenWeatherMap endpoint used by the proxy is:

```text
https://api.openweathermap.org/data/2.5/weather
```

The proxy sends either a city query:

```text
q=London,GB
```

or a postal query:

```text
zip=22304,US
```

It also sends:

```text
appid=<OPENWEATHER_API_KEY>
units=metric
lang=en or ja
```

OpenWeatherMap returns a JSON response. The proxy narrows that response down to the fields the client needs:

```text
name
sys
main
wind
weather
```

The client then prints the useful values from those fields.

## Local History

The current client-side history system is in `src/data/local_history.py`. This is separate from the proxy-side history that existed in the committed proxy version.

The local history database is SQLite. On Windows, it is stored under:

```text
%LOCALAPPDATA%\weather_application\weather_history.sqlite
```

If `LOCALAPPDATA` is not available, it falls back to:

```text
~/.weather_application/weather_history.sqlite
```

When a weather request succeeds, the client logs:

```text
created_utc
query_type
city
postal
country
units
lang
name
description
temp
humidity
wind_speed
raw_json
```

This is why the app can show history even after the weather request has already happened. It does not need to call the proxy just to show old searches. The local history menu in `src/main.py` lets the user show recent records or search by city, place name, or weather description.

## Language Support

The language strings are stored in `src/data/i18n.py`. The app supports English and Japanese through a simple dictionary called `TEXT`.

The client normalizes unsupported language input back to English. This is helpful because it prevents a bad language code from crashing the program.

There is also a `JP_WEATHER_ID` dictionary that maps OpenWeatherMap condition IDs to Japanese descriptions. This exists because weather APIs do not always return the exact translated description the application wants. Instead of relying only on the API's text, the client can use the weather condition ID and show a more consistent Japanese description.

One thing to watch for is encoding. If Japanese text looks like broken characters in a terminal, that may be a terminal encoding problem, or it may mean the file was saved incorrectly at some point. The intended idea is still simple: store all user-facing strings in one place so the rest of the app does not have repeated prompt text everywhere.

## Tests

The tests are written with pytest. They cover the most important behavior without needing to call the real OpenWeatherMap API.

`tests/test_dependencies.py` checks that the main dependencies can be imported.

`tests/test_input_flow.py` simulates user input for city and postal-code paths.

`tests/test_resolve_country_prompt.py` checks direct country code matching, country name matching, invalid matching, and confirmation behavior.

`tests/test_get_weather_client.py` replaces `requests.get()` with fake responses so the client can be tested without making real network calls.

`tests/test_proxy_weather.py` replaces `httpx.AsyncClient` with a fake async client so the proxy can be tested without calling OpenWeatherMap.

The test runner script is:

```powershell
.\tests\run_test.ps1
```

The tests expect the proxy to have the committed full proxy behavior, including a root route and a completed `/weather` route. That matters because the current archived working copy of `proxy/server.py` is not the same as the committed version.

## Current Archive State and Important Warning

There is an important state issue in the archive. The Git history shows that the committed version of `proxy/server.py` had the full proxy implementation. That committed version included:

```text
root health endpoint
OpenWeatherMap forwarding
Bearer-token security
per-minute rate limiting
daily global limiting
proxy-side SQLite history
history/search endpoints
```

However, the working copy of `proxy/server.py` saved in the zip is modified and incomplete. It removes the proxy-side database functions, removes the root/history/search endpoints, removes the daily limit, and ends before actually calling OpenWeatherMap or returning data.

There are also two clear bugs in that archived working file:

```python
auth.lower().startwith("bearer ")
```

should be:

```python
auth.lower().startswith("bearer ")
```

and:

```python
params["q"] = f"{city.strip(),{country}}"
```

should be:

```python
params["q"] = f"{city.strip()},{country}"
```

Because of this, if the proxy is run from the archived working file as-is, it should not be expected to work correctly. The remembered working version is in Git history at commit `4031eeb`, which is titled `Add proxy logging endpoints and request history`. Since `proxy/server.py` has uncommitted edits, restoring it from `HEAD` would discard those archived working-copy changes, so that should be done intentionally.

## Development Setup

The runtime dependencies are in `requirements.txt`:

```text
requests
pycountry
fastapi
uvicorn
httpx
```

The development dependencies are in `requirements-dev.txt`:

```text
pytest
pytest-asyncio
pytest-cov
anyio
black
ruff
mypy
httpx
fastapi
uvicorn
pyinstaller
```

The proxy dependencies are in `proxy/requirements.txt`:

```text
fastapi
uvicorn
httpx
```

To run the proxy locally, the intended command is:

```powershell
.\.venv\Scripts\uvicorn proxy.server:app --host 127.0.0.1 --port 8000
```

Then point the client to the local proxy:

```powershell
$env:WEATHER_PROXY_URL = "http://127.0.0.1:8000/weather"
```

The local proxy also needs:

```powershell
$env:OPENWEATHER_API_KEY = "your-openweathermap-key"
```

If testing token security locally, also set:

```powershell
$env:PROXY_TOKENS = "some-token"
$env:WEATHER_PROXY_TOKEN = "some-token"
```

The proxy reads `PROXY_TOKENS`; the client reads `WEATHER_PROXY_TOKEN`.

## Build and Release Notes

The project includes PyInstaller spec files:

```text
weather-cli.spec
WeatherApp.spec
WeatherApp_v0.2.0.spec
WeatherApp_v0.2.1.spec
```

The zip also included `build` and `dist` folders, which means executables had been generated before. Those folders are build outputs, not source code. The important source files are still the Python files under `src` and `proxy`.

The Git log shows version tags:

```text
v0.1.0
v0.2.1
```

The later work added Japanese language support, local history, search commands, and tests.

## File-by-File Explanation

`src/main.py` is the main entry point. It connects the input prompts, weather fetching, and local history menu together.

`src/functions/det_questions.py` collects the location information. It decides whether the user is using a city or postal code and asks for the country.

`src/functions/get_weather.py` talks to the proxy. It does not talk directly to OpenWeatherMap. It also prints weather output and logs successful results locally.

`src/data/country_codes.py` resolves country names and country codes using `pycountry`.

`src/data/i18n.py` stores English and Japanese text strings and the Japanese weather-condition mapping.

`src/data/local_history.py` creates and uses the local SQLite database under LocalAppData.

`proxy/server.py` is the intended FastAPI proxy, but the archived working copy is incomplete. The committed history contains the more complete version.

`tests/conftest.py` sets up import paths and test environment variables.

`tests/test_get_weather_client.py` tests client weather behavior with fake HTTP responses.

`tests/test_proxy_weather.py` tests proxy behavior with fake OpenWeatherMap responses.

`setup.ps1` creates the virtual environment and installs dependencies.

`run.ps1` runs the client after setup.

## Conclusion

This application is best understood as a command-line weather client plus a protective web proxy. The client handles input, output, country selection, language selection, and local history. The proxy handles the private OpenWeatherMap key, optional Bearer-token authorization, and rate limiting.

The main website/service that is being used for the protection layer is Render, shown by the default `onrender.com` proxy URL. OpenWeatherMap is only the data source. The sensitive information is meant to live in environment variables on Render, while the desktop client only knows the proxy URL and, optionally, a proxy token.

The most important thing to remember before continuing development is that the saved working copy of `proxy/server.py` is not in a clean working state. The committed history has the version that better matches the tests and the README. If the goal is to make the project run again, the first practical step should be restoring or repairing `proxy/server.py`, then running the pytest suite, then deciding whether local history should stay only on the client or also exist on the proxy.
