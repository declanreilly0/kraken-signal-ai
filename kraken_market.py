"""Public, read-only Kraken Spot market data. No credentials or order endpoints."""
from __future__ import annotations

import requests
import pandas as pd

ROOT = "https://api.kraken.com/0/public"
PAIRS = {
    "BTC / GBP": "XBTGBP",
    "ETH / GBP": "ETHGBP",
    "SOL / GBP": "SOLGBP",
    "BTC / USD": "XBTUSD",
    "ETH / USD": "ETHUSD",
    "SOL / USD": "SOLUSD",
}


def _fetch(route: str, params: dict) -> dict:
    resp = requests.get(f"{ROOT}/{route}", params=params, timeout=12, headers={"User-Agent": "KrakenSignalLab/1.0 (paper-analysis)"})
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError("Kraken API: " + "; ".join(payload["error"]))
    return payload["result"]


def fetch_ohlc(pair: str, interval: int = 1) -> pd.DataFrame:
    """Return completed candles only; Kraken's trailing OHLC row is in progress."""
    data = _fetch("OHLC", {"pair": pair, "interval": interval})
    key = next(k for k in data if k != "last")
    raw = data[key]
    if len(raw) < 65:
        raise RuntimeError("Not enough historical candles returned to compute signals.")
    raw = raw[:-1]  # Kraken documents final candle as the not-yet-committed interval.
    cols = ["epoch", "open", "high", "low", "close", "vwap", "volume", "count"]
    frame = pd.DataFrame(raw, columns=cols)
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    frame["time"] = pd.to_datetime(frame["epoch"], unit="s", utc=True)
    frame = frame.set_index("time")["open high low close volume".split()]
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if (frame["close"] <= 0).any():
        raise RuntimeError("Invalid OHLC price from Kraken.")
    return frame


def fetch_ticker(pair: str) -> dict:
    result = _fetch("Ticker", {"pair": pair})
    value = next(iter(result.values()))
    bid, ask, last = float(value["b"][0]), float(value["a"][0]), float(value["c"][0])
    if bid <= 0 or ask <= 0 or ask < bid:
        raise RuntimeError("Invalid top-of-book prices.")
    return {"bid": bid, "ask": ask, "last": last, "spread_pct": 100.0 * (ask - bid) / ((ask + bid) / 2)}
