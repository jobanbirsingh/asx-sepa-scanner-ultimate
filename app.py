
import math
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="ASX SEPA Scanner — Ultimate", layout="wide")

DEFAULT_TICKERS = [
    "PME","TNE","ALQ","AVH","ANN","CSL","COH","PRU","EVN","BAP","SOP","DXN","360",
    "MAH","SX2","GML","FAU","PAR","PVT","TGN","BCM","COG","JNS","NMG","SHV","ZIP",
    "APX","JIN","STK","ABB","ABG","ADH","AIH","MAF"
]

@st.cache_data(ttl=60*60*8, show_spinner=False)
def get_history(ticker):
    try:
        d = yf.download(ticker, period="2y", interval="1d", auto_adjust=False,
                         progress=False, threads=False)
        if d is None or d.empty:
            return None
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d = d[[c for c in ["Open","High","Low","Close","Volume"] if c in d.columns]].dropna()
        return d if len(d) else None
    except Exception:
        return None

@st.cache_data(ttl=60*60*24, show_spinner=False)
def get_yahoo_fundamentals(ticker):
    out = {}
    try:
        t = yf.Ticker(ticker)
        income = t.income_stmt
        balance = t.balance_sheet
        if income is not None and not income.empty:
            rev = income.loc["Total Revenue"].dropna() if "Total Revenue" in income.index else pd.Series(dtype=float)
            ni = income.loc["Net Income"].dropna() if "Net Income" in income.index else pd.Series(dtype=float)
            if len(rev) >= 2 and float(rev.iloc[1]) != 0:
                out["sales_growth_pct"] = (float(rev.iloc[0])/float(rev.iloc[1])-1)*100
            if len(ni) >= 2 and float(ni.iloc[1]) != 0:
                out["eps_growth_pct"] = (float(ni.iloc[0])/float(ni.iloc[1])-1)*100
        if balance is not None and not balance.empty and income is not None and "Net Income" in income.index:
            if "Stockholders Equity" in balance.index:
                eq = float(balance.loc["Stockholders Equity"].iloc[0])
                if eq:
                    out["roe_pct"] = float(income.loc["Net Income"].iloc[0])/eq*100
    except Exception:
        pass
    return out

def load_fundamentals(uploaded):
    if uploaded is None:
        return pd.DataFrame()
    try:
        x = pd.read_csv(uploaded)
        x.columns = [str(c).strip().lower() for c in x.columns]
        if "ticker" not in x.columns:
            return pd.DataFrame()
        x["ticker"] = x["ticker"].astype(str).str.upper().str.replace(".AX","",regex=False).str.strip()
        return x.set_index("ticker")
    except Exception:
        return pd.DataFrame()

def fund_score(ticker, supplied):
    data = {}
    if supplied is not None:
        data.update(supplied.to_dict())
    auto = get_yahoo_fundamentals(ticker)
    for k,v in auto.items():
        if k not in data or pd.isna(data[k]):
            data[k] = v
    tests = [
        ("eps_growth_pct", lambda x:x >= 15),
        ("sales_growth_pct", lambda x:x >= 10),
        ("eps_acceleration_pct", lambda x:x >= 0),
        ("roe_pct", lambda x:x >= 15),
        ("operating_margin_pct", lambda x:x >= 10),
        ("latest_eps_surprise_pct", lambda x:x >= 0),
        ("net_debt_to_ebitda", lambda x:x <= 2.5),
    ]
    checks=[]
    for key, fn in tests:
        try:
            v=float(data.get(key,np.nan))
            if not np.isnan(v):
                checks.append((key, bool(fn(v))))
        except Exception:
            pass
    passed=sum(x[1] for x in checks)
    return passed, len(checks), passed >= 4, data

