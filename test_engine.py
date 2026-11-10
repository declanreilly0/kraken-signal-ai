import numpy as np
import pandas as pd
from engine import Costs, add_indicators, evaluate, historical_replay, stop_and_target


def make_data(n=300):
    times = pd.date_range('2026-01-01', periods=n, freq='min', tz='UTC')
    # Deterministic monotonic-ish test data
    close = 2000 + 0.22 * np.arange(n) + 1.5 * np.sin(np.arange(n) / 8)
    return pd.DataFrame({
        'open':close-0.10, 'high':close+1.0, 'low':close-1.0,
        'close':close, 'volume':100 + (np.arange(n) % 17) * 10,
    }, index=times)


def test_fee_breakeven_and_no_free_round_trip():
    c = Costs(fee_pct_each_side=0.80, slippage_pct_each_side=0, spread_pct_round_trip=0)
    assert 1.60 < c.break_even_pct < 1.70
    assert abs(c.net_pnl(50, 100, 100*(1+c.break_even_pct/100))) < 1e-8
    assert c.net_pnl(50, 100, 100) < 0
    assert abs(c.net_pnl(50, 100, 100) + 50 * (1-0.992/1.008)) < 1e-8


def test_indicators_no_future_lookahead():
    raw = make_data()
    short = add_indicators(raw.iloc[:150]).iloc[-1]
    full = add_indicators(raw).iloc[149]
    for v in ('ema9', 'ema21', 'ema50', 'atr', 'rsi','previous_high', 'volume_ratio'):
        assert abs(short[v] - full[v]) < 1e-9


def test_evaluate_and_backtest_smoke():
    df = add_indicators(make_data())
    result = evaluate(df, Costs(), amount=50)
    assert result['signal'] in {'WAIT','WATCH','BUY SETUP','EXIT / AVOID'}
    assert result['stop'] < result['price'] < result['target']
    replay = historical_replay(df, Costs(), 50, max_hold_bars=15)
    assert set(['entry_utc','exit_utc','pnl']).issubset(replay.columns) or replay.empty


def test_invalid_cost():
    try:
        Costs(fee_pct_each_side=-0.1)
    except ValueError:
        pass
    else:
        assert False
