"""tools/weather_tool.py — Real-time weather via wttr.in (no API key needed)."""

import requests
import config

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get current weather conditions and a short forecast for any city or location. "
            "Use this for questions like 'what is the weather in X', 'will it rain in Y', "
            "'temperature in Z today'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name e.g. 'Chennai', 'New York'. Use 'auto' if no city is mentioned — it will detect automatically.",
                },
            },
            "required": ["location"],
        },
    },
}


def run(location: str) -> str:
    """Fetch weather from wttr.in and return a formatted string for the LLM."""
    # Auto-detect location from IP if not specified
    if not location or location.strip().lower() in ("auto", "near me", "my location", "here", ""):
        try:
            import requests as _req
            data = _req.get("https://ipapi.co/json/", timeout=5).json()
            city    = data.get("city", "")
            country = data.get("country_name", "")
            if city:
                location = f"{city}, {country}"
        except Exception:
            location = "New York"   # last resort fallback

    loc_encoded = location.strip().replace(" ", "+")
    url = f"https://wttr.in/{loc_encoded}?format=j1"

    try:
        resp = requests.get(url, headers={"User-Agent": config.HTTP_USER_AGENT}, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"Failed to get weather for '{location}': {e}"

    try:
        current = data["current_condition"][0]
        area    = data["nearest_area"][0]
        city    = area["areaName"][0]["value"]
        country = area["country"][0]["value"]

        temp_c  = current["temp_C"]
        temp_f  = current["temp_F"]
        feels_c = current["FeelsLikeC"]
        desc    = current["weatherDesc"][0]["value"]
        humidity= current["humidity"]
        wind_kph= current["windspeedKmph"]
        wind_dir= current["winddir16Point"]
        uv      = current["uvIndex"]

        forecast_line = ""
        if len(data["weather"]) > 1:
            tomorrow = data["weather"][1]
            max_c    = tomorrow["maxtempC"]
            min_c    = tomorrow["mintempC"]
            t_desc   = tomorrow["hourly"][4]["weatherDesc"][0]["value"]
            forecast_line = f"\nTomorrow: {t_desc}, {min_c}°C – {max_c}°C"

        return (
            f"Weather in {city}, {country}:\n"
            f"Condition   : {desc}\n"
            f"Temperature : {temp_c}°C ({temp_f}°F), feels like {feels_c}°C\n"
            f"Humidity    : {humidity}%\n"
            f"Wind        : {wind_kph} km/h {wind_dir}\n"
            f"UV Index    : {uv}"
            f"{forecast_line}"
        )
    except (KeyError, IndexError) as e:
        return f"Weather data received but could not be parsed (field: {e})."
