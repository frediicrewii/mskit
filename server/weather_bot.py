"""Weather bot logic: regions, WeatherAPI fetch, message formatting.

Completely independent from messaging layer. Exposes three things:
  - handle_user_message(sender, text) -> (reply_text, new_state, maybe_query_for_weather)
  - fetch_weather(query) -> dict with all forecast fields
  - format_weather_message(data, location_name) -> str
"""
import os
import httpx
from datetime import datetime, timedelta
from typing import Optional

WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
WEATHER_BASE = "https://api.weatherapi.com/v1"

BOT_USERNAME = "weather_bot"
BOT_DISPLAY_NAME = "Weather Bot"

# Uzbekistan regions/cities
UZ_REGIONS = [
    ("Ташкент", "Tashkent,Uzbekistan"),
    ("Самарканд", "Samarkand,Uzbekistan"),
    ("Бухара", "Bukhara,Uzbekistan"),
    ("Наманган", "Namangan,Uzbekistan"),
    ("Андижан", "Andijan,Uzbekistan"),
    ("Фергана", "Fergana,Uzbekistan"),
    ("Нукус", "Nukus,Uzbekistan"),
    ("Ургенч", "Urgench,Uzbekistan"),
    ("Навои", "Navoi,Uzbekistan"),
    ("Джизак", "Jizzakh,Uzbekistan"),
    ("Гулистан", "Gulistan,Uzbekistan"),
    ("Термез", "Termez,Uzbekistan"),
    ("Карши", "Karshi,Uzbekistan"),
    ("Нурафшон", "Nurafshon,Uzbekistan"),
]


def help_text() -> str:
    return (
        "Привет! Я погодный бот 🌤\n"
        "\n"
        "Команды:\n"
        "  UZ         — выбрать регион Узбекистана\n"
        "  /now       — получить прогноз сейчас\n"
        "  /change    — сменить город\n"
        "  /stop      — отписаться\n"
        "  /help      — эта справка\n"
        "\n"
        "После выбора региона я буду присылать прогноз каждые 10 минут."
    )


def region_list_text() -> str:
    lines = ["Выберите регион Узбекистана:", ""]
    for i, (name, _) in enumerate(UZ_REGIONS, 1):
        lines.append(f"  {i:2}. {name}")
    lines.append("")
    lines.append(f"Напишите номер (1–{len(UZ_REGIONS)}) или название.")
    return "\n".join(lines)


def resolve_uz_region(text: str) -> Optional[tuple]:
    """Try to match user input to one of UZ regions.
    Returns (display_name, query) or None.
    """
    t = text.strip().lower()
    # number?
    try:
        n = int(t)
        if 1 <= n <= len(UZ_REGIONS):
            return UZ_REGIONS[n - 1]
    except ValueError:
        pass
    # name match (accept Cyrillic and Latin)
    for name, query in UZ_REGIONS:
        if t == name.lower() or t == query.split(",")[0].lower():
            return (name, query)
    # substring match
    for name, query in UZ_REGIONS:
        if t in name.lower() or t in query.split(",")[0].lower():
            return (name, query)
    return None


# -------- WeatherAPI --------
async def fetch_weather(query: str) -> Optional[dict]:
    """Query WeatherAPI.com forecast.json + astronomy.json.
    Returns dict with all required fields, or None on error.
    """
    if not WEATHER_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        # forecast has current + 1 day hourly + astro, all in one call
        try:
            r = await client.get(f"{WEATHER_BASE}/forecast.json", params={
                "key": WEATHER_API_KEY,
                "q": query,
                "days": 1,
                "aqi": "no",
                "alerts": "no",
                "lang": "ru",
            })
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None


# -------- Formatting --------
RU_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]

