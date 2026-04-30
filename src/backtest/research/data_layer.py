"""Unified data collection layer — US equities, HK stocks, and crypto.

Aggregates:
  - OHLCV prices via loader registry (yfinance / ccxt / futu fallback)
  - Live news headlines via RSS feeds (crypto + finance)
  - Macro context (treasury yields, USD index, VIX, gold, oil) via yfinance
  - Sector ETF data (US) for cross-sectional comparison
  - HK market via yfinance HK tickers
  - Crypto market via ccxt (Binance)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import requests

from backtest.loaders.registry import resolve_loader

# ── Configuration ─────────────────────────────────────────────────

DEFAULT_RSS_SOURCES: Dict[str, str] = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
    "cointelegraph": "https://cointelegraph.com/rss",
    "blockworks": "https://blockworks.co/feed/",
    "decrypt": "https://decrypt.co/feed",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "newsbtc": "https://www.newsbtc.com/feed/",
    "bitcoinmagazine": "https://bitcoinmagazine.com/feed",
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "google_news_finance": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
    "reuters_markets": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best&best-sectors=markets",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories",
    "cnbc_finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
}

# Macro tickers tracked via yfinance
MACRO_TICKERS = {
    "usd_index": "DX-Y.NYB",
    "vix": "^VIX",
    "tnx_10y": "^TNX",
    "fed_funds": "^FF",
    "gold": "GC=F",
    "oil": "CL=F",
}

# Sectors to scan for cross-sectional rotation analysis
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "SMH": "Semiconductors",
    "ARKK": "Innovation/Disruptive",
    "IBB": "Biotechnology",
    "KRE": "Regional Banks",
}

# ── Default Watchlists ────────────────────────────────────────────

DEFAULT_US_WATCHLIST = [
    "SPY",
    "QQQ",
    "IWM",  # Indices
    "AAPL",
    "NVDA",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",  # Mag 7
    "AVGO",
    "ORCL",
    "CRM",
    "NOW",  # Tech
    "JPM",
    "GS",
    "BAC",
    "V",
    "MA",  # Financials
    "UNH",
    "LLY",
    "JNJ",  # Healthcare
    "XOM",
    "CVX",  # Energy
    "WMT",
    "COST",
    "PG",  # Staples
    "AMD",
    "INTC",
    "QCOM",
    "MU",  # Semis
]

DEFAULT_HK_WATCHLIST = [
    "HSI",  # Hang Seng Index
    "0700.HK",  # Tencent
    "9988.HK",  # Alibaba
    "3690.HK",  # Meituan
    "9618.HK",  # JD
    "1810.HK",  # Xiaomi
    "1299.HK",  # AIA
    "0005.HK",  # HSBC
    "3988.HK",  # Bank of China
    "0939.HK",  # CCB
    "2269.HK",  # WuXi Biologics
    "1024.HK",  # Kuaishou
    "9888.HK",  # Baidu HK
    "9999.HK",  # NetEase
    "0017.HK",  # New World Development
]

DEFAULT_CRYPTO_WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "DOGE/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "DOT/USDT",
    "MATIC/USDT",
    "NEAR/USDT",
    "ARB/USDT",
    "OP/USDT",
    "INJ/USDT",
    "TIA/USDT",
    "SEI/USDT",
]

# ── Market Code ───────────────────────────────────────────────────

MARKET_TYPES = ("us_equity", "hk_equity", "crypto")


# ── Data Models ───────────────────────────────────────────────────


@dataclass
class Headline:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    tickers: List[str] = field(default_factory=list)


@dataclass
class PriceSnapshot:
    symbol: str
    market: str
    current_price: float
    change_1d_pct: float
    change_7d_pct: float
    change_30d_pct: float
    volume_24h: float
    high_30d: float
    low_30d: float
    market_cap: float = 0.0
    name: str = ""


# ── RSS Fetcher ───────────────────────────────────────────────────


def fetch_rss(url: str, timeout: float = 15) -> List[Headline]:
    items: List[Headline] = []
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "AIMM/1.0"})
        resp.raise_for_status()
    except Exception:
        return items

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return items

    for item_elem in root.iter("item"):
        title_el = item_elem.find("title")
        link_el = item_elem.find("link")
        date_el = item_elem.find("pubDate")
        desc_el = item_elem.find("description")

        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue

        link = (link_el.text or "").strip() if link_el is not None else ""

        pub_date = datetime.now(timezone.utc)
        if date_el is not None and date_el.text:
            try:
                pub_date = datetime.strptime(date_el.text.strip(), "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                pass

        summary = (desc_el.text or "").strip() if desc_el is not None else ""

        items.append(
            Headline(
                title=title,
                url=link,
                source=url,
                published=pub_date,
                summary=summary,
            )
        )
    return items


def collect_headlines(
    sources: Optional[List[str]] = None, max_per_source: int = 3
) -> List[Headline]:
    items: List[Headline] = []
    rss = {k: v for k, v in DEFAULT_RSS_SOURCES.items() if sources is None or k in sources}
    for url in rss.values():
        items.extend(fetch_rss(url)[:max_per_source])
    items.sort(key=lambda x: x.published, reverse=True)
    return items


# ── OHLCV Data ────────────────────────────────────────────────────


def fetch_ohlcv(
    symbols: List[str],
    market: str = "us_equity",
    days: int = 365,
    interval: str = "1D",
) -> Dict[str, pd.DataFrame]:
    """Fetch OHLCV — try loader registry first, then yfinance."""
    end = datetime.now()
    start = end.replace(year=end.year - 1) if days >= 365 else end - pd.Timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Try loader registry first
    try:
        loader = resolve_loader(market)
        results = loader.fetch(symbols, start_str, end_str, interval=interval)
        if any(not df.empty for df in results.values()):
            return results
    except Exception:
        pass

    # yfinance fallback
    try:
        import yfinance as yf

        results: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                hist = yf.Ticker(sym).history(start=start_str, end=end_str, auto_adjust=True)
                if not hist.empty:
                    df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
                    df.columns = ["open", "high", "low", "close", "volume"]
                    df.index.name = "trade_date"
                    results[sym] = df
            except Exception:
                continue
        return results
    except ImportError:
        return {}


def fetch_crypto_ohlcv(
    symbols: List[str] = DEFAULT_CRYPTO_WATCHLIST,
    days: int = 365,
    interval: str = "1d",
) -> Dict[str, pd.DataFrame]:
    """Fetch crypto OHLCV via ccxt Binance."""
    results: Dict[str, pd.DataFrame] = {}
    try:
        import ccxt

        exchange = ccxt.binance()
        # Convert ms to timestamp
        since = exchange.parse8601(
            (datetime.now(timezone.utc) - pd.Timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
        )
        for sym in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(
                    sym, timeframe=interval, since=since, limit=min(days * 2, 1000)
                )
                if ohlcv and len(ohlcv) >= 2:
                    df = pd.DataFrame(
                        ohlcv, columns=["trade_date", "open", "high", "low", "close", "volume"]
                    )
                    df["trade_date"] = pd.to_datetime(df["trade_date"], unit="ms")
                    df.set_index("trade_date", inplace=True)
                    results[sym] = df
            except Exception:
                continue
    except ImportError:
        pass
    return results


def fetch_macro(days: int = 60) -> Dict[str, pd.DataFrame]:
    """Fetch macro indicators from yfinance."""
    return fetch_ohlcv(list(MACRO_TICKERS.values()), market="us_equity", days=days)


def fetch_sectors(days: int = 60) -> Dict[str, pd.DataFrame]:
    """Fetch sector ETF data for rotation analysis."""
    return fetch_ohlcv(list(SECTOR_ETFS.keys()), market="us_equity", days=days)


# ── Price Snapshots ──────────────────────────────────────────────


def price_snapshots(
    dfs: Dict[str, pd.DataFrame],
    market: str = "us_equity",
) -> Dict[str, PriceSnapshot]:
    """Compute price snapshots from fethed OHLCV dataframes."""
    snaps: Dict[str, PriceSnapshot] = {}
    for sym, df in dfs.items():
        if df.empty or len(df) < 2:
            continue
        close = df["close"]
        vol = df["volume"]
        snaps[sym] = PriceSnapshot(
            symbol=sym,
            market=market,
            current_price=float(close.iloc[-1]),
            change_1d_pct=float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
            change_7d_pct=float((close.iloc[-1] / close.iloc[-min(8, len(close))] - 1) * 100),
            change_30d_pct=float((close.iloc[-1] / close.iloc[-min(31, len(close))] - 1) * 100),
            volume_24h=float(vol.iloc[-1]),
            high_30d=float(close.iloc[-min(30, len(close)) :].max()),
            low_30d=float(close.iloc[-min(30, len(close)) :].min()),
        )
    return snaps
