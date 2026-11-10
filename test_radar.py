from datetime import datetime,timezone,timedelta
import math
import pandas as pd
import numpy as np
import pytest
import radar
from radar import conversion_rates_gbp,preliminary_rows,eligible_universe,plan_for_market,ScanSettings,order_book_cost
from discovery import record_seen
from kraken_api import Market


def markets_and_quotes():
    markets=[Market('USDGBP','USD/GBP','USD','GBP','online',False),
             Market('PEPEGBP','PEPE/GBP','PEPE','GBP','online',True),
             Market('PEPEUSD','PEPE/USD','PEPE','USD','online',True),
             Market('NEWMUSD','NEWM/USD','NEWM','USD','online',False)]
    def q(bid,ask,open_,trades=600,vol=140000):
        return {'bid':bid,'ask':ask,'last':(bid+ask)/2,'open':open_,
                'spread_pct':(ask-bid)/((ask+bid)/2)*100,'change_open_pct':2,
                'quote_volume_24h':vol,'trades_24h':trades}
    return markets,{'USDGBP':q(.795,.805,.8),
                    'PEPEGBP':q(.000001,.000001001,.00000095),
                    'PEPEUSD':q(.0000013,.000001301,.0000012),
                    'NEWMUSD':q(10,10.05,9.5)}


def candle_fixture(n=120,close=100,minutes=5,stale=False):
    end=pd.Timestamp.now(tz='UTC').floor(f'{minutes}min')
    if stale:end-=pd.Timedelta(hours=7)
    idx=pd.date_range(end=end-pd.Timedelta(minutes=minutes),periods=n,freq=f'{minutes}min')
    vals=close+np.sin(np.arange(n)/9)*1+np.arange(n)*.07
    return pd.DataFrame({'open':vals-.25,'high':vals+.45,'low':vals-.5,
        'close':vals,'vwap':vals,'volume':np.ones(n)*50,'count':np.ones(n)*120},index=idx)


def test_conversions_and_all_market_first_pass():
    markets,tickers=markets_and_quotes()
    rates=conversion_rates_gbp(markets,tickers)
    assert abs(rates['USD']-.8)<.01
    rows=preliminary_rows(markets,tickers,rates)
    assert len(rows)==len(markets)
    # A brand new but untagged coin must still be covered by ALL markets mode.
    all_candidates,stats=eligible_universe(rows,'All spot coins','GBP preferred',0,3.0,0)
    assert {'NEWM','PEPE'} <= {r['base'] for r in all_candidates}
    assert len([r for r in all_candidates if r['base']=='PEPE'])==1
    meme_candidates,_=eligible_universe(rows,'Meme hints','GBP preferred',0,3.0,0)
    assert {r['base'] for r in meme_candidates}=={'PEPE'}


def test_fee_aware_plan_rejects_unprofitable_trade(monkeypatch):
    monkeypatch.setattr(radar,'conditions',lambda row:{k:True for k in ('Uptrend','Breakout','RSI momentum','Volume confirmation','Positive candle')})
    m=Market('TESTGBP','TEST/GBP','TEST','GBP','online',True)
    candle=candle_fixture()
    ticker={'bid':104,'ask':106,'spread_pct':1.9,'quote_volume_24h':500000,
            'trades_24h':10000,'change_open_pct':5}
    plan=plan_for_market(m,ticker,candle,1.0,ScanSettings(max_spread_pct=3),now=pd.Timestamp.now(tz='UTC'))
    assert plan['status']!='POTENTIAL BUY'  # spread and/or net risk prevent it
    assert plan['profit_gbp'] is not None
    assert plan['loss_gbp']<0
    assert plan['break_even_pct']>3


def test_newcoin_not_given_signal_without_history():
    m=Market('NEWMUSD','NEWM/USD','NEWM','USD','online',False)
    q={'bid':100,'ask':100.2,'spread_pct':.2,'quote_volume_24h':100000,
            'trades_24h':2000,'change_open_pct':13}
    plan=plan_for_market(m,q,candle_fixture(n=20),.8,ScanSettings())
    assert plan['status']=='LIMITED HISTORY'
    assert plan['entry'] is None
    assert 'NOT prove' in plan['reasons'][0]


