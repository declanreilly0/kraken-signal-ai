"""Kraken Signal Lab V2: all-public-spot-market browser and paper-trading research.

Run: python -m streamlit run app.py
Read-only: NO exchange authentication, wallet access, leverage, or trade placement.
"""
from __future__ import annotations
from datetime import datetime, time as clock_time, timedelta, timezone
from html import escape
import math
import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from chart_ui import chart_html
from engine import Costs, add_indicators, evaluate, historical_replay
from kraken_api import (
    TIMEFRAMES, Market, fetch_markets, fetch_all_tickers, fetch_quote,
    fetch_ohlc, label_price, search_markets,
)

st.set_page_config(page_title="Kraken Signal Lab · V2", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
html,body,[data-testid="stApp"]{background:#0a1019}
.block-container{padding-top:1.1rem;padding-bottom:2.3rem;max-width:1250px}
h1,h2,h3{letter-spacing:-.028em}h1{font-size:1.55rem!important}h2{font-size:1.3rem!important}
[data-testid="stVerticalBlock"]{gap:.70rem}
[data-testid="stWidgetLabel"] p{font-size:.82rem;color:#a8b7c9}
[data-testid="stMetric"]{background:#141f2d;border:1px solid #26364b;border-radius:12px;padding:11px 13px;min-height:85px}
[data-testid="stMetricLabel"] p{font-size:.80rem;color:#98a9bc}
[data-testid="stMetricValue"]{font-size:clamp(1.02rem,2.2vw,1.5rem)}
[data-testid="stMetricDelta"]{font-size:.79rem}
[data-testid="stButton"] button{border-radius:10px}
[data-testid="stDataFrame"]{border-radius:10px;overflow:hidden}
/* Horizontal view selector may scroll on narrow screens instead of pushing off screen. */
[data-testid="stHorizontalBlock"]{gap:.55rem}
.smallnote{color:#8d9db3;font-size:.78rem;line-height:1.45}
.topline{font-size:.7rem;color:#b8a4f8;font-weight:800;letter-spacing:2px;margin:0 0 3px}
.subline{font-size:.84rem;color:#899bb1;margin-bottom:12px}
.tipbox{border:1px solid #293952;background:#111c2c;border-radius:12px;padding:12px 14px;color:#a9bed5;font-size:.85rem}
.quotebar{display:flex;gap:8px;overflow-x:auto;white-space:nowrap;margin:3px 0 9px;padding:1px 0;scrollbar-width:none}.quotebar::-webkit-scrollbar{display:none}.quotebar>span{border:1px solid #2b374b;background:#141f2d;border-radius:10px;padding:9px 13px;display:inline-flex;flex-direction:column;gap:2px;min-width:max-content}.quotebar strong{color:#e9edf8;font-size:1.11rem}.quotebar small{color:#93a8c2;font-size:.70rem}.pill{display:inline-block;padding:3px 10px;border-radius:8px;font-size:.75rem;font-weight:700;margin:0 7px 4px 0}
.pillup{background:#12392f;color:#55d8a8}.pilldown{background:#411e2b;color:#ff8098}.pillwait{background:#3b321f;color:#f7d183}
@media(max-width:740px){.block-container{padding:1.0rem .72rem 1.7rem!important}h1{font-size:1.4rem!important}
[data-testid="stMetric"]{padding:9px 10px;min-height:70px}
[data-testid="stMetricValue"]{font-size:1.1rem}
[data-testid="stHorizontalBlock"]{gap:.3rem}}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=15 * 60, show_spinner=False)
def catalog() -> list[Market]:
    return fetch_markets()

@st.cache_data(ttl=30, show_spinner=False)
def quote_for(pair: str) -> dict:
    return fetch_quote(pair)

@st.cache_data(ttl=45, show_spinner=False)
def candles_for(pair: str, interval: int) -> pd.DataFrame:
    return fetch_ohlc(pair, interval)

@st.cache_data(ttl=90, show_spinner=False)
def tickers_all() -> dict:
    return fetch_all_tickers()


def money(value: float, quote: str) -> str:
    return label_price(value, quote)


def safe_percent(x: float) -> str:
    return f"{x:+.2f}%" if math.isfinite(x) else "—"


def max_age_minutes(df: pd.DataFrame, interval: int) -> float:
    last_close = df.index[-1] + pd.Timedelta(minutes=interval)
    return max(0., (pd.Timestamp.now(tz="UTC") - last_close).total_seconds() / 60)


def plotly_fallback(df: pd.DataFrame, quote: str, show_emas: bool, show_vol: bool, mode: str, interval: int):
    nrows = 2 if show_vol else 1
    fig = make_subplots(rows=nrows, cols=1, shared_xaxes=True, vertical_spacing=.03,
                        row_heights=[.78, .22] if show_vol else [1.0])
    if mode == "Candles":
        fig.add_trace(go.Candlestick(x=df.index, open=df.open, high=df.high, low=df.low, close=df.close,
                        name="Spot", increasing_line_color="#29cc9b", decreasing_line_color="#f36d87"),row=1,col=1)
    else:
        fig.add_trace(go.Scatter(x=df.index,y=df.close,name="Close",mode="lines",line=dict(color="#bba4ff",width=2)),row=1,col=1)
    if show_emas:
        for n,color in ((9,"#e7b86c"),(21,"#70aafb"),(50,"#b59cf9")):
            fig.add_trace(go.Scatter(x=df.index,y=df[f"ema{n}"],name=f"EMA {n}",mode="lines",
                                     line=dict(width=1.1,color=color)),row=1,col=1)
    if show_vol:
        colors = ["#27bb90" if c>=o else "#e15e7a" for o,c in zip(df.open,df.close)]
        fig.add_trace(go.Bar(x=df.index, y=df.volume, name="Volume", marker_color=colors, showlegend=False),row=2,col=1)
    fig.update_layout(template="plotly_dark",height=515,margin=dict(l=2,r=3,t=15,b=18),
                      paper_bgcolor="#0b111b",plot_bgcolor="#0b111b",
                      dragmode="pan", hovermode="x unified", legend=dict(orientation="h",y=1.10,x=0),
                      uirevision="kraken-chart-" + quote + str(interval))
    fig.update_xaxes(rangeslider=dict(visible=False), gridcolor="#263043", showgrid=True)
    fig.update_yaxes(side="right",gridcolor="#25354a", tickprefix={"GBP":"£","USD":"$","EUR":"€"}.get(quote,""),row=1,col=1)
    if show_vol:
        fig.update_yaxes(gridcolor="#25354a",showticklabels=False,row=2,col=1)
    st.plotly_chart(fig,config={"displaylogo":False,"scrollZoom":True,"displayModeBar":True,"responsive":True},use_container_width=True)
    st.caption("Plotly backup: pinch/drag to zoom or pan, double-tap to reset; switch chart engine back to Touch chart when ready.")


def explore_markets(all_markets: list[Market]):
    st.markdown("### Every listed Kraken spot market")
    st.caption("Pairs are discovered from Kraken's current public market catalogue. Meme labels are a curated hint, not an exhaustive or official Kraken category. Exchange account eligibility may differ by location.")
    with st.spinner("Loading a single market-wide quote snapshot…"):
        try:
            tickers = tickers_all()
            ticker_error = None
        except Exception as exc:
            tickers = {}
            ticker_error = str(exc)
    if ticker_error:
        st.warning("Bulk ticker data is temporarily unavailable; the complete tradable-pair catalogue is still searchable. " + ticker_error)
    k1,k2,k3 = st.columns(3)
    k1.metric("Online spot pairs", f"{len(all_markets):,}")
    k2.metric("Distinct coins", f"{len({m.base for m in all_markets}):,}")
    k3.metric("Meme-tagged pairs",f"{sum(m.is_meme_hint for m in all_markets):,}")
    s1,s2=st.columns([2.6,1.0])
    with s1: query=st.text_input("Find any coin or pair",placeholder="DOGE, PEPE, BONK, SHIB, BTC, SOL…",key="screener_query")
    with s2: kind=st.selectbox("Filter",["All markets","Meme watchlist","My favourites"],key="screener_kind")
    quotes=sorted({m.quote for m in all_markets})
    c1,c2=st.columns(2)
    with c1: quote=st.selectbox("Quoted in",["All"] + quotes,index=0,key="screener_quote")
    with c2: sort=st.selectbox("Sort by",["24h quote volume","Daily change %","Spread %","A–Z"],index=0,key="screener_sort")
    matches=search_markets(all_markets, query, quote=quote, meme_only=(kind=="Meme watchlist"))
    if kind=="My favourites":
        favourites=set(st.session_state.get("favourites",[]))
        matches=[m for m in matches if m.pair_id in favourites]
    table=[]
    pair_names={m.pair_id:m.name for m in all_markets}
    for m in matches:
        t=tickers.get(m.pair_id,{})
        table.append({"Pair":m.name,"ID":m.pair_id,"Type":"Meme*" if m.is_meme_hint else "Spot",
                      "Last":t.get("last",float("nan")),
                      "Daily change %":t.get("change_open_pct",float("nan")),
                      "24h quote volume":t.get("quote_volume_24h",float("nan")),
                      "Spread %":t.get("spread_pct",float("nan"))})
    frame=pd.DataFrame(table,columns=["Pair","ID","Type","Last","Daily change %","24h quote volume","Spread %"])
    if sort=="A–Z": frame=frame.sort_values("Pair",ascending=True)
    elif not frame.empty and sort in frame: frame=frame.sort_values(sort,ascending=(sort=="Spread %"),na_position="last")
    st.caption(f"{len(frame):,} matching pairs • Last quote snapshot cached for up to 90 seconds • 'Daily change' compares the last price with Kraken's daily open, NOT an exact rolling 24h return • Volume in each pair's quote currency")
    st.dataframe(frame.drop(columns=["ID"]).head(500),hide_index=True,use_container_width=True,height=430,
                 column_config={"Last":st.column_config.NumberColumn(format="%.8g"),
                                "Daily change %":st.column_config.NumberColumn(format="%+.2f%%"),
                                "24h quote volume":st.column_config.NumberColumn(format="%.0f"),
                                "Spread %":st.column_config.NumberColumn(format="%.3f%%")})
    if len(frame)>500: st.caption("Displaying the first 500 matches; narrow the search to find other pairs. All catalogue pairs remain searchable.")
    if frame.empty:
        st.info("No matching markets. Remove filters or try another spelling; a coin may not have an active Kraken spot pair.")
    else:
        chosen = st.selectbox("Open any matching pair on chart",frame["ID"].tolist(),
                              format_func=lambda x:pair_names.get(x,x),key="screener_open_pair")
        if st.button("Open chart →",use_container_width=True,type="primary"):
            st.session_state.pending_open=chosen
            st.rerun()
    st.caption("*Meme tag is approximate. All untagged meme coins are still found through normal search. No meme-coin classification or exchange listing is guaranteed to remain current.")


def select_market(all_markets: list[Market]) -> Market:
    by_id={m.pair_id:m for m in all_markets}
    defaults=[m for symbol,quote in (("ETH","GBP"),("XBT","GBP"),("BTC","GBP"),("SOL","GBP"),("XDG","GBP"),("DOGE","USD"),("PEPE","USD"),("SHIB","USD"),("BONK","USD"))
              for m in all_markets if m.base==symbol and m.quote==quote]
    fallback=defaults[0] if defaults else all_markets[0]
    if st.session_state.get("selected_id") not in by_id:
        st.session_state.selected_id=fallback.pair_id
    search = st.text_input("Search any Kraken coin or pair",placeholder="Type PEPE, WIF, BTC, BONK…",key="pair_search")
    if search.strip():
        matches=search_markets(all_markets,search)[:250]
        if not matches:
            st.warning("No currently online Kraken spot pairs match that search. Try a different ticker.")
            matches=[by_id[st.session_state.selected_id]]
    else:
        # Keep the main selector fast on iPhone; use the Markets screen to browse thousands.
        matches=[]
        seen=set()
        for m in [by_id[st.session_state.selected_id]]+defaults+all_markets[:75]:
            if m.pair_id not in seen:
                matches.append(m);seen.add(m.pair_id)
    ids=[m.pair_id for m in matches]
    idx=ids.index(st.session_state.selected_id) if st.session_state.selected_id in ids else 0
    chosen=st.selectbox("Trading pair",ids,index=idx,format_func=lambda x:by_id[x].name,key="selected_market_widget")
    st.session_state.selected_id=chosen
    return by_id[chosen]


def add_date_filter(df: pd.DataFrame) -> pd.DataFrame:
    earliest, latest=df.index[0],df.index[-1]
    dates=st.toggle("Custom UTC date & time range",value=False,help="Filters the data Kraken already provides; does not download older candles.")
    if not dates:
        return df
    d1,d2=st.columns(2)
    with d1:
        start_date=st.date_input("Start date (UTC)",value=earliest.date(),key="date_from")
        start_time=st.time_input("Start time (UTC)",value=earliest.time().replace(second=0,microsecond=0),key="time_from")
    with d2:
        end_date=st.date_input("End date (UTC)",value=latest.date(),key="date_to")
        end_time=st.time_input("End time (UTC)",value=latest.time().replace(second=0,microsecond=0),key="time_to")
    start=pd.Timestamp(datetime.combine(start_date,start_time,tzinfo=timezone.utc))
    end=pd.Timestamp(datetime.combine(end_date,end_time,tzinfo=timezone.utc))
    if start>end:
        st.warning("Start must be earlier than end. Displaying all available candles.")
        return df
    cropped=df.loc[(df.index>=start)&(df.index<=end)]
    if len(cropped)<2:
        st.warning(f"No usable candles in that date range. Kraken supplied {earliest:%d %b %Y %H:%M} to {latest:%d %b %Y %H:%M} UTC for this timeframe. Showing all available candles.")
        return df
    st.caption(f"Displaying {len(cropped):,} candles from the selected UTC date range")
    return cropped


def quote_info(pair: Market) -> tuple[dict|None,str|None]:
    try:
        return quote_for(pair.pair_id),None
    except Exception as exc:
        return None,str(exc)


def analyse_signal(df: pd.DataFrame, pair: Market, q: dict|None, fee: float, slippage: float, stake: float, interval: int):
    from math import isfinite
    if len(df)<65:
        return None,None,f"Only {len(df)} completed candles available for this market; at least 65 are required for the research signal. Charting remains available."
    spread=q["spread_pct"] if q and isfinite(q["spread_pct"]) else 0.1
    costs=Costs(fee_pct_each_side=fee,slippage_pct_each_side=slippage,spread_pct_round_trip=spread)
    result=evaluate(df,costs,stake,interval,spread_known=q is not None)
    if max_age_minutes(df,interval)>max(interval*2,5):
        result["reasons"].append("Market candles are stale; new entries blocked.")
        if result["signal"]=="BUY SETUP": result["signal"]="WAIT"
    if q and (q["spread_pct"]>0.5 or q.get("trades_24h",0)<100):
        result["reasons"].append("Thin liquidity / wide spread filter: no new BUY setup on this market.")
        if result["signal"]=="BUY SETUP": result["signal"]="WAIT"
    return result,costs,None


def layout_signal(result: dict|None, costs: Costs|None, pair: Market, fee: float, stake: float, err: str|None):
    if err:
        st.info(err)
        return
    if result is None:
        return
    status=result["signal"]
    cls="pillup" if status=="BUY SETUP" else "pilldown" if status=="EXIT / AVOID" else "pillwait"
    st.markdown(f'<span class="pill {cls}">{escape(status)}</span> <span class="smallnote">{result["score"]}/5 technical checks · research signal, not a prediction</span>',unsafe_allow_html=True)
    a,b,c=st.columns(3)
    a.metric("Illustrative entry",money(result["price"],pair.quote))
    b.metric("Break-even rise",f'{result["break_even_pct"]:.2f}%')
    c.metric("Cost-adjusted R/R",f'{result["net_rr"]:.2f}:1' if result['net_rr']>0 else "Not viable")
    s1,s2=st.columns(2)
    s1.metric("Illustrative target",money(result["target"],pair.quote),delta=f'{result["move_to_target_pct"]:+.2f}%')
    s2.metric("Illustrative stop",money(result["stop"],pair.quote))
    p1,p2=st.columns(2)
    p1.metric(f"£{stake:.0f} stake · if target hit", f'£{result["expected_gain"]:+.2f}')
    p2.metric(f"£{stake:.0f} stake · if stopped", f'£{result["expected_loss"]:+.2f}')
    st.caption("Illustrative outcome, not expected profit. Fees, current spread and assumed slippage are modelled; live fills can differ. GBP P&L on non-GBP pairs is percentage-equivalent only, not an FX-adjusted cash forecast.")
    with st.expander("See all five signal checks and reasons",expanded=False):
        for label,passed in result["checks"].items():
            st.write(("✅" if passed else "○")+" "+label)
        st.progress(result["score"]/5)
        for message in result["reasons"]: st.write("• "+message)
        st.caption("A 4/5 checklist score is NOT a 80% chance of success. No AI model can establish next-minute prices reliably.")


st.markdown('<div class="topline">KRAKEN SIGNAL LAB / VERSION 2</div>',unsafe_allow_html=True)
st.title("Market explorer + signal research")
st.markdown('<div class="subline">All Kraken online public spot markets · touch charts · £50 paper-trading analysis · no account connection</div>',unsafe_allow_html=True)

with st.sidebar:
    st.subheader("⚙️ Trading assumptions")
    stake=st.number_input("Paper trade size (£)",value=50.0,min_value=5.0,max_value=1_000_000.0,step=5.0)
    order_type=st.radio("Order fee scenario",["Taker / market","Maker / resting limit"],index=0,
                        help="Maker orders may not fill and may instead be charged taker fees.")
    default_fee=.80 if order_type.startswith("Taker") else .40
    fee=st.number_input("Fee per side (%)",min_value=0.0,max_value=5.0,value=default_fee,step=.05,format="%.2f",
                        help="Check the current fee schedule for YOUR trading tier, pair, and order type.")
    slippage=st.number_input("Extra slippage each side (%)",min_value=0.0,max_value=5.0,value=.05,step=.01,format="%.2f")
    max_hold=st.slider("Maximum replay hold (candles)",5,120,30,5)
    st.divider()
    refresh=st.selectbox("Refresh while open",["Off","30 seconds","60 seconds","120 seconds"],index=0)
    if st.button("↻ Fetch fresh market data",use_container_width=True):
        candles_for.clear();quote_for.clear();tickers_all.clear()
        st.rerun()
    st.caption("Use Off to preserve chart zoom while exploring. The public REST feed cannot give guaranteed tick-level updates. Refresh never runs when this website is closed.")
    st.divider()
    st.caption("Read-only spot research. No Kraken login or private trading keys. Never use the derivatives tab for this tool.")
    st.markdown("[Kraken Pro fee schedule](https://www.kraken.com/gb/pro/fees)")

if refresh!="Off":
    st_autorefresh(interval={"30 seconds":30000,"60 seconds":60000,"120 seconds":120000}[refresh],key="refresh_public_market_data")

try:
    all_markets=catalog()
except Exception as e:
    st.error(f"Kraken's public market catalogue is unavailable: {e}. Try 'Fetch fresh market data' in the settings or reload the page.")
    st.stop()

if "selected_id" not in st.session_state:
    pick=next((m for m in all_markets if m.name=="ETH/GBP"),all_markets[0])
    st.session_state.selected_id=pick.pair_id
if "favourites" not in st.session_state:st.session_state.favourites=[]
if "view" not in st.session_state:st.session_state.view="📈 Chart"
if "pending_open" in st.session_state:
    st.session_state.selected_id=st.session_state.pop("pending_open")
    st.session_state.view="📈 Chart"
view=st.radio("Workspace",["📈 Chart","🌐 All markets","🎯 Signals","🧪 Replay","✨ AI analyst"],horizontal=True,
              key="view",label_visibility="collapsed")

if view=="🌐 All markets":
    explore_markets(all_markets)
    st.stop()

l,r=st.columns([3.8,1.2],vertical_alignment="bottom")
with l: selected=select_market(all_markets)
with r:
    is_fav=selected.pair_id in st.session_state.favourites
    if st.button("★ Saved" if is_fav else "☆ Save pair",use_container_width=True):
        fav=set(st.session_state.favourites)
        if is_fav: fav.remove(selected.pair_id)
        else: fav.add(selected.pair_id)
        st.session_state.favourites=sorted(fav)
        st.rerun()

interval_names=list(TIMEFRAMES)
small,wide=st.columns([1,1.15])
with small:
    timeframe=st.selectbox("Candle interval",interval_names,index=interval_names.index("1m"),
                            key="interval_select",help="Kraken offers 1m as its lowest public candle interval.")
with wide:
    chart_mode=st.selectbox("Chart style",["Candles","Line"],index=0,key="mode_select")
minutes=TIMEFRAMES[timeframe]

try:
    with st.spinner("Loading Kraken completed candles…"):
        raw=candles_for(selected.pair_id,minutes)
except Exception as e:
    st.error(f"Couldn't load {selected.name} {timeframe} candles: {e}")
    st.caption("Some recently listed or illiquid assets lack sufficient OHLC candles. The all-markets page is still available.")
    st.stop()
frame=add_indicators(raw)
quote,quote_err=quote_info(selected)
if quote_err:
    st.warning("Live bid/ask unavailable; trading signal entries will be blocked. Chart candles may still be visible.")
last_close=float(frame.close.iloc[-1])
change=100*(last_close/float(frame.close.iloc[-2])-1) if len(frame)>1 else float("nan")

spread_txt=f'{quote["spread_pct"]:.3f}%' if quote else 'Unavailable'
price_txt=escape(money(last_close,selected.quote))
bar_txt=escape(f"{len(frame)} bars")
st.markdown(f'''<div class="quotebar">
 <span><small>{escape(selected.name)} · last closed candle</small><strong>{price_txt} <small>{safe_percent(change)}</small></strong></span>
 <span><small>Live bid / ask spread</small><strong>{escape(spread_txt)}</strong></span>
 <span><small>Visible history available</small><strong>{bar_txt}</strong></span>
 </div>''',unsafe_allow_html=True)
st.caption(f"Kraken public spot · last complete bar: {frame.index[-1]:%d %b %H:%M} UTC · {len(all_markets):,} online markets")
if selected.is_meme_hint:
    st.markdown('<span class="pill pillwait">MEME WATCHLIST TAG • highly speculative</span>',unsafe_allow_html=True)
if max_age_minutes(raw,minutes)>max(minutes*2,5):
    st.warning("Latest completed candle looks stale, possibly due to no trades on this market. Do not assume the displayed price is executable now.")

result,costs,signal_error=analyse_signal(frame,selected,quote,fee,slippage,stake,minutes)

if view=="📈 Chart":
    with st.expander("⚙️ Chart options · date/time range · backup",expanded=False):
        engine=st.selectbox("Chart engine",["Touch chart (fast)","Plotly backup"],index=0,key="chart_engine")
        overlays=st.toggle("EMA 9/21/50",value=True,key="chart_ema")
        volume=st.toggle("Volume",value=True,key="chart_vol")
        st.caption(f"Kraken supports up to 720 recent candles per interval. Available: {raw.index[0]:%d %b %Y %H:%M} – {raw.index[-1]:%d %b %Y %H:%M} UTC. Older charts need another historical source.")
        window=add_date_filter(frame)
    if "window" not in locals(): window=frame
    if engine.startswith("Touch"):
        components.html(chart_html(window,selected.quote,timeframe,show_ema=overlays,
                                   show_volume=volume,chart_type=chart_mode),height=510,scrolling=False)
        st.caption("Touch chart: drag sideways to pan, pinch to zoom, or tap + / − / Fit. Crosshair shows each candle's OHLC and time. If a chart script is blocked, choose Plotly backup.")
    else:
        plotly_fallback(window,selected.quote,overlays,volume,chart_mode,minutes)
    if result:
        st.markdown("#### Latest research signal")
        layout_signal(result,costs,selected,fee,stake,None)
    else:
        st.info(signal_error)
    csv=raw.to_csv(index_label="time_utc").encode("utf-8")
    st.download_button("↓ Download visible market's available candles (CSV)",data=csv,
                       file_name=f"kraken_{selected.name.replace('/','_')}_{timeframe}_completed.csv",mime="text/csv")

elif view=="🎯 Signals":
    st.markdown("### Technical setup and trade costs")
    layout_signal(result,costs,selected,fee,stake,signal_error)
    if quote:
        st.caption(f"Last trade: {money(quote['last'],selected.quote)} • Bid: {money(quote['bid'],selected.quote)} • Ask: {money(quote['ask'],selected.quote)} • Trades in the last 24h: {quote['trades_24h']:,}")
    st.info("This signal engine evaluates the SELECTED pair's completed candles; it does not calculate minute-by-minute signals for every Kraken asset simultaneously. The All markets tab is a broad ticker screener.")

elif view=="🧪 Replay":
    st.markdown("### Historical replay — paper trading only")
    st.caption("Strict next-bar entries and conservative stop-first execution when a candle touches both stop and target. Current spread/fee assumptions are applied retrospectively, not actual historical spreads. Only the available ~720 completed Kraken candles can be tested.")
    if signal_error:
        st.info(signal_error)
    elif costs:
        trades=historical_replay(frame,costs,stake,max_hold_bars=max_hold)
        if trades.empty:
            st.warning("No qualifying historical entries with the current pair, fee and risk settings. Zero entries is not a broken chart, and it is not evidence of profitability.")
        else:
            win=100*(trades.pnl>0).mean(); pnl=float(trades.pnl.sum())
            a,b,c=st.columns(3)
            a.metric("Simulated trades",len(trades))
            b.metric("Win rate",f"{win:.1f}%")
            c.metric("Total paper P&L",f"£{pnl:+.2f}")
            st.dataframe(trades.rename(columns={"signal_utc":"Signal time UTC","entry_utc":"Entry UTC","exit_utc":"Exit UTC","pnl":"Net P&L (£)"}),
                         hide_index=True,use_container_width=True,height=310)
            st.download_button("↓ Export replay trades",trades.to_csv(index=False).encode(),
                               file_name=f"replay_{selected.name.replace('/','_')}_{timeframe}.csv",mime="text/csv")
        st.info("A positive replay is not proof of a repeatable edge. Small samples, market changes, partial fills, latency, tax and unavailable historical bid/ask data can make real performance much worse.")

elif view=="✨ AI analyst":
    st.markdown("### AI second opinion")
    st.write("Ask an OpenAI model to **critique** the selected pair's indicators and explain risks. This is on-demand commentary, not a live price predictor, and it cannot place orders.")
    st.caption("A separate OpenAI Platform API key and API billing are required. ChatGPT Plus is not API credit. Never enter your Kraken credentials here.")
    key=st.text_input("OpenAI Platform API key",type="password",placeholder="sk-…",help="Only for your request to OpenAI. Keep this app private if you don't want to expose your controls.")
    model=st.selectbox("Model",["gpt-4.1-mini","gpt-4.1","gpt-5-mini"],index=0)
    if st.button("Critique current setup with AI",type="primary",use_container_width=True):
        if not key.strip().startswith("sk-"):
            st.error("Enter a genuine OpenAI Platform API key created at platform.openai.com/api-keys.")
        elif not result:
            st.info(signal_error)
        else:
            try:
                from openai import OpenAI
                client=OpenAI(api_key=key.strip(),timeout=20,max_retries=1)
                last=frame.iloc[-1]
                compact=[{"UTC":str(x),"close":round(float(r.close),8),"volume":round(float(r.volume),4)}
                         for x,r in frame.tail(25).iterrows()]
                prompt={"pair":selected.name,"interval":timeframe,"signal":result['signal'],
                        "checks":result['checks'],"rsi":float(last.rsi),"ema9":float(last.ema9) if pd.notna(last.ema9) else None,
                        "ema21":float(last.ema21) if pd.notna(last.ema21) else None,
                        "stop":result['stop'],"target":result['target'],"cost_break_even_pct":result['break_even_pct'],
                        "estimated_gain_gbp_on_stake":result['expected_gain'],"stake_gbp":stake,
                        "recent_completed_candles":compact}
                import json
                reply=client.responses.create(model=model,max_output_tokens=550,
                         instructions=("You are a cautious crypto market researcher. Critique this spot chart setup in plain British English. "
                         "Use only the data given. Explicitly explain uncertainty, false signals, spread and fee risks. "
                         "Give possible bullish and bearish scenarios, not a deterministic BUY/SELL forecast, guaranteed return, or invented win rate. "
                         "No leverage and no order placement. 220 words maximum."),
                         input=json.dumps(prompt))
                st.markdown(reply.output_text or "The model returned no text. Try a different model.")
            except Exception as ex:
                # Do not echo the server error body: providers may include identifying key fragments.
                status=getattr(ex,"status_code",None)
                if status==401: st.error("API authentication failed. Create a new valid secret key at platform.openai.com/api-keys.")
                elif status==429: st.error("API rate limit or billing limit reached. Check the OpenAI Platform billing and usage settings.")
                elif status==404: st.error("The chosen model isn't available to your API account. Select a different model.")
                else: st.error(f"The model request failed (HTTP {status or 'network/other'}). Check your API connection, billing, and model permissions.")

st.divider()
st.caption("Version 2 • Read-only public spot market explorer • No futures, margin, auto-trading or wallet access. Technical rules are unverified; they can lose money. Cryptocurrency markets, especially meme coins, can move violently and have low liquidity.")
