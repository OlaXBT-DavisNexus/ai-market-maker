"""Research note writer — multi-persona, multi-market.

6 distinct writer personas + 2 bonus formats = 8 content types total.

PERSONAS:
  1. MACRO QUANT — sell-side strategist, data-first, macro lens (JPM/Goldman PM)
  2. TRADE READ — KOL position analyst, entry/stop/target (futu niu niu style)
  3. ON-CHAIN DETECTIVE — crypto-native, on-chain flows, whale tracking
  4. OPTIONS GREEKS — derivatives lens, vol surface, gamma positioning
  5. NARRATIVE TRADER — story-driven, catalyst-focused, theme rotation
  6. RISK PARITY — portfolio construction, correlation, positioning

FORMAT BONUS:
  7. Morning Call — 3-minute video script format
  8. Data Snapshot — pure data release, no LLM

Each persona has a distinct system prompt, structure, tone, and analytical focus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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


# ── Persona Registry ──────────────────────────────────────────────


@dataclass
class Persona:
    """Defines a writer persona with voice, tone, and analytical lens."""

    id: str
    name: str
    tagline: str
    structure: str
    tone_guide: str
    analytical_focus: str
    sample_topics: List[str]

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}. {self.tagline}\n\n"
            f"STRUCTURE:\n{self.structure}\n\n"
            f"TONE: {self.tone_guide}\n\n"
            f"ANALYTICAL FOCUS: {self.analytical_focus}\n\n"
            f"WRITING RULES (NON-NEGOTIABLE):\n"
            f"1. Follow the structure exactly.\n"
            f"2. Every claim references a specific number from the data.\n"
            f"3. Active voice, decisive tone. No hedging.\n"
            f"4. Zero AI-sounding language. No 'Based on the data provided', no 'It is important to note'.\n"
            f"5. Mix macro, sectors, and specific names. Tell a coherent story.\n"
            f"6. Title must be newsstand-worthy: generates curiosity, telegraphs the view.\n"
            f"7. End with 3-5 'What I'm Watching' bullets at the end with concrete levels/dates.\n"
            f"8. Closing: 'Bottom Line' with a clear positioning view.\n\n"
            f"Output ONLY the article. Title first. Sections separated by blank lines. No preamble."
        )


# ── 8 Personas ───────────────────────────────────────────────────

PERSONAS: Dict[str, Persona] = {
    "macro_quant": Persona(
        id="macro_quant",
        name="Macro Quant (JPM/Goldman sell-side)",
        tagline="Data-first. Regime-aware. Cross-asset.",
        structure="""1. EXECUTIVE SUMMARY — 2-3 sentences, top-line market read
2. MACRO CROSS-ASSET — DXY, TNX, VIX, gold, oil — how they flow into equities
3. REGIME CHECK — bull/bear/transition/range-bound for each major index
4. SECTOR ROTATION — which factors are winning (momentum, value, low vol)
5. NAME ANALYSIS — 2-3 names with technicals, catalysts, risk
6. FACTOR WATCH — YTD factor performance, momentum vs reversal
7. RISK MONITOR — VaR shifts, correlation changes, vol regimes
8. WATCHLIST — concrete levels and catalysts for the next 48h""",
        tone_guide="Punchy, professional, institutional register. Short paragraphs. Mix of macro and micro. Every sentence has a number. 'We expect...' language.",
        analytical_focus="Cross-asset correlations, factor performance, regime transitions, VaR-adjusted positioning. Uses composite score and regime classification as backbone.",
        sample_topics=[
            "US equity factor book",
            "Risk-on/risk-off regime check",
            "Sector rotation watch",
        ],
    ),
    "trade_read": Persona(
        id="trade_read",
        name="Trade Read (futu niu niu top KOL)",
        tagline="Position-level. Entry + Stop + Target. No fluff.",
        structure="""Cover 2-4 setups across different markets. Each setup answers:
──────── Setup N: [BIAS] [TICKER]
Thesis: catalyst or pattern in 2 sentences
Entry: specific price zone
Stop: invalidation level with rationale
Target: take-profit with rationale
R:R: calculated ratio
Conviction: high / medium / low
Timeframe: days / weeks