# Weather condition code -> emoji
# Based on WeatherAPI's conditions code list: https://www.weatherapi.com/docs/weather_conditions.json
def cond_emoji(code: int, is_day: int = 1) -> str:
    # Sunny/Clear
    if code == 1000:
        return "☀️" if is_day else "🌙"
    # Partly cloudy
    if code in (1003,):
        return "⛅" if is_day else "☁️"
    # Cloudy / overcast
    if code in (1006, 1009):
        return "☁️"
    # Mist / fog
    if code in (1030, 1135, 1147):
        return "🌫"
    # Patchy/light rain/drizzle
    if code in (1063, 1150, 1153, 1180, 1183, 1240):
        return "🌦"
    # Rain (heavier)
    if code in (1186, 1189, 1192, 1195, 1243, 1246):
        return "🌧"
    # Snow
    if code in (1066, 1114, 1117, 1210, 1213, 1216, 1219, 1222, 1225, 1255, 1258):
        return "🌨"
    # Sleet / freezing rain
    if code in (1069, 1072, 1168, 1171, 1198, 1201, 1204, 1207, 1237, 1249, 1252, 1261, 1264):
        return "🌧❄️"
    # Thunder
    if code in (1087, 1273, 1276, 1279, 1282):
        return "⛈"
    # fallback
    return "🌤"


