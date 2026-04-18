"""
indicators.py
حساب مؤشر بولينجر باند وإشارات التداول بدون مكتبة pandas
يعتمد على دوال بايثون الأساسية فقط (statistics.pstdev)
"""

import statistics
from typing import Optional, Tuple


def calculate_bollinger_bands(
    closes: list,
    length: int = 20,
    multiplier: float = 2.0,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    حساب بولينجر باند لقائمة أسعار الإغلاق.

    المعاملات:
        closes    : قائمة أسعار الإغلاق (الأحدث في النهاية)
        length    : عدد الشموع لحساب المتوسط المتحرك
        multiplier: معامل الانحراف المعياري

    الإرجاع:
        (upper, middle, lower) أو (None, None, None) إذا كانت البيانات غير كافية
    """
    if len(closes) < length:
        return None, None, None

    window = closes[-length:]
    middle = sum(window) / length
    std = statistics.pstdev(window)

    upper = middle + multiplier * std
    lower = middle - multiplier * std

    return upper, middle, lower


def get_signal(
    ohlcv: list,
    length: int = 20,
    multiplier: float = 2.0,
) -> Optional[str]:
    """
    تحليل بيانات الشموع وإرجاع إشارة التداول.

    المنطق:
        - إشارة شراء  : سعر الإغلاق السابق أقل من الحد السفلي السابق
                        AND سعر الإغلاق الحالي أعلى من الحد السفلي الحالي
                        AND حجم التداول الحالي أعلى من متوسط الحجم
        - إشارة بيع  : سعر الإغلاق السابق أعلى من الحد العلوي السابق
                        AND سعر الإغلاق الحالي أقل من الحد العلوي الحالي
                        AND حجم التداول الحالي أعلى من متوسط الحجم

    المعاملات:
        ohlcv     : قائمة شموع [timestamp, open, high, low, close, volume]
        length    : فترة البولينجر باند
        multiplier: معامل الانحراف المعياري

    الإرجاع:
        'BUY' | 'SELL' | None
    """
    # نحتاج على الأقل length + 3 شمعة لإجراء المقارنة
    min_required = length + 3
    if len(ohlcv) < min_required:
        return None

    closes  = [c[4] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]

    # الشمعة الأخيرة المكتملة هي [-1]، والتي قبلها [-2]
    # نحسب BB لكل شمعة بناءً على الـ `length` شمعة التي قبلها مباشرةً
    curr_close  = closes[-1]
    prev_close  = closes[-2]
    curr_volume = volumes[-1]

    # بولينجر باند للشمعة الحالية (يُحسب من الشموع السابقة لها)
    bb_curr = closes[-length - 1: -1]
    upper_curr, _, lower_curr = calculate_bollinger_bands(bb_curr, length, multiplier)

    # بولينجر باند للشمعة السابقة
    bb_prev = closes[-length - 2: -2]
    upper_prev, _, lower_prev = calculate_bollinger_bands(bb_prev, length, multiplier)

    if upper_curr is None or upper_prev is None:
        return None

    # فلتر الحجم: حجم الشمعة الحالية > متوسط حجم الـ length شمعة الأخيرة
    avg_volume = sum(volumes[-length - 1: -1]) / length
    if curr_volume <= avg_volume:
        return None

    # إشارة الشراء: اختراق الحد السفلي صعوداً
    if prev_close < lower_prev and curr_close > lower_curr:
        return "BUY"

    # إشارة البيع: اختراق الحد العلوي هبوطاً
    if prev_close > upper_prev and curr_close < upper_curr:
        return "SELL"

    return None


def get_current_bb_values(
    ohlcv: list,
    length: int = 20,
    multiplier: float = 2.0,
) -> dict:
    """
    إرجاع قيم البولينجر باند الحالية للعرض في لوحة التحكم.
    """
    if len(ohlcv) < length + 1:
        return {"upper": None, "middle": None, "lower": None}

    closes = [c[4] for c in ohlcv]
    bb_window = closes[-length - 1: -1]
    upper, middle, lower = calculate_bollinger_bands(bb_window, length, multiplier)

    return {
        "upper":  round(upper,  6) if upper  is not None else None,
        "middle": round(middle, 6) if middle is not None else None,
        "lower":  round(lower,  6) if lower  is not None else None,
    }
