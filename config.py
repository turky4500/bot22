"""
config.py
إدارة إعدادات البوت - حفظ وتحميل من ملف JSON
يستخدم مسارات مطلقة لضمان التوافق مع Render.com
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

# المجلد الذي يحتوي على هذا الملف (جذر المشروع)
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "symbol":          "BTCUSDT",
    "order_amount":    10.0,
    "timeframe":       "1h",
    "allow_rebuy":     False,
    "bb_length":       20,
    "bb_multiplier":   2.0,
    "mode":            "virtual",
    "virtual_api_key":    os.getenv("VIRTUAL_API_KEY",    ""),
    "virtual_api_secret": os.getenv("VIRTUAL_API_SECRET", ""),
    "live_api_key":       os.getenv("LIVE_API_KEY",       ""),
    "live_api_secret":    os.getenv("LIVE_API_SECRET",    ""),
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


def load_settings() -> dict:
    """تحميل الإعدادات من الملف مع دمج القيم الافتراضية للمفاتيح الناقصة"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            # نبدأ من القيم الافتراضية ثم نطغي عليها بما هو محفوظ
            settings = DEFAULT_SETTINGS.copy()
            settings.update(stored)
            return settings
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    """حفظ الإعدادات في الملف"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_flask_secret() -> str:
    return os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
