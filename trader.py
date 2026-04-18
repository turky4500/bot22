"""
trader.py
BotManager — يدير بوتات تداول متعددة في وقت واحد
"""

import threading
import time
import json
import os
from datetime import datetime
from typing import Optional, Dict

from config import load_settings, load_bots, BASE_DIR
from binance_client import BinanceClient
from indicators import get_signal, get_current_bb_values
from notifier import send_whatsapp, build_trade_message

LOGS_FILE = os.path.join(BASE_DIR, "trade_logs.json")
MAX_LOGS  = 500


def _position_file(bot_id: int) -> str:
    return os.path.join(BASE_DIR, f"position_{bot_id}.json")


def load_all_logs() -> list:
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


# ======================================================================
# SingleBot — بوت تداول واحد
# ======================================================================

class SingleBot:

    def __init__(self, bot_config: dict, client: BinanceClient):
        self.bot_id  = bot_config["id"]
        self.config  = bot_config.copy()
        self.client  = client

        self.running          = False
        self.status           = "متوقف"
        self.last_signal      = None
        self.last_check       = None
        self.current_price    = 0.0
        self.bb_values        = {}
        self.error_message    = None
        self._last_candle_ts  = None
        self._thread          = None
        self.current_position = self._load_position()

    # ── تشغيل / إيقاف ──────────────────────────────────────────────

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.status  = "يعمل 🟢"
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"Bot-{self.bot_id}-{self.config['symbol']}",
        )
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        self.status  = "متوقف 🔴"

    # ── حلقة المراقبة ──────────────────────────────────────────────

    def _run_loop(self) -> None:
        while self.running:
            try:
                self._check_market()
            except Exception as e:
                self.error_message = str(e)
                self.status        = f"خطأ ⚠️: {str(e)[:50]}"
            for _ in range(60):
                if not self.running:
                    return
                time.sleep(1)

    def _check_market(self) -> None:
        symbol      = self.config["symbol"]
        timeframe   = self.config["timeframe"]
        bb_length   = int(self.config["bb_length"])
        bb_mult     = float(self.config["bb_multiplier"])
        order_amt   = float(self.config["order_amount"])
        allow_rebuy = bool(self.config["allow_rebuy"])
        limit       = bb_length + 15

        ohlcv = self.client.get_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 5:
            return

        self.current_price = ohlcv[-1][4]
        self.bb_values     = get_current_bb_values(ohlcv, bb_length, bb_mult)
        self.last_check    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        last_ts = ohlcv[-1][0]
        if last_ts == self._last_candle_ts:
            return
        self._last_candle_ts = last_ts

        signal           = get_signal(ohlcv, length=bb_length, multiplier=bb_mult)
        self.last_signal = signal

        if signal == "BUY":
            self._handle_buy(symbol, ohlcv, order_amt, allow_rebuy)
        elif signal == "SELL":
            self._handle_sell(symbol, ohlcv)

    # ── شراء / بيع ────────────────────────────────────────────────

    def _handle_buy(self, symbol, ohlcv, order_amt, allow_rebuy) -> None:
        if self.current_position is not None and not allow_rebuy:
            return
        try:
            if self.client.get_balance("USDT") < order_amt:
                self._write_log("شراء", symbol, ohlcv[-1][4], 0,
                                "رصيد USDT غير كافٍ", "مُهمَل ⚠️")
                return

            close_price = ohlcv[-1][4]
            order       = self.client.create_limit_buy(symbol, order_amt, close_price)
            qty         = float(order.get("amount") or order.get("filled") or 0)
            exec_price  = float(order.get("price") or close_price)

            self.current_position = {
                "symbol":    symbol,
                "qty":       qty,
                "buy_price": exec_price,
                "order_id":  order.get("id", ""),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_position()
            reason = "إشارة بولينجر باند — اختراق الحد السفلي صعوداً"
            self._write_log("شراء", symbol, exec_price, qty, reason, "مكتمل ✅")
            self._notify("شراء", symbol, exec_price, qty, reason)

        except Exception as e:
            self.error_message = str(e)
            self._write_log("شراء", symbol, 0, 0, f"خطأ: {e}", "فشل ❌")

    def _handle_sell(self, symbol, ohlcv) -> None:
        if self.current_position is None:
            return
        try:
            qty = self.client.get_asset_balance(symbol)
            if qty <= 0:
                self.current_position = None
                self._save_position()
                return

            close_price = ohlcv[-1][4]
            order       = self.client.create_limit_sell(symbol, qty, close_price)
            exec_price  = float(order.get("price") or close_price)
            buy_price   = self.current_position.get("buy_price", 0)
            pnl         = (exec_price - buy_price) * qty if buy_price else 0
            pnl_pct     = ((exec_price - buy_price) / buy_price * 100) if buy_price else 0
            pnl_str     = f"{pnl:+.4f} USDT ({pnl_pct:+.2f}%)"

            reason = "إشارة بولينجر باند — اختراق الحد العلوي هبوطاً"
            self._write_log("بيع", symbol, exec_price, qty,
                            f"{reason} | ر/خ: {pnl_str}", "مكتمل ✅")
            self._notify("بيع", symbol, exec_price, qty, reason, pnl_str)
            self.current_position = None
            self._save_position()

        except Exception as e:
            self.error_message = str(e)
            self._write_log("بيع", symbol, 0, 0, f"خطأ: {e}", "فشل ❌")

    def emergency_sell(self) -> tuple:
        symbol = self.config["symbol"]
        try:
            qty = self.client.get_asset_balance(symbol)
            if qty <= 0:
                self.current_position = None
                self._save_position()
                return False, "لا توجد كمية للبيع"

            order      = self.client.create_market_sell(symbol, qty)
            exec_price = float(order.get("average") or order.get("price") or self.current_price or 0)

            self._write_log("بيع طارئ", symbol, exec_price, qty,
                            "أمر طارئ من لوحة التحكم", "مكتمل ✅")
            self._notify("بيع طارئ 🚨", symbol, exec_price, qty,
                         "أمر طارئ من لوحة التحكم")
            self.current_position = None
            self._save_position()
            return True, f"تم البيع الطارئ — السعر: {exec_price:.4f}"

        except Exception as e:
            return False, f"فشل: {e}"

    # ── إشعار واتساب ──────────────────────────────────────────────

    def _notify(self, action, symbol, price, qty, reason, pnl=None) -> None:
        try:
            s = load_settings()
            if not s.get("whatsapp_enabled"):
                return
            phone = s.get("whatsapp_phone", "")
            token = s.get("whatsapp_token", "")
            if not phone or not token:
                return
            msg = build_trade_message(
                action, symbol, price, qty, reason, pnl,
                bot_name=self.config.get("name", "")
            )
            send_whatsapp(msg, phone, token)
        except Exception:
            pass

    # ── السجلات والاستمرارية ───────────────────────────────────────

    def _write_log(self, action, symbol, price, qty, reason, status) -> None:
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_id":    self.bot_id,
            "bot_name":  self.config.get("name", f"بوت {self.bot_id}"),
            "action":    action,
            "symbol":    symbol,
            "price":     round(price, 6) if price else 0,
            "qty":       round(qty,   8) if qty   else 0,
            "reason":    reason,
            "status":    status,
        }
        logs = load_all_logs()
        logs.insert(0, entry)
        logs = logs[:MAX_LOGS]
        try:
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _save_position(self) -> None:
        try:
            with open(_position_file(self.bot_id), "w", encoding="utf-8") as f:
                json.dump(self.current_position, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_position(self) -> Optional[dict]:
        path = _position_file(self.bot_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def get_status(self) -> dict:
        return {
            "id":            self.bot_id,
            "name":          self.config.get("name", f"بوت {self.bot_id}"),
            "symbol":        self.config["symbol"],
            "timeframe":     self.config["timeframe"],
            "order_amount":  self.config.get("order_amount", 10),
            "running":       self.running,
            "status":        self.status,
            "last_signal":   self.last_signal,
            "last_check":    self.last_check,
            "current_price": self.current_price,
            "bb_values":     self.bb_values,
            "has_position":  self.current_position is not None,
            "position":      self.current_position,
            "error_message": self.error_message,
        }


# ======================================================================
# BotManager — يدير جميع البوتات
# ======================================================================

class BotManager:

    _instance = None
    _lock     = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._bots: Dict[int, SingleBot] = {}
        self._client: Optional[BinanceClient] = None
        self.error_message: Optional[str] = None

    # ── الاتصال ─────────────────────────────────────────────────────

    def _build_client(self) -> Optional[BinanceClient]:
        s = load_settings()
        if s.get("mode", "virtual") == "virtual":
            key, secret, testnet = (
                s.get("virtual_api_key",    "").strip(),
                s.get("virtual_api_secret", "").strip(),
                True,
            )
        else:
            key, secret, testnet = (
                s.get("live_api_key",    "").strip(),
                s.get("live_api_secret", "").strip(),
                False,
            )
        if not key or not secret:
            return None
        c = BinanceClient(key, secret, testnet=testnet)
        c.get_balance("USDT")   # اختبار الاتصال
        return c

    def refresh_client(self) -> None:
        """إعادة تهيئة الاتصال بعد تغيير المفاتيح"""
        self._client = None

    # ── تشغيل / إيقاف ───────────────────────────────────────────────

    def start_bot(self, bot_id: int) -> tuple:
        bots       = load_bots()
        bot_config = next((b for b in bots if b["id"] == bot_id), None)
        if not bot_config:
            return False, "البوت غير موجود"
        if bot_id in self._bots and self._bots[bot_id].running:
            return False, "البوت يعمل بالفعل"
        try:
            if self._client is None:
                self._client = self._build_client()
            if self._client is None:
                return False, "مفاتيح API غير مضبوطة. اضبطها من الإعدادات."
        except Exception as e:
            self.error_message = str(e)
            return False, f"فشل الاتصال: {e}"

        bot = SingleBot(bot_config, self._client)
        bot.start()
        self._bots[bot_id] = bot
        return True, f"تم تشغيل {bot_config['name']} ✅"

    def stop_bot(self, bot_id: int) -> tuple:
        if bot_id not in self._bots:
            return False, "البوت غير نشط"
        self._bots[bot_id].stop()
        return True, "تم الإيقاف ✅"

    def start_all(self) -> tuple:
        bots = load_bots()
        if not bots:
            return False, "لا توجد بوتات. أضف بوتاً من صفحة الإعدادات."
        try:
            if self._client is None:
                self._client = self._build_client()
            if self._client is None:
                return False, "مفاتيح API غير مضبوطة. اضبطها من الإعدادات."
        except Exception as e:
            return False, f"فشل الاتصال: {e}"

        started = 0
        for bc in bots:
            bid = bc["id"]
            if bid not in self._bots or not self._bots[bid].running:
                bot = SingleBot(bc, self._client)
                bot.start()
                self._bots[bid] = bot
                started += 1
        return True, f"تم تشغيل {started} بوت ✅"

    def stop_all(self) -> None:
        for bot in self._bots.values():
            bot.stop()

    def emergency_sell(self, bot_id: int) -> tuple:
        if bot_id not in self._bots:
            return False, "البوت غير نشط — شغّله أولاً"
        return self._bots[bot_id].emergency_sell()

    # ── بيانات لوحة التحكم ───────────────────────────────────────────

    def get_all_status(self) -> list:
        result = []
        for bc in load_bots():
            bid = bc["id"]
            if bid in self._bots:
                result.append(self._bots[bid].get_status())
            else:
                result.append({
                    "id":            bid,
                    "name":          bc.get("name", f"بوت {bid}"),
                    "symbol":        bc["symbol"],
                    "timeframe":     bc["timeframe"],
                    "order_amount":  bc.get("order_amount", 10),
                    "running":       False,
                    "status":        "متوقف",
                    "last_signal":   None,
                    "last_check":    None,
                    "current_price": 0.0,
                    "bb_values":     {},
                    "has_position":  False,
                    "position":      None,
                    "error_message": None,
                })
        return result

    def get_usdt_balance(self) -> float:
        if self._client:
            try:
                return self._client.get_balance("USDT")
            except Exception:
                pass
        return 0.0