def analyze(code, bench, funds, settings, account, risk_pct):
    d = get_history(code+".AX")
    if d is None or len(d) < 220:
        return {"Ticker":code,"Status":"INSUFFICIENT DATA","Reason":"Insufficient price history"}
    c,h,l,v=d["Close"],d["High"],d["Low"],d["Volume"]
    for n in [20,50,100,150,200]:
        d[f"sma{n}"]=c.rolling(n).mean()
    price=float(c.iloc[-1])
    s50,s150,s200=[float(d[f"sma{x}"].iloc[-1]) for x in [50,150,200]]
    slope=(s200/float(d.sma200.iloc[-21])-1)*100
    mom6=(price/float(c.iloc[-126])-1)*100
    mom12=(price/float(c.iloc[-252])-1)*100 if len(c)>=252 else np.nan
    bench6=np.nan
    if bench is not None and len(bench)>=126:
        bench6=(float(bench.iloc[-1])/float(bench.iloc[-126])-1)*100
    rs=mom6-bench6 if not np.isnan(bench6) else np.nan
    high52=float(h.tail(252).max())
    dist=(high52-price)/high52*100
    ranges={n:(float(h.tail(n).max())-float(l.tail(n).min()))/price*100 for n in [20,40,80]}
    vol20=float(v.tail(20).mean()); vol50=float(v.tail(50).mean())
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr20=float(tr.tail(20).mean()); atr50=float(tr.tail(50).mean())
    pivot=float(h.iloc[-21:-1].max())
    volratio=float(v.iloc[-1]/vol50) if vol50 else np.nan
    extension=(price/pivot-1)*100 if pivot else np.nan
    stage2=price>s50>s150>s200 and slope>0
    near=dist<=settings["near_high"]
    setup=sum([ranges[20]<ranges[40]<ranges[80],vol20<vol50*.85,atr20<atr50*.90,
               float(l.tail(20).min())>=float(l.iloc[-40:-20].min())])
    momentum=sum([mom6>0,(not np.isnan(rs) and rs>0),near])
    breakout=price>pivot and volratio>=settings["breakout_vol"]
    frow=funds.loc[code] if code in funds.index else None
    fs,fa,fp,_=fund_score(code+".AX",frow)
    risk_amount=account*risk_pct/100
    stop=min(float(l.tail(20).min()),price*.93)
    shares=math.floor(risk_amount/max(price-stop,.01)) if account else 0

    if price<settings["min_price"]:
        status,reason="REJECT","Below minimum price"
    elif stage2 and breakout and extension<=settings["max_ext"] and momentum>=2 and fp:
        status,reason="BUY TRIGGER — REVIEW","All major mechanical gates aligned"
    elif stage2 and momentum>=2 and setup>=2 and fp:
        status,reason="SEPA SETUP","Stage-2 + momentum + setup + fundamental pass"
    elif stage2 and momentum>=2 and setup>=2:
        status,reason="TECHNICAL SETUP — FUNDAMENTALS","Technical setup passes; fundamentals incomplete"
    elif stage2 and momentum>=2:
        status,reason="WATCH","Stage-2 and momentum present; setup not ready"
    elif momentum>=2:
        status,reason="DEVELOPING","Momentum present; Stage-2 incomplete"
    else:
        status,reason="REJECT","Insufficient trend/momentum"

    return {
        "Ticker":code,"Status":status,"Price":round(price,3),
        "50DMA":round(s50,3),"150DMA":round(s150,3),"200DMA":round(s200,3),
        "200DMA slope %":round(slope,2),"6M %":round(mom6,1),
        "12M %":round(mom12,1) if not np.isnan(mom12) else np.nan,
        "RS vs STW 6M %":round(rs,1) if not np.isnan(rs) else np.nan,
        "From 52W high %":round(dist,1),"20D range %":round(ranges[20],1),
        "40D range %":round(ranges[40],1),"80D range %":round(ranges[80],1),
        "Volume quiet":vol20<vol50*.85,"ATR contract":atr20<atr50*.90,
        "Higher low":float(l.tail(20).min())>=float(l.iloc[-40:-20].min()),
        "Pivot":round(pivot,3),"Vol/50D":round(volratio,2),
        "Extension %":round(extension,1),"Fund score":fs,"Fund checks":fa,
        "Fund status":"PASS" if fp else ("PARTIAL" if fa>=3 else "MISSING"),
        "Stop est.":round(stop,3),"Risk A$":round(risk_amount,2),"Shares @ risk":shares,
        "Reason":reason
    }

def run_scan(universe, fundamentals, settings, account, risk_pct):
    benchdf=get_history("STW.AX")
    bench=benchdf["Close"] if benchdf is not None else None
    rows=[]
    for code in universe:
        rows.append(analyze(code,bench,fundamentals,settings,account,risk_pct))
    out=pd.DataFrame(rows)
    order={"BUY TRIGGER — REVIEW":0,"SEPA SETUP":1,"TECHNICAL SETUP — FUNDAMENTALS":2,
           "WATCH":3,"DEVELOPING":4,"REJECT":5,"INSUFFICIENT DATA":6}
    out["__rank"]=out.Status.map(order).fillna(9)
    if "RS vs STW 6M %" in out.columns:
        out=out.sort_values(["__rank","RS vs STW 6M %"],ascending=[True,False])
    else:
        out=out.sort_values("__rank")
    out=out.drop(columns="__rank")
    s={
        "scanned":len(out),
        "buy_review":int((out.Status=="BUY TRIGGER — REVIEW").sum()),
        "sepa_setup":int((out.Status=="SEPA SETUP").sum()),
        "technical_setup":int((out.Status=="TECHNICAL SETUP — FUNDAMENTALS").sum()),
        "watch":int((out.Status=="WATCH").sum()),
        "developing":int((out.Status=="DEVELOPING").sum()),
        "rejected":int(out.Status.isin(["REJECT","INSUFFICIENT DATA"]).sum())
    }
    return out,s