def test_stale_candles_block_buy_even_with_all_checks(monkeypatch):
    monkeypatch.setattr(radar,'conditions',lambda row:{k:True for k in ('Uptrend','Breakout','RSI momentum','Volume confirmation','Positive candle')})
    m=Market('BIGGBP','BIG/GBP','BIG','GBP','online',True)
    q={'bid':110,'ask':110.01,'spread_pct':.01,'quote_volume_24h':1e7,
         'trades_24h':50000,'change_open_pct':12}
    p=plan_for_market(m,q,candle_fixture(stale=True),1.,ScanSettings(fee_pct=.1,slippage_pct=0),
                      now=pd.Timestamp.now(tz='UTC'))
    assert p['fresh'] is False
    assert p['status']!='POTENTIAL BUY'
    assert any('stale' in s.lower() for s in p['reasons'])


def test_book_depth_does_not_invent_fill():
    assert not order_book_cost([['100',.1]],[['99',10]],50)['fillable']
    q=order_book_cost([['100',1]],[['99',1]],50)
    assert q['fillable']
    assert math.isclose(q['instant_spread_impact_pct'],1.0)


def test_new_pairs_are_not_misrepresented_as_new_listing(tmp_path):
    f=tmp_path/'first.json';t=datetime(2026,11,10,tzinfo=timezone.utc)
    first=record_seen({'DOGEUSD','PEPEUSD'},f,t)
    assert first['initial_baseline'] and not first['new_ids']
    second=record_seen({'DOGEUSD','PEPEUSD','NEWUSD'},f,t+timedelta(minutes=10))
    assert not second['initial_baseline'] and second['new_ids']=={'NEWUSD'}


def test_same_price_setup_can_qualify_with_lower_fees_but_not_higher(monkeypatch):
    monkeypatch.setattr(radar,'conditions',lambda row:{k:True for k in ('Uptrend','Breakout','RSI momentum','Volume confirmation','Positive candle')})
    m=Market('TESTGBP','TEST/GBP','TEST','GBP','online',True)
    q={'bid':108,'ask':108.02,'spread_pct':.0185,'quote_volume_24h':500000,
       'trades_24h':10000,'change_open_pct':5}
    bars=candle_fixture()
    lower=plan_for_market(m,q,bars,1.,ScanSettings(fee_pct=.4,slippage_pct=0))
    higher=plan_for_market(m,q,bars,1.,ScanSettings(fee_pct=.8,slippage_pct=0))
    assert lower['status']=='POTENTIAL BUY'
    assert lower['profit_gbp']>0 and lower['rr']>1.2
    assert higher['status']!='POTENTIAL BUY'
    assert higher['rr']<lower['rr']


def test_tick_rounding_is_safe_and_exchange_aligned():
    from radar import tick_round
    assert tick_round(1.2341,.01,True)==1.24
    assert tick_round(1.2341,.01,False)==1.23
    assert tick_round(.000000123456,.00000000001,True)>=.000000123456


def test_markets_with_min_cost_above_stake_never_get_buy(monkeypatch):
    monkeypatch.setattr(radar,'conditions',lambda row:{k:True for k in ('Uptrend','Breakout','RSI momentum','Volume confirmation','Positive candle')})
    m=Market('TESTGBP','TEST/GBP','TEST','GBP','online',True,minimum_cost=70,tick_size=.01)
    q={'bid':108,'ask':108.02,'spread_pct':.0185,'quote_volume_24h':500000,
       'trades_24h':10000,'change_open_pct':5}
    plan=plan_for_market(m,q,candle_fixture(),1.,ScanSettings(fee_pct=.1,slippage_pct=0))
    assert plan['status']!='POTENTIAL BUY'
    assert any('minimum quote' in x for x in plan['reasons'])
