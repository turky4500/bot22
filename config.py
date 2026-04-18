"""
config.py
إعدادات البوت — يدعم بوتات متعددة وإعدادات واتساب
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_GLOBAL = {
    "mode":               "virtual",
    "virtual_api_key":    os.getenv("VIRTUAL_API_KEY",    ""),
    "virtual_api_secret": os.getenv("VIRTUAL_API_SECRET", ""),
    "live_api_key":       os.getenv("LIVE_API_KEY",       ""),
    "live_api_secret":    os.getenv("LIVE_API_SECRET",    ""),
    "whatsapp_enabled":   False,
    "whatsapp_token":     os.getenv("WHATSAPP_TOKEN",     ""),
    "whatsapp_phone":     os.getenv("WHATSAPP_PHONE",     ""),
    "bots":               [],
    "next_bot_id":        1,
}

DEFAULT_BOT = {
    "name":          "بوت جديد",
    "symbol":        "BTCUSDT",
    "order_amount":  10.0,
    "timeframe":     "1h",
    "allow_rebuy":   False,
    "bb_length":     20,
    "bb_multiplier": 2.0,
}

SUPPORTED_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
    "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
]

SUPPORTED_TIMEFRAMES = [
    ("1m",  "دقيقة واحدة"),
    ("5m",  "5 دقائق"),
    ("15m", "15 دقيقة"),
    ("30m", "30 دقيقة"),
    ("1h",  "ساعة واحدة"),
    ("4h",  "4 ساعات"),
    ("1d",  "يوم واحد"),
]


def _load_raw() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_raw(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_settings() -> dict:
    """تحميل الإعدادات العامة (بدون قائمة البوتات)"""
    raw      = _load_raw()
    settings = DEFAULT_GLOBAL.copy()
    for k, v in raw.items():
        if k != "bots":
            settings[k] = v
    return settings


def save_settings(settings: dict) -> None:
    """حفظ الإعدادات العامة مع الإبقاء على البوتات"""
    raw = _load_raw()
    for k, v in settings.items():
        if k != "bots":
            raw[k] = v
    _save_raw(raw)


def load_bots() -> list:
    return _load_raw().get("bots", [])


def save_bots(bots: list) -> None:
    raw = _load_raw()
    raw["bots"] = bots
    _save_raw(raw)


def add_bot(bot_data: dict) -> dict:
    raw     = _load_raw()
    bots    = raw.get("bots", [])
    next_id = raw.get("next_bot_id", 1)

    new_bot = DEFAULT_BOT.copy()
    new_bot.update(bot_data)
    new_bot["id"] = next_id

    bots.append(new_bot)
    raw["bots"]        = bots
    raw["next_bot_id"] = next_id + 1
    _save_raw(raw)
    return new_bot


def update_bot(bot_id: int, bot_data: dict) -> bool:
    raw  = _load_raw()
    bots = raw.get("bots", [])
    for i, bot in enumerate(bots):
        if bot.get("id") == bot_id:
            bots[i].update(bot_data)
            raw["bots"] = bots
            _save_raw(raw)
            return True
    return False


def delete_bot(bot_id: int) -> bool:
    raw      = _load_raw()
    bots     = raw.get("bots", [])
    new_bots = [b for b in bots if b.get("id") != bot_id]
    if len(new_bots) == len(bots):
        return False
    raw["bots"] = new_bots
    _save_raw(raw)
    return True


def get_flask_secret() -> str:
    return os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
