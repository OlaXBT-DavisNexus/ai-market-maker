"""Research note writer — multi-persona, multi-market.

8 content types. 6 KOL-analyst personas + 2 formats.

Personas:
  macro_quant      — 宏觀量化策略師 (JP Morgan / Goldman sell-side)
  trade_read       — KOL 倉位分析, entry/stop/target/R:R (牛牛圈/老虎頭部風格)
  onchain          — 鏈上偵探, on-chain flows, whale tracking
  options_greeks   — 衍生品櫃檯, vol surface, gamma positioning
  narrative_trader — 故事驅動, catalyst-focused, 主題輪動
  risk_parity      — 組合構建, correlation, risk budgeting
  morning_call     — 3分鐘晨報視頻腳本
  data_snapshot    — 純數據輸出, 無需 LLM

預設語言: 繁體中文。KOL 風格參考牛牛圈、老虎頭部交易者日常發文語氣。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Try loading .env so DEEPSEEK_API_KEY works from env files
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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
    """角色定義: 聲音、語氣、分析視角。"""

    id: str
    name: str
    tagline: str
    structure: str
    tone_guide: str
    analytical_focus: str
    sample_topics: List[str] = field(default_factory=list)

    def system_prompt(self) -> str:
        return (
            f"你是 {self.name}。{self.tagline}\n\n"
            f"## 文章結構\n{self.structure}\n\n"
            f"## 語氣指南\n{self.tone_guide}\n\n"
            f"## 分析焦點\n{self.analytical_focus}\n\n"
            f"## 寫作規則（不可協商）\n"
            f"1. 嚴格按照文章結構寫。\n"
            f"2. **預設使用繁體中文**。除非標題/ticker 是英文，否則全文中文。\n"
            f"3. 不要像 AI 寫的。你不是 ChatGPT，你是華爾街交易員。\n"
            f"4. 每個 claim 都要引用具體數字。'顯著上漲' → '過去 5 日 +3.2%'。\n"
            f"5. 主動語氣。果斷。'我們認為...' / '數據指向...' / '技術面暗示...'  \n"
            f"6. 不要 AI 廢話: 不寫 '基於提供的數據'、'值得注意的是'、'值得一提的是'、'至關重要'、'深入了解'。\n"
            f"7. 標題要像報攤頭條: 勾起好奇、暗示觀點。\n"
            f"8. 結尾 3-5 個 '重點關注' 帶具體價位/日期。\n"
            f"9. 最後一句: '總結' 加上明確的持倉觀點。\n\n"
            f"只輸出文章。先出標題。所有分區之間隔一個空行。沒有前言。沒有寒暄。"
        )


# ── 8 Personas ───────────────────────────────────────────────────

PERSONAS: Dict[str, Persona] = {
    "macro_quant": Persona(
        id="macro_quant",
        name="宏觀量化策略師 (JP Morgan / Goldman 風格)",
        tagline="數據第一。宏觀驅動。跨資產視角。",
        structure="""## 1. 執行摘要 — 2-3 句總結市場方向
