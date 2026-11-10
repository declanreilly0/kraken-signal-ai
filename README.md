# Kraken Signal Lab V2

**Mobile-first, read-only Kraken spot market explorer and paper-trading signal research.**

V2 replaces the large, slow V1 summary panels with a searchable public Kraken spot-pair catalogue and a touch-first candlestick chart. No exchange login, Kraken API credentials, trading permission, or order execution is used anywhere in this project.

## Features

- **Every online spot trading pair returned by Kraken's public `AssetPairs` endpoint**, discovered dynamically rather than a hardcoded BTC/ETH/SOL list. The list updates as Kraken changes it. Search by ticker symbol or trading pair; full marketing names are not always included in Kraken market metadata.
- A **market-wide ticker screener** using a single public `Ticker` request: last traded price, change since Kraken's daily opening price, estimated 24h volume (in each market's quote currency), and indicative bid/ask spread. Filter by quote currency, search, or favourite pairs.
- A **meme-token watchlist filter** for common symbols such as DOGE (Kraken often calls it XDG), SHIB, PEPE, BONK, WIF, FLOKI and others. This is an **approximate convenience tag**, not an exhaustive or authoritative meme-coin list. **All Kraken-listed coins remain searchable, including coins not tagged as memes.**
- Touch chart powered by **TradingView Lightweight Charts v4.2.3** (loaded from a public CDN): **pinch to zoom, drag to pan, +/− buttons, Fit, candle OHLC crosshair**, line/candle toggle, optional EMA 9/21/50 and volume overlays. **Plotly backup** if the chart library is unavailable in Safari.
- Native Kraken spot candle intervals: **1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 15d**. Custom **UTC start/end dates and times** within the available candle data. Any pair can be searched and selected for its chart.
- £50 paper-trade research signals using the original five-indicator checklist and realistic **two-sided fee, bid/ask spread and slippage** estimates; entry/target/stop shown for the *selected* pair only, without fake probability or a promised profit.
- Historical candle replay (strict, limited sample), optional on-demand OpenAI critique, raw candle CSV download.
- **Speed controls:** no always-on reruns by default; manually refresh, or enable 30/60/120-second refresh. Kraken public responses are cached. When the app is closed, it **does not monitor** prices or deliver alerts.

## Update your existing Streamlit app using an iPhone

You already have a GitHub repo named `kraken-signal-ai` that Streamlit deploys automatically. **Do not create a second repo.**

1. In the ChatGPT conversation, download and unzip `kraken_signal_lab_v2.zip` using iPhone **Files**.
2. Open your existing GitHub repository in **Safari**, then choose **Add file → Upload files**. Upload the **individual files** from the extracted V2 folder **into the repository root** (same folder as the existing `app.py`). Do **not** upload the `.zip` file.
3. Required root files: `app.py`, `engine.py`, `chart_ui.py`, `kraken_api.py`, `requirements.txt`. `README.md` is recommended. Replacing existing files with the same names is intentional. The previous `kraken_market.py` is no longer used by V2 and may remain harmlessly in your repo.
4. Optionally upload `.streamlit/config.toml` in its `.streamlit` folder. If iOS hides dotfolders, you can skip it: V2 works without that optional theme file.
5. Click **Commit changes** on GitHub. Your existing Streamlit app should redeploy from the changed main-branch files; refresh its URL. If it doesn't, open the Streamlit Community Cloud dashboard, select your app and use the redeploy/reboot control.
6. On the app, open **🌐 All markets** to explore every online spot pair, or use **📈 Chart**, search for any ticker, then choose **Candle interval**. Touch/pinch to zoom. Pick **Plotly backup** if the fast chart doesn't load.

**Do not commit Kraken passwords, API secrets or OpenAI keys to GitHub.** The optional AI analyst accepts an OpenAI Platform API key at run time for an individual request. API use may incur costs independent of ChatGPT Plus. The app only sends a short snapshot of *public market data* to OpenAI.

### First launch from a computer (alternative)

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit Cloud: repository = your GitHub repo, branch = `main`, main file = `app.py`.

## Important caveats

1. **Kraken REST OHLC limits:** The public OHLC endpoint returns **no more than 720 recent candles for a chosen interval** and includes an *unfinished* final candle. This app deliberately **excludes the unfinished one** for calculations. For example, the 1-minute chart covers approximately the most recent 12 hours, *not* arbitrarily old dates. **Custom date fields cannot retrieve data older than this limit.** Kraken also publishes historical OHLCVT CSV archives if you want to extend history in a future version.
2. **Chart updates:** The server requests fresh candles at most once each 45 seconds per selected pair/interval, unless you manually clear its cache and refresh. A 30-second browser rerun is not second-by-second exchange streaming. On very illiquid coins, candles may be missing during periods with no trades.
3. **All-market scanning vs signal engine:** The *all-markets* tab discovers every online spot pair and ranks public tickers. **It does not compute a full 1-minute EMA/RSI trading signal for every market simultaneously.** Doing so would require heavy polling beyond the simple public REST model and could hit exchange rate limits. Technical signals and historical replay are calculated for the *selected* pair and timeframe.
4. **Meme tagging:** Kraken's `AssetPairs` metadata isn't an exhaustive, verified meme taxonomy. The heuristic meme filter can miss new meme coins and accidentally include ambiguous symbols. Use **All markets** + search when in doubt.
5. **Kraken accounts and region:** A public trading pair being listed does not guarantee it is available for trading in your jurisdiction or account. Check Kraken directly for current restrictions, minimum trade sizes and personal fee tier.
6. **Costs and execution:** A 0.80% taker fee each way is the initial example, **not a guaranteed fee for your account**. Maker 0.40% each way is also illustrative; maker orders may not execute or may end up with taker fees. The model considers a fixed extra slippage allowance and a current bid/ask spread, not a full, historical order-book or fill simulation.
7. **Risk:** Meme coins can have rapid manipulation, delisting, shallow liquidity, extreme spread, failed fills and total losses. No AI or historical replay guarantees returns. Avoid leveraged derivatives and don't use the tool for automated trading.
8. **API key security:** All Kraken operations in this project use public, unauthenticated, **read-only** endpoints. The optional OpenAI request is *only* for explanatory commentary. Replace a compromised secret key.

## Data references

- Kraken markets/symbols and market-wide Ticker: https://support.kraken.com/articles/360000920306-api-symbols-and-tickers
- Kraken API OHLC/history limitations: https://support.kraken.com/articles/advanced-api-faq
- Kraken downloadable OHLCVT: https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data
- Kraken Pro fees: https://www.kraken.com/gb/pro/fees
- TradingView Lightweight Charts: https://tradingview.github.io/lightweight-charts/docs/4.2

## Files

```
app.py                   # Streamlit V2 user interface
kraken_api.py            # Dynamic spot-pair discovery, quotes, candle parsing
chart_ui.py              # Interactive mobile lightweight chart
engine.py                # Fee-aware research rules and historical replay
requirements.txt         # Python dependencies
.streamlit/config.toml  # Optional dark theme
README.md                # Guide
/tests/                  # Offline tests
```

## Run tests

```bash
python -m pip install pytest
python -m pytest -q
```

This software is experimental research software only; it is **not** verified as a profitable trading strategy, broker, regulated financial adviser, or execution service.
