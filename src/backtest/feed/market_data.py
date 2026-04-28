"""Market data gathering using existing loaders — OHLCV + derived metrics."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from backtest.loaders.registry import resolve_loader

SUPPORTED_MARKETS: Dict[str, List[str]] = {
    "crypto": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    "hk_equity": ["700.HK", "5.HK", "9988.HK"],
    "us_equity": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ"],
}


def fetch_market_data(
    market: str,
    symbols: List[str] | None = None,
    start: str = "",
    end: str = "",
    interval: str = "1D",
) -> Dict[str, pd.DataFrame]:
    """Fetch OHLCV for the given market, returning {symbol: df}."""
    if not symbols:
        symbols = SUPPORTED_MARKETS.get(market, [])

    loader = resolve_loader(market)
    results: Dict[str, pd.DataFrame] = {}

    for sym in symbols:
        try:
            bars = loader.fetch([sym], start, end, interval=interval)
        except Exception:
            continue
        if sym in bars and not bars[sym].empty:
            results[sym] = bars[sym]

    return results if results else _fallback_fetch(market, symbols, start, end, interval)


def _fallback_fetch(
    market: str, symbols: List[str], start: str, end: str, interval: str
) -> Dict[str, pd.DataFrame]:
    """Direct yfinance fallback when loader chain fails."""
    try:
        import yfinance as yf  # noqa: PLC0415
    except ImportError:
        return {}

    results: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(
                start=start,
                end=end,
                interval="1d" if interval in ("1D", "4H") else "60m",
                auto_adjust=True,
            )
        except Exception:
            continue
        if hist.empty:
            continue
        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "trade_date"
        df["volume"] = df["volume"].fillna(0.0)
        results[sym] = df
    return results


def compute_metrics(
    dfs: Dict[str, pd.DataFrame],
    lookback: int = 30,
) -> Dict[str, Dict]:
    """Derive hedge-fund-grade metrics from OHLCV data.

    Returns per-symbol dict with:
      - price_change_{1d,7d,30d}
      - volatility (annualised)
      - volume_change_{7d,30d}
      - rsi_14
      - ma_{20,50,200} (latest value)
      - atr_14
      - max_drawdown_30d
    """
    metrics: Dict[str, Dict] = {}

    for sym, df in dfs.items():
        if len(df) < 14:
            metrics[sym] = {}
            continue

        close = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]
        latest = close.iloc[-1]
        m: Dict = {}

        # Price changes
        for label, days in [("1d", 1), ("7d", 7), ("30d", 30)]:
            if len(close) > days:
                m[f"price_change_{label}"] = float((latest / close.iloc[-days - 1] - 1) * 100)
            else:
                m[f"price_change_{label}"] = 0.0

        # Annualised volatility (daily returns)
        returns = close.pct_change().dropna()
        m["volatility"] = float(returns.std() * (252**0.5) * 100)

        # Volume change
        vol_later = volume.iloc[-5:].mean()
        vol_earlier = volume.iloc[-30:-5].mean() if len(volume) > 30 else volume.iloc[0].mean()
        m["volume_change_30d"] = float(((vol_later / vol_earlier) - 1) * 100)

        # RSI 14
        gain = returns.where(returns > 0, 0).rolling(14).mean()
        loss = (-returns.where(returns < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("inf"))
        m["rsi_14"] = float(rs.iloc[-1]) if len(rs) > 0 else 50.0

        # Moving averages
        for period in (20, 50, 200):
            if len(close) >= period:
                m[f"ma_{period}"] = float(close.rolling(period).mean().iloc[-1])
            else:
                m[f"ma_{period}"] = None

        # ATR 14
        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
        ).max(axis=1)
        m["atr_14"] = float(tr.rolling(14).mean().iloc[-1])

        # Max drawdown 30d
        if len(close) >= 30:
            peak = close.iloc[-30:].cummax()
            dd = close.iloc[-30:] / peak - 1
            m["max_drawdown_30d"] = float(dd.min() * 100)
        else:
            m["max_drawdown_30d"] = 0.0

        m["current_price"] = float(latest)
        metrics[sym] = m

    return metrics
