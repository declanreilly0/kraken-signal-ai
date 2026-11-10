"""Kraken Signal Lab — read-only crypto spot signal research for paper trading."""
from __future__ import annotations

import json
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kraken_market import PAIRS, fetch_ohlc, fetch_ticker
from engine import Costs, add_indicators, evaluate, historical_replay


st.set_page_config(page_title="Signal Lab | Kraken Spot", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container{padding-top:1.2rem;max-width:1260px}
h1,h2,h3{letter-spacing:-.035em}
div[data-testid="stMetric"]{background:#12202c;border:1px solid #263947;border-radius:12px;padding:15px 18px}
div[data-testid="stMetricLabel"]{color:#9cb9bc}
.topbrand{font-size:0.77rem;font-weight:800;letter-spacing:.23em;color:#28ddaa;margin-bottom:.3rem}
.summary{border:1px solid #244152;border-radius:15px;background:#11212d;padding:18px 20px;margin:12px 0}
.tag{letter-spacing:.07em;color:#a4b8c6;font-size:.75rem}
.dim{color:#9bb2bd;font-size:.89rem}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=23, show_spinner=False)
def get_market(pair: str, timeframe: int):
    return fetch_ohlc(pair, timeframe)


@st.cache_data(ttl=18, show_spinner=False)
def get_quote(pair: str):
    return fetch_ticker(pair)


def demo_candles(interval: int) -> pd.DataFrame:
    """Fabricated examples for exploring UI offline. Never described as market data."""
    rng = np.random.default_rng(721)
    n = 450
    end = pd.Timestamp.now(tz="UTC").floor(f"{interval}min") - pd.Timedelta(minutes=interval)
    index = pd.date_range(end=end, periods=n, freq=f"{interval}min", tz="UTC")
    log_returns = rng.normal(0.00003, 0.0018 * np.sqrt(interval), n)
    close = 2030 * np.exp(log_returns.cumsum())
    open_ = np.r_[close[0], close[:-1]]
    intrarange = rng.uniform(.00015, .0012 * np.sqrt(interval), n)
    high = np.maximum(open_, close) * (1 + intrarange)
    low = np.minimum(open_, close) * (1 - intrarange)
    volume = rng.lognormal(3.5, 0.7, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)


def quote_price(price: float, currency: str) -> str:
    sign = "£" if currency == "GBP" else "$"
    return f"{sign}{price:,.2f}" if price >= 1 else f"{sign}{price:,.5f}"


def show_chart(df: pd.DataFrame, result: dict, currency: str):
    frame = df.tail(130)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=frame.index, open=frame.open, high=frame.high, low=frame.low, close=frame.close,
                                 name="Spot", increasing_line_color="#28E0AE", decreasing_line_color="#F65B82"))
    for n, colour in [(9, "#F6C66F"), (21, "#72ADFF"), (50, "#9A82D7")]:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[f"ema{n}"], name=f"EMA {n}",
                                 line=dict(color=colour, width=1.4), opacity=.9))
    fig.add_hline(y=result["target"], line_dash="dot", line_color="#2BD6A8", opacity=.7,
                  annotation_text="Illustrative target", annotation_font_color="#2BD6A8")
    fig.add_hline(y=result["stop"], line_dash="dot", line_color="#F65B82", opacity=.7,
                  annotation_text="Illustrative stop", annotation_font_color="#F65B82")
    fig.update_layout(height=480, margin=dict(t=15,l=2,r=2,b=10), template="plotly_dark",
                      paper_bgcolor="#080E18", plot_bgcolor="#080E18",
                      legend=dict(orientation="h", y=1.08, x=0),
                      xaxis_rangeslider_visible=False, hovermode="x unified",
                      yaxis=dict(side="right", tickprefix="£" if currency == "GBP" else "$", gridcolor="#23323E"),
                      xaxis=dict(gridcolor="#23323E"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})


st.markdown('<div class="topbrand">SIGNAL // LAB &nbsp; • &nbsp; KRAKEN SPOT</div>', unsafe_allow_html=True)
st.title("Crypto signal scanner")
st.caption("Research and paper-trading tool • live public Kraken data • no exchange login • no auto-orders • no leverage")

with st.sidebar:
    st.header("Market controls")
    pair_label = st.selectbox("Trading pair", list(PAIRS), index=1)
    interval = st.selectbox("Candle timeframe", [1,5,15], format_func=lambda x: f"{x} minute{'s' if x>1 else ''}")
    capital = st.number_input("Paper trade budget (£)", min_value=5.0, max_value=10000.0, value=50.0, step=5.0)
    order_mode = st.radio("Assumed fees", ["Taker / market order", "Maker / limit order"], index=0)
    base_fee = 0.8 if order_mode.startswith("Taker") else 0.4
    fee = st.number_input("Fee each side (%)", min_value=0.0, max_value=3.0, value=base_fee, step=0.05, format="%.2f")
    slip = st.number_input("Extra slippage each side (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.01, format="%.2f")
    hold = st.slider("Maximum holding period (candles)", 5, 120, 30, step=5)
    demo = st.toggle("Demo mode (fake prices)", value=False, help="Explore the interface with generated data, never real prices")
    live_refresh = st.toggle("Auto-refresh (30 seconds)", value=True)
    if st.button("↻ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("**Safety**")
    st.caption("This app ONLY reads public spot market data. It cannot view your Kraken balance or submit trades. No futures, margin or shorting.")
    st.markdown("[Kraken Pro official fee schedule](https://www.kraken.com/gb/pro/fees)")

if live_refresh and not demo:
    st_autorefresh(interval=30_000, limit=None, key="kraken_chart_refresh")

pair = PAIRS[pair_label]
currency = pair_label.rsplit("/", 1)[-1].strip()
if demo:
    st.warning("DEMO MODE — all candles and prices below are fabricated examples, NOT Kraken market data.", icon="🧪")
    raw = demo_candles(interval)
    ticker = {"bid":float(raw.close.iloc[-1])*.9999, "ask":float(raw.close.iloc[-1])*1.0001,
              "last":float(raw.close.iloc[-1]), "spread_pct":.02}
    spread_known = True
else:
    try:
        with st.spinner("Retrieving completed Kraken candles…"):
            raw = get_market(pair, interval)
    except Exception as ex:
        st.error(f"Couldn't retrieve Kraken spot candles: {ex}. Check the symbol or internet connection. No signal is available.")
        st.stop()
    try:
        ticker = get_quote(pair)
        spread_known = True
    except Exception as ex:
        st.warning(f"Live spread could not be checked ({ex}). New BUY signals are disabled; a conservative 0.10% spread estimate is shown.")
        ticker = {"bid":np.nan,"ask":np.nan,"last":float(raw.close.iloc[-1]), "spread_pct":.1}
        spread_known = False

computed = add_indicators(raw)
costs = Costs(fee_pct_each_side=fee, slippage_pct_each_side=slip, spread_pct_round_trip=ticker["spread_pct"])
result = evaluate(computed, costs, capital, interval, spread_known=spread_known)
last_close_time = computed.index[-1] + pd.Timedelta(minutes=interval)
minutes_old = max(0.0, (pd.Timestamp.now(tz="UTC") - last_close_time).total_seconds()/60)
if not demo and minutes_old > max(3, interval * 2):
    st.error(f"Market candles appear stale (last closed {minutes_old:.1f} minutes ago). BUY signal is blocked.")
    if result["signal"] == "BUY SETUP":
        result["signal"] = "WAIT"
    result["reasons"].append("Stale market data; no reliable entry signal.")

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Last completed close",quote_price(result["price"],currency))
with c2: st.metric("Signal",result["signal"])
with c3: st.metric("Technical checks",f"{result['score']} / 5")
with c4: st.metric("Price rise to break even",f"{result['break_even_pct']:.2f}%")
st.caption(f"Last completed candle opened {result['bar_time'].strftime('%Y-%m-%d %H:%M UTC')} • live bid/ask spread ~{ticker['spread_pct']:.3f}% • {len(computed)} completed historical candles • {'demo' if demo else 'Kraken public market feed'}")

if result["signal"] == "BUY SETUP":
    st.success("POTENTIAL LONG SETUP — technically aligned and illustrative economics pass the filters. This is not a guaranteed profitable trade.")
elif result["signal"] == "EXIT / AVOID":
    st.error("BEARISH / EXIT WATCH — only relevant to closing a position you already own; not an instruction to short.")
elif result["signal"] == "WATCH":
    st.info("WATCH — there may be momentum, but the full cost-adjusted entry requirements aren't met.")
else:
    st.warning("WAIT — no qualifying spot long entry at this completed candle.")

tab_chart, tab_checks, tab_replay, tab_ai = st.tabs(["📈 Live chart", "🔎 Signal details", "🧪 Historical replay", "✨ AI analyst"])
with tab_chart:
    show_chart(computed, result, currency)
    st.caption("Each candle is complete. Targets/stops are illustrative levels, not placed exchange orders. Signals can change each candle.")
    a,b,c,d = st.columns(4)
    a.metric("Reference entry", quote_price(result["price"], currency))
    b.metric("Illustrative target", quote_price(result["target"], currency), f"+{result['move_to_target_pct']:.2f}%")
    c.metric("Illustrative stop", quote_price(result["stop"], currency))
    d.metric("Net reward / risk", f"{result['net_rr']:.2f} : 1" if result["net_rr"] > 0 else "Not viable")
    st.markdown("#### Estimated outcomes for a £%.2f trade" % capital)
    left,right = st.columns(2)
    left.metric("If target is reached (after estimated costs)",f"£{result['expected_gain']:+.2f}")
    right.metric("If stop is reached (after estimated costs)",f"£{result['expected_loss']:+.2f}")
    st.caption("All estimates assume a filled trade at the modelled price, with fees and assumed slippage. These are NOT expected values/probabilities. £ P&L is a percentage-equivalent calculation even on USD pairs; FX and conversion costs are not modelled.")

with tab_checks:
    st.subheader("Five technical confirmations")
    for label, passed in result["checks"].items():
        st.markdown(("✅ " if passed else "⬜ ") + label)
    st.progress(result["score"]/5)
    st.caption("This is a checklist score, NOT a confidence percentage or prediction accuracy.")
    for why in result["reasons"]:
        st.write("• "+why)
    last = computed.iloc[-1]
    st.markdown("#### Indicator readings")
    i1,i2,i3,i4 = st.columns(4)
    i1.metric("RSI 14",f"{last.rsi:.1f}")
    i2.metric("EMA 9",quote_price(last.ema9,currency))
    i3.metric("EMA 21",quote_price(last.ema21,currency))
    i4.metric("Volume vs 20-bar average",f"{last.volume_ratio:.2f}×")
    st.markdown("#### Trading economics")
    st.write(f"At **{fee:.2f}% per-side trading fees**, **{slip:.2f}% assumed slippage each side**, and **{ticker['spread_pct']:.3f}% spread**, the estimated break-even price rise is **{costs.break_even_pct:.2f}%**.")
    st.info("Maker / limit pricing is only a scenario: there is no guarantee a resting order fills, or that both sides qualify for maker fees. A stop-loss can also execute with worse-than-assumed slippage.")

with tab_replay:
    st.subheader("Historical signal replay")
    st.caption("Simulated, not actual trades. Next-candle open entries; stops assumed to hit before targets if both touched. No look-ahead in the indicator rules. API history provides at most 720 recent candles; this is nowhere near enough to prove a strategy works.")
    with st.spinner("Replaying completed candles…"):
        trades = historical_replay(computed, costs, capital, max_hold_bars=hold)
    if trades.empty:
        st.info("No qualifying historical trades in this short window with these fee and risk settings. That is useful information: forcing a trade would ignore the filters.")
    else:
        wins = int((trades.pnl > 0).sum())
        x1,x2,x3,x4 = st.columns(4)
        x1.metric("Simulated trades",len(trades))
        x2.metric("Winning trades",f"{wins}/{len(trades)}")
        x3.metric("Win rate",f"{wins/len(trades)*100:.1f}%")
        x4.metric("Total £ P&L",f"£{trades.pnl.sum():+.2f}")
        equity = capital + trades.pnl.cumsum()
        fig = go.Figure(go.Scatter(x=trades.exit_utc,y=equity,mode="lines+markers",line_color="#28E0AE",name="Illustrative equity"))
        fig.update_layout(template="plotly_dark",paper_bgcolor="#080E18",plot_bgcolor="#080E18",height=250,
                          margin=dict(t=10,l=0,r=10,b=10), yaxis_title="£ (not compounded)")
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(trades.sort_values("entry_utc",ascending=False),use_container_width=True,hide_index=True)
        st.download_button("Download simulated trades CSV",data=trades.to_csv(index=False).encode(),file_name="kraken_paper_replay.csv",mime="text/csv")
    st.warning("A positive historical replay is not proof of future profits. It ignores order-fill uncertainty, some real-world liquidity effects, tax, FX conversion, outages and market regime changes. Do not use this result to justify increasing stakes.")

with tab_ai:
    st.subheader("Ask AI to critique the setup")
    st.write("An OpenAI model can interpret the current signal, question weak assumptions and suggest what to check next. The fixed cost/risk rules remain in control; it cannot place trades.")
    st.caption("Optional: requires your own OpenAI API key. ChatGPT subscriptions do not include API credits. Never enter a Kraken password or trading API secret here.")
    api_key = st.text_input("OpenAI API key (only for AI commentary)",type="password",placeholder="sk-…")
    model = st.selectbox("AI model",["gpt-5-mini","gpt-4.1-mini"],index=0)
    if st.button("Analyse this chart with AI",type="primary",disabled=not bool(api_key.strip())):
        from openai import OpenAI
        recent = computed.tail(25)
        prices = [{"t":v.strftime('%H:%M'),"close":round(float(row.close),5),"high":round(float(row.high),5),
                   "low":round(float(row.low),5),"volume":round(float(row.volume),4)} for v,row in recent.iterrows()]
        packet = {
            "market":pair_label,"timeframe_minutes":interval,"snapshot_utc":result["bar_time"].isoformat(),
            "market_mode":"SYNTHETIC DEMO" if demo else "KRAKEN REAL COMPLETED CANDLES",
            "signal":result["signal"],"technical_score_not_probability":result["score"],
            "conditions":result["checks"],"RSI":round(float(computed.iloc[-1].rsi),2),
            "entry_reference":result["price"],"illustrative_stop":result["stop"],"illustrative_target":result["target"],
            "estimated_net_target_gbp":round(result["expected_gain"],3),
            "estimated_net_stop_gbp":round(result["expected_loss"],3),
            "break_even_move_pct":round(result["break_even_pct"],3),
            "fees_each_side_pct":fee,"spread_pct":round(ticker["spread_pct"],4),
            "last_25_completed_candles":prices,
        }
        try:
            with st.spinner("AI is critically reviewing this snapshot…"):
                resp = OpenAI(api_key=api_key.strip(),timeout=25.0).responses.create(
                    model=model,
                    instructions=("You are a cautious crypto trading research assistant for a UK retail user exploring spot-only paper trades. "
                                  "Only use data in the supplied snapshot. Never imply live monitoring beyond it, assert assured profit, "
                                  "invent win rates, or advise leverage, futures, or automated execution. Treat technical score as not a probability. "
                                  "State: (1) strongest bullish/bearish evidence, (2) reasons NOT to trade, "
                                  "(3) whether modelled costs overwhelm the move, and (4) a short conditional plan for PAPER observation only. "
                                  "Be concise, sceptical, transparent that data are delayed closed candles; mention if demo."),
                    input=json.dumps(packet),max_output_tokens=600,
                )
            st.markdown(resp.output_text)
        except Exception as ex:
            st.error(f"The AI request failed. Check the model's availability, API key, and billing: {ex}")
    else:
        st.caption("Without an API key, the live scanner, rules, chart and historical replay all still work.")

st.divider()
st.caption("Not investment advice or automated execution. Cryptocurrency is high-risk; losses can include all capital. Signal Lab uses spot public price feeds only; it does not track your Kraken account, watch markets when closed, or send push notifications.")
