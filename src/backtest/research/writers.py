"""Research note writer — multi-market, multi-style. Daily brief, Trade Read, KOL post.

Writing style references:
  - **Daily Brief**: JPM / Goldman morning note. Macro first, sector rotation, 2-3 actionable
    names. Punchy. Data-driven.
  - **Trade Read**: Position-level write-up. Why this trade, entry, stop, target, conviction.
    Common on futu niu niu / Webull / TradingView.
  - **KOL Daily**: Twitter-style. More narrative, opinionated, mix of macro + specific setups +
    risk awareness. Popular on Chinese trading apps.

No AI filler. Every claim backed by numbers from the factor engine.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .data_layer import (
    DEFAULT_CRYPTO_WATCHLIST,
    DEFAULT_HK_WATCHLIST,
    DEFAULT_US_WATCHLIST,
    Headline,
    PriceSnapshot,
    collect_headlines,
    fetch_crypto_ohlcv,
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
    """Generate publication-quality research notes across US/HK/crypto markets."""

    # ── Human-readable name registry for tickers ──
    TICKER_NAMES = {
        "SPY": "S&P 500",
        "QQQ": "Nasdaq 100",
        "IWM": "Russell 2000",
        "AAPL": "Apple",
        "NVDA": "Nvidia",
        "MSFT": "Microsoft",
        "AMZN": "Amazon",
        "GOOGL": "Google",
        "META": "Meta",
        "TSLA": "Tesla",
        "AVGO": "Broadcom",
        "JPM": "JPMorgan",
        "GS": "Goldman Sachs",
        "BAC": "Bank of America",
        "V": "Visa",
        "MA": "Mastercard",
        "UNH": "UnitedHealth",
        "LLY": "Eli Lilly",
        "JNJ": "Johnson & Johnson",
        "XOM": "Exxon Mobil",
        "CVX": "Chevron",
        "AMD": "AMD",
        "INTC": "Intel",
        "QCOM": "Qualcomm",
        "MU": "Micron",
        "0700.HK": "Tencent",
        "9988.HK": "Alibaba",
        "3690.HK": "Meituan",
        "9618.HK": "JD.com",
        "1810.HK": "Xiaomi",
        "1299.HK": "AIA",
        "0005.HK": "HSBC",
        "3988.HK": "Bank of China",
        "0939.HK": "CCB",
        "2269.HK": "WuXi Biologics",
        "1024.HK": "Kuaishou",
        "9888.HK": "Baidu HK",
        "9999.HK": "NetEase",
        "BTC/USDT": "Bitcoin",
        "ETH/USDT": "Ethereum",
        "SOL/USDT": "Solana",
        "XRP/USDT": "XRP",
    }

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or ""
        self.factor_matrices: Dict[str, FactorMatrix] = {}
        self.price_snapshots: Dict[str, PriceSnapshot] = {}
        self.sector_rotation: Optional[SectorRotation] = None
        self.macro_data: Dict[str, Any] = {}
        self.headlines: List[Headline] = []
        self.hk_matrices: Dict[str, FactorMatrix] = {}
        self.hk_snapshots: Dict[str, PriceSnapshot] = {}
        self.crypto_matrices: Dict[str, FactorMatrix] = {}
        self.crypto_snapshots: Dict[str, PriceSnapshot] = {}
        self.note_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _name(self, sym: str) -> str:
        return self.TICKER_NAMES.get(sym, sym)

    # ── Data Collection ───────────────────────────────────────────

    def gather(self, include_hk: bool = True, include_crypto: bool = True) -> "ResearchNoteWriter":
        """Collect data from all configured markets."""
        # ── US Equities ──
        us_dfs = fetch_ohlcv(DEFAULT_US_WATCHLIST, market="us_equity", days=365)
        self.price_snapshots = price_snapshots(us_dfs, market="us_equity")
        spy_df = us_dfs.get("SPY")
        for sym in DEFAULT_US_WATCHLIST:
            df = us_dfs.get(sym)
            if df is not None and not df.empty:
                self.factor_matrices[sym] = compute_technical_factors(
                    df, sym, market="us_equity", benchmark_df=spy_df
                )

        # ── HK Equities ──
        if include_hk:
            hk_dfs = fetch_ohlcv(DEFAULT_HK_WATCHLIST, market="hk_equity", days=365)
            self.hk_snapshots = price_snapshots(hk_dfs, market="hk_equity")
            hsi_df = hk_dfs.get("HSI")
            for sym in DEFAULT_HK_WATCHLIST:
                df = hk_dfs.get(sym)
                if df is not None and not df.empty:
                    self.hk_matrices[sym] = compute_technical_factors(
                        df,
                        sym,
                        market="hk_equity",
                        benchmark_df=hsi_df,
                        use_short_ma="HSI" not in sym,
                    )

        # ── Crypto ──
        if include_crypto:
            crypto_dfs = fetch_crypto_ohlcv(DEFAULT_CRYPTO_WATCHLIST, days=365)
            self.crypto_snapshots = price_snapshots(crypto_dfs, market="crypto")
            btc_df = crypto_dfs.get("BTC/USDT")
            for sym in DEFAULT_CRYPTO_WATCHLIST:
                df = crypto_dfs.get(sym)
                if df is not None and not df.empty:
                    self.crypto_matrices[sym] = compute_technical_factors(
                        df, sym, market="crypto", benchmark_df=btc_df, use_short_ma=True
                    )

        # ── Macro & Sector & News ──
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

        sector_dfs = fetch_sectors(days=60)
        self.sector_rotation = analyze_sector_rotation(sector_dfs)
        self.headlines = collect_headlines(max_per_source=3)

        return self

    # ── Quant Context Builder ─────────────────────────────────────

    def _build_macro_block(self) -> str:
        lines = ["### Macro Cross-Asset"]
        for name, data in self.macro_data.items():
            lines.append(f"- {name}: {data['price']:.2f} (30d: {data['change_30d']:+.2f}%)")
        lines.append("")
        return "\n".join(lines)

    def _build_sector_block(self) -> str:
        if not self.sector_rotation:
            return ""
        sr = self.sector_rotation
        lines = [
            "### Sector Rotation",
            f"Direction: {sr.rotation_direction}",
            f"Top 3: {', '.join(sr.top_3)}",
            f"Bottom 3: {', '.join(sr.bottom_3)}",
            "Rankings:",
        ]
        for ticker, name, ret, regime in sr.ranking[:8]:
            lines.append(f"  {ticker} ({name}): {ret:+.2f}% [{regime}]")
        lines.append("")
        return "\n".join(lines)

    def _build_matrix_block(
        self,
        matrices: Dict[str, FactorMatrix],
        snapshots: Dict[str, PriceSnapshot],
        max_count: int = 15,
    ) -> str:
        lines = []
        for sym in list(matrices.keys())[:max_count]:
            m = matrices[sym]
            snap = snapshots.get(sym)
            if not snap:
                continue
            lines.append(f"\n#### {sym} ({self._name(sym)})")
            lines.append(
                f"Price: {snap.current_price:.2f} | 1d: {snap.change_1d_pct:+.2f}% | 7d: {snap.change_7d_pct:+.2f}% | 30d: {snap.change_30d_pct:+.2f}%"
            )
            lines.append(f"30d Range: {snap.low_30d:.2f} - {snap.high_30d:.2f}")

            t = m.technical
            lines.append(
                f"Tech: RSI={t.rsi_14:.1f} | ADX={t.adx:.1f} ({t.trend_strength} {t.trend_direction}) | MACD Hist={t.macd_histogram:+.4f}"
            )
            lines.append(
                f"  ROC 5d={t.roc_5d:+.2f}% | ROC 20d={t.roc_20d:+.2f}% | Momentum={t.momentum_regime}"
            )
            lines.append(
                f"  MA50={t.distance_to_ma50_pct:+.2f}% | MA200={t.distance_to_ma200_pct:+.2f}% | Z={t.z_score:+.2f}"
            )
            lines.append(
                f"  BB Width={t.bb_width_pct:.1f}% | OBV={t.obv_trend} | Vol Ratio={t.volume_ratio_vs_20d:.1f}x"
            )
            lines.append(
                f"  S={t.nearest_support:.2f} ({t.distance_to_support_pct:.1f}%) | R={t.nearest_resistance:.2f} ({t.distance_to_resistance_pct:.1f}%)"
            )

            v = m.volatility
            lines.append(
                f"Vol: ATR={v.atr_pct:.1f}% | HV 20d={v.historical_vol_20d:.0f}% | Regime={v.vol_regime} | DD 30d={v.max_drawdown_30d:.1f}%"
            )

            r = m.risk
            lines.append(
                f"Risk: Sharpe={r.sharpe_ratio_30d:.2f} | VaR={r.var_95_1d:.2f}% | Skew={r.skewness_20d:+.2f} | Kurt={r.kurtosis_20d:.2f}"
            )

            lines.append(
                f"Regime: {m.regime.upper()} | Score: {m.composite_score:.1f}/100 | Bias: {m.trade_bias} ({m.conviction})"
            )
            if m.stop_loss_level > 0:
                lines.append(
                    f"  Trade Read: Entry={snap.current_price:.2f} | Stop={m.stop_loss_level:.2f} | Target={m.target_level:.2f} | R:R={m.risk_reward_ratio:.2f}"
                )
            if m.key_observation:
                lines.append(f"  Hook: {m.key_observation}")
            if m.risk_warning:
                lines.append(f"  Risk: {m.risk_warning}")
        return "\n".join(lines)

    def _build_quant_context_block(
        self,
        include_macro: bool = True,
        include_sectors: bool = True,
        include_us: bool = True,
        include_hk: bool = True,
        include_crypto: bool = True,
    ) -> str:
        parts = ["## QUANTITATIVE CONTEXT"]

        # Market overview — SPY
        spy = self.price_snapshots.get("SPY")
        spy_mat = self.factor_matrices.get("SPY")
        if spy:
            parts.append("\n### US Market Overview")
            parts.append(
                f"SPY: {spy.current_price:.2f} (1d: {spy.change_1d_pct:+.2f}% | 30d: {spy.change_30d_pct:+.2f}%)"
            )
            if spy_mat:
                parts.append(
                    f"Regime: {spy_mat.regime.upper()} | Score: {spy_mat.composite_score:.1f} | ADX: {spy_mat.technical.adx:.1f} | Vol: {spy_mat.volatility.historical_vol_20d:.0f}% ann"
                )

        if include_macro and self.macro_data:
            parts.append("")
            parts.append(self._build_macro_block())

        if include_sectors and self.sector_rotation:
            parts.append(self._build_sector_block())

        if include_us and self.factor_matrices:
            parts.append("### US Equity Factor Matrices")
            parts.append(self._build_matrix_block(self.factor_matrices, self.price_snapshots))

        if include_hk and self.hk_matrices:
            parts.append("\n### HK Equity Factor Matrices")
            parts.append(self._build_matrix_block(self.hk_matrices, self.hk_snapshots))

        if include_crypto and self.crypto_matrices:
            parts.append("\n### Crypto Factor Matrices")
            parts.append(self._build_matrix_block(self.crypto_matrices, self.crypto_snapshots))

        if self.headlines:
            parts.append("\n### Live News")
            for h in self.headlines[:12]:
                src = h.source.split("/")[2] if "//" in h.source else h.source
                parts.append(f"- [{h.published.strftime('%H:%M')}] [{src}] {h.title}")

        return "\n".join(parts)

    # ── Prompt Builder ────────────────────────────────────────────

    def _build_prompt(self, topic: str, style: str, include_quant: bool = True) -> str:
        quant = self._build_quant_context_block() if include_quant else ""

        anchors = self._get_style_anchor(style)

        prompt = f"""You are a veteran sell-side strategist writing today's research note.

