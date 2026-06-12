import asyncio,logging,time
from datetime import datetime,time as dt_time
import pytz,requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from telegram import Bot
from telegram.ext import Application,CommandHandler,ContextTypes
from telegram.constants import ParseMode
TELEGRAM_TOKEN="8588720942:AAE4MDA-ySCdbkcTZqrsj3mPc_LIJvatSAc"
CHAT_ID="659414065"
SCAN_INTERVAL=900
VOLUME_SPIKE_MIN=1.5
RSI_MAX=65
RSI_MIN=35
ET=pytz.timezone("America/New_York")
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s",level=logging.INFO)
log=logging.getLogger(__name__)
H={"User-Agent":"Mozilla/5.0"}
def build_url(p):
 f="sh_avgvol_o500,sh_price_o5,ta_rsi_nos65,ta_volatility_mo5" if p=="us" else "sh_avgvol_o100,sh_price_u10,cap_smallunder,ta_rsi_nos65"
 return"https://finviz.com/screener.ashx?v=111&f="+f+"&o=-volume"
def fetch(p):
 t=[]
 try:
  r=requests.get(build_url(p),headers=H,timeout=15)
  s=BeautifulSoup(r.text,"html.parser")
  tb=s.find("table",{"id":"screener-views-table"})
  if not tb:return[]
  for row in tb.find_all("tr")[1:26]:
   c=row.find_all("td")
   if len(c)<11:continue
   try:
    x={"symbol":c[1].text.strip(),"company":c[2].text.strip(),"price":float(c[8].text.strip().replace(",","")or 0),"change":c[9].text.strip(),"volume":c[10].text.strip()}
    if x["symbol"]:t.append(x)
   except:continue
 except Exception as e:log.error(e)
 return t
def ohlcv(sym):
 try:
  import yfinance as yf
  df=yf.download(sym,period="3mo",interval="1d",progress=False)
  if df.empty or len(df)<20:return None
  df.columns=[c[0] if isinstance(c,tuple)else c for c in df.columns]
  return df.tail(50)
 except:return None
def squeeze(df):
 c,h,l,n=df["Close"],df["High"],df["Low"],20
 m=c.rolling(n).mean()
 bu=m+2*c.rolling(n).std();bd=m-2*c.rolling(n).std()
 tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
 a=tr.rolling(n).mean()
 ku=m+1.5*a;kd=m-1.5*a
 n1=(bu.iloc[-1]<ku.iloc[-1])and(bd.iloc[-1]>kd.iloc[-1])
 p1=(bu.iloc[-2]<ku.iloc[-2])and(bd.iloc[-2]>kd.iloc[-2])
 mom=((c-((h+l)/2).rolling(n).mean())).rolling(n).mean().iloc[-1]
 return{"in":n1,"rel":(not n1)and p1,"up":mom>0}
def rsi(df):
 d=df["Close"].diff()
 rs=d.clip(lower=0).rolling(14).mean()/(-d.clip(upper=0).rolling(14).mean())
 return round(float(100-(100/(1+rs.iloc[-1]))),1)
def pvol(s):
 s=s.upper().replace(",","")
 if"M"in s:return float(s.replace("M",""))*1e6
 if"K"in s:return float(s.replace("K",""))*1e3
 try:return float(s)
 except:return 0.0
def analyze(t):
 df=ohlcv(t["symbol"])
 if df is None:return None
 sq=squeeze(df)
 avg=df["Volume"].rolling(20).mean().iloc[-1]
 ratio=pvol(t["volume"])/avg if avg>0 else 0
 r=rsi(df)
 e20=df["Close"].ewm(span=20).mean().iloc[-1]
 e50=df["Close"].ewm(span=50).mean().iloc[-1]
 pr=df["Close"].iloc[-1]
 tr="🟢 صاعد" if pr>e20>e50 else("🔴 هابط" if pr<e20<e50 else"🟡 محايد")
 if not((sq["rel"]or(sq["in"]and sq["up"]))and ratio>=VOLUME_SPIKE_MIN and RSI_MIN<=r<=RSI_MAX):return None
 return{**t,"str":"🔥🔥 قوية" if sq["rel"]else"⚡ معقولة","rel":sq["rel"],"ratio":round(ratio,2),"rsi":r,"trend":tr}
def fmt(s,cat):
 lb="🏛 US" if cat=="us"else"💎 Penny"
 sq="🚀 Squeeze انفجر!"if s["rel"]else"🔄 Squeeze نشط"
 return f"━━━━━━━━━━━━━━━\n{lb} | {s['str']}\n━━━━━━━━━━━━━━━\n🎯 *{s['symbol']}* — {s['company'][:25]}\n💰 ${s['price']} | {s['change']}\n\n📡 *الإشارات:*\n  {sq}\n  📦 Volume: `{s['ratio']}x`\n  📈 RSI: `{s['rsi']}`\n  🧭 {s['trend']}\n⚠️ _أداة تحليل فقط_\n━━━━━━━━━━━━━━━"
async def scan(bot):
 now=datetime.now(ET)
 if not(dt_time(9,30)<=now.time()<=dt_time(16,0)):return
 found=[]
 for cat in["us","penny"]:
  for t in fetch(cat):
   r=analyze(t)
   if r:found.append((r,cat))
   time.sleep(0.3)
 if found:
  await bot.send_message(CHAT_ID,f"🔔 *تنبيهات الدخول*\n🕐 {now.strftime('%H:%M ET')} | {len(found)} إشارة",parse_mode=ParseMode.MARKDOWN)
  for s,c in found[:8]:
   await bot.send_message(CHAT_ID,fmt(s,c),parse_mode=ParseMode.MARKDOWN)
   await asyncio.sleep(0.5)
async def s1(u,ctx):await u.message.reply_text("👋 بوت تنبيهات الأسهم\n/scan سكان فوري\n/status الحالة")
async def s2(u,ctx):
 await u.message.reply_text("🔍 جاري السكان...")
 await scan(ctx.bot)
async def s3(u,ctx):
 now=datetime.now(ET)
 st="🟢 مفتوح" if dt_time(9,30)<=now.time()<=dt_time(16,0)else"🔴 مغلق"
 await u.message.reply_text(f"✅ البوت يعمل\n{st} | {now.strftime('%H:%M ET')}")
async def periodic(ctx):await scan(ctx.bot)
def main():
 app=Application.builder().token(TELEGRAM_TOKEN).build()
 app.add_handler(CommandHandler("start",s1))
 app.add_handler(CommandHandler("scan",s2))
 app.add_handler(CommandHandler("status",s3))
 app.job_queue.run_repeating(periodic,interval=SCAN_INTERVAL,first=60)
 app.run_polling()
if __name__=="__main__":main()
