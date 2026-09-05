# ASX SEPA Scanner — Ultimate

A modular, browser-based ASX SEPA research scanner.

## Core pipeline

Universe → data quality → fundamentals → Stage 2 → momentum → relative strength → base/VCP proxies → pivot → breakout → extension → risk → ranked manual review.

## What is included

- Configurable universe
- Cached daily price data
- 50/150/200DMA trend analysis
- 200DMA slope
- 6M/12M momentum
- Relative strength vs STW
- 52-week high proximity
- Range contraction
- Volume contraction
- ATR contraction
- Higher-low detection
- Mechanical pivot
- Breakout-volume test
- Extension control
- Best-effort fundamental data adapter
- Optional fundamentals CSV
- Risk-based position sizing
- Ranked review queue
- Interactive candlestick charts
- Daily scan history
- CSV exports
- Separate data / analysis / UI modules

## Data-source reality

The free version uses yfinance for research convenience. It should not be treated as a licensed real-time ASX feed. ASX provides official market-data services and third-party access options.

The announcement adapter is deliberately a placeholder until an authorized/appropriate announcement feed is connected. The scanner will not silently scrape an unstable endpoint and pretend that it is production-grade.

## Important

This is a mechanical approximation of a SEPA workflow. It cannot automatically determine every discretionary VCP/base feature or replace manual fundamental/chart review.

A BUY TRIGGER is a review signal, not an automatic trade.

## Deployment

Upload the contents of this repository to GitHub, then deploy `app.py` through Streamlit Community Cloud.

Python 3.12 is recommended.