def wind_dir_emoji(deg: float) -> str:
    """Arrow showing where the wind is blowing TO (meteorological convention)."""
    # deg is FROM direction. Invert for TO.
    d = (deg + 180) % 360
    # 8 directions
    dirs = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    idx = int((d + 22.5) // 45) % 8
    return dirs[idx]


def wind_dir_ru(deg: float) -> str:
    """From-direction abbrev in Russian."""
    dirs = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
            "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]
    idx = int((deg + 11.25) // 22.5) % 16
    return dirs[idx]


def signed(n: float) -> str:
    """+14 or -5 or 0"""
    v = round(n)
    if v > 0:
        return f"+{v}°"
    if v < 0:
        return f"−{abs(v)}°"
    return "0°"


def pick_hour(hours: list, hour: int) -> Optional[dict]:
    """Find entry for specific hour (0-23) from hourly array."""
    for h in hours:
        try:
            t = datetime.fromisoformat(h["time"])
            if t.hour == hour:
                return h
        except Exception:
            pass
    return None


# Moon phase translation
MOON_PHASES_RU = {
    "New Moon": "Новолуние",
    "Waxing Crescent": "Молодая Луна",
    "First Quarter": "Первая четверть",
    "Waxing Gibbous": "Растущая Луна",
    "Full Moon": "Полнолуние",
    "Waning Gibbous": "Убывающая Луна",
    "Last Quarter": "Последняя четверть",
    "Waning Crescent": "Старая Луна",
}


def parse_astro_time(s: str) -> str:
    """Convert '05:42 AM' -> '05:42'."""
    if not s:
        return "—"
    try:
        dt = datetime.strptime(s.strip(), "%I:%M %p")
        return dt.strftime("%H:%M")
    except Exception:
        return s


def format_weather_message(data: dict, location_name: str) -> str:
    """Format the fetched data into the exact required format."""
    try:
        current = data["current"]
        forecast_day = data["forecast"]["forecastday"][0]
        day = forecast_day["day"]
        astro = forecast_day["astro"]
        hours = forecast_day["hour"]
    except (KeyError, IndexError):
        return "Не удалось получить данные о погоде."

    # Date
    now = datetime.now()
    date_str = f"Сегодня, {now.day} {RU_MONTHS[now.month]}"

    # Summary: high/low + condition
    max_t = signed(day["maxtemp_c"])
    min_t = signed(day["mintemp_c"])
    day_cond_text = day["condition"]["text"]
    day_cond_emoji = cond_emoji(day["condition"]["code"], is_day=1)

    # Current
    cur_t = signed(current["temp_c"])
    cur_emoji = cond_emoji(current["condition"]["code"], current["is_day"])
    wind_speed_ms = round(current["wind_kph"] / 3.6, 1)
    wind_arrow = wind_dir_emoji(current["wind_degree"])

    # Morning (9am), Afternoon (15), Evening (21)
    morning = pick_hour(hours, 9)
    afternoon = pick_hour(hours, 15)
    evening = pick_hour(hours, 21)

    def hour_line(h: Optional[dict]) -> str:
        if not h:
            return "—"
        e = cond_emoji(h["condition"]["code"], h.get("is_day", 1))
        return f"{e} {signed(h['temp_c'])}"

    # Humidity / wind / pressure
    humidity = round(current["humidity"])
    avg_wind_ms = round(current["wind_kph"] / 3.6, 1)
    wind_dir = wind_dir_ru(current["wind_degree"])
    pressure_mm = round(current["pressure_mb"] * 0.750062)

    # Astronomy
    moon_en = astro.get("moon_phase", "")
    moon_ru = MOON_PHASES_RU.get(moon_en, moon_en)
    sunrise = parse_astro_time(astro.get("sunrise", ""))
    sunset = parse_astro_time(astro.get("sunset", ""))

    lines = [
        date_str,
        f"{day_cond_emoji} {max_t}...{min_t}, {day_cond_text}",
        f"Сейчас: {cur_emoji} {cur_t}, {wind_arrow} {wind_speed_ms} м/с",
        f"Утром: {hour_line(morning)}",
        f"Днем: {hour_line(afternoon)}",
        f"Вечером: {hour_line(evening)}",
        f"Влажность: {humidity}%",
        f"Ветер: {wind_dir}, {avg_wind_ms} м/с",
        f"Давление: {pressure_mm} мм рт. ст.",
        f"Луна: {moon_ru}",
        f"Восход: {sunrise}",
        f"Закат: {sunset}",
    ]
    return f"📍 {location_name}\n" + "\n".join(lines)


# -------- Command handling --------
async def handle_user_message(text: str, current_sub: Optional["WeatherSubscription"]):
    """Parse user message, return (reply_text, action).
    action is one of:
      - {"type": "help"}
      - {"type": "show_regions"}
      - {"type": "subscribe", "location_name": str, "location_query": str}
      - {"type": "unsubscribe"}
      - {"type": "send_now"}
      - {"type": "nothing"} (just reply)
    """
    t = text.strip()
    tl = t.lower()

    if not t:
        return None, {"type": "nothing"}

    if tl in ("/start", "/help", "help", "start", "hi", "hello", "привет"):
        return help_text(), {"type": "nothing"}

    if tl == "/stop":
        if current_sub:
            return "Вы отписались от прогноза. Напишите UZ, чтобы подписаться снова.", {"type": "unsubscribe"}
        return "Вы и не были подписаны.", {"type": "nothing"}

    if tl in ("/change", "change"):
        return region_list_text(), {"type": "show_regions"}

    if tl == "/now":
        if current_sub and current_sub.state == "active":
            return None, {"type": "send_now"}
        return "Сначала выберите регион. Напишите UZ.", {"type": "nothing"}

    if tl in ("uz", "узбекистан", "uzbekistan"):
        return region_list_text(), {"type": "show_regions"}

    # If user is in "await_region" state, try to match UZ regions
    if current_sub and current_sub.state == "await_region":
        r = resolve_uz_region(t)
        if r:
            name, query = r
            reply = (
                f"Подписка оформлена: {name}\n"
                f"Первый прогноз через несколько секунд.\n"
                f"Интервал: каждые 10 минут.\n"
                f"\n"
                f"Команды: /now, /change, /stop"
            )
            return reply, {"type": "subscribe", "location_name": name, "location_query": query}
        return ("Не нашёл такой регион. Напишите номер (1–14) или название. "
                "Например: 1 или Ташкент."), {"type": "nothing"}

    # Else try to match UZ region by name directly (shortcut: "Ташкент")
    r = resolve_uz_region(t)
    if r:
        name, query = r
        reply = (
            f"Подписка оформлена: {name}\n"
            f"Первый прогноз через несколько секунд.\n"
            f"Интервал: каждые 10 минут."
        )
        return reply, {"type": "subscribe", "location_name": name, "location_query": query}

    # Unknown
    return help_text(), {"type": "nothing"}