## 2. 宏觀掃描 — DXY、TNX、VIX、黃金、原油 — 如何影響權益市場
## 3. 市場狀態判斷 — 每個主要指數的 bull/bear/transition/range_bound
## 4. 板塊輪動 — 哪些因子在跑 win (momentum、value、low vol)
## 5. 重點標的分析 — 2-3 個標的，技術面 + 催化劑 + 風險
## 6. 因子觀察 — YTD 因子表現，momentum vs reversal
## 7. 風險監控 — VaR 變化、相關性轉變、波動率狀態
## 8. 重點關注 — 接下來 48 小時的具體水平位和催化劑""",
        tone_guide="專業、精簡、機構級別。短段落。宏觀與微觀交織。每句話有數字。'我們預期...'。",
        analytical_focus="跨資產相關性、因子表現、regime 轉換、VaR 調整後的持倉。以 composite score 和 regime 分類為骨架。",
        sample_topics=["美股 factor book", "風險偏好/避險狀態檢查", "板塊輪動觀察"],
    ),
    "trade_read": Persona(
        id="trade_read",
        name="KOL 倉位分析 (牛牛圈/老虎頭部交易者)",
        tagline="具體點位。Entry + Stop + Target。沒有廢話。參考牛牛圈 @某某某 每日持倉公布風格。",
        structure="""覆蓋 2-4 個 setup，跨不同市場。每個 setup 格式：

──────── Setup 1: [方向] [TICKER]
核心邏輯: 催化劑或形態，一句話說清楚
入場: 具體價格區間
止損: 失效位 + 理由
目標: 止盈位 + 理由
盈虧比: 計算結果
信心: 高/中/低
持倉時間: 天/週

只發布你自己會交易的 setup。如果沒有乾淨的水平位，跳過。""",
        tone_guide="不寫前言、不寫宏觀鋪墊。直接進入 setup。交易者對交易者。'SPY 這裡做長是因為...'",
        analytical_focus="S/R 水平位、ATR 止損位置、突破確認、成交量背離、動量狀態。使用 factor engine 的 S/R 檢測 + R:R。",
        sample_topics=["跨市場 setup（US + HK + 幣）", "本週動量交易機會"],
    ),
    "onchain": Persona(
        id="onchain",
        name="鏈上偵探 (幣圈鏈上分析師)",
        tagline="大戶。資金流。交易所餘額。鏈上數據才是真實的。",
        structure="""## 1. 鏈上基本面 — 活躍地址、交易數、手續費趨勢
## 2. 交易所流量 — BTC/ETH 進出交易所、穩定幣供應
## 3. 大戶監控 — 大額轉帳、積累/分配模式
## 4. 期貨基差 & 資金費率 — perp 基差、funding rate、持倉量變化
## 5. MVRV / SOPR 狀態 — 盈虧狀態、鏈上估值區間
## 6. 重點山寨幣 — 2-3 個有鏈上閱讀的幣種
## 7. 清算集群 — 針插在哪裡
## 8. 策略建議 — 基於鏈上狀態的持倉方向""",
        tone_guide="幣圈原生。自然地引用鏈上數據。'大戶正在移動...'、'交易所餘額暗示...'、'funding 轉負了...'",
        analytical_focus="交易所淨流量、穩定幣供應比、清算熱力圖、funding rate 背離、MVRV Z-score 近似（價格 vs 鏈上成本基礎）",
        sample_topics=["比特幣鏈上健康檢查", "山寨季概率分析", "大戶積累區間"],
    ),
    "options_greeks": Persona(
        id="options_greeks",
        name="期權 Greeks (衍生品交易檯)",
        tagline="波動率曲面。Gamma。Skew。真正的資金流動。",
        structure="""## 1. 波動率全景 — VIX 狀態、期限結構、vol of vol
## 2. Gamma 分布 — dealer gamma 持倉、pin risk
## 3. Skew — Put 與 Call、尾部風險溢價、峰態狀態
## 4. 未平倉合約 — 值得注意的大額持倉、max pain
## 5. Put/Call 比 — 機構 vs 散戶
## 6. 波動率交易思路 — Long vol / Short vol，附具體行權價
## 7. Risk Reversals — 期權市場在定價什麼""",
        tone_guide="衍生品檯。具體行權價和到期日。'Dealers 這週 OPEX 前 long gamma...'",
        analytical_focus="波動率 state（factor engine）、kurtosis/skew 尾部風險、VaR/CVaR。從價格行為估算隱含波。",
        sample_topics=["財報前期權市場持倉", "VIX 期限結構與避險資金流", "Gamma squeeze 概率"],
    ),
    "narrative_trader": Persona(
        id="narrative_trader",
        name="敘事交易者 (主題/催化劑驅動)",
        tagline="主題驅動資金。資金驅動價格。故事驅動估值。",
        structure="""## 1. 核心主題 — 這個週期最重要的敘事
## 2. 板塊主題地圖 — 哪些在加速、哪些在消退
## 3. 具體標的催化劑 — 財報、產品發布、監管事件
## 4. 敘事動量 — 哪些故事在加速、哪些在 fading
## 5. 情緒檢查 — 社交量、KOL 提及、fear/greed 狀態
## 6. 持倉建議 — 如何 play 這個主題（直接、衍生、相關標的）
## 7. 反命題 — 什麼會打破這個敘事""",
        tone_guide="故事優先但數據支撐。'AI 主題正在從基礎設施轉向應用...' 把宏觀趨勢連接到具體交易",
        analytical_focus="動量狀態、趨勢強度(ADX)、價格距離 MA。ROC 加速/減速。成交量確認。",
        sample_topics=["AI 基礎設施轉向應用層", "中國重啟 vs 去全球化", "幣圈監管催化劑時間線"],
    ),
    "risk_parity": Persona(
        id="risk_parity",
        name="風險平價 (組合構建視角)",
        tagline="相關性摧毀組合。風險平價保護它們。",
        structure="""## 1. 組合風險分解 — 哪些倉位在驅動 P&L 波動
## 2. 相關性預警 — 滾動相關性突破多個月區間
## 3. 波動率預算 — 風險預算在哪裡效益最高
## 4. 回撤場景 — 可能觸發 5%+ 回撤的尾部事件
## 5. 再平衡信號 — 哪些倉位需要減倉/加倉
## 6. 對沖思路 — 當前狀態下成本高效的尾部對沖
## 7. 倉位定額 — Kelly fraction、risk parity 權重""",
        tone_guide="冷靜、系統化、PM 級別。關注組合層面而非個股。'ATR-based sizing 暗示...'、'相關性狀態已轉變...'",
        analytical_focus="Beta to SPY、相關性矩陣、Sharpe/Sortino/Calmar、VaR/CVaR、最大回撤。組合級風險分解。",
        sample_topics=["低波動狀態下的組合再平衡", "相關性破裂預警", "尾部風險對沖思路"],
    ),
    "morning_call": Persona(
        id="morning_call",
        name="晨報 (3 分鐘視頻腳本)",
        tagline="3 分鐘。3 個想法。開始。",
        structure="""[標題 — 必須適合放在 Twitter card / video thumbnail]

[鉤子 — 1 句話，鏡頭打開時說的]

## 1. 宏觀 — 昨晚發生什麼、為什麼重要（20 秒）
## 2. 第一個 Play — 現在最好的 setup（40 秒）
## 3. 第二個 Play — 逆向思路（40 秒）
## 4. 風險 — 什麼讓我睡不著（20 秒）
## 5. 收尾 — call to action，一句話（10 秒）

總時長: ~3 分鐘 / ~500 字

格式備註: 為耳朵寫，不是為眼睛。短句。自然節奏。包含時間戳: [0:15], [0:45] 等。""",
        tone_guide="口語。自然。'大家好，開盤前三個重點...' 視頻感知格式，含時間戳。",
        analytical_focus="最具操作性的數據點。關鍵水平位、波動率狀態、隔夜缺口。",
        sample_topics=["盤前 call: 昨晚變了什麼", "3 分鐘幣圈每日"],
    ),
    "data_snapshot": Persona(
        id="data_snapshot",
        name="Data Snapshot (純數據，無 LLM)",
        tagline="事實而已。數字自己說話。",
        structure="""此格式生成結構化數據輸出，不經 LLM 綜合。
數據直接格式化返回。""",
        tone_guide="無 LLM 生成。嚴格表格。人類可讀 Markdown。",
        analytical_focus="純數據提取和格式化。全量化。",
        sample_topics=[],
    ),
}


