"""Mobile-first, touch-enabled TradingView Lightweight Charts component (public CDN)."""
from __future__ import annotations
import json
import math
import pandas as pd

CDN = "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"


def chart_payload(df: pd.DataFrame) -> dict:
    candle, volume = [], []
    lines = {"ema9": [], "ema21": [], "ema50": []}
    for timestamp, row in df.iterrows():
        time = int(timestamp.timestamp())
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        if not all(math.isfinite(v) and v > 0 for v in (o, h, l, c)):
            continue
        candle.append({"time": time, "open": o, "high": h, "low": l, "close": c})
        v = float(row.get("volume", 0))
        volume.append({"time": time, "value": v if math.isfinite(v) and v >= 0 else 0,
                       "color": "rgba(39,196,146,0.30)" if c >= o else "rgba(255,93,124,0.30)"})
        for key in lines:
            val = float(row.get(key, float("nan")))
            if math.isfinite(val) and val > 0:
                lines[key].append({"time": time, "value": val})
    return {"candles": candle, "volume": volume, "lines": lines}


def chart_html(df: pd.DataFrame, quote: str, timeframe: str, show_ema: bool = True,
               show_volume: bool = True, chart_type: str = "Candles") -> str:
    payload = chart_payload(df)
    if not payload["candles"]:
        raise ValueError("No candles to chart")
    data_js = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    is_candles_js = json.dumps(chart_type == "Candles")
    quote_js = json.dumps(quote)
    timeframe_js = json.dumps(timeframe)
    display_ema_js = json.dumps(bool(show_ema))
    display_volume_js = json.dumps(bool(show_volume))
    return r'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5.0"/>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8edf5;background:#0b111b}
