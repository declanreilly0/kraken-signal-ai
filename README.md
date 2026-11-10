# Kraken Meme Signal Radar — Version 3

**What it does:** automatically examines Kraken's **currently online public spot markets** from a bulk market-data snapshot, prioritises meme coins and newly discovered listings, then performs **batched** technical analysis for potential spot-long trades. For a deeply scanned coin it can show a **buy trigger, conditional sell target, stop level, conditional £50 net profit/loss and reasons for WAIT/SKIP**. No exchange account connection, automatic order execution, leverage, or guaranteed profits.

## Deploy on your existing Streamlit website (iPhone)

You have already created `declanreilly0/kraken-signal-ai` and deployed its `app.py` to Streamlit. **Keep that repository and Streamlit website.**

1. Download the Version 3 ZIP and tap it in iPhone **Files → Downloads** to unpack.
2. Open `https://github.com/declanreilly0/kraken-signal-ai` in **Safari** (not GitHub's mobile app). If the Add file button is hidden, use Safari's **Request Desktop Website** option.
3. **Add file → Upload files**, and select the files **inside** the extracted V3 folder: `app.py`, `radar.py`, `discovery.py`, `engine.py`, `kraken_api.py`, `chart_ui.py`, `requirements.txt`, `README.md` (and optionally `UPGRADE_IPHONE.txt`). Upload to the **root** of the repo, not inside a V3 subfolder. Existing same-named files must be **replaced**, not retained as duplicates.
4. Select **Commit directly to the `main` branch → Commit changes**.
5. Streamlit Community Cloud normally redeploys after the GitHub commit. Open your **existing Streamlit app URL**, reload Safari, and look for **KRAKEN · SIGNAL RADAR / V3**. If an error occurs, open **Manage app → Logs** and check the specific error.
6. Your previous `.streamlit/config.toml` can remain. Old V1/V2 files such as `kraken_market.py` can remain unused; they do not power V3.

**No new GitHub repository or new Streamlit deployment is required.** Never put Kraken account keys or OpenAI API keys in public GitHub files.

## How to use

1. Open **Best setups** (the home page). It immediately deep-checks the first **8** candidates. Tap **Scan next batch** to check more. Enable auto-scan in the sidebar to scan the next batch on an approximately 90-second refresh while the site is open. It is not always-on monitoring when closed.
2. Default is **Meme-first (all coins)**: all Kraken online spot markets are in the broad initial screen, but known meme tickers are prioritised for deeper analysis. To catch untagged new coins, the remaining market universe is also included. **Meme hints** is a narrower curated (non-exhaustive) token list.
3. Results have four states:
   - **POTENTIAL BUY**: all quantitative eligibility and risk gates passed **when the pair was last checked**. Entry is a price **trigger**, not a market order or promised fill.
   - **WATCH**: technical conditions partly align, but a key entry, cost or risk test is missing; do **not** treat it as BUY.
   - **SKIP**: poor setup, too expensive, illiquid or unconfirmed.
   - **LIMITED HISTORY**: too few finished candles for the model, often a risk with very new markets; this does **not** prove the listing is new.
4. The trade card shows **entry trigger / target / stop / profit if target hit / loss if stopped / net reward:risk**. A modelled positive target payoff is **not an expected profit**. You may never reach the target, the stop may slip, or you may miss the entry entirely.
5. Tap **Open [coin] chart** to inspect the selected coin, or use **All markets** to search for tokens by name or ticker. Use the **Chart & depth** screen to switch 1m/5m/15m/30m/1h/4h/1d/1w/15d, zoom/pan candles and optionally inspect order-book depth for a hypothetical £50 order.
6. If you see **NO ACTIONABLE SETUP**, that is the intended result when no scanned pair clears the criteria. Keep the fee assumptions realistic; do not set them to zero to manufacture trading opportunities.
7. **Restart scan** clears the analysed candidates and pulls the latest data. Old analysis expires from the actionable list rather than continuing to look like a new signal. You can change fee and risk settings in the left sidebar. The app is read-only and only uses Kraken's public market-data endpoints.

## What “all coins” and “new” really mean

- **All online Kraken spot pairs** are covered by a single **first-pass** snapshot using public `AssetPairs` and `Ticker`. Only pairs meeting the liquidity/quote filters are queued for deep candle analysis, **one batch at a time**. A single snapshot is not a full technical backtest or BUY/SELL forecast for all 1,000+ pairs. The app counts how many pairs have actually been deeply analysed. This staged approach avoids freezing the phone and hammering Kraken's public rate limits.
- **Meme status is approximate**: there is no exhaustive official Kraken “meme” category in `AssetPairs`, so the app applies a curated tag list. Untagged meme coins can still appear in the All spot coins queue or via search.
- **Brand-new coins**: A token is only scanable after Kraken actually lists an online spot market for it. Solana DEX-only launches or tokens on other exchanges are **outside this Kraken-only app**. The app checks for newly discovered pair IDs and may label them “newly noticed”, but those are NOT guaranteed listing times. The lightweight first-seen file on Streamlit hosting may reset on a server redeploy.
- **New market with limited candles**: If Kraken provides fewer than 65 completed candles, the app refuses a confident technical setup. It's not reliable to infer token age from Kraken's limited OHLC history.
- The REST OHLC endpoint caps the most recent history at 720 candles per timeframe and includes an unfinished current candle. The current unfinished candle is ignored by the signal engine.

## Trading-cost model

Starting published Kraken Pro spot fees (check your account/pair for actual fees): **0.80% taker per side, 0.40% maker per side**, with volume-based discounts for eligible accounts. The default app assumption is **0.80% each way**, a hypothetical 0.05% slippage each way, and the ticker's actual *quoted* bid/ask spread. Higher volatility / thin order books can cause slippage much worse than this assumption. Maker orders may not fill, and real fees may differ.

The signal engine evaluates a **hypothetical £50 budget inclusive of purchase fees**:

```text
buy_multiplier  = (1 + (half_spread_pct + slippage_pct)/100) * (1 + fee_pct/100)
sell_multiplier = (1 - (half_spread_pct + slippage_pct)/100) * (1 - fee_pct/100)
modelled_net_pnl = stake * ((target_mid / entry_mid) * sell_multiplier/buy_multiplier - 1)
```

If the pair is USD/USDT/EUR quoted, estimated £ P&L is GBP-*equivalent* based on the £50 stake, **excluding any separate FX conversion/deposit costs**. GBP spot pairs are preferable for literal £50 modelling. The projected stop loss may be exceeded by real slippage or gaps; **there is no guaranteed maximum loss**. Even the best-looking BUY tag can lose money.

## Technology and privacy

- Python, Streamlit, `requests`, `pandas`, `numpy`, TradingView Lightweight Charts via public CDN (plus fallback). Chart data and position analysis use Kraken's public REST endpoints; no Kraken login is used.
- Optional **OpenAI API** commentary critiques the strongest currently scanned candidate. It is separate from ChatGPT Plus, may require paid API credits, and **does not control or override the fixed signal gates**.
- Don't paste exchange passwords, seed phrases or Kraken trading API secrets into the app. The OpenAI key is entered only into a password-type field for the optional feature; don't share screenshots of that value or publish it in GitHub. On a public hosted app, do not store a shared API key in public source files.
- Automatically refreshes its *display* every ~90 seconds when open, so aged results can expire. Automatic progression through the scan queue requires the optional toggle. No background scanning or iOS push notifications when closed.
- Public Kraken API limits, internet failures and Streamlit Community Cloud sleep/restarts can interrupt analysis. This is **not** tick-by-tick market making or a professional execution engine.

## Testing

20 automated tests for market parsing, ticker/rate conversion, quote filtering, fee model, limited history, stale-market suppression, order-book depth and viable/unviable cases. All four pages also passed a mocked UI launch. **The production Streamlit site itself was not inspected or live-tested from the build environment.**

To run locally (Python 3.11+):

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

To run tests:

```bash
python -m pip install pytest
python -m pytest -q
```

## Sources

- [Kraken Pro fee tiers](https://www.kraken.com/gb/pro/fees)
- [Kraken public market data examples](https://support.kraken.com/articles/360000919986-public-endpoint-examples-you-can-try-them-directly-in-a-web-browser-)
- [Kraken public API rate limits](https://support.kraken.com/gb/articles/206548367-what-are-the-api-rate-limits-)
- [Kraken listing roadmap](https://www.kraken.com/listings) — roadmap entries are **not automatically live tradable markets**.

**Important:** This software is educational market research, not personalised financial advice, a prediction, an automated trading system, or an established profitable strategy. No win rate or profit guarantee is claimed. Consider forward paper testing, longer historical datasets and independent validation before risking any money; crypto can lose its full value.