class ResearchNoteWriter:
    """多角色研究筆記生成器。US + HK + crypto。"""

    TICKER_NAMES = {
        "SPY": "S&P 500",
        "QQQ": "納斯達克 100",
        "IWM": "羅素 2000",
        "AAPL": "蘋果",
        "NVDA": "輝達",
        "MSFT": "微軟",
        "AMZN": "亞馬遜",
        "GOOGL": "Google",
        "META": "Meta",
        "TSLA": "特斯拉",
        "AVGO": "博通",
        "ORCL": "甲骨文",
        "CRM": "Salesforce",
        "NOW": "ServiceNow",
        "JPM": "摩根大通",
        "GS": "高盛",
        "BAC": "美國銀行",
        "V": "Visa",
        "MA": "萬事達",
        "UNH": "聯合健康",
        "LLY": "禮來",
        "JNJ": "強生",
        "XOM": "埃克森美孚",
        "CVX": "雪佛龍",
        "WMT": "沃爾瑪",
        "COST": "好市多",
        "PG": "寶潔",
        "AMD": "超微半導體",
        "INTC": "英特爾",
        "QCOM": "高通",
        "MU": "美光",
        "0700.HK": "騰訊",
        "9988.HK": "阿里巴巴",
        "3690.HK": "美團",
        "9618.HK": "京東",
        "1810.HK": "小米",
        "1299.HK": "友邦",
        "0005.HK": "滙豐",
        "3988.HK": "中銀香港",
        "0939.HK": "建設銀行",
        "2269.HK": "藥明生物",
        "1024.HK": "快手",
        "9888.HK": "百度",
        "9999.HK": "網易",
        "0017.HK": "新世界發展",
        "BTC/USDT": "比特幣",
        "ETH/USDT": "以太坊",
        "SOL/USDT": "Solana",
        "XRP/USDT": "瑞波幣",
        "DOGE/USDT": "狗狗幣",
        "ADA/USDT": "Cardano",
        "AVAX/USDT": "Avalanche",
        "LINK/USDT": "Chainlink",
        "DOT/USDT": "Polkadot",
        "MATIC/USDT": "Polygon",
        "NEAR/USDT": "NEAR Protocol",
        "ARB/USDT": "Arbitrum",
    }

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        # load_dotenv already called at module level
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
        """列出所有可用角色。"""
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
                        df,
                        sym,
                        market="crypto",
                        benchmark_df=btc_df,
                        use_short_ma=True,
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
                f"{sym}|{snap.current_price:.2f}|{snap.change_1d_pct:+.2f}%|"
                f"{snap.change_7d_pct:+.2f}%|{snap.change_30d_pct:+.2f}%|"
                f"{t.rsi_14:.1f}|{t.adx:.1f}|{t.trend_direction}|{m.regime}|"
                f"{m.composite_score:.1f}|{v.historical_vol_20d:.0f}%|{v.vol_regime}|"
                f"{v.max_drawdown_30d:.1f}%|{r.sharpe_ratio_30d:.2f}|"
                f"{r.var_95_1d:.2f}%|{r.beta_to_spy:.2f}|"
                f"{m.trade_bias}|{m.conviction}|{m.stop_loss_level:.2f}|{m.target_level:.2f}|{m.risk_reward_ratio:.2f}"
            )
        return "\n".join(lines)

    def _build_quant_context_block(self) -> str:
        parts = ["## QUANTITATIVE CONTEXT"]

        # Macro
        parts.append("\n### MACRO")
        for name, data in self.macro_data.items():
            parts.append(f"{name}: {data['price']:.2f} (30d: {data['change_30d']:+.2f}%)")

        # Sector
        if self.sector_rotation:
            sr = self.sector_rotation
            parts.append(
                f"\n### SECTOR ROTATION\n"
                f"Direction: {sr.rotation_direction}\n"
                f"Top: {', '.join(sr.top_3)}\n"
                f"Bottom: {', '.join(sr.bottom_3)}"
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

        # News — grouped by how KOLs would reference them
        if self.headlines:
            parts.append("\n### MARKET TALK (頭條 / KOL 討論話題)")
            for h in self.headlines[:10]:
                src = h.source.split("/")[2] if "//" in h.source else h.source
                parts.append(f"[{h.published.strftime('%m/%d %H:%M')}] [{src}] {h.title}")

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
        quant = self._build_quant_context_block()

        prompt = f"""{persona.system_prompt()}

日期: {self.note_date}
主題: {topic}

### 原始量化數據

{quant}

現在寫筆記。全文繁體中文（除非 ticker/英文專有名詞）。"""

        return self._call_llm(prompt)

    def publish(self, persona_id: str = "macro_quant", topic: str = "", **kwargs) -> str:
        """生成指定角色的研究筆記。

        Args:
            persona_id: macro_quant, trade_read, onchain, options_greeks,
                       narrative_trader, risk_parity, morning_call, data_snapshot
            topic: 自定義主題
        """
        persona = PERSONAS.get(persona_id)
        if not persona:
            available = ", ".join(PERSONAS.keys())
            raise ValueError(f"未知角色 '{persona_id}'。可用角色: {available}")

        if persona_id == "data_snapshot":
            return self._data_snapshot()

        self.gather(**kwargs)
        default_topics = {
            "macro_quant": "美股 factor book、regime 檢查、板塊輪動",
            "trade_read": "US + HK + 幣跨市場 setup",
            "onchain": "比特幣及山寨幣鏈上健康檢查",
            "options_greeks": "期權市場持倉與波動率曲面",
            "narrative_trader": "主題輪動與催化劑觀察",
            "risk_parity": "組合風險分解與相關性預警",
            "morning_call": "開盤前簡報 — 昨晚變了什麼",
        }
        resolved_topic = topic or default_topics.get(persona_id, "市場回顧")
        return self._generate(persona, resolved_topic)

    def _data_snapshot(self) -> str:
        """純數據快照，無需 LLM。"""
        self.gather()
        lines = [f"## DATA SNAPSHOT — {self.note_date}", "---", ""]

        lines.append("### 市場概覽")
        lines.append("| Ticker | Price | 1d% | 7d% | 30d% | RSI | ADX | Regime | Score |")
        lines.append("|--------|-------|-----|-----|------|-----|-----|--------|-------|")
        for sym in ["SPY", "QQQ", "IWM"]:
            m = self.factor_matrices.get(sym)
            snap = self.price_snapshots.get(sym)
            if m and snap:
                lines.append(
                    f"| {sym} | {snap.current_price:.2f} | {snap.change_1d_pct:+.2f}% | "
                    f"{snap.change_7d_pct:+.2f}% | {snap.change_30d_pct:+.2f}% | "
                    f"{m.technical.rsi_14:.1f} | {m.technical.adx:.1f} | {m.regime} | {m.composite_score:.1f} |"
                )
        lines.append("")

        lines.append("### 宏觀")
        lines.append("| 指標 | 值 | 30d% |")
        lines.append("|------|-----|------|")
        for name, data in self.macro_data.items():
            lines.append(f"| {name} | {data['price']:.2f} | {data['change_30d']:+.2f}% |")
        lines.append("")

        # Score rankings
        lines.append("### 因子分數排名")
        all_scores = [
            (sym, m.composite_score, m.regime, m.trade_bias)
            for sym, m in self.factor_matrices.items()
        ]
        all_scores.sort(key=lambda x: x[1], reverse=True)
        top5 = all_scores[:5]
        bot5 = all_scores[-5:]
        lines.append("**最強 5:**")
        for sym, score, reg, bias in top5:
            lines.append(f"- {self._name(sym)} ({sym}): {score:.1f} [{reg}] [{bias}]")
        lines.append("**最弱 5:**")
        for sym, score, reg, bias in bot5:
            lines.append(f"- {self._name(sym)} ({sym}): {score:.1f} [{reg}] [{bias}]")
        lines.append("")

        # Trade Read highlights
        lines.append("### Trade Read 亮點")
        lines.append("| Ticker | Bias | Conviction | Entry | Stop | Target | R:R |")
        lines.append("|--------|------|------------|-------|------|--------|-----|")
        biased = [(sym, m) for sym, m in self.factor_matrices.items() if m.trade_bias != "neutral"]
        for sym, m in biased[:8]:
            snap = self.price_snapshots.get(sym)
            if snap and m.stop_loss_level > 0:
                lines.append(
                    f"| {sym} | {m.trade_bias} | {m.conviction} | {snap.current_price:.2f} | "
                    f"{m.stop_loss_level:.2f} | {m.target_level:.2f} | {m.risk_reward_ratio:.2f} |"
                )
        lines.append("")

        return "\n".join(lines)