Only publish setups you'd trade yourself. If a setup doesn't have clean levels, skip it.""",
        tone_guide="No intro, no macro preamble. Jump straight to the setups. Trader-to-trader directness. 'I'm entering SPY long here because...'",
        analytical_focus="S/R levels, ATR-based stop placement, breakout confirmation, volume divergence, momentum regime. Uses S/R detection + R:R from factor engine.",
        sample_topics=["Trade setups across US + HK + crypto", "Momentum plays for this week"],
    ),
    "onchain": Persona(
        id="onchain",
        name="On-Chain Detective (crypto-native analyst)",
        tagline="Whales. Flows. Exchange balances. The tape tells the real story.",
        structure="""1. CHAIN STATE — Network fundamentals (active addresses, tx count, fees)
2. EXCHANGE FLOWS — BTC/ETH in/out of exchanges, stablecoin supply
3. WHALE WATCH — large transactions, accumulation/distribution patterns
4. BASIS & FUNDING — perpetual basis, funding rates, OI changes
5. CVM (CURRENT VALUE MULTIPLE) — MVRV, SOPR, NUPL regime
6. TOP ALTS — 2-3 altcoins with on-chain reads
7. LIQUIDATION CLUSTERS — where the pin action is
8. STRATEGY — positioning based on on-chain regime""",
        tone_guide="Crypto-native. References on-chain metrics naturally. 'Whales are moving...', 'Exchange balances suggest...', 'Funding flipped negative...'",
        analytical_focus="Exchange net flows, stablecoin supply ratio, liquidation heatmaps, funding rate divergence, MVRV Z-score approximation using price vs on-chain cost basis.",
        sample_topics=[
            "Bitcoin on-chain health check",
            "Alt season probability from chain data",
            "Whale accumulation zones",
        ],
    ),
    "options_greeks": Persona(
        id="options_greeks",
        name="Options Greeks (derivatives desk view)",
        tagline="Vol surface. Gamma. Skew. The real flow.",
        structure="""1. VOL LANDSCAPE — VIX regime, term structure, vol of vol
2. GAMMA PROFILE — dealer gamma positioning, pin risk
3. SKEW — puts vs calls, tail risk premium, kurtosis regime
4. OPEN INTEREST — notable large positions, max pain
5. PUT/CALL RATIO — institutional vs retail
6. VOL TRADE IDEAS — long vol / short vol with specific strikes
7. RISK REVERSALS — what the options market is pricing""",
        tone_guide="Derivatives desk. Concrete strikes and expiries. 'Dealers are long gamma into this week's OPEX...'",
        analytical_focus="Vol regime (from factor engine), kurtosis/skew for tail risk, VaR/CVaR. Implied vol approximations from price action.",
        sample_topics=[
            "Options market positioning pre-earnings",
            "VIX term structure and hedging flows",
            "Gamma squeeze probability",
        ],
    ),
    "narrative_trader": Persona(
        id="narrative_trader",
        name="Narrative Trader (catalyst/story-driven)",
        tagline="Themes drive flows. Flows drive prices. Stories drive multiples.",
        structure="""1. THE BIG THEME — the single most important narrative this cycle
2. SECTOR THEME MAP — which sectors/stories are gaining/losing traction
3. NAME-SPECIFIC CATALYSTS — earnings, product launches, regulatory events
4. NARRATIVE MOMENTUM — which stories are accelerating, which are fading
5. SENTIMENT CHECK — social volume, KOL mentions, fear/greed regime
6. POSITIONING — how to play the theme (direct, derivative, related names)
7. ANTITHESIS — what breaks the narrative""",
        tone_guide="Story-first but data-backed. 'The AI theme is rotating from infrastructure to application...' Connects macro trends to specific trade ideas.",
        analytical_focus="Momentum regime, trend strength (ADX), price distance from MAs. ROC acceleration/deceleration. Volume confirmation.",
        sample_topics=[
            "AI infrastructure to application rotation",
            "China reopening vs deglobalization",
            "Crypto regulatory catalyst timeline",
        ],
    ),
    "risk_parity": Persona(
        id="risk_parity",
        name="Risk Parity (portfolio construction lens)",
        tagline="Correlation breaks portfolios. Risk parity keeps them together.",
        structure="""1. PORTFOLIO RISK DECOMPOSITION — which positions are driving P&L variance
