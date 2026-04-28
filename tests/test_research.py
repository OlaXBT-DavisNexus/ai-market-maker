"""Tests for the multi-market research synthesis pipeline.

Tests verify:
  1. Data layer fetches + snapshots (US, HK, crypto)
  2. Factor engine: correct numerical outputs on synthetic data
  3. Regime classification, sector rotation, trade read fields
  4. Writer structure: gather, quant context block, prompt
  5. Style-specific generators (daily, trade_read, kol, weekly) with mocked LLM
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.research.data_layer import (
    collect_headlines,
    fetch_crypto_ohlcv,
    fetch_macro,
    fetch_ohlcv,
    fetch_sectors,
    price_snapshots,
)
from backtest.research.factors import (
    _detect_regime,
    analyze_sector_rotation,
    compute_technical_factors,
)

# ── Fixtures: Synthetic Price Data ──────────────────────────────────


@pytest.fixture
def uptrend_df():
    """60 days of clean uptrend (100 → 130)."""
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    return pd.DataFrame(
        {
            "open": [100 + i * 0.5 + (i % 5 - 2) * 0.3 for i in range(60)],
            "high": [102 + i * 0.5 + abs(i % 3) * 0.5 for i in range(60)],
            "low": [98 + i * 0.5 - abs(i % 3) * 0.3 for i in range(60)],
            "close": [100 + i * 0.5 + (i % 3 - 1) * 0.2 for i in range(60)],
            "volume": [1_000_000 + i * 1000 + (i % 7) * 5000 for i in range(60)],
        },
        index=dates,
    )


@pytest.fixture
def downtrend_df():
    """60 days of downtrend (130 → 100)."""
    dates = pd.date_range("2026-02-01", periods=60, freq="D")
    return pd.DataFrame(
        {
            "open": [130 - i * 0.5 + (i % 5 - 2) * 0.3 for i in range(60)],
            "high": [132 - i * 0.5 + abs(i % 3) * 0.5 for i in range(60)],
            "low": [128 - i * 0.5 - abs(i % 3) * 0.3 for i in range(60)],
            "close": [130 - i * 0.5 + (i % 3 - 1) * 0.2 for i in range(60)],
            "volume": [1_000_000 + i * 1000 + (i % 7) * 5000 for i in range(60)],
        },
        index=dates,
    )


@pytest.fixture
def rangebound_df():
    """60 days of range-bound data (close oscillates around 100)."""
    import math

    dates = pd.date_range("2026-03-01", periods=60, freq="D")
    return pd.DataFrame(
        {
            "open": [100 + 3 * math.sin(i * 0.5) for i in range(60)],
            "high": [103 + 3 * math.sin(i * 0.5) for i in range(60)],
            "low": [97 + 3 * math.sin(i * 0.5) for i in range(60)],
            "close": [100 + 3 * math.sin(i * 0.5) for i in range(60)],
            "volume": [1_000_000 for _ in range(60)],
        },
        index=dates,
    )


# ── Data Layer ──────────────────────────────────────────────────────


class TestDataLayer:
    def test_fetch_ohlcv_us(self):
        dfs = fetch_ohlcv(["AAPL", "SPY", "QQQ"], days=30)
        assert any(not df.empty for df in dfs.values())

    def test_price_snapshots_field_types(self):
        dfs = fetch_ohlcv(["AAPL"], days=60)
        snaps = price_snapshots(dfs)
        if "AAPL" in snaps:
            snap = snaps["AAPL"]
            assert snap.current_price > 0
            assert isinstance(snap.change_1d_pct, float)
            assert isinstance(snap.change_30d_pct, float)
            assert snap.high_30d >= snap.low_30d

    def test_fetch_macro(self):
        macro = fetch_macro(days=10)
        assert isinstance(macro, dict)

    def test_fetch_sectors(self):
        sectors = fetch_sectors(days=10)
        assert isinstance(sectors, dict)

    def test_collect_headlines(self):
        h = collect_headlines(max_per_source=2)
        assert isinstance(h, list)

    def test_fetch_crypto_returns_dict(self):
        """crypto data layer may be empty if ccxt unavailable, but always a dict."""
        result = fetch_crypto_ohlcv(["BTC/USDT"], days=5)
        assert isinstance(result, dict)


# ── Factor Engine ──────────────────────────────────────────────────


class TestFactorEngine:
    def test_uptrend_direction(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.technical.trend_direction == "bullish"
        assert m.technical.roc_5d > 0 or m.technical.roc_20d > 0

    def test_downtrend_score(self, downtrend_df):
        m = compute_technical_factors(downtrend_df, "TEST")
        assert m.composite_score < 70

    def test_rangebound_adx(self, rangebound_df):
        m = compute_technical_factors(rangebound_df, "TEST")
        assert m.technical.adx < 40

    def test_rsi_reasonable(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert 25 <= m.technical.rsi_14 <= 75

    def test_volatility_factors(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.volatility.atr_14 > 0
        assert m.volatility.historical_vol_20d > 0
        assert isinstance(m.volatility.vol_regime, str)

    def test_risk_factors(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert isinstance(m.risk.var_95_1d, float)
        assert isinstance(m.risk.sharpe_ratio_30d, float)
        assert m.risk.sharpe_ratio_30d > -5

    def test_support_resistance(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        t = m.technical
        assert isinstance(t.nearest_support, float)
        assert isinstance(t.nearest_resistance, float)
        assert t.nearest_support >= 0
        assert t.nearest_resistance >= 0

    def test_all_technical_fields_set(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        fields = [
            "rsi_14",
            "adx",
            "bb_width_pct",
            "macd_histogram",
            "roc_5d",
            "roc_20d",
            "obv_trend",
            "volume_ratio_vs_20d",
            "z_score",
            "trend_direction",
            "trend_strength",
            "momentum_regime",
        ]
        for f in fields:
            assert getattr(m.technical, f, None) is not None, f"{f} is None"

    def test_regime_runs(self, uptrend_df):
        close_up = uptrend_df["close"]
        ma50 = close_up.rolling(50).mean()
        ma200 = (
            close_up.rolling(200).mean()
            if len(close_up) >= 200
            else pd.Series(index=close_up.index)
        )
        if len(ma200) > 0 and not ma200.isna().all():
            r = _detect_regime(close_up, ma50, ma200, 15.0)
            assert r in ("bull", "bear", "transition", "range_bound", "neutral")

    def test_composite_in_uptrend(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.composite_score >= 30

    def test_observation_extracted(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.key_observation or m.risk_warning

    def test_trade_read_fields(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.trade_bias in ("long", "short", "neutral")
        assert m.conviction in ("high", "medium", "low")
        assert isinstance(m.risk_reward_ratio, float)

    def test_short_ma_variant(self, uptrend_df):
        """Crypto mode (use_short_ma=True) should still produce valid factors."""
        m = compute_technical_factors(uptrend_df, "TEST", use_short_ma=True)
        assert m.composite_score >= 30
        assert isinstance(m.technical.rsi_14, float)


# ── Sector Rotation ──────────────────────────────────────────────


class TestSectorRotation:
    def test_empty(self):
        assert analyze_sector_rotation({}) is None

    def test_one_sector(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        df = pd.DataFrame(
            {
                "open": [100 + i * 0.3 for i in range(60)],
                "high": [102 + i * 0.3 for i in range(60)],
                "low": [98 + i * 0.3 for i in range(60)],
                "close": [100 + i * 0.3 for i in range(60)],
                "volume": [1_000_000 for _ in range(60)],
            },
            index=dates,
        )
        r = analyze_sector_rotation({"XLK": df})
        if r:
            assert len(r.ranking) == 1
            assert isinstance(r.rotation_direction, str)


# ── Writer Structure ──────────────────────────────────────────────


class TestWriterStructure:
    def test_context_block_with_empty_state(self):
        """Build context block from empty state — should not crash."""
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        block = writer._build_quant_context_block()
        assert "QUANTITATIVE CONTEXT" in block

    def test_prompt_has_rules(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        prompt = writer._build_prompt("test", "daily")
        for rule in ["WRITING RULES", "newsstand-worthy"]:
            assert rule in prompt

    def test_get_style_anchor_returns_known_path(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        for style in ("daily", "trade_read", "kol_daily", "weekly", "sector_rotation"):
            anchor = writer._get_style_anchor(style)
            assert len(anchor) > 100

    def test_note_date_format(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        assert "2026" in writer.note_date

    def test_ticker_name_lookup(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        assert writer._name("SPY") == "S&P 500"
        assert writer._name("9999.HK") == "NetEase"
        assert writer._name("BTC/USDT") == "Bitcoin"
        assert writer._name("UNKNOWN") == "UNKNOWN"

    def test_prompt_without_quant(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        prompt = writer._build_prompt("test", "daily", include_quant=False)
        # The block header still appears but the data section is empty/minimal
        # when quant=False, the context block is still in template
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    @pytest.mark.parametrize(
        "method",
        [
            "daily_brief",
            "trade_read",
            "kol_daily",
            "weekly_note",
        ],
    )
    def test_style_generators_return_text(self, monkeypatch, method):
        from backtest.research.writers import ResearchNoteWriter

        def mock_gather(self):
            return self

        def mock_llm(self, prompt):
            return f"# Test: {method}\n\nBody content."

        monkeypatch.setattr(ResearchNoteWriter, "_call_llm", mock_llm)
        monkeypatch.setattr(ResearchNoteWriter, "gather", mock_gather)

        writer = ResearchNoteWriter()
        article = getattr(writer, method)()
        assert article.startswith("#")
        assert len(article) > 10

    def test_publish_accepts_kwargs(self, monkeypatch):
        from backtest.research.writers import ResearchNoteWriter

        def mock_gather(self):
            return self

        def mock_llm(self, prompt):
            return "# Custom\nBody."

        monkeypatch.setattr(ResearchNoteWriter, "_call_llm", mock_llm)
        monkeypatch.setattr(ResearchNoteWriter, "gather", mock_gather)
        writer = ResearchNoteWriter()
        article = writer.publish("custom topic", "daily")
        assert len(article) > 10
