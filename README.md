# Kraken Signal Lab — paper-trading research dashboard

**A runnable, read-only Kraken spot signal scanner**, built for small trades and accessible from desktop or phone when deployed on a web host. It is **not a money-making guarantee**, a Kraken account connection, or a trading robot.

## What it does

- Fetches **public BTC/GBP, ETH/GBP, SOL/GBP** (and USD) Kraken **spot** candles; 1, 5, 15 minute selectable.
- Refreshes the open dashboard every 30 seconds (it **does not run while closed**).
- Excludes the current unfinished candle; calculates EMA 9/21/50, RSI 14, ATR, 12-bar price breakout and relative volume.
- Produces `BUY SETUP`, `WATCH`, `WAIT`, or `EXIT / AVOID` (exit/avoid is **not** permission to short).
- Requires 4/5 technical conditions and a **positive, cost-adjusted target and >=1.2:1 modelled net reward/risk** before a `BUY SETUP`.
- Shows indicative prices and simulated £50 P&L after fees, live bid/ask spread and assumed slippage.
- Replays historical signals with next-candle entry and pessimistic stop-first treatment of ambiguous candles.
- Optionally has an OpenAI model **critique** the setup, if you provide an OpenAI API key; it cannot override the hard signal rules.
- No API keys required for Kraken, no private balance access, and no order placement code anywhere.

## Quick start on a Windows or Mac computer

1. Install **Python 3.11+** from https://python.org and unzip this folder.
2. In Terminal / PowerShell, go into the unzipped `kraken_signal_lab` folder.
3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

   On some Macs, use `python3` instead of `python`.
4. Run:

   ```bash
   python -m streamlit run app.py
   ```

5. Open the local URL shown by Streamlit (usually `http://localhost:8501`).

No Kraken login is needed. The default market is **ETH/GBP**, timeframe **1 minute**, theoretical stake **£50**, and Kraken Pro **base-tier taker** fees at 0.80% per side.

## How to use on an iPhone

Streamlit apps require a Python environment or host to run. To have a mobile-friendly website, upload the folder to your **own GitHub repository**, then deploy `app.py` on [Streamlit Community Cloud](https://share.streamlit.io/). The host installs `requirements.txt`. Open your deployment's website URL in Safari on iPhone. Hosting limits, privacy and possible plan fees depend on the provider. **Do not commit API keys** to GitHub.

You can also run it on your computer and use the computer's network address on your phone when connected to the same local Wi-Fi, subject to firewall settings.

## Optional ChatGPT-powered commentary

In **✨ AI analyst**, paste an **OpenAI Platform API** key into the password field, select a supported model, and click **Analyse this chart with AI**. This sends a small snapshot of candle/indicator data to OpenAI; it does **not** send your Kraken credentials (this app doesn't know them). A ChatGPT Plus subscription is **not** the same as OpenAI API billing. More information: https://platform.openai.com/docs/api-reference/responses.

The AI is for reasoning and explanations. Price monitoring, signal rules and costs do not rely on AI model prompts. The dashboard is **read-only** and never places orders.

## Strategy and costs

A 1-minute candle is an **observation interval**, not a required holding period. Entry filters require an uptrend, previous 12-bar high breakout, RSI momentum, relative volume and a constructive candle; four of the five are needed. A volatility-based stop and a target 2.8× the initial mid-price stop distance are evaluated against both-side trading fees, spread, slippage, and at least 1.2:1 **net** target reward / stop risk.

When most minute movements are smaller than total round-trip fees, **WAIT** is the intended outcome. The price movement needed to break even is calculated with fee compounding and should typically exceed 1.6% for base-tier taker fees **before** spread/slippage. A hypothetical maker scenario is available but maker fills are not guaranteed; actual filled orders can receive taker fees.

Source: https://www.kraken.com/gb/pro/fees (the published fees may change, and your account tier/pair can differ). Kraken public data: https://support.kraken.com/articles/360000919986-public-endpoint-examples-you-can-try-them-directly-in-a-web-browser-

## Limitations / warnings

- Kraken's OHLC REST data returns **only up to 720 recent candles** per chosen interval. This is **not enough** to verify statistical edge. See https://support.kraken.com/in/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data.
- Indicative entry at a candle close is **not a trade fill**. The replay assumes an order can fill at the next candle's opening reference price adjusted by a fixed cost/slippage model. Reality often differs, especially at one-minute frequencies.
- Stop-first assumptions on candles that crossed both levels, but gaps, tick-level intrabar ordering, network delay, varying spread, maker fill probability, FX conversion, tax and outages aren't fully captured.
- Paper replay assumes fixed stakes and never compounds. Historical results have no predictive guarantee.
- USD pairs use percentage-equivalent £50 P&L without modelling currency conversion, so choose GBP pairs for a £50 comparison.
- Only read-only **spot** market data is fetched. No derivatives, margin, short-selling, order placement, balance access, or access to your Kraken account. No API trading keys are needed. Never share trading keys with a third party.
- This isn't institutional/high-frequency low-latency execution. If it shows a bullish signal, that **does not** mean it is safe or profitable to follow.

## Run tests

From the project folder:

```bash
python -m pytest -q
```

Requires `pytest` (install with `python -m pip install pytest`).

## Files

- `app.py` – interactive dashboard / optional AI commentary
- `kraken_market.py` – public Kraken REST client
- `engine.py` – indicators, signals, fee economics, replay
- `requirements.txt`, `.streamlit/config.toml` – install / styling
- `tests/test_engine.py` – unit and replay tests

Not financial advice. You could lose your entire crypto allocation. This is research software, not a profitable product with established performance.
