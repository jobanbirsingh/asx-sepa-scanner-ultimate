
import streamlit as st
import pandas as pd
from scanner.config import DEFAULT_SETTINGS, DEFAULT_TICKERS
from scanner.engine import run_scan
from storage.history import save_snapshot, load_history
from ui.charts import make_chart

st.set_page_config(page_title="ASX SEPA Scanner Ultimate", layout="wide")

st.title("ASX SEPA Scanner — Ultimate")
st.caption("Daily ASX SEPA research workflow: universe → data quality → fundamentals → Stage 2 → RS/momentum → base/VCP → pivot/breakout → risk → ranked review.")

with st.sidebar:
    st.header("Scanner controls")
    account = st.number_input("Account size (A$)", 0.0, 10_000_000.0, 50_000.0, 5_000.0)
    risk_pct = st.number_input("Risk per position (%)", 0.1, 5.0, 0.5, 0.1)
    min_price = st.number_input("Minimum share price (A$)", 0.01, 100.0, float(DEFAULT_SETTINGS["min_price"]), 0.10)
    near_high = st.number_input("Maximum distance from 52W high (%)", 5.0, 50.0, float(DEFAULT_SETTINGS["near_high_pct"]), 1.0)
    breakout_vol = st.number_input("Breakout volume / 50D average", 1.0, 5.0, float(DEFAULT_SETTINGS["breakout_volume"]), 0.1)
    max_ext = st.number_input("Maximum extension above pivot (%)", 1.0, 20.0, float(DEFAULT_SETTINGS["max_extension_pct"]), 0.5)
    universe_file = st.file_uploader("Optional custom universe CSV", type=["csv"])
    fundamentals_file = st.file_uploader("Optional fundamentals CSV", type=["csv"])
    run = st.button("Run daily scan", type="primary")

settings = dict(DEFAULT_SETTINGS)
settings.update({
    "min_price": min_price,
    "near_high_pct": near_high,
    "breakout_volume": breakout_vol,
    "max_extension_pct": max_ext,
})

if run:
    with st.spinner("Running the full scan..."):
        result = run_scan(
            universe_file=universe_file,
            fundamentals_file=fundamentals_file,
            account_size=account,
            risk_pct=risk_pct,
            settings=settings,
        )
        save_snapshot(result["results"])
        st.session_state["result"] = result

result = st.session_state.get("result")
if result is None:
    st.info("Run the daily scan to populate the dashboard.")
    st.markdown("""
### What this version is designed to do

**Hard gates**
- Stage-2 trend
- rising 200DMA
- positive momentum
- relative strength
- constructive base
- pivot/breakout quality
- extension control
- fundamental evidence

**It does not automatically buy anything.** A BUY TRIGGER is a shortlist for manual review.
""")
    st.stop()

s = result["summary"]
metrics = st.columns(7)
for col, label, value in zip(metrics,
    ["Scanned","Buy review","SEPA setup","Technical setup","Watch","Developing","Rejected"],
    [s["scanned"],s["buy_review"],s["sepa_setup"],s["technical_setup"],s["watch"],s["developing"],s["rejected"]]):
    col.metric(label, value)

df = result["results"]

st.subheader("Priority review queue")
priority = df[df["Status"].isin(["BUY TRIGGER — REVIEW","SEPA SETUP","TECHNICAL SETUP — FUNDAMENTALS","WATCH"])]
st.dataframe(priority, use_container_width=True, hide_index=True)

st.subheader("Individual stock review")
codes = df["Ticker"].dropna().astype(str).tolist()
selected = st.selectbox("Select ticker", codes)
row = df[df["Ticker"] == selected].iloc[0]
st.write(f"**{selected}: {row['Status']}** — {row['Reason']}")

chart = make_chart(selected + ".AX", row)
if chart is not None:
    st.plotly_chart(chart, use_container_width=True)

detail_cols = st.columns(4)
detail_cols[0].metric("Price", f"A${row.get('Price', 0):.2f}")
detail_cols[1].metric("Pivot", f"A${row.get('Pivot', 0):.2f}")
detail_cols[2].metric("6M momentum", f"{row.get('6M %', 0):.1f}%")
detail_cols[3].metric("RS vs STW", f"{row.get('RS vs STW 6M %', 0):.1f}%")

st.subheader("Full scan")
st.dataframe(df, use_container_width=True, hide_index=True)

st.download_button("Download daily scan CSV", df.to_csv(index=False).encode(), "asx_sepa_daily_scan.csv", "text/csv")

st.subheader("Scan history")
hist = load_history()
if hist.empty:
    st.caption("History will appear after multiple daily scans.")
else:
    st.dataframe(hist.tail(200), use_container_width=True, hide_index=True)
    st.download_button("Download scan history", hist.to_csv(index=False).encode(), "asx_sepa_history.csv", "text/csv")

st.markdown("""
### Important interpretation

**BUY TRIGGER — REVIEW** means the mechanical conditions have aligned. It does not mean the stock is automatically a SEPA buy.

Before acting, manually confirm:
1. Earnings and sales growth are genuinely strong and current.
2. The chart is a clean base/VCP rather than a news spike.
3. The pivot is obvious.
4. Breakout volume is convincing.
5. The stock is not materially extended.
6. The business/news context does not invalidate the setup.
7. Position size matches your predefined account risk.

Free-data fields are labelled according to their evidence quality. Missing information is never silently converted into a pass.
""")
