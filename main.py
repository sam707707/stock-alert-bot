import asyncio,logging,time
from datetime import datetime,time as dt_time
import pytz,requests
from bs4 import BeautifulSoup
from telegram.ext import Application,CommandHandler,ContextTypes
from telegram.constants import ParseMode
import yfinance as yf

TELEGRAM_TOKEN="8588720942:AAE4MDA-ySCdbkcTZqrsj3mPc_LIJvatSAc"
CHAT_ID="659414065"
SCAN_INTERVAL=900
ET=pytz.timezone("America/New_York")
logging.basicConfig(format="%(asctime)s|%(levelname)s|%(message)s",level=logging.INFO)
log=logging.getLogger(__name__)
H={"User-Agent":"Mozilla/5.0"}

def fetch(p):
 t=[]
 f="sh_avgvol_o500,sh_price_o5,ta_rsi_nos65" if p=="us" else "sh_avgvol_o100,sh_price_u10,cap_smallunder"
 url="https://finviz.com/screener.ashx?v=111&f="+f+"&o=-volume"
 try:
  r=requests.get(url,headers=H,timeout=15)
  from bs4 import BeautifulSoup
  s=BeautifulSoup(r.text,"html.parser")
  tb=s.find("table",{"id":"screener-views-table"})
  if not tb:return[]
  for row in tb.find_all("tr")[1:20]:
   c=row.find_all("td")
   if len(c)<11:continue
   try:
    x={"symbol":c[1].text.strip(),"company":c[2].text.strip(),"price":c[8].text.strip(),"change":c[9].text.strip(),"volume":c[10].text.strip()}
    if x["symbol"]:t.append(x)
   except:continue
 except Exception as e:log.error(e)
 return t

def analyze(t):
 try:
  df=yf.download(t["symbol"],period="2mo",interval="1d",progress=False)
  if df.empty or len(df)<20:return None
  if hasattr(df.columns,'levels'):df.columns=[c[0] for c in df.columns]
  c=list(df["Close"])
  h=list(df["High"])
  l=list(df["Low"])
  v=list(df["Volume"])
  n=20
  avg_c=sum(c[-n:])/n
  std_c=(sum((x-avg_c)**2 for x in c[-n:])/n)**0.5
  bb_up=avg_c+2*std_c;bb_dn=avg_c-2*std_c
  trs=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))for i in range(-n,0)]
  atr=sum(trs)/n
  kc_up=avg_c+1.5*atr;kc_dn=avg_c-1.5*atr
  in_sq=(bb_up<kc_up)and(bb_dn>kc_dn)
  avg_c2=sum(c[-n-1:-1])/n
  std_c2=(sum((x-avg_c2)**2 for x in c[-n-1:-1])/n)**0.5
  bb_up2=avg_c2+2*std_c2;bb_dn2=avg_c2-2*std_c2
  trs2=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))for i in range(-n-1,-1)]
  atr2=sum(trs2)/n
  kc_up2=avg_c2+1.5*atr2;kc_dn2=avg_c2-1.5*atr2
  in_sq2=(bb_up2<kc_up2)and(bb_dn2>kc_dn2)
  released=(not in_sq)and in_sq2
  avg_v=sum(v[-20:])/20
  def pv(s):
   s=str(s).upper().replace(",","")
   if"M"in s:return float(s.replace("M",""))*1e6
   if"K"in s:return float(s.replace("K",""))*1e3
   try:return float(s)
   except:return 0.0
  ratio=pv(t["volume"])/avg_v if avg_v>0 else 0
  gains=[max(c[i]-c[i-1],0)for i in range(-14,0)]
  losses=[max(c[i-1]-c[i],0)for i in range(-14,0)]
  ag=sum(gains)/14;al=sum(losses)/14
  rsi=100-(100/(1+(ag/al if al>0 else 99)))
  e20=c[-1];e50=c[-1]
  for i in range(len(c)-2,-1,-1):
   e20=c[i]*2/21+e20*(1-2/21)
   if i>=len(c)-50:e50=c[i]*2/51+e50*(1-2/51)
  trend="🟢 صاعد" if c[-1]>e20>e50 else("🔴 هابط" if c[-1]<e20<e50 else"🟡 محايد")
  if not((released or(in_sq and c[-1]>avg_c))and ratio>=1.5 and 35<=rsi<=65):return None
  return{**t,"str":"🔥🔥 قوية" if released else"⚡ معقولة","rel":released,"ratio":round(ratio,2),"rsi":round(rsi,1),"trend":trend}
 except Exception as e:
  log.warning(f"{t['symbol']}: {e}");return None

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
