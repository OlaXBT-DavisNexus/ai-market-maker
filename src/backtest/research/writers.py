"""Research note writer — transforms factor data + news into hedge fund prose.

This is the crown jewel. It takes quantitative factor matrices, sector
rotation data, macro context, and news headlines, then synthesises them
into a published research note that reads like a sell-side strategist
or a PM's morning memo — not like an AI dump.

Writing principles:
  1. Data-first. Every claim backed by a number.
  2. Narrative arc: Hook → Context → Deep Dive → Catalysts → Risk → Positioning
  3. Human registry: opinions, forecasts, specific price targets
  4. No AI filler: zero "based on the data", zero "it is important to note"
  5. Professional register: short sentences, emphatic structure, Wall Street prose
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .data_layer import (
    Headline,
    PriceSnapshot,
    collect_headlines,
    fetch_macro,
    fetch_ohlcv,
    fetch_sectors,
    price_snapshots,
)
from .factors import (
    FactorMatrix,
    SectorRotation,
    analyze_sector_rotation,
    compute_technical_factors,
)

DEFAULT_MODEL = os.environ.get("RESEARCH_LLM_MODEL", "deepseek/deepseek-chat")


class ResearchNoteWriter:
    """Master synthesizer: raw data → quantified analysis → publishable research note."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or ""

        # Symbols the note will cover
        self.cover_symbols: List[str] = []
        self.factor_matrices: Dict[str, FactorMatrix] = {}
        self.price_snapshots: Dict[str, PriceSnapshot] = {}
        self.sector_rotation: Optional[SectorRotation] = None
        self.macro_data: Dict[str, Any] = {}
        self.headlines: List[Headline] = []
        self.note_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def gather(self) -> "ResearchNoteWriter":
        """Collect all data needed for a research note."""
        # Core coverage
        self.cover_symbols = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL"]
        dfs = fetch_ohlcv(self.cover_symbols, market="us_equity", days=365)
        self.price_snapshots = price_snapshots(dfs, market="us_equity")

        # Factor analysis for each symbol
        spy_df = dfs.get("SPY")
        for sym in self.cover_symbols:
            df = dfs.get(sym)
            if df is not None and not df.empty:
                self.factor_matrices[sym] = compute_technical_factors(df, sym, spy_df=spy_df)

        # Macro
        macro_dfs = fetch_macro(days=60)
        for sym, df in macro_dfs.items():
            if not df.empty:
                close = df["close"]
                self.macro_data[sym] = {
                    "price": float(close.iloc[-1]),
                    "change_30d": float(((close.iloc[-1] / close.iloc[-30]) - 1) * 100)
                    if len(close) >= 30
                    else 0.0,
                }

        # Sector rotation
        sector_dfs = fetch_sectors(days=60)
        self.sector_rotation = analyze_sector_rotation(sector_dfs)

        # News
        self.headlines = collect_headlines(max_per_source=3)

        return self

    def _build_quant_context_block(self) -> str:
        """Build the full quantitative context block for the LLM prompt.

        This is structured data, not prose — the LLM writes the final
        article using this as raw material.
        """
        parts: List[str] = ["## QUANTITATIVE CONTEXT", ""]

        # Market overview
        spy_snap = self.price_snapshots.get("SPY")
        if spy_snap:
            spy_mat = self.factor_matrices.get("SPY")
            parts.append("### Market Overview")
            parts.append(
                f"- SPY: {spy_snap.current_price:.2f} (1d: {spy_snap.change_1d_pct:+.2f}% | 7d: {spy_snap.change_7d_pct:+.2f}% | 30d: {spy_snap.change_30d_pct:+.2f}%)"
            )
            if spy_mat:
                parts.append(
                    f"- Regime: {spy_mat.regime.upper()} | Composite Score: {spy_mat.composite_score:.1f}/100"
                )
                parts.append(
                    f"- RSI: {spy_mat.technical.rsi_14:.1f} | ADX: {spy_mat.technical.adx:.1f} | MACD Hist: {spy_mat.technical.macd_histogram:+.4f}"
                )
                parts.append(
                    f"- 30d Vol (ann): {spy_mat.volatility.historical_vol_20d:.1f}% | Regime: {spy_mat.volatility.vol_regime}"
                )
                parts.append(
                    f"- Max DD 30d: {spy_mat.volatility.max_drawdown_30d:.1f}% | Max DD 90d: {spy_mat.volatility.max_drawdown_90d:.1f}%"
                )
                parts.append(
                    f"- Sharpe 30d: {spy_mat.risk.sharpe_ratio_30d:.2f} | Sortino 30d: {spy_mat.risk.sortino_ratio_30d:.2f}"
                )
                parts.append(
                    f"- VaR 95% 1d: {spy_mat.risk.var_95_1d:.2f}% | CVaR 95%: {spy_mat.risk.cvar_95_1d:.2f}%"
                )
                parts.append(f"- Key: {spy_mat.key_observation}" if spy_mat.key_observation else "")
                parts.append(f"- Risk: {spy_mat.risk_warning}" if spy_mat.risk_warning else "")
            parts.append("")

        # Macro context
        if self.macro_data:
            parts.append("### Macro Cross-Asset")
            for name, data in self.macro_data.items():
                parts.append(f"- {name}: {data['price']:.2f} (30d: {data['change_30d']:+.2f}%)")
            parts.append("")

        # Names in coverage
        parts.append("### Factor Matrices (Per-Symbol)")
        for sym in self.cover_symbols:
            m = self.factor_matrices.get(sym)
            snap = self.price_snapshots.get(sym)
            if not m or not snap:
                parts.append(f"\n#### {sym}: insufficient data")
                continue

            parts.append(f"\n#### {sym}")
            parts.append(
                f"Price: {snap.current_price:.2f} | 1d: {snap.change_1d_pct:+.2f}% | 7d: {snap.change_7d_pct:+.2f}% | 30d: {snap.change_30d_pct:+.2f}%"
            )
            parts.append(f"30d Range: {snap.low_30d:.2f} - {snap.high_30d:.2f}")

            t = m.technical
            parts.append(
                f"Technicals: RSI={t.rsi_14:.1f} | ADX={t.adx:.1f} ({t.trend_strength} {t.trend_direction}) | MACD Hist={t.macd_histogram:+.4f}"
            )
            parts.append(
                f"  Momentum: ROC 5d={t.roc_5d:+.2f}% | ROC 20d={t.roc_20d:+.2f}% ({t.momentum_regime})"
            )
            parts.append(
                f"  Distance: MA50={t.distance_to_ma50_pct:+.2f}% | MA200={t.distance_to_ma200_pct:+.2f}% | Z-score={t.z_score:+.2f}"
            )
            parts.append(f"  BB Width={t.bb_width_pct:.1f}% | BB Position={t.bb_position:.0f}%")
            parts.append(
                f"  Support={t.nearest_support:.2f} ({(t.distance_to_support_pct):.1f}% below) | Resistance={t.nearest_resistance:.2f} ({(t.distance_to_resistance_pct):.1f}% above)"
            )
            parts.append(f"  OBV={t.obv_trend} | Vol Ratio vs 20d={t.volume_ratio_vs_20d:.1f}x")

            v = m.volatility
            parts.append(
                f"Volatility: ATR={v.atr_14:.2f} ({v.atr_pct:.1f}%) | HV 20d={v.historical_vol_20d:.1f}% ann | Regime={v.vol_regime}"
            )
            parts.append(f"  HV Contraction (20 vs 60d): {v.hv_contraction_pct:+.1f}%")

            r = m.risk
            parts.append(
                f"Risk: Sharpe={r.sharpe_ratio_30d:.2f} | Sortino={r.sortino_ratio_30d:.2f} | Calmar={r.calmar_ratio_90d:.2f}"
            )
            parts.append(
                f"  VaR 95%={r.var_95_1d:.2f}% | CVaR 95%={r.cvar_95_1d:.2f}% | Skew={r.skewness_20d:+.2f} | Kurt={r.kurtosis_20d:.2f}"
            )
            parts.append(
                f"  Beta to SPY={r.beta_to_spy:.2f} | Corr to SPY={r.correlation_to_spy:.2f}"
            )
            parts.append(f"Regime: {m.regime.upper()} | Composite: {m.composite_score:.1f}/100")
            if m.key_observation:
                parts.append(f"Narrative Hook: {m.key_observation}")
            if m.risk_warning:
                parts.append(f"Risk Flag: {m.risk_warning}")
            parts.append("")

        # Sector rotation
        if self.sector_rotation:
            parts.append("### Sector Rotation")
            parts.append(f"Rotation Direction: {self.sector_rotation.rotation_direction}")
            parts.append(f"Top 3: {', '.join(self.sector_rotation.top_3)}")
            parts.append(f"Bottom 3: {', '.join(self.sector_rotation.bottom_3)}")
            parts.append("Rankings (ticker, name, 30d return, regime):")
            for ticker, name, ret, regime in self.sector_rotation.ranking[:8]:
                parts.append(f"  {ticker} ({name}): {ret:+.2f}% [{regime}]")
            parts.append("")

        # News headlines
        if self.headlines:
            parts.append("### Live News Headlines")
            for h in self.headlines[:15]:
                src = h.source.split("/")[2] if "//" in h.source else h.source
                parts.append(f"- [{h.published.strftime('%H:%M')}] [{src}] {h.title}")
            parts.append("")

        return "\n".join(parts)

    def _build_prompt(self, topic: str, style: str, include_quant: bool = True) -> str:
        """Build the complete LLM prompt."""

        quant_context = self._build_quant_context_block() if include_quant else ""

        today = self.note_date

        # Real hedge fund research note examples embedded as style anchors
        style_anchors = {
            "daily": """\
=== STYLE ANCHOR: DAILY BRIEFING (sell-side equivalent) ===
Title: "[Date] Morning Briefing — [Hook Statement]"
Structure:
1. EXECUTIVE SUMMARY (2-3 sentences with top-line market read)
2. MACRO/MARKET CONTEXT (1-2 paragraphs tying cross-asset moves to equity/crypto impact)
3. THE TRADE (deep dive into 2-3 names or one sector with specific catalysts)
4. INTERESTING HEADLINES THIS MORNING (annotated — what matters, what doesn't)
5. RISK WATCH (specific risk events, vol regimes, correlation shifts)
6. POSITIONING / TRADE IDEAS (actionable, with entry/stop/target if relevant)
7. CALENDAR (key events this week)

Writing: Punchy. JPM Morning Note / Goldman's Top of Mind. Mix of macro + micro.
""",
            "weekly": """\
=== STYLE ANCHOR: WEEKLY DEEP DIVE ===
Title: "Weekly Factor Book: [Theme]"
Structure:
1. MACRO VIEW (big picture regime assessment, factor performance YTD)
2. SECTOR ROTATION ANALYSIS (who's leading, who's lagging, narrative behind the flows)
3. NAME OF THE WEEK (deep dive on one name: financials, narrative, technicals, risk, catalyst)
4. FACTOR WATCH (which factors worked this week: momentum, value, quality, low vol, size)
5. VOLATILITY & LIQUIDITY REVIEW (vol surface, gamma positioning, options market tells)
6. POSITIONING SUGGESTIONS (tactical and strategic)
7. WHAT WE'RE WATCHING NEXT WEEK (catalysts, events, macro releases)
""",
            "sector_rotation": """\
=== STYLE ANCHOR: SECTOR ROTATION NOTE ===
Title: "Sector Rotation Watch: [Direction]"
Focus on cross-sectional relative strength, factor exposure within sectors,
and narrative catalysts driving inflows/outflows. Use RRG-chart-style language
("Technology is leading but rotating from growth to value within the sector").
""",
        }

        anchor = style_anchors.get(style, style_anchors["daily"])

        prompt = f"""You are a sell-side strategist at a top-tier investment bank writing today's {style} research note.

DATE: {today}
TOPIC: {topic}

{anchor}

Below is the raw quantitative context (prices, factors, news, macro, sector data). Your job is to write a publishable research note using this as raw material.

### WRITING RULES (NON-NEGOTIABLE)

1. Structure must follow the style anchor above exactly.
2. Every substantive claim must reference a specific number from the data.
3. Write in active voice, future tense, decisive tone. "We expect...", "The data argues...", "We are watching..."
4. No hedging unless discussing tail risks. "The pattern is clear" > "It could be interpreted as"
5. No AI-sounding language: ban "It is important to note", "Based on the data provided", "As an AI", "I don't have access to real-time", "In the context of", "It's worth mentioning".
6. Mix sectors, single names, macro, and narrative. Create a coherent story.
7. Include 3-5 specific "What we are watching" bullets at the end with concrete price levels or catalyst dates.
8. Closing paragraph: "Bottom line" or "Our Take" with clear positioning view.
9. Title should be newsstand-worthy — generates curiosity, telegraphs the view. Example: "SPY Grinds Higher But the Tape Is Losing Conviction" not "Market Update April 28".

### QUANTITATIVE DATA

{quant_context}

Now write the research note. Output ONLY the article. Title first, then body sections separated by blank lines. No preamble. No metadata. No "Here is your note". Just the publication-ready text."""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM for synthesis."""
        if self.model.startswith("deepseek/"):
            import requests

            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model.replace("deepseek/", ""),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You write sell-side research notes for institutional investors. "
                                "Your prose is measured, data-driven, and opinionated. "
                                "You never write like an AI — always like a human analyst who "
                                "has been covering markets for 15 years. Short paragraphs. "
                                "Crisp sentences. Specific numbers. No empty phrases."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.65,
                    "max_tokens": 3072,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        return f"[LLM call not implemented for model: {self.model}]"

    def publish(
        self,
        topic: str = "US equity market review",
        style: str = "daily",
        include_quant: bool = True,
    ) -> str:
        """Gather data, synthesize, and return a publication-ready research note."""
        self.gather()
        prompt = self._build_prompt(topic, style, include_quant=include_quant)
        article = self._call_llm(prompt)
        return article

    def quick_note(self) -> str:
        """Generate a quick daily note with minimal data."""
        self.gather()
        return self.publish(topic="US equity market and factor review", style="daily")

    def weekly_note(self) -> str:
        """Generate a full weekly deep-dive research note."""
        self.gather()
        return self.publish(
            topic="Weekly factor book and sector rotation deep dive", style="weekly"
        )
