from unittest.mock import patch
from kraken_market import fetch_ohlc, fetch_ticker


def test_kraken_candles_drop_last_uncommitted_candle():
    rows = []
    for i in range(70):
        rows.append([1750000000 + i*60, "100", "102", "99", str(100+i*.01), "100", "1.0", 3])
    rows[-1][4] = "99999"  # deliberately unrealistic, unfinished price
    with patch('kraken_market._fetch',return_value={'XXBTZGBP':rows,'last':1750000000}):
        df = fetch_ohlc('XBTGBP',1)
    assert len(df)==69
    assert df.close.iloc[-1]!=99999


def test_spread_from_top_of_book():
    response={'XXBTZGBP':{'a':['100.2','1','1'],'b':['99.8','1','1'],'c':['100','1']}}
    with patch('kraken_market._fetch',return_value=response):
        book=fetch_ticker('XBTGBP')
    assert round(book['spread_pct'],3)==0.4