DATE: {self.note_date}
TOPIC: {topic}
STYLE: {style}

{anchors}

### RAW QUANTITATIVE DATA

{quant}

### WRITING RULES (NON-NEGOTIABLE)

1. Follow the structure in the style anchor exactly.
2. Every claim references a specific number from the data.
3. Active voice, decisive tone. "We expect..." / "The data argues..." / "We are watching..."
4. No hedging. "The pattern is clear" > "It could be interpreted."
5. Zero AI-sounding language. No "Based on the data provided", "As an AI", "In the context of".
6. Mix macro, sectors, and specific names. Tell a coherent story.
7. Include 3-5 "What we are watching" bullets at the end with concrete prices/dates.
8. Closing paragraph: "Bottom line" with clear positioning view.
9. Title must be newsstand-worthy: generates curiosity, telegraphs the view.

Output ONLY the article. Title first. Sections separated by blank lines. No preamble. No "Here is your note". Just the publication-ready text."""

        return prompt

    def _get_style_anchor(self, style: str) -> str:
        anchors = {
            "daily": """STYLE: DAILY BRIEFING (sell-side equivalent: JPM Morning Note / Goldman Top of Mind)

Structure:
1. EXECUTIVE SUMMARY — 2-3 sentences, top-line market read
2. MACRO & CROSS-ASSET — treasury vol, USD, VIX, gold, oil — how they impact equities/crypto
3. SECTOR ROTATION WATCH — which sectors are leading, which lagging, what it tells us
4. THE TRADE — deep dive on 2-3 specific names with catalyst, entry levels
5. RISK WATCH — vol regimes, correlation shifts, specific risk events
6. POSITIONING / TRADE IDEAS — actionable, directional
7. WATCHLIST — 3-5 specific levels, dates, or catalysts

