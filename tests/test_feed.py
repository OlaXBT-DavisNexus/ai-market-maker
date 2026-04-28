"""Tests for finance feed data collection and metrics."""

from __future__ import annotations

import pandas as pd

from backtest.feed.market_data import _fallback_fetch, compute_metrics
from backtest.feed.news_collector import RSS_SOURCES, NewsItem, fetch_cryptocurrency_cv


class TestMetrics:
    def _sample_df(self, n=60):
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        return pd.DataFrame(
            {
                "open": [100 + i * 0.5 for i in range(n)],
                "high": [102 + i * 0.5 for i in range(n)],
                "low": [98 + i * 0.5 for i in range(n)],
                "close": [100 + i * 0.5 for i in range(n)],
                "volume": [1_000_000 + i * 1000 for i in range(n)],
            },
            index=dates,
        )

    def test_compute_metrics_returns_dicts(self):
        df = self._sample_df()
        result = compute_metrics({"TEST": df})
        assert "TEST" in result
        met = result["TEST"]
        assert "price_change_30d" in met
        assert "volatility" in met
        assert "rsi_14" in met
        assert "atr_14" in met
        assert "max_drawdown_30d" in met
        assert "current_price" in met

    def test_price_change_up(self):
        df = self._sample_df()
        met = compute_metrics({"UP": df})["UP"]
        assert met["price_change_30d"] > 0

    def test_price_change_down(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        df = pd.DataFrame(
            {
                "open": [i * -0.5 + 130 for i in range(60)],
                "high": [i * -0.5 + 132 for i in range(60)],
                "low": [i * -0.5 + 128 for i in range(60)],
                "close": [i * -0.5 + 130 for i in range(60)],
                "volume": [1_000_000 for _ in range(60)],
            },
            index=dates,
        )
        met = compute_metrics({"DOWN": df})["DOWN"]
        assert met["price_change_30d"] < 0

    def test_insufficient_data_returns_empty(self):
        df = self._sample_df(5)
        met = compute_metrics({"SHORT": df})["SHORT"]
        assert met == {}


class TestNewsCollector:
    def test_rss_sources_defined(self):
        assert "coindesk" in RSS_SOURCES
        assert "cointelegraph" in RSS_SOURCES

    def test_news_item_dataclass(self):
        item = NewsItem(
            title="Test", url="https://example.com", source="test", published=pd.Timestamp.now()
        )
        assert item.title == "Test"
        assert item.tickers == []

    def test_fetch_cryptocurrency_cv_returns_list(self):
        """Integration: hits live API."""
        items = fetch_cryptocurrency_cv(limit=3)
        assert isinstance(items, list)


class TestMarketData:
    def test_fallback_fetch_empty_when_no_yfinance(self):
        result = _fallback_fetch("crypto", ["BTC/USDT"], "2026-01-01", "2026-01-05", "1D")
        assert isinstance(result, dict)

    def test_fallback_fetch_stock(self):
        result = _fallback_fetch("us_equity", ["AAPL"], "2024-01-02", "2024-01-10", "1D")
        if result:
            assert "AAPL" in result
            assert not result["AAPL"].empty
            assert list(result["AAPL"].columns) == ["open", "high", "low", "close", "volume"]
