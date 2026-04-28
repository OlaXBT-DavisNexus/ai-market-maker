"""Quantitative factor analysis engine for the research pipeline.

Implements the core factor framework used by AIMM:
  - Technical factors: trend, momentum, mean-reversion
  - Volatility factors: regime-switching, ATR-scaled
  - Volume factors: divergence, accumulation/distribution
  - Cross-sectional factors: sector rotation, relative strength
  - Risk factors: VaR, drawdown, correlation to macro
  - Regime classification: bull/bear/transition/range-bound

Each factor is computed independently then aggregated into a factor
matrix that the writer uses as the analytical backbone.
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
    bb_width_pct: float = 0.0  # (upper - lower) / mid
    bb_position: float = 50.0  # 0=at lower, 100=at upper
    adx: float = 25.0
    trend_direction: str = "neutral"  # bullish | bearish | neutral
    trend_strength: str = "weak"  # strong | moderate | weak

    # Momentum
    roc_5d: float = 0.0
    roc_20d: float = 0.0
    momentum_regime: str = "neutral"  # accelerating | decelerating | neutral

    # Mean reversion
    z_score: float = 0.0  # distance from 50-day MA in std
    distance_to_ma50_pct: float = 0.0
    distance_to_ma200_pct: float = 0.0

    # Volume
    obv_trend: str = "neutral"  # rising | falling | neutral
    volume_ratio_vs_20d: float = 1.0

    # Support / Resistance
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    distance_to_support_pct: float = 0.0
    distance_to_resistance_pct: float = 0.0


@dataclass
class VolatilityFactors:
    atr_14: float = 0.0
    atr_pct: float = 0.0  # ATR as % of price
    historical_vol_20d: float = 0.0
    historical_vol_60d: float = 0.0
    vol_regime: str = "normal"  # low | normal | elevated | extreme
    hv_contraction_pct: float = 0.0  # negative = compressing vol
    max_drawdown_30d: float = 0.0
    max_drawdown_90d: float = 0.0


@dataclass
class RiskFactors:
    var_95_1d: float = 0.0  # 95% VaR, 1-day horizon
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
    technical: TechnicalFactors = field(default_factory=TechnicalFactors)
    volatility: VolatilityFactors = field(default_factory=VolatilityFactors)
    risk: RiskFactors = field(default_factory=RiskFactors)
    regime: str = "neutral"  # bull | bear | transition | range_bound
    composite_score: float = 50.0  # 0-100 where >65 = bullish, <35 = bearish

    # Narrative hooks extracted by factor analysis
    key_observation: str = ""
    risk_warning: str = ""


# ── Regime Detection ──────────────────────────────────────────────


def _detect_regime(close: pd.Series, ma50: pd.Series, ma200: pd.Series, adx: float) -> str:
    """Classify market regime based on moving average alignment and ADX."""
    if len(close) < 200 or ma50.isna().all() or ma200.isna().all():
        return "neutral"

    last_close = close.iloc[-1]
    last_ma50 = ma50.iloc[-1]
    last_ma200 = ma200.iloc[-1]

    if pd.isna(last_ma50) or pd.isna(last_ma200) or last_ma200 <= 0:
        return "neutral"

    above_50 = last_close > last_ma50 * 1.01
    above_200 = last_close > last_ma200 * 1.01
    ma50_above_200 = last_ma50 > last_ma200 * 1.01
    crossover_recent = False

    # Detect crossovers in last 5 bars
    if len(ma50) >= 5 and len(ma200) >= 5:
        for i in range(-5, 0):
            if abs(i) > len(ma50) or abs(i) > len(ma200):
                continue
            prev_50 = ma50.iloc[i - 1] if i - 1 >= len(ma50) else ma50.iloc[i]
            prev_200 = ma200.iloc[i - 1] if i - 1 >= len(ma200) else ma200.iloc[i]
            if (prev_50 <= prev_200 and ma50.iloc[i] > ma200.iloc[i]) or (
                prev_50 >= prev_200 and ma50.iloc[i] < ma200.iloc[i]
            ):
                crossover_recent = True
                break

    trend_strength = "strong" if adx > 30 else "moderate" if adx > 20 else "weak"

    if above_200 and ma50_above_200:
        return "bull" if trend_strength != "weak" else "range_bound"
    elif not above_200 and not above_50:
        return "bear" if trend_strength != "weak" else "range_bound"
    elif crossover_recent:
        return "transition"
    elif not ma50_above_200 and above_200:
        return "transition"

    return "range_bound"


# ── Technical Indicator Computation ────────────────────────────────


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def compute_technical_factors(
    df: pd.DataFrame,
    symbol: str,
    spy_df: Optional[pd.DataFrame] = None,
) -> FactorMatrix:
    """Compute the full factor matrix for a single symbol."""
    if df.empty or len(df) < 30:
        return FactorMatrix(symbol=symbol)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    latest = float(close.iloc[-1])

    tech = TechnicalFactors()
    vol_f = VolatilityFactors()
    risk = RiskFactors()

    # ── Moving Averages ──
    ma20 = close.rolling(20).mean()
    ma50 = (
        close.rolling(50).mean() if len(close) >= 50 else pd.Series(index=close.index, dtype=float)
    )
    ma200 = (
        close.rolling(200).mean()
        if len(close) >= 200
        else pd.Series(index=close.index, dtype=float)
    )

    if not ma20.isna().all():
        tech.distance_to_ma50_pct = (
            float(((close.iloc[-1] / ma20.iloc[-1]) - 1) * 100)
            if not pd.isna(ma20.iloc[-1])
            else 0.0
        )

    if len(ma50) > 0 and not ma50.isna().all() and not pd.isna(ma50.iloc[-1]):
        tech.distance_to_ma50_pct = float(((close.iloc[-1] / ma50.iloc[-1]) - 1) * 100)
        tech.z_score = (
            float((close.iloc[-1] - ma50.iloc[-1]) / close.rolling(50).std().iloc[-1])
            if close.rolling(50).std().iloc[-1] > 0
            else 0.0
        )

    if len(ma200) > 0 and not ma200.isna().all() and not pd.isna(ma200.iloc[-1]):
        tech.distance_to_ma200_pct = float(((close.iloc[-1] / ma200.iloc[-1]) - 1) * 100)

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
    bb_mid = ma20
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

    # Directional movement
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

    # Trend direction from DMI
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

    # Momentum regime
    if tech.roc_5d > 3 and tech.roc_20d > 5:
        tech.momentum_regime = "accelerating"
    elif tech.roc_5d < -3 and tech.roc_20d < -5:
        tech.momentum_regime = "decelerating"

    # ── OBV (On-Balance Volume) ──
    obv = (volume * (close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)))).cumsum()
    if len(obv) > 10:
        obv_ma5 = obv.rolling(5).mean()
        obv_slope = (
            obv_ma5.iloc[-1] - obv_ma5.iloc[-6]
            if not pd.isna(obv_ma5.iloc[-1]) and not pd.isna(obv_ma5.iloc[-6])
            else 0
        )
        tech.obv_trend = "rising" if obv_slope > 0 else "falling" if obv_slope < 0 else "neutral"

    # Volume ratio
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

    # Vol contraction Vs 60d
    if vol_f.historical_vol_60d > 0:
        vol_f.hv_contraction_pct = float(
            ((vol_f.historical_vol_20d / vol_f.historical_vol_60d) - 1) * 100
        )

    # Vol regime
    hv = vol_f.historical_vol_20d
    if hv > 60:
        vol_f.vol_regime = "extreme"
    elif hv > 40:
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

    # Sharpe / Sortino (30-day)
    if len(returns) >= 30:
        r30 = returns.tail(30)
        rf = 0.05 / 365  # daily risk-free approximation
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

    # Calmar (90-day)
    if len(returns) >= 90:
        r90_ann = float(returns.tail(90).mean() * 252 * 100)
        dd_90 = vol_f.max_drawdown_90d
        risk.calmar_ratio_90d = r90_ann / abs(dd_90) if dd_90 != 0 else 0.0

    # Beta to SPY
    if spy_df is not None and not spy_df.empty:
        spy_returns = spy_df["close"].pct_change().dropna()
        aligned = pd.concat([returns, spy_returns], axis=1, join="inner").dropna()
        if len(aligned) > 20:
            cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
            spy_var = aligned.iloc[:, 1].var()
            risk.beta_to_spy = float(cov / spy_var) if spy_var > 0 else 0.0
            risk.correlation_to_spy = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    # ── Regime Classification ──
    regime = _detect_regime(close, ma50, ma200, tech.adx)

    # ── Composite Score ──
    score = 50.0
    # RSI contribution
    if tech.rsi_14 > 60:
        score += 8
    elif tech.rsi_14 < 40:
        score -= 8
    # MACD contribution
    if tech.macd_histogram > 0 and float(macd_line.iloc[-1] if len(macd_line) > 0 else 0) > 0:
        score += 6
    elif tech.macd_histogram < 0:
        score -= 6
    # Trend contribution
    if tech.trend_direction == "bullish":
        score += 6
    elif tech.trend_direction == "bearish":
        score -= 6
    # Volume contribution
    if tech.obv_trend == "rising":
        score += 4
    elif tech.obv_trend == "falling":
        score -= 4
    # Regime contribution
    if regime == "bull":
        score += 10
    elif regime == "bear":
        score -= 10
    elif regime == "transition":
        score -= 3
    # Mean reversion
    if abs(tech.z_score) > 2 and tech.z_score < 0 and tech.trend_direction == "bearish":
        score += 5  # oversold bounce
    elif abs(tech.z_score) > 2 and tech.z_score > 0:
        score -= 5  # overbought pullback

    score = max(0, min(100, score))

    # ── Narrative Hooks ──
    observations = []
    warnings = []

    if tech.rsi_14 > 70:
        observations.append(f"RSI at {tech.rsi_14:.0f} — overbought territory, due for a pullback")
        warnings.append("Overbought RSI — 70+ suggests short-term exhaustion")
    elif tech.rsi_14 < 30:
        observations.append(f"RSI at {tech.rsi_14:.0f} — oversold bounce candidate")
    if tech.adx > 40:
        observations.append(
            f"Strong trend detected (ADX {tech.adx:.0f}) — trending conditions favor momentum strategies"
        )
    if tech.adx < 15:
        observations.append(
            f"Low ADX ({tech.adx:.0f}) — choppy / range-bound conditions, mean reversion preferred"
        )
    if vol_f.vol_regime == "elevated" or vol_f.vol_regime == "extreme":
        warnings.append(
            f"Elevated volatility ({hv:.0f}% annualized) — reduce position sizing, widen stops"
        )
    if vol_f.hv_contraction_pct < -20:
        observations.append(
            f"Volatility compressing ({vol_f.hv_contraction_pct:.0f}% vs 60d) — breakout setup forming"
        )

    factor_matrix = FactorMatrix(
        symbol=symbol,
        technical=tech,
        volatility=vol_f,
        risk=risk,
        regime=regime,
        composite_score=round(score, 1),
        key_observation=" | ".join(observations[:3]) if observations else "",
        risk_warning=" | ".join(warnings[:3]) if warnings else "",
    )
    return factor_matrix


# ── Sector Rotation Analysis ──────────────────────────────────────


@dataclass
class SectorRotation:
    """Cross-sectional sector rotation snapshot."""

    ranking: List[Tuple[str, str, float, str]]  # (ticker, name, 30d_return, regime)
    top_3: List[str]
    bottom_3: List[str]
    rotation_direction: str  # defensive -> cyclical or cyclical -> defensive
    concentration_risk: str  # high | moderate | low


def analyze_sector_rotation(sector_dfs: Dict[str, pd.DataFrame]) -> Optional[SectorRotation]:
    """Score each sector and detect rotation patterns."""
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

        # Quick regime
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

    # Determine rotation direction
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
        concentration_risk="high"
        if (top_3[0].split()[0] if top_3 else "") in ["XLK", "SMH"]
        else "moderate",
    )
