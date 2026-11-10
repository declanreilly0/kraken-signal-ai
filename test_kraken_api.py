from unittest.mock import patch
from datetime import datetime, timezone
import pandas as pd
from kraken_api import (
    parse_market_catalog, search_markets, parse_ticker, match_pair_from_response,
    parse_ohlc, fetch_all_tickers, fetch_markets, label_price, TIMEFRAMES,
)
from chart_ui import chart_html,chart_payload
from engine import add_indicators


def fixture_catalog():
    return {
      'XXBTZGBP': {'aclass_base':'currency','aclass_quote':'currency','wsname':'XBT/GBP','altname':'XBTGBP','status':'online'},
      'XDGUSD': {'aclass_base':'currency','aclass_quote':'currency','wsname':'XDG/USD','status':'online'},
      'PEPEUSD': {'aclass_base':'currency','aclass_quote':'currency','wsname':'PEPE/USD','status':'online'},
      'SOLSOM': {'aclass_base':'currency','aclass_quote':'currency','wsname':'SOL/USD','status':'limit_only'},
      'XBTUSD.d':{'aclass_base':'currency','aclass_quote':'currency','wsname':'XBT/USD','status':'online'},
      'XSTOCKS': {'aclass_base':'tokenized_asset','aclass_quote':'currency','wsname':'XYZ/USD','status':'online'},
    }


def test_catalog_all_online_market_pairs_except_non_spot():
    markets=parse_market_catalog(fixture_catalog())
    assert len(markets)==3
    assert {m.name for m in markets}=={'BTC/GBP','DOGE/USD','PEPE/USD'}
    assert len(search_markets(markets,'DOGE'))==1
    assert len(search_markets(markets,'XDG'))==1
    assert len(search_markets(markets,'PEPE',meme_only=True))==1
    assert len(search_markets(markets,'GBP',quote='GBP'))==1


def test_parse_ticker_correct_spread_volume_and_open():
    t=parse_ticker({'a':['100.2','1','1'],'b':['99.8','1','1'],'c':['101','1'],
                    'o':'100','v':['1000','3000'],'p':['100','100.3'],'t':[8,1005]})
    assert abs(t['spread_pct']-0.4)<1e-9
    assert abs(t['change_open_pct']-1)<1e-9
    assert t['quote_volume_24h']==3000*100.3
    assert t['trades_24h']==1005


def test_ohlc_drops_uncommitted_bar_sorts_and_indexes_utc():
    rows=[]
    for i in range(82):
        rows.append([1750000000+i*60,'100','102','99',str(100+i*.01),'100','1',30])
    rows[-1][4]='99999'
    parsed=parse_ohlc({'XXBTZGBP':rows,'last':1750000000},'XBTGBP')
    assert len(parsed)==81
    assert parsed.close.iloc[-1]!=99999
    assert str(parsed.index.tz)=='UTC'


def test_bulk_ticker_uses_one_request_and_skips_bad_market():
    good={'a':['11','2','2'],'b':['10','3','3'],'c':['10.5','1'],
          'o':'10','v':['5','30'],'p':['10','10'],'t':[1,60]}
    with patch('kraken_api._get',return_value={'BTCUSD':good,'BAD':{'a':['0']}}) as call:
        data=fetch_all_tickers()
    call.assert_called_once_with('Ticker')
    assert list(data)==['BTCUSD']


def test_chart_payload_and_html_valid_data():
    ix=pd.date_range('2026-01-01', periods=65, freq='min', tz='UTC')
    df=pd.DataFrame({'open':[100.]*65,'high':[102.]*65,'low':[99.]*65,'close':[101.]*65,'volume':[13.]*65},index=ix)
    ind=add_indicators(df)
    data=chart_payload(ind)
    assert len(data['candles'])==65
    assert len(data['lines']['ema50'])==16
    assert data['candles'][0]['time']==int(ix[0].timestamp())
    html=chart_html(ind,'GBP','1m')
    assert 'LightweightCharts.createChart' in html
    assert 'pinch:true' in html
    assert 'zoom(1.65)' in html
    assert 'setVisibleLogicalRange' in html


def test_timeframes_include_all_user_requested_intervals():
    assert all(x in TIMEFRAMES for x in ('1m','5m','15m','30m','1h','4h','1d','1w'))


def test_price_display_small_memecoin():
    assert label_price(0.00000125, 'GBP').startswith('£0.000001250')
