"""
app.py — تطبيق Flask الرئيسي (يدعم بوتات متعددة)
"""

import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from config import (
    load_settings, save_settings, get_flask_secret,
    load_bots, add_bot, update_bot, delete_bot,
    SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES,
)
from trader import BotManager, load_all_logs

app = Flask(__name__)
app.secret_key = get_flask_secret()

manager = BotManager()


# ======================================================================
# الصفحة الرئيسية
# ======================================================================

@app.route("/")
def index():
    settings    = load_settings()
    bots_status = manager.get_all_status()
    balance     = manager.get_usdt_balance()
    recent_logs = load_all_logs()[:5]
    return render_template(
        "index.html",
        settings=settings,
        bots_status=bots_status,
        balance=balance,
        recent_logs=recent_logs,
    )


# ======================================================================
# الإعدادات العامة
# ======================================================================

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        s = load_settings()
        s["mode"]               = request.form.get("mode",               s["mode"])
        s["virtual_api_key"]    = request.form.get("virtual_api_key",    s["virtual_api_key"])
        s["virtual_api_secret"] = request.form.get("virtual_api_secret", s["virtual_api_secret"])
        s["live_api_key"]       = request.form.get("live_api_key",       s["live_api_key"])
        s["live_api_secret"]    = request.form.get("live_api_secret",    s["live_api_secret"])
        s["whatsapp_enabled"]   = "whatsapp_enabled" in request.form
        s["whatsapp_token"]     = request.form.get("whatsapp_token",     s.get("whatsapp_token", ""))
        s["whatsapp_phone"]     = request.form.get("whatsapp_phone",     s.get("whatsapp_phone", ""))
        save_settings(s)
        manager.refresh_client()
        flash("تم حفظ الإعدادات بنجاح ✅", "success")
        return redirect(url_for("settings_page"))

    return render_template(
        "settings.html",
        settings=load_settings(),
        bots=load_bots(),
        symbols=SUPPORTED_SYMBOLS,
        timeframes=SUPPORTED_TIMEFRAMES,
    )


# ======================================================================
# إدارة البوتات (إضافة / تعديل / حذف)
# ======================================================================

@app.route("/bot/add", methods=["POST"])
def bot_add():
    bot_data = {
        "name":          request.form.get("name", "بوت جديد"),
        "symbol":        request.form.get("symbol", "BTCUSDT"),
        "order_amount":  float(request.form.get("order_amount", 10)),
        "timeframe":     request.form.get("timeframe", "1h"),
        "allow_rebuy":   "allow_rebuy" in request.form,
        "bb_length":     int(request.form.get("bb_length", 20)),
        "bb_multiplier": float(request.form.get("bb_multiplier", 2.0)),
    }
    new_bot = add_bot(bot_data)
    flash(f"تم إضافة البوت '{new_bot['name']}' ✅", "success")
    return redirect(url_for("settings_page"))


@app.route("/bot/<int:bot_id>/edit", methods=["POST"])
def bot_edit(bot_id):
    bot_data = {
        "name":          request.form.get("name"),
        "symbol":        request.form.get("symbol"),
        "order_amount":  float(request.form.get("order_amount", 10)),
        "timeframe":     request.form.get("timeframe"),
        "allow_rebuy":   "allow_rebuy" in request.form,
        "bb_length":     int(request.form.get("bb_length", 20)),
        "bb_multiplier": float(request.form.get("bb_multiplier", 2.0)),
    }
    update_bot(bot_id, bot_data)
    flash("تم تحديث البوت ✅", "success")
    return redirect(url_for("settings_page"))


@app.route("/bot/<int:bot_id>/delete", methods=["POST"])
def bot_delete(bot_id):
    manager.stop_bot(bot_id)
    delete_bot(bot_id)
    flash("تم حذف البوت ✅", "success")
    return redirect(url_for("settings_page"))


# ======================================================================
# تشغيل / إيقاف البوتات
# ======================================================================

@app.route("/bot/<int:bot_id>/start", methods=["POST"])
def bot_start(bot_id):
    ok, msg = manager.start_bot(bot_id)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


@app.route("/bot/<int:bot_id>/stop", methods=["POST"])
def bot_stop(bot_id):
    ok, msg = manager.stop_bot(bot_id)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


@app.route("/bot/<int:bot_id>/emergency", methods=["POST"])
def bot_emergency(bot_id):
    ok, msg = manager.emergency_sell(bot_id)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


@app.route("/control/start_all", methods=["POST"])
def start_all():
    ok, msg = manager.start_all()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


@app.route("/control/stop_all", methods=["POST"])
def stop_all():
    manager.stop_all()
    flash("تم إيقاف جميع البوتات ✅", "success")
    return redirect(url_for("index"))


# ======================================================================
# سجل العمليات
# ======================================================================

@app.route("/logs")
def logs_page():
    logs = load_all_logs()
    return render_template("logs.html", logs=logs)


@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_logs.json")
    try:
        if os.path.exists(path):
            os.remove(path)
        flash("تم مسح السجل ✅", "success")
    except Exception as e:
        flash(f"خطأ: {e}", "danger")
    return redirect(url_for("logs_page"))


# ======================================================================
# API
# ======================================================================

@app.route("/api/status")
def api_status():
    return jsonify({
        "bots":    manager.get_all_status(),
        "balance": manager.get_usdt_balance(),
    })


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

@app.route("/api/test_whatsapp", methods=["POST"])
def test_whatsapp():
    from notifier import send_whatsapp
    s     = load_settings()
    phone = s.get("whatsapp_phone", "")
    token = s.get("whatsapp_token", "")
    if not phone or not token:
        return jsonify({"success": False, "message": "رقم الجوال أو التوكن غير محدد"})
    msg = "✅ اختبار من راصد التداول — البوت يعمل بشكل صحيح!"
    ok  = send_whatsapp(msg, phone, token)
    return jsonify({"success": ok, "message": "تم الإرسال" if ok else "فشل الإرسال"})
