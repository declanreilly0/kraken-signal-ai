"""Read-only public Kraken spot market API (NO keys, balances, or orders)."""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
import requests
import pandas as pd

ROOT = "https://api.kraken.com/0/public"
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60,
              "4h": 240, "1d": 1440, "1w": 10080, "15d": 21600}
# This is a DISCOVERY hint, not a complete/final meme-coin classification.
SYMBOL_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}
MEME_SYMBOLS = frozenset((
    """DOGE XDG SHIB PEPE BONK FLOKI WIF TRUMP MELANIA FARTCOIN POPCAT PENGU
    MOG BRETT TURBO MEW BOME GOAT PNUT ACT MOODENG NEIRO GIGA SPX PONKE
    DOGS HMSTR NOT TOSHI BABYDOGE ELON DEGEN CHILLGUY AI16Z AIXBT PIPPIN
    WEN MEME COQ MYRO PUPS BILLY MICHI GME BODEN MOTHER FWOG GORK
    USELESS ZEREBRO UFD SPX6900 PEPECOIN KISHU CAT DOG 1MBABYDOGE
    SNEK NYAN BONGO PUMP TROLL KET ZORA BANANAS31 RIF CATE
    """.split()
))


@dataclass(frozen=True)
class Market:
    pair_id: str
    name: str
    base: str
    quote: str
    status: str
    is_meme_hint: bool
    minimum_order: float | None = None
    minimum_cost: float | None = None
    tick_size: float | None = None


