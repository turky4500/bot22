"""
trader.py
المنطق الرئيسي للتداول — إدارة دورة حياة الصفقة والخيط الخلفي
يستخدم مسارات مطلقة للتوافق مع Render.com
"""

import threading
import time
import json
import os
from datetime import datetime
from typing import Optional

from config import load_settings, BASE_DIR
from binance_client import BinanceClient
from indicators import get_signal, get_current_bb_values

LOGS_FILE     = os.path.join(BASE_DIR, "trade_logs.json")
POSITION_FILE = os.path.join(BASE_DIR, "position.json")
MAX_LOGS      = 500  # الحد الأقصى للسجلات المحفوظة


class Trader:
    """
    Singleton — يُنشأ مرة واحدة ويُشارَك عبر تطبيق Flask بأكمله.
    يدير:
      - الخيط الخلفي (background thread) لمراقبة السوق
      - حالة الصفقة الحالية (current position)
      - سجل العمليات (trade logs)
    """

    _instance: Optional["Trader"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "Trader":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.running:  bool = False
        self.status:   str  = "متوقف"
        self._thread:  Optional[threading.Thread] = None
        self.client:   Optional[BinanceClient]    = None

        # معلومات السوق (تُحدَّث في كل دورة)
        self.last_signal:   Optional[str] = None
        self.last_check:    Optional[str] = None
        self.current_price: float         = 0.0
        self.bb_values:     dict          = {}
        self.error_message: Optional[str] = None

        # الطابع الزمني للشمعة الأخيرة التي عولجت (لتجنب التكرار)
        self._last_candle_ts: Optional[int] = None

        # تحميل الوضع المستمر (الصفقة الحالية) من الملف
        self.current_position: Optional[dict] = self._load_position()

    # ------------------------------------------------------------------
    # واجهة التحكم (تُستدعى من Flask)
    # ------------------------------------------------------------------

    def start(self) -> tuple:
        """تشغيل البوت"""
        if self.running:
            return False, "البوت يعمل بالفعل"

        settings = load_settings()
        mode     = settings.get("mode", "virtual")

        if mode == "virtual":
            api_key    = settings.get("virtual_api_key", "").strip()
            api_secret = settings.get("virtual_api_secret", "").strip()
            testnet    = True
        else:
            api_key    = settings.get("live_api_key", "").strip()
            api_secret = settings.get("live_api_secret", "").strip()
            testnet    = False

        if not api_key or not api_secret:
            return False, "مفاتيح API غير مضبوطة. يرجى تحديثها في صفحة الإعدادات."

        try:
            self.client = BinanceClient(api_key, api_secret, testnet=testnet)
            # اختبار الاتصال
            self.client.get_balance("USDT")
        except Exception as e:
            self.error_message = str(e)
            return False, f"فشل الاتصال بـ Binance: {e}"

        self.error_message      = None
        self._last_candle_ts    = None
        self.running            = True
        self.status             = "يعمل 🟢"
        self._thread            = threading.Thread(
            target=self._run_loop, daemon=True, name="BotThread"
        )
        self._thread.start()
        return True, "تم تشغيل البوت بنجاح"

    def stop(self) -> None:
        """إيقاف البوت"""
        self.running = False
        self.status  = "متوقف 🔴"

    def emergency_sell(self) -> tuple:
        """بيع طارئ فوري بسعر السوق"""
        if not self.client:
            return False, "البوت غير متصل بـ Binance"

        settings = load_settings()
        symbol   = settings.get("symbol", "BTCUSDT")

        try:
            qty = self.client.get_asset_balance(symbol)
            if qty <= 0:
                self.current_position = None
                self._save_position()
                return False, "لا توجد كمية متاحة للبيع"

            order = self.client.create_market_sell(symbol, qty)
            price = float(order.get("average") or order.get("price") or self.current_price or 0)

            self._write_log(
                action="بيع طارئ",
                symbol=symbol,
                price=price,
                qty=qty,
                reason="أمر بيع طارئ من لوحة التحكم",
                status="مكتمل ✅",
            )
            self.current_position = None
            self._save_position()
            return True, f"تم تنفيذ البيع الطارئ بنجاح — السعر: {price:.4f}"

        except Exception as e:
            self.error_message = str(e)
            return False, f"فشل البيع الطارئ: {e}"

    # ------------------------------------------------------------------
    # حلقة المراقبة الرئيسية
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """الخيط الخلفي — يفحص السوق كل 60 ثانية"""
        while self.running:
            try:
                self._check_market()
            except Exception as e:
                self.error_message = str(e)
                self.status        = f"خطأ ⚠️: {str(e)[:60]}"

            # انتظار 60 ثانية مع إمكانية الإيقاف الفوري
            for _ in range(60):
                if not self.running:
                    return
                time.sleep(1)

    def _check_market(self) -> None:
        """فحص السوق وتنفيذ المنطق التداولي"""
        settings   = load_settings()
        symbol     = settings["symbol"]
        timeframe  = settings["timeframe"]
        bb_length  = int(settings["bb_length"])
        bb_mult    = float(settings["bb_multiplier"])
        order_amt  = float(settings["order_amount"])
        allow_rebuy= bool(settings["allow_rebuy"])

        limit = bb_length + 15  # نجلب شموعاً إضافية للحسابات

        ohlcv = self.client.get_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 5:
            return

        # تحديث السعر والمؤشر للعرض
        self.current_price = ohlcv[-1][4]
        self.bb_values     = get_current_bb_values(ohlcv, bb_length, bb_mult)
        self.last_check    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # تجاهل الشمعة التي عُولجت سابقاً
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

    # ------------------------------------------------------------------
    # تنفيذ الصفقات
    # ------------------------------------------------------------------

    def _handle_buy(self, symbol, ohlcv, order_amt, allow_rebuy) -> None:
        """منطق تنفيذ أمر الشراء"""
        if self.current_position is not None and not allow_rebuy:
            return

        try:
            usdt_balance = self.client.get_balance("USDT")
            if usdt_balance < order_amt:
                self._write_log(
                    action="شراء",
                    symbol=symbol,
                    price=ohlcv[-1][4],
                    qty=0,
                    reason="رصيد USDT غير كافٍ",
                    status="مُهمَل ⚠️",
                )
                return

            close_price = ohlcv[-1][4]
            order       = self.client.create_limit_buy(symbol, order_amt, close_price)

            qty        = float(order.get("amount") or order.get("filled") or 0)
            exec_price = float(order.get("price") or close_price)
            order_id   = order.get("id", "")

            self.current_position = {
                "symbol":    symbol,
                "qty":       qty,
                "buy_price": exec_price,
                "order_id":  order_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_position()

            self._write_log(
                action="شراء",
                symbol=symbol,
                price=exec_price,
                qty=qty,
                reason="إشارة بولينجر باند — اختراق الحد السفلي صعوداً",
                status="مكتمل ✅",
            )

        except Exception as e:
            self.error_message = str(e)
            self._write_log(
                action="شراء", symbol=symbol, price=0, qty=0,
                reason=f"خطأ في التنفيذ: {e}", status="فشل ❌",
            )

    def _handle_sell(self, symbol, ohlcv) -> None:
        """منطق تنفيذ أمر البيع"""
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

            exec_price = float(order.get("price") or close_price)
            buy_price  = self.current_position.get("buy_price", 0)
            pnl        = (exec_price - buy_price) * qty if buy_price else 0
            pnl_pct    = ((exec_price - buy_price) / buy_price * 100) if buy_price else 0

            self._write_log(
                action="بيع",
                symbol=symbol,
                price=exec_price,
                qty=qty,
                reason=(
                    f"إشارة بولينجر باند — اختراق الحد العلوي هبوطاً | "
                    f"ربح/خسارة: {pnl:+.4f} USDT ({pnl_pct:+.2f}%)"
                ),
                status="مكتمل ✅",
            )
            self.current_position = None
            self._save_position()

        except Exception as e:
            self.error_message = str(e)
            self._write_log(
                action="بيع", symbol=symbol, price=0, qty=0,
                reason=f"خطأ في التنفيذ: {e}", status="فشل ❌",
            )

    # ------------------------------------------------------------------
    # السجلات والاستمرارية
    # ------------------------------------------------------------------

    def _write_log(self, action, symbol, price, qty, reason, status) -> None:
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action":    action,
            "symbol":    symbol,
            "price":     round(price, 6) if price else 0,
            "qty":       round(qty,   8) if qty   else 0,
            "reason":    reason,
            "status":    status,
        }
        logs = self.load_logs()
        logs.insert(0, entry)
        logs = logs[:MAX_LOGS]
        try:
            with open(LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_logs(self) -> list:
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_position(self) -> None:
        try:
            with open(POSITION_FILE, "w", encoding="utf-8") as f:
                json.dump(self.current_position, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_position(self) -> Optional[dict]:
        if os.path.exists(POSITION_FILE):
            try:
                with open(POSITION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return None

    # ------------------------------------------------------------------
    # بيانات لوحة التحكم
    # ------------------------------------------------------------------

    def get_dashboard_data(self) -> dict:
        usdt_balance = 0.0
        if self.client and self.running:
            try:
                usdt_balance = self.client.get_balance("USDT")
            except Exception:
                pass

        return {
            "running":          self.running,
            "status":           self.status,
            "last_signal":      self.last_signal,
            "last_check":       self.last_check,
            "current_price":    self.current_price,
            "bb_values":        self.bb_values,
            "current_position": self.current_position,
            "usdt_balance":     usdt_balance,
            "error_message":    self.error_message,
        }