*{box-sizing:border-box}body{margin:0;background:#0b111b}
.card{border:1px solid #263244;border-radius:15px;overflow:hidden;background:#0b111b}
.bar{height:43px;display:flex;align-items:center;gap:8px;padding:0 10px;border-bottom:1px solid #263244;white-space:nowrap}
.tag{color:#a6b0c3;font-size:11px;letter-spacing:.6px;font-weight:700}
.candle-info{color:#b9c4d4;font-size:11px;overflow:hidden;text-overflow:ellipsis;flex:1}
button{color:#e8edf5;background:#192536;border:1px solid #30435b;border-radius:8px;padding:6px 9px;cursor:pointer;font-size:13px;font-weight:600}
button:active{background:#31455e}button:focus-visible{outline:2px solid #c2a2ff}
#chart{width:100%;height:420px;touch-action:pan-y} .foot{display:flex;gap:12px;flex-wrap:wrap;justify-content:space-between;color:#8290a5;padding:8px 12px;font-size:10.5px;border-top:1px solid #263244}a{color:#a9a0f9;text-decoration:none}
#fail{display:none;padding:25px;color:#ffb4bc}
@media(max-width:520px){#chart{height:400px}.bar{gap:5px;padding:0 6px}.candle-info{font-size:10px}button{padding:6px 8px}}
</style></head><body><div class="card">
<div class="bar"><span class="tag" id="timeframe"></span><span class="candle-info" id="ohlc">Touch candle to inspect • drag to pan • pinch to zoom</span>
<button aria-label="Zoom out" onclick="zoom(1.65)">−</button><button aria-label="Zoom in" onclick="zoom(.60)">+</button><button onclick="fit()">Fit</button></div>
<div id="chart"></div><div id="fail">The interactive chart library could not load. Switch to Plotly using the chart settings above.</div>
<div class="foot"><span><span style="color:#24c793">●</span> Up &nbsp; <span style="color:#ff597a">●</span> Down</span><span>Times UTC · Kraken completed candles · <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">Charts by TradingView</a></span></div></div>
<script src="''' + CDN + r'''"></script><script>
const DATA=''' + data_js + r''';
const IS_CANDLES=''' + is_candles_js + r''', QUOTE=''' + quote_js + r''', INTERVAL=''' + timeframe_js + r''';
const SHOW_EMA=''' + display_ema_js + r''', SHOW_VOLUME=''' + display_volume_js + r''';
let chart;document.getElementById('timeframe').textContent=INTERVAL+' • '+QUOTE;
const e=document.getElementById('chart');
const money=(v)=>{if(!Number.isFinite(v))return '—';let digits=v>=100?2:v>=1?4:v>=.001?6:9;return (QUOTE==='GBP'?'£':QUOTE==='USD'?'$':QUOTE==='EUR'?'€':'')+Number(v).toLocaleString('en-GB',{minimumFractionDigits:digits,maximumFractionDigits:digits})};
function fit(){if(chart)chart.timeScale().fitContent()}
function zoom(factor){if(!chart)return;let ts=chart.timeScale(),r=ts.getVisibleLogicalRange();if(!r)return;let centre=(r.from+r.to)/2,half=(r.to-r.from)*factor/2;ts.setVisibleLogicalRange({from:centre-half,to:centre+half})}
try {
if(!window.LightweightCharts) throw new Error('Could not load chart library');
chart=LightweightCharts.createChart(e,{width:e.clientWidth,height:e.clientHeight,layout:{background:{type:'solid',color:'#0b111b'},textColor:'#aab7ca',fontSize:11},
grid:{vertLines:{color:'#182538'},horzLines:{color:'#1a293b'}},
rightPriceScale:{visible:true,borderColor:'#26364a',scaleMargins:{top:.09,bottom:SHOW_VOLUME?.24:.08}},leftPriceScale:{visible:false},
timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#26364a',rightOffset:4,barSpacing:8,lockVisibleTimeRangeOnResize:false,fixLeftEdge:false},
localization:{locale:'en-GB'},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
handleScale:{axisPressedMouseMove:{time:true,price:true},mouseWheel:true,pinch:true},
watermark:{visible:false}});
let main;
if(IS_CANDLES){main=chart.addCandlestickSeries({upColor:'#25c69a',downColor:'#ff5d80',borderUpColor:'#25c69a',borderDownColor:'#ff5d80',wickUpColor:'#25c69a',wickDownColor:'#ff5d80'}); main.setData(DATA.candles);}
else{main=chart.addLineSeries({color:'#bba4ff',lineWidth:2});main.setData(DATA.candles.map(x=>({time:x.time,value:x.close})));}
if(SHOW_VOLUME){const v=chart.addHistogramSeries({priceScaleId:'',priceFormat:{type:'volume'},lastValueVisible:false,priceLineVisible:false});v.priceScale().applyOptions({scaleMargins:{top:.77,bottom:.01}});v.setData(DATA.volume)}
if(SHOW_EMA){const col={ema9:'#eab867',ema21:'#71aaf4',ema50:'#b69af6'};
for(let key of Object.keys(DATA.lines)){let ln=chart.addLineSeries({color:col[key],lineWidth:1.35,lastValueVisible:false,priceLineVisible:false});ln.setData(DATA.lines[key])}}
const barMap=new Map(DATA.candles.map(x=>[x.time,x]));
chart.subscribeCrosshairMove(p=>{let c=barMap.get(p.time);if(!c){document.getElementById('ohlc').textContent='Touch candle to inspect • drag to pan • pinch to zoom';return;}
const d=new Date(c.time*1000);document.getElementById('ohlc').textContent=d.toLocaleString('en-GB',{timeZone:'UTC',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})+'  O '+money(c.open)+' H '+money(c.high)+' L '+money(c.low)+' C '+money(c.close)});
const n=DATA.candles.length;chart.timeScale().setVisibleLogicalRange({from:Math.max(0,n-110),to:n+3});
new ResizeObserver(()=>{const w=e.clientWidth,h=e.clientHeight;if(w>0&&h>0)chart.resize(w,h)}).observe(e);
}catch(err){document.getElementById('chart').style.display='none';document.getElementById('fail').style.display='block';document.getElementById('fail').textContent='Chart failed to start: '+String(err)+'. Switch to Plotly in chart settings.';}
</script></body></html>'''