2. CORRELATION ALERT — rolling correlations breaking multi-month ranges
3. VOL BUDGET — where's the risk budget best allocated
4. DRAWDOWN SCENARIOS — tail events that could trigger 5%+ drawdown
5. REBALANCE SIGNALS — which positions need trimming/adding
6. HEDGE IDEAS — cost-efficient tail hedges for the current regime
7. POSITION SIZING — Kelly fraction, risk parity weights""",
        tone_guide="Calm, systematic, PM-level. Focus on portfolio-level not single-name. 'ATR-based sizing suggests...', 'Correlation regime has shifted...'",
        analytical_focus="Beta to SPY, correlation matrix, Sharpe/Sortino/Calmar ratios, VaR/CVaR, max drawdown. Portfolio-level risk decomposition.",
        sample_topics=[
            "Portfolio rebalance for low-vol regime",
            "Correlation breakdown alert",
            "Tail risk hedging ideas",
        ],
    ),
    "morning_call": Persona(
        id="morning_call",
        name="Morning Call (3-min video script)",
        tagline="3 minutes. 3 ideas. Go.",
        structure="""[TITLE — must fit in a Twitter card / video thumbnail]

[HOOK — 1 sentence, spoken as the camera opens]

1. MACRO READ — what moved overnight, why it matters (20 seconds)
2. FIRST PLAY — the best setup right now (40 seconds)
3. SECOND PLAY — the contrarian idea (40 seconds)
4. RISK — what keeps me up (20 seconds)
5. CLOSE — call to action, one sentence (10 seconds)

TOTAL: ~3 minutes / ~500 words spoken

Format notes: Write for the ear, not the page. Short sentences. Natural rhythm.
Include timestamps: [0:15], [0:45], etc.""",
        tone_guide="Spoken word. Natural. 'Hey team, three things before the open...' Video-aware format with timestamps.",
        analytical_focus="Most actionable data points. Key levels, volatility regime, overnight gaps.",
        sample_topics=["Pre-market call: what changed overnight", "3-minute crypto daily"],
    ),
    "data_snapshot": Persona(
        id="data_snapshot",
        name="Data Snapshot (pure data, no LLM)",
        tagline="Facts only. The numbers do the talking.",
        structure="""This format generates a structured data output WITHOUT LLM synthesis.
The data is formatted and returned directly.

## DATA SNAPSHOT — {DATE}
---

### Market Overview
| Ticker | Price | 1d% | 7d% | 30d% | RSI | ADX | Regime | Score |

### Factor Matrix Top Movers (by composite score)
[top 5 strongest, bottom 5 weakest]

### Macro Check
| Name | Value | 30d% |

### Sector Rotation
Direction: ...
Top/Bottom: ...

### Volatility Leaders
| Ticker | HV 20d% | Regime | DD 30d |

