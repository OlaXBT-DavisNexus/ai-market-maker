"""Quantitative factor analysis engine — US, HK, and crypto markets.

Implements the core factor framework:
  - Technical factors: trend, momentum, mean-reversion
  - Volatility factors: regime-switching, ATR-scaled
  - Volume factors: divergence, accumulation/distribution
  - Cross-sectional factors: sector rotation, relative strength
  - Risk factors: VaR, drawdown, correlation to macro
  - Regime classification: bull/bear/transition/range-bound
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .data_layer import SECTOR_ETFS

# ── Factor Data Models ───────────────────────────────────────────


@dataclass
class TechnicalFactors:
    rsi_14: float = 50.0
    macd_histogram: float = 0.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    bb_width_pct: float = 0.0
    bb_position: float = 50.0
    adx: float = 25.0
    trend_direction: str = "neutral"
    trend_strength: str = "weak"
    roc_5d: float = 0.0
    roc_20d: float = 0.0
    momentum_regime: str = "neutral"
    z_score: float = 0.0
    distance_to_ma50_pct: float = 0.0
    distance_to_ma200_pct: float = 0.0
    obv_trend: str = "neutral"
    volume_ratio_vs_20d: float = 1.0
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    distance_to_support_pct: float = 0.0
    distance_to_resistance_pct: float = 0.0


@dataclass
class VolatilityFactors:
    atr_14: float = 0.0
    atr_pct: float = 0.0
    historical_vol_20d: float = 0.0
    historical_vol_60d: float = 0.0
    vol_regime: str = "normal"
    hv_contraction_pct: float = 0.0
    max_drawdown_30d: float = 0.0
    max_drawdown_90d: float = 0.0


@dataclass
class RiskFactors:
    var_95_1d: float = 0.0
    cvar_95_1d: float = 0.0
    sharpe_ratio_30d: float = 0.0
    sortino_ratio_30d: float = 0.0
    calmar_ratio_90d: float = 0.0
    beta_to_spy: float = 0.0
    correlation_to_spy: float = 0.0
    skewness_20d: float = 0.0
    kurtosis_20d: float = 0.0


@dataclass
class FactorMatrix:
    symbol: str
    market: str = "us_equity"
    technical: TechnicalFactors = field(default_factory=TechnicalFactors)
    volatility: VolatilityFactors = field(default_factory=VolatilityFactors)
    risk: RiskFactors = field(default_factory=RiskFactors)
    regime: str = "neutral"
    composite_score: float = 50.0
    key_observation: str = ""
    risk_warning: str = ""

    # Trade Read specific fields
    trade_bias: str = "neutral"  # long | short | neutral
    conviction: str = "low"  # high | medium | low
    stop_loss_level: float = 0.0
    target_level: float = 0.0
    risk_reward_ratio: float = 0.0


# ── Regime Detection ──────────────────────────────────────────────


def _detect_regime(close: pd.Series, ma50: pd.Series, ma200: pd.Series, adx: float) -> str:
    """Classify market regime based on moving average alignment and ADX."""
    if len(close) < 50 or ma50.isna().all():
        return "neutral"

    last_close = close.iloc[-1]
    last_ma50 = ma50.iloc[-1]
    last_ma200 = ma200.iloc[-1]

    if pd.isna(last_ma50):
        return "neutral"

    above_50 = last_close > last_ma50 * 1.01
    has_ma200 = not (pd.isna(last_ma200) or last_ma200 <= 0)
    above_200 = last_close > last_ma200 * 1.01 if has_ma200 else False
    ma50_above_200 = last_ma50 > last_ma200 * 1.01 if has_ma200 else True

    trend_strength = "strong" if adx > 30 else "moderate" if adx > 20 else "weak"

    if has_ma200 and above_200 and ma50_above_200:
        return "bull" if trend_strength != "weak" else "range_bound"
    elif has_ma200 and not above_200 and not above_50:
        return "bear" if trend_strength != "weak" else "range_bound"
    elif not has_ma200 and above_50:
        return "bull" if trend_strength != "weak" else "range_bound"
    elif not has_ma200 and not above_50:
        return "bear" if trend_strength != "weak" else "range_bound"

    return "range_bound"


# ── Indicator Computation ────────────────────────────────────────


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    return tr


def compute_technical_factors(
    df: pd.DataFrame,
    symbol: str,
    market: str = "us_equity",
    benchmark_df: Optional[pd.DataFrame] = None,
    use_short_ma: bool = False,
) -> FactorMatrix:
    """Compute the full factor matrix for a single symbol.

    use_short_ma=True: use 20/50 MA instead of 50/200 (for crypto or short-history assets).
    """
    if df.empty or len(df) < 20:
        return FactorMatrix(symbol=symbol, market=market)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    latest = float(close.iloc[-1])

    tech = TechnicalFactors()
    vol_f = VolatilityFactors()
    risk = RiskFactors()

    # ── Moving Averages ──
    ma_long_period = 50 if use_short_ma else 200

    ma_short = close.rolling(20).mean()
    ma_long = (
        close.rolling(50).mean() if len(close) >= 50 else pd.Series(index=close.index, dtype=float)
    )
    ma_extra = (
        close.rolling(ma_long_period).mean()
        if len(close) >= ma_long_period
        else pd.Series(index=close.index, dtype=float)
    )
    ma50 = ma_long

    if len(ma_short) > 0 and not ma_short.isna().all() and not pd.isna(ma_short.iloc[-1]):
        tech.distance_to_ma50_pct = float(((close.iloc[-1] / ma_short.iloc[-1]) - 1) * 100)
        tech.z_score = (
            float((close.iloc[-1] - ma_short.iloc[-1]) / close.rolling(50).std().iloc[-1])
            if close.rolling(50).std().iloc[-1] > 0
            else 0.0
        )

    if len(ma50) > 0 and not ma50.isna().all() and not pd.isna(ma50.iloc[-1]):
        tech.distance_to_ma50_pct = float(((close.iloc[-1] / ma50.iloc[-1]) - 1) * 100)

    if len(ma_extra) > 0 and not ma_extra.isna().all() and not pd.isna(ma_extra.iloc[-1]):
        tech.distance_to_ma200_pct = float(((close.iloc[-1] / ma_extra.iloc[-1]) - 1) * 100)

    # ── RSI ──
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_val = rs.iloc[-1] if len(rs) > 0 else None
    if rsi_val is None or pd.isna(rsi_val) or rsi_val == np.inf:
        tech.rsi_14 = 50.0
    else:
        tech.rsi_14 = float(rsi_val)

    # ── MACD ──
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd_line = ema12 - ema26
    signal = _ema(macd_line, 9)
    if len(macd_line) > 0:
        tech.macd_line = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0.0
        tech.macd_signal = float(signal.iloc[-1]) if not pd.isna(signal.iloc[-1]) else 0.0
        tech.macd_histogram = (
            float((macd_line - signal).iloc[-1])
            if not pd.isna((macd_line - signal).iloc[-1])
            else 0.0
        )

    # ── Bollinger Bands ──
    bb_std = close.rolling(20).std()
    bb_mid = close.rolling(20).mean()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    if not pd.isna(bb_mid.iloc[-1]) and bb_mid.iloc[-1] > 0:
        tech.bb_width_pct = float(((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1]) * 100)
        if bb_upper.iloc[-1] != bb_lower.iloc[-1]:
            tech.bb_position = float(
                ((close.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]))
                * 100
            )

    # ── ADX ──
    tr = _true_range(high, low, close)
    atr = tr.rolling(14).mean()
    vol_f.atr_14 = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) and latest > 0 else 0.0
    vol_f.atr_pct = float((vol_f.atr_14 / latest) * 100) if latest > 0 else 0.0

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(0.0, index=close.index)
    minus_dm = pd.Series(0.0, index=close.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    plus_di = 100 * _ema(plus_dm / tr.replace(0, np.nan), 14)
    minus_di = 100 * _ema(minus_dm / tr.replace(0, np.nan), 14)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx_series = _ema(dx, 14)
    if len(adx_series) > 0 and not pd.isna(adx_series.iloc[-1]) and adx_series.iloc[-1] != np.inf:
        tech.adx = float(adx_series.iloc[-1])
    else:
        tech.adx = 25.0

    if (
        len(plus_di) > 0
        and len(minus_di) > 0
        and not pd.isna(plus_di.iloc[-1])
        and not pd.isna(minus_di.iloc[-1])
    ):
        if plus_di.iloc[-1] > minus_di.iloc[-1]:
            tech.trend_direction = "bullish"
        elif minus_di.iloc[-1] > plus_di.iloc[-1]:
            tech.trend_direction = "bearish"

    tech.trend_strength = "strong" if tech.adx > 30 else "moderate" if tech.adx > 20 else "weak"

    # ── Rate of Change ──
    if len(close) > 5:
        tech.roc_5d = (
            float(((close.iloc[-1] / close.iloc[-6]) - 1) * 100)
            if not pd.isna(close.iloc[-6])
            else 0.0
        )
    if len(close) > 20:
        tech.roc_20d = (
            float(((close.iloc[-1] / close.iloc[-21]) - 1) * 100)
            if not pd.isna(close.iloc[-21])
            else 0.0
        )

    if tech.roc_5d > 3 and tech.roc_20d > 5:
        tech.momentum_regime = "accelerating"
    elif tech.roc_5d < -3 and tech.roc_20d < -5:
        tech.momentum_regime = "decelerating"

    # ── OBV ──
    obv = (volume * (close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)))).cumsum()
    if len(obv) > 10:
        obv_ma5 = obv.rolling(5).mean()
        obv_slope = (
            obv_ma5.iloc[-1] - obv_ma5.iloc[-6]
            if not pd.isna(obv_ma5.iloc[-1]) and not pd.isna(obv_ma5.iloc[-6])
            else 0
        )
        tech.obv_trend = "rising" if obv_slope > 0 else "falling" if obv_slope < 0 else "neutral"

    if len(volume) > 20:
        avg_vol_20d = volume.iloc[-20:].mean()
        tech.volume_ratio_vs_20d = float(volume.iloc[-1] / avg_vol_20d) if avg_vol_20d > 0 else 1.0

    # ── Support / Resistance ──
    lookback = min(60, len(close))
    recent = close.iloc[-lookback:]
    swing_highs = (recent.diff(1) > 0) & (recent.diff(1).shift(-1) < 0)
    swing_lows = (recent.diff(1) < 0) & (recent.diff(1).shift(-1) > 0)
    resistances = recent[swing_highs].values
    supports = recent[swing_lows].values
    if len(resistances) > 0:
        above = resistances[resistances > latest]
        tech.nearest_resistance = float(above.min()) if len(above) > 0 else float(resistances.max())
        tech.distance_to_resistance_pct = float(((tech.nearest_resistance / latest) - 1) * 100)
    if len(supports) > 0:
        below = supports[supports < latest]
        tech.nearest_support = float(below.max()) if len(below) > 0 else float(supports.min())
        tech.distance_to_support_pct = float(((latest / tech.nearest_support) - 1) * 100)

    # ── Volatility Factors ──
    returns = close.pct_change().dropna()
    vol_f.historical_vol_20d = (
        float(returns.tail(20).std() * (252**0.5) * 100) if len(returns) >= 20 else 0.0
    )
    vol_f.historical_vol_60d = (
        float(returns.tail(60).std() * (252**0.5) * 100) if len(returns) >= 60 else 0.0
    )

    if vol_f.historical_vol_60d > 0:
        vol_f.hv_contraction_pct = float(
            ((vol_f.historical_vol_20d / vol_f.historical_vol_60d) - 1) * 100
        )

    hv = vol_f.historical_vol_20d
    if hv > 80:
        vol_f.vol_regime = "extreme"
    elif hv > 45:
        vol_f.vol_regime = "elevated"
    elif hv < 15:
        vol_f.vol_regime = "low"

    # Drawdown
    if len(close) >= 30:
        peak_30 = close.iloc[-30:].cummax()
        vol_f.max_drawdown_30d = float(((close.iloc[-30:] / peak_30 - 1).min()) * 100)
    if len(close) >= 90:
        peak_90 = close.iloc[-90:].cummax()
        vol_f.max_drawdown_90d = float(((close.iloc[-90:] / peak_90 - 1).min()) * 100)

    # ── Risk Factors ──
    if len(returns) >= 20:
        risk.var_95_1d = float(returns.tail(20).quantile(0.05) * 100)
        loss_tail = returns.tail(20)[returns.tail(20) < returns.tail(20).quantile(0.05)]
        risk.cvar_95_1d = float(loss_tail.mean() * 100) if len(loss_tail) > 0 else risk.var_95_1d
        risk.skewness_20d = float(returns.tail(20).skew())
        risk.kurtosis_20d = float(returns.tail(20).kurtosis())

    if len(returns) >= 30:
        r30 = returns.tail(30)
        rf = 0.05 / 365
        excess = r30 - rf
        risk.sharpe_ratio_30d = (
            float((excess.mean() / r30.std()) * (252**0.5)) if r30.std() > 0 else 0.0
        )
        downside = r30[r30 < 0]
        risk.sortino_ratio_30d = (
            float((excess.mean() / downside.std()) * (252**0.5))
            if len(downside) > 0 and downside.std() > 0
            else 0.0
        )

    if len(returns) >= 90:
        r90_ann = float(returns.tail(90).mean() * 252 * 100)
        dd_90 = vol_f.max_drawdown_90d
        risk.calmar_ratio_90d = r90_ann / abs(dd_90) if dd_90 != 0 else 0.0

    # Beta to benchmark
    if benchmark_df is not None and not benchmark_df.empty:
        bm_returns = benchmark_df["close"].pct_change().dropna()
        aligned = pd.concat([returns, bm_returns], axis=1, join="inner").dropna()
        if len(aligned) > 20:
            cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
            bm_var = aligned.iloc[:, 1].var()
            risk.beta_to_spy = float(cov / bm_var) if bm_var > 0 else 0.0
            risk.correlation_to_spy = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    # ── Regime Classification ──
    regime = _detect_regime(close, ma50, ma_extra if len(ma_extra) > 0 else ma50, tech.adx)

    # ── Composite Score ──
    score = 50.0
    if tech.rsi_14 > 60:
        score += 8
    elif tech.rsi_14 < 40:
        score -= 8
    if tech.macd_histogram > 0:
        score += 6
    elif tech.macd_histogram < 0:
        score -= 6
    if tech.trend_direction == "bullish":
        score += 6
    elif tech.trend_direction == "bearish":
        score -= 6
    if tech.obv_trend == "rising":
        score += 4
    elif tech.obv_trend == "falling":
        score -= 4
    if regime == "bull":
        score += 10
    elif regime == "bear":
        score -= 10
    elif regime == "transition":
        score -= 3
    if abs(tech.z_score) > 2 and tech.z_score < 0:
        score += 5
    elif abs(tech.z_score) > 2 and tech.z_score > 0:
        score -= 5

    score = max(0, min(100, score))

    # ── Trade Read fields ──
    trade_bias = "long" if score > 60 else "short" if score < 40 else "neutral"
    conviction = "high" if abs(score - 50) > 25 else "medium" if abs(score - 50) > 15 else "low"
    stop_loss = 0.0
    target = 0.0
    if trade_bias == "long":
        stop_loss = tech.nearest_support if tech.nearest_support > 0 else latest * 0.95
        target = tech.nearest_resistance if tech.nearest_resistance > 0 else latest * 1.05
    elif trade_bias == "short":
        stop_loss = tech.nearest_resistance if tech.nearest_resistance > 0 else latest * 1.05
        target = tech.nearest_support if tech.nearest_support > 0 else latest * 0.95

    rrr = abs((target - latest) / (stop_loss - latest)) if stop_loss != latest else 0.0

    # ── Narrative Hooks ──
    observations = []
    warnings = []

    if tech.rsi_14 > 70:
        observations.append(f"RSI at {tech.rsi_14:.0f} — overbought, pullback likely")
        warnings.append("Overbought RSI — 70+ suggests short-term exhaustion")
    elif tech.rsi_14 < 30:
        observations.append(f"RSI at {tech.rsi_14:.0f} — oversold bounce candidate")
    if tech.adx > 40:
        observations.append(f"Strong trend (ADX {tech.adx:.0f}) — momentum strategies favored")
    if tech.adx < 15:
        observations.append(
            f"Low ADX ({tech.adx:.0f}) — choppy/range-bound, mean reversion preferred"
        )
    if vol_f.vol_regime in ("elevated", "extreme"):
        warnings.append(f"Elevated vol ({hv:.0f}% ann) — reduce sizing, widen stops")
    if vol_f.hv_contraction_pct < -20:
        observations.append(
            f"Vol compressing ({vol_f.hv_contraction_pct:.0f}% vs 60d) — breakout setup"
        )

    return FactorMatrix(
        symbol=symbol,
        market=market,
        technical=tech,
        volatility=vol_f,
        risk=risk,
        regime=regime,
        composite_score=round(score, 1),
        key_observation=" | ".join(observations[:3]) if observations else "",
        risk_warning=" | ".join(warnings[:3]) if warnings else "",
        trade_bias=trade_bias,
        conviction=conviction,
        stop_loss_level=round(stop_loss, 2) if stop_loss > 0 else 0.0,
        target_level=round(target, 2) if target > 0 else 0.0,
        risk_reward_ratio=round(rrr, 2),
    )


# ── Sector Rotation ──────────────────────────────────────────────


@dataclass
class SectorRotation:
    ranking: List[Tuple[str, str, float, str]]
    top_3: List[str]
    bottom_3: List[str]
    rotation_direction: str
    concentration_risk: str


def analyze_sector_rotation(sector_dfs: Dict[str, pd.DataFrame]) -> Optional[SectorRotation]:
    scores: List[Tuple[str, str, float, str]] = []
    for sym, df in sector_dfs.items():
        if df.empty or len(df) < 30:
            continue
        close = df["close"]
        ret_30d = (
            float(((close.iloc[-1] / close.iloc[-30]) - 1) * 100)
            if not pd.isna(close.iloc[-30])
            else 0.0
        )
        ma50 = (
            close.rolling(50).mean()
            if len(close) >= 50
            else pd.Series(index=close.index, dtype=float)
        )
        if len(ma50) > 0 and not ma50.isna().all() and not pd.isna(ma50.iloc[-1]):
            sector_regime = (
                "bull"
                if close.iloc[-1] > ma50.iloc[-1]
                else "bear"
                if close.iloc[-1] < ma50.iloc[-1] * 0.95
                else "neutral"
            )
        else:
            sector_regime = "neutral"
        name = SECTOR_ETFS.get(sym, sym)
        scores.append((sym, name, ret_30d, sector_regime))

    if not scores:
        return None

    scores.sort(key=lambda x: x[2], reverse=True)
    top_3 = [f"{s[0]} ({s[1]})" for s in scores[:3]]
    bottom_3 = [f"{s[0]} ({s[1]})" for s in scores[-3:]]

    defensive = ["XLP", "XLU", "XLV"]
    cyclical = ["XLY", "XLE", "XLI", "XLF", "XLK"]
    def_perf = sum(s[2] for s in scores if s[0] in defensive) / max(
        len([s for s in scores if s[0] in defensive]), 1
    )
    cyc_perf = sum(s[2] for s in scores if s[0] in cyclical) / max(
        len([s for s in scores if s[0] in cyclical]), 1
    )

    if cyc_perf > def_perf + 3:
        rotation = "cyclical (risk-on)"
    elif def_perf > cyc_perf + 3:
        rotation = "defensive (risk-off)"
    else:
        rotation = "mixed / no clear rotation"

    return SectorRotation(
        ranking=scores,
        top_3=top_3,
        bottom_3=bottom_3,
        rotation_direction=rotation,
        concentration_risk="high" if top_3[0].startswith("XLK") else "moderate",
    )
