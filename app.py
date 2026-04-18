"""
app.py
تطبيق Flask الرئيسي — لوحة تحكم البوت
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from config import load_settings, save_settings, get_flask_secret, SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES
from trader import Trader

app = Flask(__name__)
app.secret_key = get_flask_secret()

# الـ Singleton — يُنشأ مرة واحدة عند بدء التطبيق
trader = Trader()


# ======================================================================
# الصفحة الرئيسية — لوحة التحكم
# ======================================================================

@app.route("/")
def index():
    settings = load_settings()
    data     = trader.get_dashboard_data()
    recent_logs = trader.load_logs()[:5]
    return render_template("index.html", settings=settings, data=data, recent_logs=recent_logs)


# ======================================================================
# الإعدادات
# ======================================================================

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        s = load_settings()

        s["symbol"]            = request.form.get("symbol",     s["symbol"])
        s["order_amount"]      = float(request.form.get("order_amount", s["order_amount"]))
        s["timeframe"]         = request.form.get("timeframe",  s["timeframe"])
        s["allow_rebuy"]       = "allow_rebuy" in request.form
        s["bb_length"]         = int(request.form.get("bb_length",     s["bb_length"]))
        s["bb_multiplier"]     = float(request.form.get("bb_multiplier", s["bb_multiplier"]))
        s["mode"]              = request.form.get("mode",       s["mode"])
        s["virtual_api_key"]   = request.form.get("virtual_api_key",   s["virtual_api_key"])
        s["virtual_api_secret"]= request.form.get("virtual_api_secret",s["virtual_api_secret"])
        s["live_api_key"]      = request.form.get("live_api_key",      s["live_api_key"])
        s["live_api_secret"]   = request.form.get("live_api_secret",   s["live_api_secret"])

        save_settings(s)
        flash("تم حفظ الإعدادات بنجاح ✅", "success")
        return redirect(url_for("settings_page"))

    s = load_settings()
    return render_template(
        "settings.html",
        settings=s,
        symbols=SUPPORTED_SYMBOLS,
        timeframes=SUPPORTED_TIMEFRAMES,
    )


# ======================================================================
# أوامر التحكم
# ======================================================================

@app.route("/control/start", methods=["POST"])
def start_bot():
    ok, msg = trader.start()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


@app.route("/control/stop", methods=["POST"])
def stop_bot():
    trader.stop()
    flash("تم إيقاف البوت ✅", "success")
    return redirect(url_for("index"))


@app.route("/control/emergency_sell", methods=["POST"])
def emergency_sell():
    ok, msg = trader.emergency_sell()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("index"))


# ======================================================================
# سجل العمليات
# ======================================================================

@app.route("/logs")
def logs_page():
    logs = trader.load_logs()
    return render_template("logs.html", logs=logs)


@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    import os
    try:
        if os.path.exists("trade_logs.json"):
            os.remove("trade_logs.json")
        flash("تم مسح السجل بنجاح ✅", "success")
    except Exception as e:
        flash(f"خطأ في مسح السجل: {e}", "danger")
    return redirect(url_for("logs_page"))


# ======================================================================
# API — بيانات فورية (للتحديث التلقائي)
# ======================================================================

@app.route("/api/status")
def api_status():
    data     = trader.get_dashboard_data()
    settings = load_settings()
    return jsonify({
        "running":       data["running"],
        "status":        data["status"],
        "last_signal":   data["last_signal"],
        "last_check":    data["last_check"],
        "current_price": data["current_price"],
        "bb_upper":      data["bb_values"].get("upper"),
        "bb_middle":     data["bb_values"].get("middle"),
        "bb_lower":      data["bb_values"].get("lower"),
        "has_position":  data["current_position"] is not None,
        "position":      data["current_position"],
        "usdt_balance":  data["usdt_balance"],
        "error":         data["error_message"],
        "symbol":        settings["symbol"],
        "mode":          settings["mode"],
    })


# ======================================================================
# تشغيل التطبيق
# ======================================================================

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