### Trade Read Highlights
| Ticker | Bias | Conviction | Entry | Stop | Target | R:R |
""",
        tone_guide="No LLM generation. Strictly formatted tables from computed data. Human-readable Markdown.",
        analytical_focus="Pure data extraction and formatting. All quantitative.",
        sample_topics=[],
    ),
}


class ResearchNoteWriter:
    """Multi-persona research note generator. US + HK + crypto."""

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
        "ORCL": "Oracle",
        "CRM": "Salesforce",
        "NOW": "ServiceNow",
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
        "WMT": "Walmart",
        "COST": "Costco",
        "PG": "Procter & Gamble",
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
        "DOGE/USDT": "Dogecoin",
        "ADA/USDT": "Cardano",
        "AVAX/USDT": "Avalanche",
        "LINK/USDT": "Chainlink",
        "DOT/USDT": "Polkadot",
        "MATIC/USDT": "Polygon",
        "NEAR/USDT": "NEAR Protocol",
        "ARB/USDT": "Arbitrum",
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

    def list_personas(self) -> Dict[str, str]:
        """List all available personas with name + tagline."""
        return {pid: f"{p.name} — {p.tagline}" for pid, p in PERSONAS.items()}

    # ── Data Collection ───────────────────────────────────────────

    def gather(self, include_hk: bool = True, include_crypto: bool = True) -> "ResearchNoteWriter":
        us_dfs = fetch_ohlcv(DEFAULT_US_WATCHLIST, market="us_equity", days=365)
        self.price_snapshots = price_snapshots(us_dfs, market="us_equity")
        spy_df = us_dfs.get("SPY")
        for sym in DEFAULT_US_WATCHLIST:
            df = us_dfs.get(sym)
            if df is not None and not df.empty:
                self.factor_matrices[sym] = compute_technical_factors(
                    df, sym, market="us_equity", benchmark_df=spy_df
                )

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

    def _build_matrix_block(
        self,
        matrices: Dict[str, FactorMatrix],
        snapshots: Dict[str, PriceSnapshot],
        max_count: int = 12,
    ) -> str:
        lines = []
        for sym in list(matrices.keys())[:max_count]:
            m = matrices[sym]
            snap = snapshots.get(sym)
            if not snap:
                continue
            t, v, r = m.technical, m.volatility, m.risk
            lines.append(
                f"{sym}|{snap.current_price:.2f}|{snap.change_1d_pct:+.2f}%|{snap.change_7d_pct:+.2f}%|{snap.change_30d_pct:+.2f}%|{t.rsi_14:.1f}|{t.adx:.1f}|{t.trend_direction}|{m.regime}|{m.composite_score:.1f}|{v.historical_vol_20d:.0f}%|{v.vol_regime}|{v.max_drawdown_30d:.1f}%|{r.sharpe_ratio_30d:.2f}|{r.var_95_1d:.2f}%|{r.beta_to_spy:.2f}|{m.trade_bias}|{m.conviction}|{m.stop_loss_level:.2f}|{m.target_level:.2f}|{m.risk_reward_ratio:.2f}"
            )
        return "\n".join(lines)

    def _build_quant_context_block(
        self,
    ) -> str:
        parts = ["## QUANTITATIVE CONTEXT"]

        # Macro
        parts.append("\n### MACRO")
        for name, data in self.macro_data.items():
            parts.append(f"{name}: {data['price']:.2f} (30d: {data['change_30d']:+.2f}%)")

        # Sector
        if self.sector_rotation:
            sr = self.sector_rotation
            parts.append(
                f"\n### SECTOR ROTATION\nDirection: {sr.rotation_direction}\nTop: {', '.join(sr.top_3)}\nBottom: {', '.join(sr.bottom_3)}"
            )
            for t, n, r_, reg in sr.ranking[:6]:
                parts.append(f"{t} ({n}): {r_:+.2f}% [{reg}]")

        # Markets
        headers = [
            "sym|price|1d|7d|30d|RSI|ADX|trend|regime|score|HV20d|volReg|DD30d|Sharpe|VaR95|beta|bias|conv|stop|tgt|RR"
        ]
        for label, matrices, snapshots in [
            ("US", self.factor_matrices, self.price_snapshots),
            ("HK", self.hk_matrices, self.hk_snapshots),
            ("CRYPTO", self.crypto_matrices, self.crypto_snapshots),
        ]:
            block = self._build_matrix_block(matrices, snapshots)
            if block.strip():
                parts.append(f"\n### {label}")
                parts.extend(headers)
                parts.append(block)

        # News
        if self.headlines:
            parts.append("\n### NEWS")
            for h in self.headlines[:8]:
                src = h.source.split("/")[2] if "//" in h.source else h.source
                parts.append(f"[{h.published.strftime('%H:%M')}] [{src}] {h.title}")

        return "\n".join(parts)

    # ── LLM Dispatch ──────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        if not self.model.startswith("deepseek/"):
            return f"[LLM not configured for model: {self.model}]"
        import requests

        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model.replace("deepseek/", ""),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.65,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── Generate ──────────────────────────────────────────────────

    def _generate(self, persona: Persona, topic: str) -> str:
        """Core generate — builds prompt from persona definition + quant data."""
        quant = self._build_quant_context_block()

        prompt = f"""{persona.system_prompt()}

DATE: {self.note_date}
TOPIC: {topic}

### RAW QUANTITATIVE DATA

{quant}

