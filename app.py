"""Kraken Signal Radar V3 — read-only, fee-aware, batched market research.

Streamlit Community Cloud entrypoint: app.py
No account keys, auto-orders, leveraged instruments or synthetic live prices.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import json
import math
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from engine import Costs, add_indicators
from chart_ui import chart_html
from kraken_api import (Market, TIMEFRAMES, fetch_markets, fetch_all_tickers,
                        fetch_ohlc, label_price, _get)
from discovery import record_seen
from radar import (ScanSettings, conversion_rates_gbp, preliminary_rows,
                   eligible_universe, plan_for_market, order_book_cost)

st.set_page_config(page_title="Meme Signal Radar V3", page_icon="📡", layout="wide", initial_sidebar_state="collapsed")
st.markdown('''<style>
html,body,[data-testid="stApp"] {background:#080d15;color:#e8f0ff}
.block-container{max-width:1160px;padding-top:.8rem;padding-bottom:3rem}
[data-testid="stVerticalBlock"]{gap:.62rem}
h1,h2,h3{letter-spacing:-.03em}h1{font-size:clamp(1.7rem,4vw,2.5rem)!important;margin-bottom:0}
h2{font-size:1.28rem!important}h3{font-size:1.08rem!important}
[data-testid="stWidgetLabel"] p{font-size:.83rem;color:#a5b7cc}
[data-testid="stMetric"]{background:#111f2e;border:1px solid #24354a;border-radius:13px;padding:11px 13px}
[data-testid="stMetricLabel"] p{font-size:.8rem;color:#9eafc4}
[data-testid="stMetricValue"]{font-size:1.26rem}
[data-testid="stButton"] button{border-radius:11px;min-height:40px}
[data-testid="stDataFrame"]{border-radius:11px;overflow:hidden}
.muted{color:#a4b4c8;font-size:.86rem;line-height:1.45}
.toptag{color:#46dfb4;font-size:.77rem;letter-spacing:2px;font-weight:800;margin-bottom:6px}
.hero{font-size:.9rem;color:#a5b6ca;margin-bottom:16px}
.notice{border:1px solid #30425a;border-radius:13px;background:#121f31;padding:11px 14px;color:#c2d2e8;font-size:.87rem}
.good{border-color:#26745f;background:#102a25}.warn{border-color:#68502e;background:#2b2417}
.plan{background:#111f30;border:1px solid #314257;border-radius:15px;padding:16px 18px;margin:9px 0}
.plan-head{font-weight:800;font-size:1.13rem;display:flex;align-items:center;justify-content:space-between;gap:9px}
.plan-sub{color:#a3b3c7;font-size:.8rem;margin-top:4px}
.pill{font-size:.73rem;padding:5px 9px;border-radius:7px;display:inline-block;white-space:nowrap}
.p-buy{background:#123a2e;color:#5ae1ae}.p-watch{background:#3b3020;color:#facd7d}.p-skip{background:#40202a;color:#ff9db0}
.plan-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0}
.plan-grid>div{padding:9px 7px;border:1px solid #2b3d52;border-radius:9px;min-width:0}
.plan-grid small{display:block;color:#9dacc0;font-size:.68rem;line-height:1.4}
.plan-grid strong{font-size:clamp(.82rem,2vw,1.12rem);overflow-wrap:anywhere}
.plan-foot{font-size:.78rem;color:#b5c5d9;margin-top:10px}
@media(max-width:760px){.block-container{padding:.76rem .68rem 2rem!important}
[data-testid="stMetric"]{padding:8px 9px}
[data-testid="stMetricValue"]{font-size:1.05rem}
.plan-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.plan{padding:12px}.plan-grid strong{font-size:.94rem}}
</style>''',unsafe_allow_html=True)

@st.cache_data(ttl=600,show_spinner=False)
def markets_cached(): return fetch_markets()

@st.cache_data(ttl=60,show_spinner=False)
def tickers_cached(): return fetch_all_tickers()

@st.cache_data(ttl=45,show_spinner=False)
def candles_cached(pid:str,interval:int): return fetch_ohlc(pid,interval)

@st.cache_data(ttl=40,show_spinner=False)
def depth_cached(pid:str):
    d=_get('Depth',{'pair':pid,'count':30})
    if pid in d:return d[pid]
    values=list(d.values())
    if len(values)!=1:raise ValueError('Cannot identify Kraken depth response')
    return values[0]


def money(n:float|None,quote:str):
    if n is None or not math.isfinite(float(n)):return '—'
    return label_price(float(n),quote)


def gbp(n:float|None)->str:
    return '—' if n is None or not math.isfinite(float(n)) else f'£{n:+.2f}'


def pct(n:float|None, signed:bool=False):
    if n is None or not math.isfinite(float(n)):return '—'
    return f'{n:+.2f}%' if signed else f'{n:.2f}%'


def tile(plan:dict, stake_gbp:float, show_why:bool=True):
    status=plan['status']; css='p-buy' if status=='POTENTIAL BUY' else 'p-watch' if status=='WATCH' else 'p-skip'
    entry=money(plan.get('entry'),plan['quote']); stop=money(plan.get('stop'),plan['quote']); target=money(plan.get('target'),plan['quote'])
    result='—' if plan.get('profit_gbp') is None else gbp(plan['profit_gbp'])
    loss='—' if plan.get('loss_gbp') is None else gbp(plan['loss_gbp'])
    benefit= 'GBP spot' if plan['quote']=='GBP' else 'GBP-equivalent; FX not included'
    header=f'''<div class="plan"><div class="plan-head"><span>{escape(plan['pair'])}</span><span class="pill {css}">{escape(status)}</span></div>
    <div class="plan-sub">{int(plan.get('technical',0))}/5 technical conditions · {escape(benefit)} · {escape(str(plan.get('bar_count',0)))} candles</div>
    <div class="plan-grid"><div><small>Buy trigger (reference)</small><strong>{escape(entry)}</strong></div>
    <div><small>Sell target (hypothetical)</small><strong>{escape(target)}</strong></div>
    <div><small>Stop level</small><strong>{escape(stop)}</strong></div>
    <div><small>£{stake_gbp:.0f} if target hits</small><strong>{escape(result)}</strong></div>
    <div><small>£{stake_gbp:.0f} if stopped</small><strong>{escape(loss)}</strong></div>
    <div><small>Net reward / risk</small><strong>{(plan.get('rr') or 0):.2f}:1</strong></div></div>
    <div class="plan-foot">Target profit is conditional, not predicted or guaranteed. Buy trigger is not an executable order quote.</div></div>'''
    st.markdown(header,unsafe_allow_html=True)
    if st.button(f"📈 Open {plan['pair']} chart",key=f"chart_jump_{plan['pair_id']}"):
        st.session_state.pending_chart=plan['pair_id']
        st.rerun()
    if show_why and plan.get('reasons'):
        with st.expander('Why this status?',expanded=False):
            for reason in plan['reasons'][:8]:st.write('• '+reason)


def scan_batch(rows:list[dict], by_id:dict[str,Market], tickers:dict,
               rates:dict[str,float], settings:ScanSettings, selected:set[str], batch_size:int)->tuple[dict,dict]:
    to_scan=[r for r in rows if r['pair_id'] not in selected][:batch_size]
    output={};fail={}
    def work(r):
        pid=r['pair_id']; market=by_id[pid]
        candles=fetch_ohlc(pid,settings.interval_minutes)
        return plan_for_market(market,tickers[pid],candles,rates[market.quote],settings)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(work,r):r for r in to_scan}
        for fut in as_completed(futures):
            pid=futures[fut]['pair_id']
            try:output[pid]=fut.result()
            except Exception as exc:fail[pid]=str(exc)[:180]
    return output,fail


def show_chart(market:Market,ticker:dict,interval:int):
    st.markdown(f'#### {market.name} · interactive chart')
    try:
        raw=candles_cached(market.pair_id,interval)
        if len(raw)<2:raise ValueError('Insufficient candles')
        df=add_indicators(raw)
        st.caption(f'{len(df)} completed candles · UTC · Kraken OHLC (max 720 per interval)')
        components.html(chart_html(df,market.quote,next((k for k,v in TIMEFRAMES.items() if v==interval),'5m')),
                        height=510,scrolling=False)
        with st.expander('Fallback chart (if the touch chart fails)',expanded=False):
            import plotly.graph_objects as go
            fig=go.Figure(data=[go.Candlestick(x=raw.index,open=raw.open,high=raw.high,
                             low=raw.low,close=raw.close,name=market.name)])
            fig.update_layout(template='plotly_dark',height=450,margin=dict(l=3,r=3,b=15,t=10),
                              dragmode='pan',xaxis_rangeslider_visible=False,paper_bgcolor='#0b111b',plot_bgcolor='#0b111b')
            st.plotly_chart(fig,use_container_width=True,config={'scrollZoom':True,'displaylogo':False})
        return df
    except Exception as exc:
        st.error('Could not load these candles: '+str(exc)[:160])
        return None


st.markdown('<div class="toptag">KRAKEN · SIGNAL RADAR / V3</div>',unsafe_allow_html=True)
st.title('Find potential trades. Not just charts.')
st.markdown('<div class="hero">Scans live public Kraken spot-market snapshots, then checks candidate candles for entry triggers, profit targets, stops and modelled £50 outcomes.</div>',unsafe_allow_html=True)

with st.sidebar:
    st.subheader('⚙️ Scanner settings')
    mode=st.radio('Find candidates in',['Meme-first (all coins)','All spot coins','Meme hints'],horizontal=False,index=0,
                  help='All spot coins covers every Kraken pair in the first-pass screen. Meme hints uses a curated, incomplete ticker list.')
    quote_pref=st.radio('Quoted in',['GBP preferred','GBP only'],index=0)
    timeframe=st.selectbox('Signal timeframe',['1m','5m','15m','30m','1h','4h'],index=1)
    order_type=st.radio('Order fee scenario',['Taker / market','Maker / resting limit'],index=0)
    fee=st.number_input('Each-side fee (%)',min_value=0.,max_value=4.,value=.8 if order_type.startswith('Taker') else .4,step=.05,
          help='Overrides are assumptions, not a promise that your Kraken account qualifies.')
    slip=st.number_input('Slippage each side (%)',value=.05,min_value=0.,max_value=2.,step=.01)
    stake=st.number_input('Paper stake (£)',min_value=5.0,max_value=100000.0,value=50.0,step=5.0)
    max_loss=st.number_input('Maximum modelled loss (£)',min_value=.5,max_value=1000.,value=3.0,step=.5)
    min_volume=st.select_slider('Minimum 24h GBP-equivalent turnover',options=[0,1000,5000,15000,50000,150000],value=5000,
                               help='GBP-converted volume approximated from Kraken prices; does not ensure order-book depth.')
    max_spread=st.select_slider('Maximum quoted spread',options=[.2,.5,1.,1.5,2.5,5.],value=1.5,format_func=lambda v:f'{v:g}%')
    min_trades=st.select_slider('Minimum reported trades (24h)',options=[0,10,30,100,500],value=30)
    batch_size=st.slider('Deep-scan candles per batch',4,16,8,2)
    auto_scan=st.toggle('Scan next batch every 90s (while open)',value=False)
    st.markdown('[Official Kraken Pro fees](https://www.kraken.com/gb/pro/fees)')
    st.caption('Maker orders might never fill; do not treat the lower maker fees as guaranteed. This is read-only spot research.')

# Refresh the rendered page for expiration checks even when auto-scanning is off.
# Automatic next-batch analysis happens only if the user enables it.
st_autorefresh(interval=90000,key='radar_expiry_refresh_v3')
settings=ScanSettings(stake_gbp=stake,fee_pct=fee,slippage_pct=slip,max_loss_gbp=max_loss,
    max_spread_pct=max_spread,min_volume_gbp=float(min_volume),min_trades_24h=min_trades,
    interval_minutes=TIMEFRAMES[timeframe])

try:
    with st.spinner('Fetching Kraken market catalogue and ticker snapshot…'):
        all_markets=markets_cached();tickers=tickers_cached()
    if not all_markets or not tickers:raise ValueError('Market catalogue or ticker data is empty')
except Exception as exc:
    st.error('Kraken market data is temporarily unavailable: '+str(exc)[:250])
    st.info('Refresh the website later. Do not interpret an API outage as a trading signal.')
    st.stop()

by_id={m.pair_id:m for m in all_markets}
rates=conversion_rates_gbp(all_markets,tickers)
rows=preliminary_rows(all_markets,tickers,rates)
considered,counts=eligible_universe(rows,mode,quote_pref,float(min_volume),float(max_spread),int(min_trades))
try:observed=record_seen(set(by_id))
except Exception:observed={'initial_baseline':True,'new_ids':set(),'first_seen':{}}
# Newly noticed Kraken markets get first access to deep-scanning if they pass
# liquidity checks. 'First noticed' does not assert a real listing date.
if observed['new_ids']:
    considered.sort(key=lambda r:(r['pair_id'] in observed['new_ids'],r['meme'],r['pre_score']),reverse=True)

# Reset scored results when assumptions or interval change. Session-based scan state;
# refreshing the browser tab or host restart may lose progress.
scan_key=(mode,quote_pref,timeframe,order_type,round(fee,3),round(slip,3),float(stake),float(max_loss),
          min_volume,max_spread,min_trades)
if st.session_state.get('scan_key')!=scan_key:
    st.session_state.scan_key=scan_key
    st.session_state.plans={}
    st.session_state.failed={}

scan_now= not st.session_state.plans and not st.session_state.failed
controls1,controls2=st.columns([1.4,1.0])
with controls1: more=st.button('📡 Scan next batch',type='primary',use_container_width=True,
                               help='Deep-check the next batch of candidates (candles fetched per pair).')
with controls2: reset=st.button('↻ Restart scan',use_container_width=True,
                                help='Clear prior signal analysis and recheck highest-ranked candidates.')
if reset:
    st.session_state.plans={};st.session_state.failed={}
    candles_cached.clear();tickers_cached.clear();st.rerun()
if more or scan_now or auto_scan:
    scanned=set(st.session_state.plans)|set(st.session_state.failed)
    if len(scanned)>=len(considered) and auto_scan and considered:
        # Old results are not left permanently frozen once all candidates have been visited.
        st.session_state.plans={};st.session_state.failed={};scanned=set()
    if len(scanned)<len(considered):
        with st.spinner(f'Analysing up to {batch_size} Kraken candle charts…'):
            found,failed=scan_batch(considered,by_id,tickers,rates,settings,scanned,batch_size)
            st.session_state.plans.update(found)
            st.session_state.failed.update(failed)

plans=list(st.session_state.plans.values())
plan_ids=set(st.session_state.plans)|set(st.session_state.failed)
def scan_is_fresh(plan):
    try:
        ts=datetime.fromisoformat(plan['scanned_at'])
        return (datetime.now(timezone.utc)-ts).total_seconds() <= max(120,settings.interval_minutes*60*2)
    except (KeyError,TypeError,ValueError):return False
qualified=[x for x in plans if x['status']=='POTENTIAL BUY' and scan_is_fresh(x)]
qualified.sort(key=lambda x:(x.get('rr') or 0,x['technical']),reverse=True)
watch=[x for x in plans if x['status']=='WATCH' and scan_is_fresh(x)]
watch.sort(key=lambda x:(x['technical'],x.get('signal_strength',0)),reverse=True)

k1,k2,k3=st.columns(3)
k1.metric('Kraken spot pairs',f'{len(all_markets):,}')
k2.metric('Deep checked',f'{len(plan_ids):,} / {len(considered):,}')
k3.metric('Qualifying setups',f'{len(qualified)}')
st.progress(min(1,len(plan_ids)/max(1,len(considered))))
st.caption(f'{len({m.base for m in all_markets}):,} distinct base symbols · {counts["passes_liquidity"]:,} pairs pass first-pass filters · {len(considered)} deduplicated candidate coins · market data cached briefly')

if observed['new_ids']:
    newly=[by_id[x].name for x in observed['new_ids'] if x in by_id]
    st.info(f'{len(newly)} pairs newly noticed by this app instance: '+', '.join(newly[:20])+('…' if len(newly)>20 else '')+'. First-seen times are NOT official listing dates.')
else:
    st.caption('New listings: this app includes newly available Kraken spot pairs on catalogue refresh. It cannot trade coins before Kraken lists them; “first seen” is not an official listing timestamp.')

expired=sum(not scan_is_fresh(p) for p in plans)
if expired:
    st.caption(f'{expired} old result(s) are now expired and are NOT shown as current potential trades. Tap Restart scan for fresh analysis.')
if not considered:
    st.warning('No pairs meet those quote/liquidity filters. Widen the settings to explore more coins. No trade signal is available.')

if st.session_state.get('pending_chart'):
    st.session_state.screen_view='📈 Chart & depth'
    st.session_state.focus_pair_id=st.session_state.pending_chart
    st.session_state.chart_search=by_id[st.session_state.pending_chart].base
    del st.session_state.pending_chart
view=st.radio('Choose screen',['🎯 Best setups','🌐 All markets','📈 Chart & depth','🧠 AI / method'],horizontal=True,key='screen_view')
if view=='🎯 Best setups':
    if qualified:
        st.markdown('### Potential trade setups')
        st.markdown('<div class="notice good">These candidates passed the model rules at their last scan. Recheck current Kraken bid/ask and candle freshness before any decision. A pass is not a guarantee of profit.</div>',unsafe_allow_html=True)
        for candidate in qualified[:8]:tile(candidate,stake)
    else:
        st.markdown('<div class="notice warn"><b>NO ACTIONABLE SETUP FOUND IN SCANNED PAIRS.</b><br/>That is a valid outcome. The scanner will not invent a BUY signal just to have something to show.</div>',unsafe_allow_html=True)
    st.markdown('### Closest candidates to watch')
    if watch:
        for candidate in watch[:8]:tile(candidate,stake)
    elif plans:
        st.info('Nothing passes even the WATCH checks in these batches. These are the strongest rejected candidates, NOT buy recommendations:')
        rejects=sorted([p for p in plans if p['status']=='SKIP' and scan_is_fresh(p) and p.get('entry') is not None],
                       key=lambda p:(p['technical'],p.get('signal_strength',0)),reverse=True)
        for candidate in rejects[:3]:tile(candidate,stake)
    else:st.info('No candle results returned yet. Check Kraken availability and scan another batch.')
    with st.expander('See all completed deep-scan results'):
        tab=[]
        for x in sorted(plans,key=lambda v:(v['technical'],v.get('signal_strength',0)),reverse=True):
            tab.append({'Coin':x['pair'],'Signal':x['status'],'Checks':f"{x['technical']}/5",
                'Buy trigger':x.get('entry'), 'Sell target':x.get('target'),
                '£50 profit if hit':x.get('profit_gbp'),'£50 loss if stopped':x.get('loss_gbp'),
                'Modelled R/R':x.get('rr'),'Spread %':x.get('spread_pct')})
        if tab:st.dataframe(pd.DataFrame(tab),hide_index=True,use_container_width=True,height=420)
        for pid,error in list(st.session_state.failed.items())[:12]:
            st.caption(f'Could not deeply scan {by_id.get(pid).name if pid in by_id else pid}: {error}')
    st.caption('RANKING LIMIT: only deep-scanned coins can appear as potential buys. A bulk ticker snapshot surveys all online spot pairs, but this is NOT a simultaneous 1-minute candle analysis of every market.')

if view=='🌐 All markets':
    st.markdown('### All Kraken spot markets — first-pass screener')
    st.caption('Filter by any symbol including untagged/new meme coins. This table contains ticker statistics, not deep-scanned BUY signals.')
    query=st.text_input('Search symbol or pair',placeholder='PEPE, WIF, BONK, new token…',key='all_search')
    only_meme=st.toggle('Show curated meme hints only (incomplete classification)',value=False)
    filtered=[r for r in rows if (not query or query.upper().strip() in r['pair'].upper())
              and (not only_meme or r['meme'])]
    filtered.sort(key=lambda x:x['pre_score'],reverse=True)
    display=[{'Pair':r['pair'],'Meme hint':'Yes' if r['meme'] else '',
       'Daily change %':r['change_pct'],'Vol 24h £-equiv':r['volume_gbp'],
       'Spread %':r['spread_pct'],'Trades 24h':r['trades'],'Initial screen rank':r['pre_score']}
       for r in filtered[:700]]
    st.dataframe(pd.DataFrame(display),hide_index=True,use_container_width=True,height=465)
    st.caption(f'{len(filtered):,} matching markets; showing up to 700. Quotes are a cached public snapshot. Volume conversions are approximate.')

if view=='📈 Chart & depth':
    st.markdown('### Inspect any market')
    search=st.text_input('Find pair',placeholder='DOGE, PEPE, WIF, ETH/GBP…',key='chart_search')
    matching=[m for m in all_markets if search.strip().upper() in m.name.upper() or search.strip().upper() in m.pair_id.upper()]
    preferred=sorted(matching,key=lambda m:(m.pair_id!=st.session_state.get('focus_pair_id'),m.quote!='GBP',m.name))[:300]
    if preferred:
        market=st.selectbox('Market',preferred,format_func=lambda m:m.name,key='chart_select')
        chart_tf=st.selectbox('Chart interval',list(TIMEFRAMES),index=list(TIMEFRAMES).index(timeframe),key='chart_interval')
        chart_ticker=tickers.get(market.pair_id)
        if chart_ticker:st.caption(f'Latest quote: {money(chart_ticker["last"],market.quote)} · Spread: {pct(chart_ticker["spread_pct"])}')
        show_chart(market,chart_ticker,TIMEFRAMES[chart_tf])
        st.markdown('#### Check current order-book depth for £50')
        if st.button('Estimate immediate buy/sell impact for selected pair',use_container_width=True):
            if market.quote not in rates:
                st.warning('No quote-to-GBP conversion available for this market; depth check disabled.')
            else:
                try:
                    depth=depth_cached(market.pair_id)
                    hypothetical_quote=stake/rates[market.quote]
                    impact=order_book_cost(depth.get('asks',[]),depth.get('bids',[]),hypothetical_quote)
                    if not impact['fillable']:st.warning(impact['detail'])
                    else:
                        st.metric('Instantaneous buy-and-sell depth cost before fees',pct(impact['instant_spread_impact_pct']))
                        st.caption('A static order-book snapshot, not a promised fill. Fees, FX, latency and price changes are NOT included in this depth-only estimate.')
                except Exception as e:st.warning('Depth unavailable: '+str(e)[:180])
    else:st.warning('No listed Kraken spot pair matches that search.')

if view=='🧠 AI / method':
    st.markdown('### What the scanner does')
    st.write('**Step 1:** Kraken AssetPairs + one market-wide Ticker snapshot screens all currently online public spot pairs, including tokens added since the catalogue last refreshed.')
    st.write('**Step 2:** Quote liquidity, spread and activity determine which pairs are suitable for deeper analysis. One preferred fiat/stablecoin market per base coin is queued.')
    st.write('**Step 3:** Up to the batch size of OHLC charts are fetched at a time. EMA, RSI, breakout, relative volume and candle checks are evaluated on completed candles only.')
    st.write('**Step 4:** An illustrative entry trigger, volatility-based target and stop are checked against both trading fees, spread, slippage, maximum loss and net reward/risk.')
    st.write('**Step 5:** The list shows POTENTIAL BUY, WATCH, SKIP or LIMITED HISTORY; nothing automatically trades.')
    st.warning('A buy label is NOT a prediction of the next 1–5 minute price move. The £50 figure is what the model computes **if** the target were hit, not a forecast of expected profits. Backtesting and forward paper trading are needed to assess an edge.')
    st.caption('New coins that Kraken has not yet listed cannot appear in this exchange-only scanner. The meme ticker list is incomplete. An untagged meme coin can still be examined via All spot coins and search. Quotes may vary by account and UK availability. Prices can move before you react.')
    st.markdown('#### Optional AI explanation (requires separate OpenAI API billing)')
    key=st.text_input('OpenAI API key — optional, never upload to GitHub',type='password',key='api_key_v3')
    if st.button('Critique strongest scanned candidate with AI',disabled=not bool(plans),use_container_width=True):
        candidate=(qualified or watch or plans)[0]
        if not key:st.info('Enter an OpenAI API key or just use the free rule-based scanner.')
        else:
            try:
                from openai import OpenAI
                record={k:v for k,v in candidate.items() if k in ('pair','status','technical','entry','target','stop','profit_gbp','loss_gbp','rr','reasons','break_even_pct','spread_pct','price_change_pct','volume_gbp')}
                ans=OpenAI(api_key=key,timeout=18).chat.completions.create(
                  model='gpt-4.1-mini',temperature=.1,max_tokens=450,
                  messages=[{'role':'system','content':'You are a cautious UK retail crypto research assistant. Explain this hypothetical technical spot setup briefly. Avoid recommendations to trade, claims of certainty or probability, and never suggest leverage. Discuss market-data age, liquidity, fees, and what could invalidate the setup. Do not claim to see future/live data.'},
                            {'role':'user','content':json.dumps(record,default=str)}])
                st.write(ans.choices[0].message.content)
            except Exception:
                st.error('AI request failed. Check API key, available model and separate platform billing. The error is hidden to avoid exposing key details.')
    st.markdown('#### Sources and caveats')
    st.markdown('[Kraken Pro fees](https://www.kraken.com/gb/pro/fees) · [Kraken API market data](https://support.kraken.com/articles/360000919986-public-endpoint-examples-you-can-try-them-directly-in-a-web-browser-) · [Kraken listing roadmap](https://www.kraken.com/listings)')
    st.caption('Kraken REST OHLC provides up to 720 recent bars and includes an unfinished final candle (excluded). Browser-hosted Streamlit does not keep monitoring while closed. Session scan results can become stale or be lost on host restart. No account API keys are required.')

st.divider()
st.caption(f"Data checked on app run: {datetime.now(timezone.utc):%d %b %Y %H:%M UTC} · Exchange-only, public data · Paper research · No orders · No leverage")
