"""
notifier.py
إرسال إشعارات واتساب عند كل عملية شراء أو بيع
"""

import requests
from typing import Optional

WHATSAPP_API_URL = "https://whatsapp.tkwin.com.sa/api/v1/send"


def send_whatsapp(message: str, phone: str, token: str) -> bool:
    """إرسال رسالة واتساب"""
    if not phone or not token:
        return False
    try:
        r = requests.post(
            WHATSAPP_API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json={"to": phone, "message": message},
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def build_trade_message(
    action:  str,
    symbol:  str,
    price:   float,
    qty:     float,
    reason:  str,
    pnl:     Optional[str] = None,
    bot_name: str = "",
) -> str:
    """بناء نص رسالة الواتساب"""
    if "شراء" in action:
        icon = "📈"
    elif "طارئ" in action:
        icon = "🚨"
    else:
        icon = "📉"

    total = price * qty if price and qty else 0
    lines = [
        f"🤖 *راصد التداول*",
        f"━━━━━━━━━━━━━━━━━",
        f"{icon} *{action}*",
    ]
    if bot_name:
        lines.append(f"البوت: {bot_name}")
    lines += [
        f"الزوج: {symbol}",
        f"السعر: {price:,.4f} USDT",
        f"الكمية: {qty:.8f}",
        f"الإجمالي: {total:,.4f} USDT",
    ]
    if pnl:
        lines.append(f"الربح/الخسارة: {pnl}")
    lines += [
        f"السبب: {reason}",
        f"━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)
