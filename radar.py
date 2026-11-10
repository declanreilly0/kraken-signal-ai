"""Fee-aware Kraken spot-market signal research.

A market-wide snapshot is a first-pass *screen*, not a candle analysis.
Deep analysis is explicitly limited to fetched candles on scanned markets.
No exchange credentials or order placement are present.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import numpy as np
import pandas as pd
from engine import Costs, add_indicators, conditions
from kraken_api import Market

LIQUID_QUOTES = ("GBP", "USD", "EUR", "USDT", "USDC", "BTC", "ETH")
PRIMARY_QUOTES = ("GBP", "USD", "EUR", "USDT", "USDC")


def conversion_rates_gbp(markets: list[Market], tickers: dict[str,dict]) -> dict[str,float]:
    """Convert known quote currencies to GBP using current available Kraken markets.

    Unresolvable quotes are excluded from GBP-volume and GBP P&L comparisons.
    Bid/ask conversion fees are NOT modelled for non-GBP trading pairs.
    """
    rates = {"GBP":1.0}
    for _ in range(3):
        for m in markets:
            q = tickers.get(m.pair_id)
            if not q: continue
            mid = (q["bid"]+q["ask"])/2
            if not math.isfinite(mid) or mid<=0: continue
            if m.quote in rates and m.base not in rates:
                rates[m.base] = mid * rates[m.quote]
            if m.base in rates and m.quote not in rates:
                rates[m.quote] = rates[m.base] / mid
    return rates


def preliminary_rows(markets: list[Market], tickers: dict[str,dict], rates: dict[str,float]) -> list[dict]:
    """Every online market is represented, even if it lacks ticker/conversion."""
    out=[]
    for m in markets:
        q=tickers.get(m.pair_id)
        conv=rates.get(m.quote)
        if not q:
            out.append(dict(pair_id=m.pair_id,pair=m.name,base=m.base,quote=m.quote,meme=m.is_meme_hint,
                price=float('nan'),volume_gbp=float('nan'),spread_pct=float('nan'),change_pct=float('nan'),
                trades=0,pre_score=-999.0,exclusion="No ticker"))
            continue
        volume_gbp=float(q['quote_volume_24h'])*conv if conv is not None else float('nan')
        spread=float(q['spread_pct']); change=float(q['change_open_pct']); trades=int(q['trades_24h'])
        # This is a ranking heuristic, not a forecast or claimed win probability.
        if not math.isfinite(volume_gbp) or volume_gbp<=0: liq=-12
        else: liq=max(-12,min(22,4.0*math.log10(max(volume_gbp,1)/1000)))
        moderate_momentum = max(-16,min(22, change*0.8)) if math.isfinite(change) else -12
        spread_penalty = min(35,max(0,spread)*14)
        activity=min(12,2.8*math.log10(max(trades,1)))
        pre_score=round(liq + moderate_momentum + activity - spread_penalty,2)
        reason="" if conv is not None else "Quote currency cannot be converted to GBP"
        out.append(dict(pair_id=m.pair_id,pair=m.name,base=m.base,quote=m.quote,meme=m.is_meme_hint,
            price=float(q['last']),volume_gbp=volume_gbp,spread_pct=spread,change_pct=change,
            trades=trades,pre_score=pre_score,exclusion=reason))
    return out


def eligible_universe(rows: list[dict], market_mode: str="Meme hints", quote_mode: str="GBP preferred",
                      min_gbp_volume: float=5000, max_spread_pct: float=1.5,
                      min_trades: int=30) -> tuple[list[dict],dict]:
    """Choose one usable quote market per base coin for deeper OHLC study.

    Does NOT mislabel all pairs as deeply scanned.
    """
    counts={"catalog_pairs":len(rows),"with_usable_ticker":0,"passes_liquidity":0,"distinct_candidates":0}
    filt=[]
    for r in rows:
        if not math.isfinite(r['price']) or not math.isfinite(r['volume_gbp']):continue
        counts['with_usable_ticker']+=1
        if market_mode=="Meme hints" and not r['meme']: continue
        if quote_mode=="GBP only" and r['quote']!='GBP':continue
        if r['volume_gbp']<min_gbp_volume or r['trades']<min_trades or r['spread_pct']>max_spread_pct:continue
        if r['quote'] not in PRIMARY_QUOTES:continue
        counts['passes_liquidity']+=1
        filt.append(r)
    # Primary quote GBP is favoured but only when sufficiently competitive.
    quote_priority={"GBP":4,"USD":3,"EUR":2,"USDT":1,"USDC":0}
    selected={}
    for r in filt:
        key=r['base']
        preference= (r['pre_score'] + (7 if r['quote']=='GBP' else 0)
                     + 2.1*math.log10(max(r['volume_gbp'],1)))
        if key not in selected or preference > selected[key][0]:
            selected[key]=(preference,r)
    result=[v[1] for v in selected.values()]
    if market_mode == 'Meme-first (all coins)':
        # Prioritise named meme assets without excluding untagged/new tokens.
        result.sort(key=lambda r:r['pre_score'] + (22 if r['meme'] else 0),reverse=True)
    else:
        result.sort(key=lambda r:r['pre_score'],reverse=True)
    counts['distinct_candidates']=len(result)
    return result,counts


@dataclass(frozen=True)
class ScanSettings:
    stake_gbp: float=50
    fee_pct: float=0.8
    slippage_pct: float=0.05
    min_net_reward_risk: float=1.2
    max_loss_gbp: float=3.0
    max_spread_pct: float=1.5
    min_volume_gbp: float=5000
    min_trades_24h: int=30
    interval_minutes: int=5


def tick_round(price: float, tick_size: float | None, upward: bool) -> float:
    if tick_size is None or not math.isfinite(tick_size) or tick_size <= 0:
        return price
    step=Decimal(str(tick_size))
    units=(Decimal(str(price))/step).to_integral_value(rounding=ROUND_CEILING if upward else ROUND_FLOOR)
    return float(units*step)


def plan_for_market(m: Market, ticker: dict, candles: pd.DataFrame, conversion_gbp: float,
                    settings: ScanSettings, now: pd.Timestamp | None=None) -> dict:
    """Creates hypothetical spot long setup based only on completed candles and *current* top-of-book.

    'POTENTIAL BUY' requires technical, risk and fee constraints. This is not a
    probability of success, an executable quote, or an order recommendation.
    """
    result={"pair_id":m.pair_id,"pair":m.name,"quote":m.quote,"base":m.base,
            "tagged_meme":m.is_meme_hint, "status":"SKIP", "technical":0,
            "entry":None,"target":None,"stop":None,"profit_gbp":None,
            "loss_gbp":None,"rr":None,"reasons":[],"time_utc":None,
            "break_even_pct":None,"conditions":{},"scanned_at":datetime.now(timezone.utc).isoformat(),
            "bar_count":len(candles),"signal_strength":0.0,"spread_pct":ticker.get('spread_pct'),
            "volume_gbp": ticker.get('quote_volume_24h',0)*conversion_gbp,
            "price_change_pct":ticker.get('change_open_pct',0),"trades":ticker.get('trades_24h',0),
            "fresh":False}
    if len(candles)<65:
        result.update(status="LIMITED HISTORY",reasons=[f"Only {len(candles)} completed bars; need at least 65 for this technical model. This does NOT prove the token was recently listed."])
        return result
    data=add_indicators(candles)
    row=data.iloc[-1]
    scored=conditions(row)
    score=sum(scored.values()); result['technical']=score; result['conditions']=scored
    result['time_utc']=str(data.index[-1])
    now=now or pd.Timestamp.now(tz="UTC")
    bar_minutes=settings.interval_minutes
    age_mins = max(0.,(now-(data.index[-1]+pd.Timedelta(minutes=bar_minutes))).total_seconds()/60)
    fresh=age_mins<=max(4.,2*bar_minutes)
    result['fresh']=fresh
    try:
        cost=Costs(fee_pct_each_side=settings.fee_pct, slippage_pct_each_side=settings.slippage_pct,
            spread_pct_round_trip=float(ticker['spread_pct']))
    except (ValueError,TypeError) as e:
        result['reasons'].append(f"Invalid/unknown costs: {e}")
        return result
    result['break_even_pct']=cost.break_even_pct
    mid=(float(ticker['bid'])+float(ticker['ask']))/2
    close=float(row.close)
    if not 0<mid or not 0<close or not math.isfinite(float(row.atr)):
        result['reasons'].append("Invalid market prices or volatility data")
        return result
    # If ticker differs markedly from the completed candle, do not pretend that
    # levels from the old candle are executable now.
    diverged=abs(mid/close-1)*100 > max(1.2, 2.5*float(row.atr)/close*100)
    # Plan a trigger slightly above the last completed candle's resistance;
    # spot entry is NOT assumed filled until the price actually trades there.
    resistance=float(data['high'].iloc[-13:-1].max())
    trigger=max(mid,resistance*1.0005)
    stop_distance=max(float(row.atr)*1.3,trigger*.006)
    stop=trigger-stop_distance
    # Fixed volatility target; do NOT move the target merely to fake profitability.
    target=trigger+stop_distance*3.15
    # Real Kraken orders must respect the pair's tick increment. Use conservative
    # rounding: entry upward, target downward, stop downward.
    trigger=tick_round(trigger,m.tick_size,True)
    target=tick_round(target,m.tick_size,False)
    stop=tick_round(stop,m.tick_size,False)
    if not 0<stop<trigger<target:
        result['reasons'].append('Tick rounding yielded unusable price levels')
        return result
    p=cost.net_pnl(settings.stake_gbp,trigger,target)
    l=cost.net_pnl(settings.stake_gbp,trigger,stop)
    rr=p/-l if l<0 else 0
    trigger_gap=(trigger/mid-1)*100
    vol_gbp=float(result['volume_gbp'])
    result.update(entry=trigger,target=target,stop=stop,profit_gbp=p,loss_gbp=l,
        rr=rr,signal_strength=float(score*16+min(18,max(0,float(row.volume_ratio or 0))*3)),
        trigger_gap_pct=trigger_gap,mid_now=mid)
    reasons=[]
    if score<4:reasons.append(f"Only {score}/5 technical confirmations")
    if p<=0:reasons.append(f"Target fails to cover {cost.break_even_pct:.2f}% estimated round-trip break-even")
    if rr<settings.min_net_reward_risk:reasons.append(f"Net reward/risk {rr:.2f}:1 is below {settings.min_net_reward_risk:.2f}:1")
    if l < -settings.max_loss_gbp:reasons.append(f"Modelled loss £{-l:.2f} exceeds your £{settings.max_loss_gbp:.2f} cap")
    if float(ticker['spread_pct'])>settings.max_spread_pct:reasons.append("Spread is wider than permitted")
    if vol_gbp<settings.min_volume_gbp:reasons.append("Insufficient 24h quoted turnover")
    if int(ticker['trades_24h'])<settings.min_trades_24h:reasons.append("Too few reported trades")
    if not fresh:reasons.append("Last completed candle is stale")
    if diverged:reasons.append("Current quote deviates sharply from last completed candle")
    if trigger_gap>2.5:reasons.append(f"Breakout trigger is {trigger_gap:.2f}% above current midpoint")
    if stop<=0:reasons.append("Invalid stop level")
    # Check exchange spot minimum, based on the projected entry (and quote conversion).
    if m.minimum_order is not None and m.minimum_order*trigger*conversion_gbp > settings.stake_gbp:
        reasons.append("Stake is below Kraken's approximate minimum base quantity for this pair")
    if m.minimum_cost is not None and m.minimum_cost*conversion_gbp > settings.stake_gbp:
        reasons.append("Stake is below Kraken's minimum quote-currency order value")
    if score>=4 and not reasons:
        result['status']="POTENTIAL BUY"
        reasons=["All model gates passed; requires price reaching the entry trigger and a live spread recheck"]
    elif score>=3 and p>0 and fresh and not diverged:
        result['status']="WATCH"
    else:
        result['status']="SKIP"
    result['reasons']=reasons
    return result


def order_book_cost(asks: list, bids: list, amount_quote: float) -> dict:
    """Sample top-of-book market impact for a hypothetical quote-currency budget.

    This is NOT an actual exchange execution and excludes fees.
    """
    if amount_quote<=0: raise ValueError('budget must be positive')
    rem=amount_quote; units=0; max_ask=None
    for level in asks:
        price,qty=float(level[0]),float(level[1])
        if price<=0 or qty<=0:continue
        q=min(qty,rem/price)
        units+=q;rem-=q*price; max_ask=price
        if rem<=1e-8: break
    if rem>1e-5 or units<=0:return {"fillable":False,"detail":"Insufficient ask depth shown"}
    avg_buy=amount_quote/units
    rem_units=units;proceeds=0
    for level in bids:
        price,qty=float(level[0]),float(level[1])
        if price<=0 or qty<=0:continue
        take=min(rem_units,qty)
        proceeds+=take*price;rem_units-=take
        if rem_units<=1e-10:break
    if rem_units>1e-8:return {"fillable":False,"detail":"Insufficient bid depth shown"}
    return {"fillable":True,"avg_buy":avg_buy,"immediate_sell_quote":proceeds,
            "instant_spread_impact_pct":(1-proceeds/amount_quote)*100,"max_ask":max_ask}