def chart(ticker,row):
    d=get_history(ticker)
    if d is None: return None
    fig=go.Figure(go.Candlestick(x=d.index,open=d.Open,high=d.High,low=d.Low,close=d.Close,name="Price"))
    for n in [50,150,200]:
        fig.add_trace(go.Scatter(x=d.index,y=d.Close.rolling(n).mean(),name=f"{n}DMA"))
    if pd.notna(row.get("Pivot")):
        fig.add_hline(y=float(row["Pivot"]),annotation_text=f"Pivot {row['Pivot']}")
    fig.update_layout(height=600,xaxis_rangeslider_visible=False)
    return fig

st.title("ASX SEPA Scanner — Ultimate")
st.caption("One-file iPad-friendly deployment. Mechanical SEPA research aid; not automatic trading.")

with st.sidebar:
    st.header("Controls")
    account=st.number_input("Account size (A$)",0.0,10000000.0,50000.0,5000.0)
    risk_pct=st.number_input("Risk per position (%)",0.1,5.0,0.5,0.1)
    min_price=st.number_input("Minimum price (A$)",0.01,100.0,0.50,0.10)
    near_high=st.number_input("Max distance from 52W high (%)",5.0,50.0,25.0,1.0)
    breakout_vol=st.number_input("Breakout volume / 50D avg",1.0,5.0,1.5,0.1)
    max_ext=st.number_input("Max extension above pivot (%)",1.0,20.0,7.5,0.5)
    universe_upload=st.file_uploader("Optional universe CSV",type=["csv"])
    fundamentals_upload=st.file_uploader("Optional fundamentals CSV",type=["csv"])
    run=st.button("Run daily scan",type="primary")

if universe_upload:
    try:
        u=pd.read_csv(universe_upload)
        col=next(c for c in u.columns if c.lower() in ["ticker","symbol","code"])
        universe=sorted(set(u[col].astype(str).str.upper().str.replace(".AX","",regex=False).str.strip()))
    except Exception:
        universe=DEFAULT_TICKERS
else:
    universe=DEFAULT_TICKERS

funds=load_fundamentals(fundamentals_upload)
settings={"min_price":min_price,"near_high":near_high,"breakout_vol":breakout_vol,"max_ext":max_ext}

if run:
    with st.spinner(f"Scanning {len(universe)} stocks..."):
        df,summary=run_scan(universe,funds,settings,account,risk_pct)
    st.session_state["df"]=df
    st.session_state["summary"]=summary

if "df" not in st.session_state:
    st.info("Run the daily scan.")
    st.stop()

df=st.session_state["df"]; s=st.session_state["summary"]
for col,label,value in zip(st.columns(7),
    ["Scanned","Buy review","SEPA setup","Technical setup","Watch","Developing","Rejected"],
    [s["scanned"],s["buy_review"],s["sepa_setup"],s["technical_setup"],s["watch"],s["developing"],s["rejected"]]):
    col.metric(label,value)

st.subheader("Priority review queue")
st.dataframe(df[df.Status.isin(["BUY TRIGGER — REVIEW","SEPA SETUP","TECHNICAL SETUP — FUNDAMENTALS","WATCH"])],
             use_container_width=True,hide_index=True)

st.subheader("Individual chart review")
selected=st.selectbox("Ticker",df.Ticker.tolist())
r=df[df.Ticker==selected].iloc[0]
st.write(f"**{selected} — {r['Status']}**: {r['Reason']}")
fig=chart(selected+".AX",r)
if fig: st.plotly_chart(fig,use_container_width=True)

st.subheader("Full scan")
st.dataframe(df,use_container_width=True,hide_index=True)
st.download_button("Download scan CSV",df.to_csv(index=False).encode(),"asx_sepa_scan.csv","text/csv")

st.subheader("Fundamentals template")
cols=["ticker","eps_growth_pct","sales_growth_pct","eps_acceleration_pct","roe_pct","net_debt_to_ebitda","operating_margin_pct","latest_eps_surprise_pct"]
st.download_button("Download fundamentals template",pd.DataFrame(columns=cols).to_csv(index=False).encode(),"fundamentals_template.csv","text/csv")

st.markdown("""
### Interpretation

**BUY TRIGGER — REVIEW:** all major mechanical gates aligned. Manually verify the business, current earnings, chart, pivot and risk before any trade.

**SEPA SETUP:** trend, momentum, setup and fundamental gate align, but breakout is not confirmed.

**TECHNICAL SETUP — FUNDAMENTALS:** technical setup qualifies but fundamental evidence is incomplete.

**WATCH / DEVELOPING:** promising but not ready.

The free data layer uses yfinance and may be incomplete or delayed. It is not a licensed ASX real-time feed. Missing fundamentals never automatically count as a pass.
""")
