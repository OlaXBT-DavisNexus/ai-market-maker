"""Tests for multi-persona research synthesis pipeline.

Tests cover:
  1. Data layer + snapshots (US, HK, crypto)
  2. Factor engine (15 tests, synthetic data)
  3. Sector rotation
  4. Writer: all 8 personas generate correctly structured output
  5. Persona definitions are valid
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

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def uptrend_df():
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


# ── Data Layer ──────────────────────────────────────────────────


class TestDataLayer:
    def test_fetch_ohlcv_us(self):
        dfs = fetch_ohlcv(["AAPL", "SPY", "QQQ"], days=30)
        assert any(not df.empty for df in dfs.values())

    def test_price_snapshots_types(self):
        dfs = fetch_ohlcv(["AAPL"], days=60)
        snaps = price_snapshots(dfs)
        if "AAPL" in snaps:
            snap = snaps["AAPL"]
            assert snap.current_price > 0
            assert isinstance(snap.change_1d_pct, float)
            assert snap.high_30d >= snap.low_30d

    def test_macro(self):
        assert isinstance(fetch_macro(days=5), dict)

    def test_sectors(self):
        assert isinstance(fetch_sectors(days=5), dict)

    def test_headlines(self):
        assert isinstance(collect_headlines(max_per_source=2), list)

    def test_crypto(self):
        assert isinstance(fetch_crypto_ohlcv(["BTC/USDT"], days=3), dict)


# ── Factor Engine ──────────────────────────────────────────────


class TestFactorEngine:
    def test_uptrend_bullish(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.technical.trend_direction == "bullish"

    def test_downtrend_score(self, downtrend_df):
        m = compute_technical_factors(downtrend_df, "TEST")
        assert m.composite_score < 70

    def test_rangebound_adx(self, rangebound_df):
        m = compute_technical_factors(rangebound_df, "TEST")
        assert m.technical.adx < 40

    def test_rsi_reasonable(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert 25 <= m.technical.rsi_14 <= 75

    def test_volatility(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.volatility.atr_14 > 0
        assert m.volatility.historical_vol_20d > 0

    def test_risk(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert isinstance(m.risk.var_95_1d, float)
        assert m.risk.sharpe_ratio_30d > -5

    def test_support_resistance_type(self, uptrend_df):
        t = compute_technical_factors(uptrend_df, "TEST").technical
        assert isinstance(t.nearest_support, float)
        assert isinstance(t.nearest_resistance, float)
        assert t.nearest_support >= 0

    def test_all_fields_set(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        for f in [
            "rsi_14",
            "adx",
            "bb_width_pct",
            "macd_histogram",
            "roc_5d",
            "roc_20d",
            "obv_trend",
            "z_score",
            "trend_direction",
            "momentum_regime",
        ]:
            assert getattr(m.technical, f, None) is not None, f"{f} missing"

    def test_regime_runs(self, uptrend_df):
        c = uptrend_df["close"]
        r = _detect_regime(c, c.rolling(50).mean(), pd.Series(index=c.index), 15.0)
        assert r in ("bull", "bear", "transition", "range_bound", "neutral")

    def test_composite_uptrend(self, uptrend_df):
        assert compute_technical_factors(uptrend_df, "TEST").composite_score >= 30

    def test_observation(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.key_observation or m.risk_warning

    def test_trade_read(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST")
        assert m.trade_bias in ("long", "short", "neutral")
        assert m.conviction in ("high", "medium", "low")
        assert isinstance(m.risk_reward_ratio, float)

    def test_short_ma(self, uptrend_df):
        m = compute_technical_factors(uptrend_df, "TEST", use_short_ma=True)
        assert m.composite_score >= 30


# ── Sector Rotation ────────────────────────────────────────────


class TestSectorRotation:
    def test_empty(self):
        assert analyze_sector_rotation({}) is None

    def test_one(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        df = pd.DataFrame(
            {
                "open": [100] * 60,
                "high": [102] * 60,
                "low": [98] * 60,
                "close": [100 + i * 0.3 for i in range(60)],
                "volume": [1_000_000] * 60,
            },
            index=dates,
        )
        r = analyze_sector_rotation({"XLK": df})
        if r:
            assert len(r.ranking) == 1


# ── Persona Definitions ────────────────────────────────────────


class TestPersonaDefinitions:
    def test_all_personas_have_required_fields(self):
        from backtest.research.writers import PERSONAS

        for _pid, p in PERSONAS.items():
            assert p.id
            assert len(p.name) > 3
            assert len(p.tagline) > 5
            assert len(p.structure) > 30
            assert len(p.tone_guide) > 20
            assert len(p.analytical_focus) > 10

    def test_data_snapshot_has_different_structure(self):
        from backtest.research.writers import PERSONAS

        p = PERSONAS["data_snapshot"]
        # data_snapshot name explicitly says "no LLM"
        assert "純數據" in p.name or "no LLM" in p.name

    def test_morning_call_has_timestamps(self):
        from backtest.research.writers import PERSONAS

        mc = PERSONAS["morning_call"]
        # morning_call name says "video script"
        assert "視頻" in mc.name or "video" in mc.name.lower()
        assert "[0:15]" in mc.structure

    def test_persona_system_prompt_includes_rules(self):
        from backtest.research.writers import PERSONAS

        for _pid, p in PERSONAS.items():
            sp = p.system_prompt()
            assert "不可協商" in sp or "WRITING RULES" in sp
            assert "標題要像" in sp or "newsstand-worthy" in sp
            assert "總結" in sp or "Bottom Line" in sp

    def test_list_personas(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        personas = writer.list_personas()
        assert len(personas) == 8
        assert "macro_quant" in personas
        assert "data_snapshot" in personas

    def test_invalid_persona_raises(self):
        from backtest.research.writers import ResearchNoteWriter

        writer = ResearchNoteWriter()
        with pytest.raises(ValueError, match="未知角色"):
            writer.publish("nonexistent")

    def test_publish_all_personas_mocked(self, monkeypatch):
        from backtest.research.writers import PERSONAS, ResearchNoteWriter

        def mock_gather(self):
            return self

        def mock_llm(self, prompt):
            return "# Test Title\n\nBody content."

        monkeypatch.setattr(ResearchNoteWriter, "_call_llm", mock_llm)
        monkeypatch.setattr(ResearchNoteWriter, "gather", mock_gather)

        writer = ResearchNoteWriter()
        # data_snapshot doesn't need LLM
        for pid in PERSONAS:
            if pid == "data_snapshot":
                continue
            article = writer.publish(pid)
            assert article.startswith("#")
            assert len(article) > 10

    def test_data_snapshot_no_llm(self, monkeypatch):
        """DataSnapshot should work without calling LLM at all."""
        from backtest.research.writers import ResearchNoteWriter

        called = [False]

        def mock_gather(self):
            called[0] = True
            return self

        monkeypatch.setattr(ResearchNoteWriter, "gather", mock_gather)

        writer = ResearchNoteWriter()
        result = writer.publish("data_snapshot")
        # Should get some output even with empty state
        assert "DATA SNAPSHOT" in result