Tone: Punchy. Professional. Mix of macro and micro. Every paragraph has a number.

---

""",
            "trade_read": """STYLE: TRADE READ (institutional / top futu niu niu KOL style)

Focus on specific trade setups with entry, stop, target, conviction. Each setup must answer:
1. WHY THIS TRADE — thesis in 2 sentences (what catalyst, what pattern, what data)
2. ENTRY — specific price level or zone
3. STOP LOSS — invalidation level with rationale
4. TARGET — take-profit level with rationale
5. RISK / REWARD — ratio calculation
6. CONVICTION — high / medium / low and why
7. TIMEFRAME — days / weeks / months

Cover 2-4 setups across different markets (US + HK + crypto if data available).
If a setup doesn't have clean levels, skip it. Only publish setups you'd trade yourself.

Structure per setup:
```
──────── Setup 1: [BIAS] [TICKER]
Thesis: ...
Entry: ...
Stop: ...
Target: ...
R:R: ...
Conviction: ...
```

---

""",
            "kol_daily": """STYLE: KOL DAILY BRIEF (top trading community KOL — Twitter / futu niu niu / webull)

This reads like a trader posting to their 50k followers. Opinionated. Punchy. 
Mix of morning market read + 2-3 specific setups + risk awareness + a "big picture" thought.

