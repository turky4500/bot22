"""
binance_client.py
صنف مخصص للتعامل مع منصة Binance عبر مكتبة CCXT
يدعم الوضع الافتراضي (Testnet) والوضع الحقيقي (Live)
"""

import ccxt
from typing import Optional


class BinanceClient:
    """واجهة موحدة للتعامل مع Binance Spot"""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.testnet = testnet
        self._markets_loaded = False

        self.exchange = ccxt.binance({
            "apiKey":          api_key,
            "secret":          api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        })

        if testnet:
            self.exchange.set_sandbox_mode(True)

    # ------------------------------------------------------------------
    # بيانات السوق
    # ------------------------------------------------------------------

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list:
        """جلب بيانات الشموع اليابانية"""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return raw  # [[timestamp, open, high, low, close, volume], ...]

    def get_ticker_price(self, symbol: str) -> float:
        """السعر الحالي للزوج"""
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"] or ticker["close"] or 0)

    def get_order_book(self, symbol: str, limit: int = 5) -> dict:
        """دفتر الأوامر"""
        return self.exchange.fetch_order_book(symbol, limit)

    # ------------------------------------------------------------------
    # إدارة الرصيد
    # ------------------------------------------------------------------

    def get_balance(self, currency: str = "USDT") -> float:
        """الرصيد المتاح لعملة معينة"""
        balance = self.exchange.fetch_balance()
        return float(balance.get(currency, {}).get("free", 0))

    def get_asset_balance(self, symbol: str) -> float:
        """
        الرصيد المتاح من العملة الأساسية للزوج.
        مثال: BTCUSDT → رصيد BTC
        """
        base = self._get_base_currency(symbol)
        return self.get_balance(base)

    def get_full_balance(self) -> dict:
        """جميع الأرصدة غير الصفرية"""
        balance = self.exchange.fetch_balance()
        result = {}
        for currency, info in balance.get("total", {}).items():
            if isinstance(info, (int, float)) and info > 0:
                result[currency] = {
                    "free":  float(balance.get(currency, {}).get("free", 0)),
                    "used":  float(balance.get(currency, {}).get("used", 0)),
                    "total": float(info),
                }
        return result

    # ------------------------------------------------------------------
    # تنفيذ الأوامر
    # ------------------------------------------------------------------

    def _ensure_markets(self) -> None:
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def _get_base_currency(self, symbol: str) -> str:
        """استخراج العملة الأساسية من رمز الزوج"""
        self._ensure_markets()
        market = self.exchange.market(symbol)
        return market["base"]

    def _calc_qty(self, symbol: str, amount_usdt: float, price: float) -> float:
        """حساب الكمية بدقة السوق"""
        self._ensure_markets()
        raw_qty = amount_usdt / price
        return float(self.exchange.amount_to_precision(symbol, raw_qty))

    def create_limit_buy(self, symbol: str, amount_usdt: float, price: float) -> dict:
        """
        أمر شراء محدود السعر (Limit Buy)
        amount_usdt: المبلغ بالـ USDT
        price      : سعر التنفيذ المطلوب (سعر إغلاق الشمعة)
        """
        self._ensure_markets()
        qty   = self._calc_qty(symbol, amount_usdt, price)
        price = float(self.exchange.price_to_precision(symbol, price))
        order = self.exchange.create_order(symbol, "limit", "buy", qty, price)
        return order

    def create_market_buy(self, symbol: str, amount_usdt: float) -> dict:
        """أمر شراء بسعر السوق (Market Buy) — يُستخدم للحالات الطارئة"""
        self._ensure_markets()
        price = self.get_ticker_price(symbol)
        qty   = self._calc_qty(symbol, amount_usdt, price)
        order = self.exchange.create_order(symbol, "market", "buy", qty)
        return order

    def create_limit_sell(self, symbol: str, qty: float, price: float) -> dict:
        """أمر بيع محدود السعر (Limit Sell)"""
        self._ensure_markets()
        qty   = float(self.exchange.amount_to_precision(symbol, qty))
        price = float(self.exchange.price_to_precision(symbol, price))
        order = self.exchange.create_order(symbol, "limit", "sell", qty, price)
        return order

    def create_market_sell(self, symbol: str, qty: float) -> dict:
        """أمر بيع بسعر السوق (Market Sell) — للبيع الطارئ"""
        self._ensure_markets()
        qty = float(self.exchange.amount_to_precision(symbol, qty))
        order = self.exchange.create_order(symbol, "market", "sell", qty)
        return order

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """إلغاء أمر معلق"""
        return self.exchange.cancel_order(order_id, symbol)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """الأوامر المعلقة"""
        return self.exchange.fetch_open_orders(symbol)

    def get_order_status(self, order_id: str, symbol: str) -> dict:
        """حالة أمر محدد"""
        return self.exchange.fetch_order(order_id, symbol)
