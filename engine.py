"""Transparent, long-only, fee-aware signal research and conservative OHLC replay.

No orders, leverage, guaranteed edge, or model-generated probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    fee_pct_each_side: float = 0.80  # Kraken Pro base-tier taker, per side
    slippage_pct_each_side: float = 0.05
    spread_pct_round_trip: float = 0.03  # actual ticker spread when available

    def __post_init__(self):
        if not all(0 <= x < 20 for x in (self.fee_pct_each_side, self.slippage_pct_each_side, self.spread_pct_round_trip)):
            raise ValueError("Invalid fee, slippage, or spread assumption.")

    @property
    def buy_multiplier(self) -> float:
        return (1 + (self.spread_pct_round_trip / 2 + self.slippage_pct_each_side) / 100) * (1 + self.fee_pct_each_side / 100)

    @property
    def sell_multiplier(self) -> float:
        return (1 - (self.spread_pct_round_trip / 2 + self.slippage_pct_each_side) / 100) * (1 - self.fee_pct_each_side / 100)

    @property
    def break_even_pct(self) -> float:
        """Required rise in the mid-price for a zero-net-profit round trip."""
        return (self.buy_multiplier / self.sell_multiplier - 1) * 100

    def net_pnl(self, amount: float, mid_entry: float, mid_exit: float) -> float:
        """Buy using *total amount including fees*, sell net of fees and friction."""
        if mid_entry <= 0 or mid_exit <= 0 or amount <= 0:
            raise ValueError("Invalid trade amount/prices")
        return amount * ((mid_exit / mid_entry) * self.sell_multiplier / self.buy_multiplier - 1)


def add_indicators(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy().sort_index()
    for n in (9, 21, 50):
        df[f"ema{n}"] = df["close"].ewm(span=n, adjust=False, min_periods=n).mean()
    delta = df["close"].diff()
    avg_up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    # All-up, all-down, or flat series are common in synthetic tests / thin markets.
    rsi = rsi.mask((avg_down == 0) & (avg_up > 0), 100)
    rsi = rsi.mask((avg_up == 0) & (avg_down > 0), 0)
    rsi = rsi.mask((avg_down == 0) & (avg_up == 0), 50)
    df["rsi"] = rsi.fillna(50)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(), (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=14).mean()
    df["volume_ratio"] = df["volume"] / df["volume"].rolling(20, min_periods=20).mean().replace(0, np.nan)
    df["previous_high"] = df["high"].shift(1).rolling(12, min_periods=12).max()
    df["ema21_slope"] = df["ema21"] - df["ema21"].shift(3)
    return df


def conditions(row: pd.Series) -> dict[str, bool]:
    """Fixed rules; no hindsight, scores are NOT probabilities."""
    if row[["ema9", "ema21", "ema50", "atr", "volume_ratio", "previous_high", "ema21_slope"]].isna().any():
        return {k: False for k in ("Uptrend", "Breakout", "RSI momentum", "Volume confirmation", "Positive candle")}
    return {
        "Uptrend": bool(row.ema9 > row.ema21 > row.ema50 and row.ema21_slope > 0),
        "Breakout": bool(row.close > row.previous_high),
        "RSI momentum": bool(53 <= row.rsi <= 72),
        "Volume confirmation": bool(row.volume_ratio >= 1.15),
        "Positive candle": bool(row.close > row.open and (row.close - row.open) >= 0.35 * row.atr),
    }


def exit_warning(row: pd.Series) -> bool:
    if pd.isna(row.ema9) or pd.isna(row.ema21) or pd.isna(row.ema50):
        return False
    return bool(row.ema9 < row.ema21 and row.close < row.ema50 and row.rsi < 45)


def stop_and_target(price: float, atr: float) -> tuple[float, float]:
    # Target is based only on volatility/risk, not fabricated to clear fees.
    risk_dist = max(price * 0.003, float(atr) * 1.35)
    return price - risk_dist, price + risk_dist * 2.8


def evaluate(df: pd.DataFrame, costs: Costs, amount: float, bar_minutes: int = 1, spread_known: bool = True) -> dict:
    if len(df) < 60:
        raise ValueError("Need at least 60 completed candles.")
    row = df.iloc[-1]
    price = float(row.close)
    signal_conditions = conditions(row)
    score = sum(signal_conditions.values())
    stop, target = stop_and_target(price, float(row.atr))
    profit = costs.net_pnl(amount, price, target)
    loss = costs.net_pnl(amount, price, stop)
    net_rr = profit / -loss if loss < 0 else 0
    price_move_pct = 100 * (target / price - 1)
    reasons = []
    if exit_warning(row):
        status = "EXIT / AVOID"
        reasons.append("Bearish trend: an exit warning if you already hold spot; not a short-selling signal.")
    elif score >= 4 and profit > 0 and net_rr >= 1.2 and spread_known:
        status = "BUY SETUP"
        reasons.append("Technical conditions align and the illustrative target clears expected costs.")
    elif score >= 3:
        status = "WATCH"
        reasons.append("Some momentum conditions align, but the full cost-and-risk test did not pass.")
    else:
        status = "WAIT"
        reasons.append("Not enough technical confirmations for a long setup.")
    if profit <= 0:
        reasons.append(f"Target move {price_move_pct:.2f}% does not cover the {costs.break_even_pct:.2f}% estimated break-even rise.")
    elif net_rr < 1.2:
        reasons.append("Net reward/risk is below the 1.2 minimum after costs.")
    if not spread_known:
        reasons.append("Live spread is unavailable, so BUY signals are disabled until it can be checked.")
    return {
        "signal": status, "score": score, "checks": signal_conditions,
        "price": price, "stop": stop, "target": target, "atr": float(row.atr),
        "expected_gain": profit, "expected_loss": loss, "net_rr": net_rr,
        "move_to_target_pct": price_move_pct,
        "break_even_pct": costs.break_even_pct,
        "bar_time": df.index[-1], "reasons": reasons,
        "risk_note": "Spot only, long-only research; no orders are placed.",
    }


def historical_replay(df: pd.DataFrame, costs: Costs, amount: float, max_hold_bars: int = 30) -> pd.DataFrame:
    """Very limited historical replay, next-bar entries, stop-first when ambiguous.

    Assumes immediate fills at adjusted next open and exit midpoint; maker fills are
    NOT guaranteed. No future candles influence entry conditions.
    """
    if max_hold_bars < 1:
        raise ValueError("max_hold_bars must be >=1")
    trades = []
    i = 60
    n = len(df)
    while i < n - 1:
        row = df.iloc[i]
        checks = conditions(row)
        score = sum(checks.values())
        if score < 4 or pd.isna(row.atr) or exit_warning(row):
            i += 1
            continue
        # Entry on next bar, not the signal candle.
        entry_i = i + 1
        entry = float(df.iloc[entry_i].open)
        if entry <= 0:
            i += 1
            continue
        stop, target = stop_and_target(entry, float(row.atr))
        if costs.net_pnl(amount, entry, target) <= 0:
            i += 1
            continue
        loss = costs.net_pnl(amount, entry, stop)
        if loss >= 0 or costs.net_pnl(amount, entry, target) / -loss < 1.2:
            i += 1
            continue
        last_j = min(n - 1, entry_i + max_hold_bars - 1)
        closed = False
        for j in range(entry_i, last_j + 1):
            bar = df.iloc[j]
            # If stop & target hit in one candle, assume the unfavourable stop occurred first.
            if bar.low <= stop:
                # A gap below the stop is worse than an assumed stop-level fill.
                exit_price, why = min(stop, float(bar.open)), "Stop loss"
            elif bar.high >= target:
                exit_price, why = target, "Target reached"
            elif j == last_j:
                exit_price, why = float(bar.close), "Time exit"
            else:
                continue
            pnl = costs.net_pnl(amount, entry, exit_price)
            trades.append({
                "signal_utc": df.index[i], "entry_utc": df.index[entry_i],
                "exit_utc": df.index[j], "entry": entry, "exit": exit_price,
                "pnl": pnl, "return_pct": 100 * pnl / amount,
                "reason": why, "bars_held": j - entry_i + 1,
            })
            i = j + 1  # no overlapping trades
            closed = True
            break
        if not closed:
            i += 1
    return pd.DataFrame(trades)
