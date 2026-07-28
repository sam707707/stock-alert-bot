"""
Webull Options Volume/OI Scanner - Railway Version
----------------------------------------------------
نسخة معدّلة تشتغل بدون تفاعل يدوي (تقرأ بيانات الدخول من Environment Variables)
عشان تنشر على Railway كـ Service منفصل بجانب بوت التيليجرام الموجود.

Environment Variables المطلوبة (تضاف من Railway → Variables):
    WEBULL_EMAIL        - إيميل أو رقم جوالك في Webull
    WEBULL_PASSWORD     - كلمة المرور
    WEBULL_MFA_CODE     - رمز التحقق (اختياري، لو الحساب يطلبه أول مرة فقط)
    TELEGRAM_BOT_TOKEN  - (اختياري) لو تبي يرسل التنبيهات على نفس بوت التيليجرام
    TELEGRAM_CHAT_ID    - (اختياري) الآيدي حقك في تيليجرام
"""

import os
import time
import requests
import pandas as pd
from webull import webull, paper_webull

# ============ الإعدادات ============
USE_PAPER_ACCOUNT = True
WATCHLIST = ["AAPL", "NVDA", "CRWV", "TTE", "NOK", "AMD", "SOFI", "PLTR"]
MIN_VOL_OI_RATIO = 2.0
MIN_VOLUME = 50
MAX_DTE = 60
REFRESH_SECONDS = 0  # كل 5 دقائق (عدّلها زي ما تبي)

EMAIL = os.environ.get("WEBULL_EMAIL")
PASSWORD = os.environ.get("WEBULL_PASSWORD")
MFA_CODE = os.environ.get("WEBULL_MFA_CODE")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        print(f"⚠️ تعذر إرسال تيليجرام: {e}")


def login():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("لازم تحدد WEBULL_EMAIL و WEBULL_PASSWORD في Environment Variables")

    wb = paper_webull() if USE_PAPER_ACCOUNT else webull()
    wb.login(EMAIL, PASSWORD)

    if MFA_CODE:
        wb.get_mfa(MFA_CODE)

    return wb


def scan_symbol(wb, symbol):
    results = []
    try:
        expirations = wb.get_options_expiration_dates(stock=symbol)
    except Exception as e:
        print(f"⚠️ تعذر جلب تواريخ الانتهاء لـ {symbol}: {e}")
        return pd.DataFrame()

    for exp in expirations:
        exp_date = exp.get("date")
        dte = exp.get("days") or 0
        if dte > MAX_DTE:
            continue

        try:
            chain = wb.get_options(stock=symbol, count=-1, direction="all")
        except Exception as e:
            print(f"⚠️ تعذر جلب سلسلة العقود لـ {symbol} @ {exp_date}: {e}")
            continue

        for contract in chain:
            for side in ("call", "put"):
                leg = contract.get(side)
                if not leg:
                    continue
                vol = leg.get("volume") or 0
                oi = leg.get("openInterest") or 0
                if vol < MIN_VOLUME or oi <= 0:
                    continue

                ratio = vol / oi
                if ratio >= MIN_VOL_OI_RATIO:
                    results.append({
                        "symbol": symbol,
                        "type": side.upper(),
                        "strike": leg.get("strikePrice"),
                        "expiry": exp_date,
                        "dte": dte,
                        "volume": vol,
                        "open_interest": oi,
                        "vol_oi_ratio": round(ratio, 2),
                        "last_price": leg.get("close"),
                        "delta": leg.get("delta"),
                        "iv": leg.get("impVol"),
                    })

    return pd.DataFrame(results)


def run_scan(wb):
    all_hits = []
    for symbol in WATCHLIST:
        print(f"🔍 يفحص {symbol} ...")
        df = scan_symbol(wb, symbol)
        if not df.empty:
            all_hits.append(df)

    if not all_hits:
        print("ما فيه عقود تجاوزت الفلتر هالجولة.")
        return

    final = pd.concat(all_hits, ignore_index=True)
    final = final.sort_values("vol_oi_ratio", ascending=False)

    print("\n=== 🚨 عقود بنشاط غير طبيعي (Volume/OI) ===")
    print(final.to_string(index=False))
    final.to_csv("vol_oi_hits.csv", index=False)

    # يرسل أعلى 5 عقود على تيليجرام لو مفعّل
    top5 = final.head(5)
    for _, row in top5.iterrows():
        msg = (
            f"🚨 <b>{row['symbol']} {row['type']}</b>\n"
            f"Strike: {row['strike']} | Exp: {row['expiry']} ({row['dte']}d)\n"
            f"Vol/OI: {row['vol_oi_ratio']}x | Vol: {row['volume']} | OI: {row['open_interest']}\n"
            f"Price: {row['last_price']} | Delta: {row['delta']} | IV: {row['iv']}"
        )
        send_telegram(msg)


if __name__ == "__main__":
    print("🔐 يسجل الدخول على Webull...")
    wb = login()
    print("✅ تسجيل الدخول تم بنجاح.\n")

    while True:
        run_scan(wb)
        if REFRESH_SECONDS <= 0:
            break
        print(f"\n⏳ ينتظر {REFRESH_SECONDS} ثانية للفحص التالي...\n")
        time.sleep(REFRESH_SECONDS)