Structure:
1. MARKET READ — "The tape tells me..." (macro + vol + regime in 3-4 sentences)
2. WHAT I'M WATCHING — 2-3 specific names with quick technical read
3. ACTIVE SETUPS — brief trade reads (entry, stop, target in 1 line each)
4. RISK MANAGEMENT — "What keeps me up" — specific risks being managed
5. BIG PICTURE — one paragraph about a structural trend / regime change / macro risk
6. TODAY'S PLAN — what the writer is actually doing (adding, trimming, sitting)

Tone: Confident. First-person ("I'm watching..."). Numbers in every claim.
Trader personality: disciplined, data-driven, risk-aware.

---

""",
            "weekly": """STYLE: WEEKLY DEEP DIVE (sell-side weekly / institutional)

Structure:
1. MACRO VIEW — big picture regime, factor performance YTD
2. SECTOR ROTATION ANALYSIS — who's leading/lagging, narrative behind flows
3. NAME OF THE WEEK — deep dive: financials, narrative, technicals, catalyst
4. FACTOR WATCH — which factors worked: momentum, value, quality, low vol
5. VOL & LIQUIDITY REVIEW — vol surface, gamma, options tells
6. POSITIONING SUGGESTIONS — tactical and strategic
7. CATALYST CALENDAR — key events next week

---

""",
            "sector_rotation": """STYLE: SECTOR ROTATION NOTE

Focus on cross-sectional relative strength, factor exposure within sectors.
Use RRG-chart language. "Technology is leading but rotating from growth to value within the sector."

---
""",
        }
        return anchors.get(style, anchors["daily"])

    # ── LLM Call ──────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        if not self.model.startswith("deepseek/"):
            return f"[LLM not configured for model: {self.model}]"

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
                            "You never write like an AI. Short paragraphs. Crisp sentences. "
                            "Specific numbers. No empty phrases."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.65,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── Public API ────────────────────────────────────────────────

    def publish(
        self,
        topic: str = "Global markets review",
        style: str = "daily",
        include_quant: bool = True,
        **kwargs,
    ) -> str:
        """Generate a publishable research note."""
        self.gather(**kwargs)
        prompt = self._build_prompt(topic, style, include_quant=include_quant)
        return self._call_llm(prompt)

    def daily_brief(self, topic: str = "US + HK + crypto market review") -> str:
        """Quick daily brief across all markets."""
        return self.publish(topic=topic, style="daily")

    def trade_read(self, topic: str = "Trade setups across US + HK + crypto") -> str:
        """Position-level trade write-ups."""
        return self.publish(topic=topic, style="trade_read")

    def kol_daily(self, topic: str = "Trader's morning brief across HK, US, and crypto") -> str:
        """KOL-style daily brief."""
        return self.publish(topic=topic, style="kol_daily")

    def weekly_note(self) -> str:
        """Full weekly deep dive."""
        return self.publish(
            topic="Weekly factor book and sector rotation deep dive", style="weekly"
        )