def _get(endpoint: str, params: dict | None = None) -> dict:
    response = requests.get(
        f"{ROOT}/{endpoint}", params=params or {}, timeout=(5, 15),
        headers={"User-Agent": "KrakenSignalLabV3/3.0 educational-readonly"},
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
        raise ValueError("Unexpected Kraken response")
    if body.get("error"):
        raise RuntimeError("Kraken reported: " + ", ".join(map(str, body["error"])))
    return body["result"]


def parse_market_catalog(payload: dict, online_only: bool = True) -> list[Market]:
    markets: list[Market] = []
    for pair_id, value in payload.items():
        if not isinstance(value, dict):
            continue
        if value.get("aclass_base") != "currency" or value.get("aclass_quote") != "currency":
            continue
        if ".d" in pair_id or pair_id.endswith(".d"):
            continue  # historical dark-pool codes
        status = str(value.get("status", "online"))
        if online_only and status != "online":
            continue
        wsname = str(value.get("wsname") or "")
        if "/" in wsname:
            base, quote = wsname.split("/", 1)
        else:
            # Kraken's identifiers vary; this is only a display fallback.
            alt = str(value.get("altname") or pair_id)
            base, quote = alt, "OTHER"
        base, quote = SYMBOL_ALIASES.get(base.upper(),base.upper()), quote.upper()
        if not base or not quote:
            continue
        # XDG is Kraken's exchange symbol for DOGE.
        meme = base in MEME_SYMBOLS or base.removeprefix("X") in MEME_SYMBOLS
        minimum = value.get("ordermin")
        try:
            minimum = float(minimum) if minimum is not None else None
        except (TypeError, ValueError):
            minimum = None
        costmin=value.get("costmin")
        try: costmin=float(costmin) if costmin is not None else None
        except (TypeError,ValueError): costmin=None
        tick=value.get("tick_size")
        if tick is None and value.get("pair_decimals") is not None:
            try:tick=10**(-int(value["pair_decimals"]))
            except (TypeError,ValueError):tick=None
        try: tick=float(tick) if tick is not None and float(tick)>0 else None
        except (TypeError,ValueError):tick=None
        markets.append(Market(pair_id=str(pair_id), name=f"{base}/{quote}", base=base,
                              quote=quote, status=status, is_meme_hint=meme,
                              minimum_order=minimum, minimum_cost=costmin, tick_size=tick))
    return sorted(markets, key=lambda m: (m.base, m.quote, m.pair_id))


def fetch_markets() -> list[Market]:
    markets = parse_market_catalog(_get("AssetPairs"))
    if not markets:
        raise RuntimeError("Kraken returned no online spot markets")
    return markets


def parse_ticker(ticker: dict) -> dict:
    def one(key: str, pos: int = 0) -> float:
        raw = ticker.get(key)
        if isinstance(raw, list):
            return float(raw[pos])
        return float(raw)
    bid, ask = one("b"), one("a")
    last, opening = one("c"), one("o")
    base_volume_24h = one("v", 1)
    vwap_24h = one("p", 1)
    if not 0 < bid <= ask or not 0 < last:
        raise ValueError("Missing or invalid bid/ask price")
    return {
        "bid": bid, "ask": ask, "last": last, "open": opening,
        "change_open_pct": (last / opening - 1) * 100 if opening > 0 else float("nan"),
        "spread_pct": (ask - bid) / ((ask + bid) / 2) * 100,
        "base_volume_24h": base_volume_24h,
        "quote_volume_24h": base_volume_24h * vwap_24h,
        "trades_24h": int(ticker.get("t", [0, 0])[1]),
    }


def match_pair_from_response(data: dict, requested: str) -> dict:
    if requested in data:
        return data[requested]
    matches = [value for key, value in data.items() if key != "last"]
    if len(matches) != 1:
        raise RuntimeError("Could not identify requested pair in Kraken response")
    return matches[0]


def fetch_quote(pair_id: str) -> dict:
    data = _get("Ticker", {"pair": pair_id})
    return parse_ticker(match_pair_from_response(data, pair_id))


def fetch_all_tickers() -> dict[str, dict]:
    """One request for the market-wide ticker, not one request per token."""
    data = _get("Ticker")
    parsed = {}
    for pair_id, value in data.items():
        try:
            parsed[pair_id] = parse_ticker(value)
        except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
            continue
    return parsed


def parse_ohlc(payload: dict, pair_id: str) -> pd.DataFrame:
    data = match_pair_from_response(payload, pair_id)
    if len(data) < 2:
        raise RuntimeError("This pair has too few candles for a chart")
    cols = ["epoch", "open", "high", "low", "close", "vwap", "volume", "count"]
    # Kraken always includes a final in-progress candle. Exclude it from signals and replays.
    candles = data[:-1]
    frame = pd.DataFrame(candles, columns=cols)
    for col in cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["epoch", "open", "high", "low", "close", "volume"])
    frame = frame[(frame["close"] > 0) & (frame["high"] >= frame["low"])]
    frame["epoch"] = frame["epoch"].astype("int64")
    frame["time"] = pd.to_datetime(frame["epoch"], unit="s", utc=True)
    frame = frame.drop_duplicates(subset=["time"], keep="last").set_index("time").sort_index()
    if frame.empty:
        raise RuntimeError("No completed Kraken candles available for this pair")
    return frame[["open", "high", "low", "close", "vwap", "volume", "count"]]


def fetch_ohlc(pair_id: str, interval: int) -> pd.DataFrame:
    if interval not in TIMEFRAMES.values():
        raise ValueError("Unsupported Kraken candle interval")
    data = _get("OHLC", {"pair": pair_id, "interval": interval})
    return parse_ohlc(data, pair_id)


def label_price(price: float, quote: str) -> str:
    if price is None or not math.isfinite(price):
        return "—"
    prefix = {"GBP": "£", "USD": "$", "EUR": "€"}.get(quote, "")
    suffix = "" if prefix else f" {quote}"
    precision = (2 if price >= 100 else 4 if price >= 1 else 6 if price >= 0.001
                 else 9 if price >= .0000001 else 12 if price >= .0000000001 else 15)
    return f"{prefix}{price:,.{precision}f}{suffix}"


def search_markets(markets: list[Market], query: str = "", quote: str = "All",
                   meme_only: bool = False) -> list[Market]:
    q = query.strip().upper()
    def match(m: Market) -> bool:
        if quote != "All" and m.quote != quote:
            return False
        if meme_only and not m.is_meme_hint:
            return False
        return q in f"{m.name} {m.pair_id}" if q else True
    return [m for m in markets if match(m)]
