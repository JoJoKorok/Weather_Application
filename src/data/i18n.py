"""
Simple i18n strings for the CLI.

Goal:
- Keep it lightweight (no extra libs)
- Keep strings centralized
- Avoid KeyError crashes (always have fallbacks)
"""

TEXT = {
    "en": {
        # Language selection
        "language_prompt": "Language? [en/ja] (default en): ",

        # Location prompts
        "enter_city_or_postal": "Enter a municipality name or press Enter to use a postal code: ",
        "enter_postal": "Enter a postal/ZIP code: ",

        # Country prompts
        "enter_country": "Enter country (name, alpha-2, or alpha-3): ",
        "no_country_found": "No country found. Try 'United States', 'US', 'USA', 'Japan', 'JP', etc.\n",
        "possible_matches": "\nPossible matches:",
        "select_number": "Select a number (or press Enter for #1): ",
        "invalid_selection": "Invalid selection. Try again.\n",
        "confirm_country": "Use '{name}' ({code})? [y/n]: ",
        "try_again": "Okay — try again.\n",

        # Weather output labels
        "weather_in": "Weather in",
        "temp_label": "Temperature",
        "humidity_label": "Humidity",
        "wind_label": "Wind Speed",
        "desc_label": "Description",

        # Errors
        "incomplete_city": "Could not retrieve complete weather data for",
        "incomplete_postal": "Incomplete weather data retrieved for",
        "city_not_found": "Error: City not found",
        "postal_not_found": "Error: Postal code not found",
        "unauthorized_proxy": "Error: Unauthorized proxy request. Check proxy token.",
        "rate_limited": "Error: Proxy rate limit exceeded. Please try again later.",
        "rate_limited_retry": "Request limit reached. Try again in about {seconds} seconds.",
        "service_paused": "Live weather is temporarily unavailable.",
        "cached_result": "Cached result ({seconds} seconds old).",
        "http_error": "HTTP error occurred",
        "request_error": "An error occurred during the API request",

        # History/search menu
        "history_prompt": "\n[h]istory, [s]earch, or press Enter to quit: ",
        "history_count": "How many entries? (default 10): ",
        "search_prompt": "Search text (ex: 'rain', 'Tokyo'): ",
        "search_blank": "Search text can't be blank.",
        "no_history": "\nNo history found yet.\n",
        "history_title": "\n--- Local History ---",
        "history_footer": "---------------------\n",
        "unknown_option": "Unknown option. Use 'h', 's', or Enter.",
    },

    "ja": {
        # Language selection
        "language_prompt": "言語? [en/ja] (default en): ",

        # Location prompts
        "enter_city_or_postal": "市区町村名を入力（郵便番号ならEnter）: ",
        "enter_postal": "郵便番号を入力: ",

        # Country prompts
        "enter_country": "国を入力（国名 / alpha-2 / alpha-3）: ",
        "no_country_found": "国が見つかりません。例: 'United States', 'US', 'USA', 'Japan', 'JP' など。\n",
        "possible_matches": "\n候補:",
        "select_number": "番号を選択（Enterで#1）: ",
        "invalid_selection": "無効な選択です。もう一度。\n",
        "confirm_country": "'{name}'（{code}）でOK？ [y/n]: ",
        "try_again": "OK — もう一度。\n",

        # Weather output labels
        "weather_in": "現在の天気",
        "temp_label": "気温",
        "humidity_label": "湿度",
        "wind_label": "風速",
        "desc_label": "概要",

        # Errors
        "incomplete_city": "天気データを取得できませんでした:",
        "incomplete_postal": "天気データが不完全です:",
        "city_not_found": "エラー: 市区町村が見つかりません",
        "postal_not_found": "エラー: 郵便番号が見つかりません",
        "unauthorized_proxy": "エラー: 認証に失敗しました（トークン確認）",
        "rate_limited": "エラー: レート制限です。少し待ってから再試行してください。",
        "rate_limited_retry": "リクエスト制限です。約{seconds}秒後に再試行してください。",
        "service_paused": "現在、ライブ天気情報を一時停止しています。",
        "cached_result": "キャッシュ結果（{seconds}秒前）。",
        "http_error": "HTTPエラー",
        "request_error": "APIリクエスト中にエラーが発生しました",

        # History/search menu
        "history_prompt": "\n[h]履歴, [s]検索, Enterで終了: ",
        "history_count": "件数（default 10）: ",
        "search_prompt": "検索（例: 'rain', 'Tokyo'）: ",
        "search_blank": "検索文字は空にできません。",
        "no_history": "\n履歴はまだありません。\n",
        "history_title": "\n--- ローカル履歴 ---",
        "history_footer": "---------------------\n",
        "unknown_option": "無効な選択です。'h' / 's' / Enter を使ってください。",
    },
}


# OpenWeather condition ID -> JP text.
# This is the reliable fallback when OpenWeather returns English even with lang=ja.
JP_WEATHER_ID = {
    # Thunderstorm (200-232)
    200: "雷雨（小雨）",
    201: "雷雨（雨）",
    202: "雷雨（大雨）",
    210: "弱い雷雨",
    211: "雷雨",
    212: "強い雷雨",
    221: "雷雨（不規則）",
    230: "雷雨（霧雨）",
    231: "雷雨（霧雨）",
    232: "雷雨（強い霧雨）",

    # Drizzle (300-321)
    300: "霧雨",
    301: "霧雨",
    302: "強い霧雨",
    310: "霧雨（小雨）",
    311: "霧雨（雨）",
    312: "霧雨（強い雨）",
    313: "にわか雨",
    314: "強いにわか雨",
    321: "霧雨",

    # Rain (500-531)
    500: "小雨",
    501: "雨",
    502: "強い雨",
    503: "非常に強い雨",
    504: "豪雨",
    511: "氷雨",
    520: "にわか雨",
    521: "強いにわか雨",
    522: "激しいにわか雨",
    531: "不規則なにわか雨",

    # Snow (600-622)
    600: "小雪",
    601: "雪",
    602: "大雪",
    611: "みぞれ",
    612: "にわかみぞれ",
    613: "みぞれ",
    615: "雨と雪",
    616: "雨と雪",
    620: "にわか雪",
    621: "強いにわか雪",
    622: "激しいにわか雪",

    # Atmosphere (701-781)
    701: "霧",
    711: "煙",
    721: "もや",
    731: "砂塵",
    741: "霧",
    751: "砂",
    761: "ちり",
    762: "火山灰",
    771: "スコール",
    781: "竜巻",

    # Clear/Clouds (800-804)
    800: "快晴",
    801: "晴れ（雲が少ない）",
    802: "晴れ（雲が散らばっている）",
    803: "くもり（雲が多い）",
    804: "曇天",
}


def jp_description_from_weather(weather0: dict) -> str | None:
    # Converts OpenWeather weather[0] into JP text using its condition ID.
    # Returns None if we can't read the ID or it's not in our map.

    try:
        wid = int((weather0 or {}).get("id"))
    except Exception:
        return None

    return JP_WEATHER_ID.get(wid)