Now write the note.
"""

        return self._call_llm(prompt)

    def publish(self, persona_id: str = "macro_quant", topic: str = "", **kwargs) -> str:
        """Generate a research note with a specific persona.

        Args:
            persona_id: one of macro_quant, trade_read, onchain, options_greeks,
                       narrative_trader, risk_parity, morning_call, data_snapshot
            topic: custom topic override
        """
        persona = PERSONAS.get(persona_id)
        if not persona:
            available = ", ".join(PERSONAS.keys())
            raise ValueError(f"Unknown persona '{persona_id}'. Available: {available}")

        # Data snapshot skips LLM entirely
        if persona_id == "data_snapshot":
            return self._data_snapshot()

        self.gather(**kwargs)
        default_topics = {
            "macro_quant": "US equity factor book, regime check, sector rotation",
            "trade_read": "Trade setups across US + HK + crypto",
            "onchain": "Bitcoin and altcoin on-chain health check",
            "options_greeks": "Options market positioning and vol surface",
            "narrative_trader": "Thematic rotation and catalyst watch",
            "risk_parity": "Portfolio risk decomposition and correlation alert",
            "morning_call": "Pre-market briefing — what changed overnight",
        }
        resolved_topic = topic or default_topics.get(persona_id, "Market review")
        return self._generate(persona, resolved_topic)

    def _data_snapshot(self) -> str:
        """Generate pure data snapshot without LLM."""
        self.gather()
        lines = [f"## DATA SNAPSHOT — {self.note_date}", "---", ""]

        # Market overview table
        lines.append("### Market Overview")
        lines.append("| Ticker | Price | 1d% | 7d% | 30d% | RSI | ADX | Regime | Score |")
        lines.append("|--------|-------|-----|-----|------|-----|-----|--------|-------|")
        for sym in ["SPY", "QQQ", "IWM"]:
            m = self.factor_matrices.get(sym)
            snap = self.price_snapshots.get(sym)
            if m and snap:
                lines.append(
                    f"| {sym} | {snap.current_price:.2f} | {snap.change_1d_pct:+.2f}% | {snap.change_7d_pct:+.2f}% | {snap.change_30d_pct:+.2f}% | {m.technical.rsi_14:.1f} | {m.technical.adx:.1f} | {m.regime} | {m.composite_score:.1f} |"
                )
        lines.append("")

        # Macro
        lines.append("### Macro")
        lines.append("| Name | Value | 30d% |")
        lines.append("|------|-------|------|")
        for name, data in self.macro_data.items():
            lines.append(f"| {name} | {data['price']:.2f} | {data['change_30d']:+.2f}% |")
        lines.append("")

        # Score rankings
        lines.append("### Factor Score Rankings")
        all_scores = [
            (sym, m.composite_score, m.regime, m.trade_bias)
            for sym, m in self.factor_matrices.items()
        ]
        all_scores.sort(key=lambda x: x[1], reverse=True)
        top5 = all_scores[:5]
        bot5 = all_scores[-5:]
        lines.append("**Strongest 5:**")
        for sym, score, reg, bias in top5:
            lines.append(f"- {self._name(sym)} ({sym}): {score:.1f} [{reg}] [{bias}]")
        lines.append("**Weakest 5:**")
        for sym, score, reg, bias in bot5:
            lines.append(f"- {self._name(sym)} ({sym}): {score:.1f} [{reg}] [{bias}]")
        lines.append("")

        # Trade Read highlights
        lines.append("### Trade Read Highlights")
        lines.append("| Ticker | Bias | Conviction | Entry | Stop | Target | R:R |")
        lines.append("|--------|------|------------|-------|------|--------|-----|")
        biased = [(sym, m) for sym, m in self.factor_matrices.items() if m.trade_bias != "neutral"]
        for sym, m in biased[:8]:
            snap = self.price_snapshots.get(sym)
            if snap and m.stop_loss_level > 0:
                lines.append(
                    f"| {sym} | {m.trade_bias} | {m.conviction} | {snap.current_price:.2f} | {m.stop_loss_level:.2f} | {m.target_level:.2f} | {m.risk_reward_ratio:.2f} |"
                )
        lines.append("")

        return "\n".join(lines)
