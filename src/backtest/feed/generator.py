"""Finance feed article generator — hedge-fund-analyst-level writing.

Pipeline:
  1. Collect market data  (OHLCV + metrics via loaders)
  2. Collect headlines    (RSS + free APIs)
  3. Synthesise article   (LLM with structured prompt + example tone)
  4. Return publishable text
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

from .market_data import SUPPORTED_MARKETS, compute_metrics, fetch_market_data
from .news_collector import collect_headlines

DEFAULT_MODEL = os.environ.get("FEED_LLM_MODEL", "deepseek/deepseek-chat")
# Which markets to cover in each article
DEFAULT_MARKETS = ["crypto", "us_equity"]

_SAMPLE_TONE = """\
### CHINA CRYPTO LEADS WEEKLY ROUNDUP: BITCOIN SIDEWAYS, ALTCOINS RIP, AND THE FED DOESN'T CARE

Bitcoin spent another week consolidating between $84K and $87K while the real action happened elsewhere. SOL ripped 18% on the back of Firedancer testnet news, memecoins on Pump.fun printed another $200M in volume, and the Fed minutes revealed... nothing new. Macro remains a non-event for crypto, which frankly is bullish.

The standout narrative this week: Chinese-linked crypto projects. Conflux (CFX) +32%, Neo +28%, and even VeChain (+19%) caught a bid after rumors of a Hong Kong crypto ETF product expansion. Whether the rumors hold water doesn't matter — the market is pricing in the bet.

On the equities side, SPY barely budged (+0.4%) but the Mag Seven saw rotation. NVDA flat, AAPL +2.1% on services revenue beat, TSLA -4.3% on delivery miss headlines. The AI trade is taking a breather but the structural bid remains.

### What we're watching this week:
1. BTC weekly close — losing $84K support opens $78K
2. Hong Kong SFC commentary on retail crypto access
3. NVIDIA earnings whisper numbers leaking
4. SOL / ETH ratio — SOL grinding higher vs ETH for 5th straight week

Bottom line: risk-on with sector rotation. Altcoins > majors. China narrative > everything else. Position accordingly.
"""


class FeedArticleGenerator:
    """Generate publishable finance articles from raw market data + news."""

    def __init__(
        self,
        markets: Optional[List[str]] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.markets = markets or DEFAULT_MARKETS
        self.model = model or DEFAULT_MODEL
        self.api_key = (
            api_key or os.environ.get("FEED_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
        )

    def generate(self, topic: str = "market overview") -> str:
        """Collect data and generate a complete feed article."""
        data_context = self._gather_data()
        return self._synthesize(topic, data_context)

    def _gather_data(self) -> Dict:
        context: Dict = {"markets": {}, "headlines": []}

        for market in self.markets:
            symbols = SUPPORTED_MARKETS.get(market, [])
            dfs = fetch_market_data(market, start="2026-03-28", end="2026-04-28")
            metrics = compute_metrics(dfs)
            context["markets"][market] = {"symbols": symbols, "metrics": metrics}
            # Raw prices
            raw = {}
            for sym, df in dfs.items():
                if not df.empty and len(df) > 0:
                    price_data = []
                    for idx, row in df.tail(30).iterrows():
                        price_data.append(
                            {
                                "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                                "close": float(row["close"]),
                                "volume": float(row["volume"]),
                            }
                        )
                    raw[sym] = price_data
            context["markets"][market]["prices"] = raw

        # Headlines
        news = collect_headlines(max_per_source=3)
        context["headlines"] = [
            {"title": n.title, "source": n.source, "published": n.published.isoformat()}
            for n in news[:25]
        ]

        return context

    def _synthesize(self, topic: str, data: Dict) -> str:
        """Call LLM to write a publishable article."""
        metrics_summary = self._format_metrics(data["markets"])
        headlines = "\n".join(f"- {h['title']} ({h['source']})" for h in data["headlines"][:15])

        prompt = f"""You are a veteran hedge fund analyst writing for a finance newsletter read by institutional traders, crypto funds, and sophisticated retail. Write a ~500-800 word weekly market roundup article.

TOPIC: {topic}

## Market Data (past 30 days)
{metrics_summary}

## Headlines in the Last Hour
{headlines}

## Style Guide
- Write like a human finance editor. NOT a language model.
- No engineering-speak, no "based on the data", no "I've analyzed".
- Use a hook statement to open. Strong opinion. Specific numbers.
- Reference credible headlines naturally woven in.
- Include a "What we're watching" section with 3-5 forward-looking bullets.
- End with a bottom-line positioning take.
- Tone: sharp, informed, slightly cynical. Like reading a Morning Briefing from a top-tier desk.

## Sample Tone (DO NOT COPY CONTENT — match voice)
{_SAMPLE_TONE}

Output ONLY the article. No preamble, no "Here's your article", no markdown formatting in the output besides plain text paragraphs and bullet points. Use line breaks to separate sections."""

        return self._llm_call(prompt)

    def _llm_call(self, prompt: str) -> str:
        """Call the configured LLM provider."""
        if self.model.startswith("deepseek/"):
            return self._call_openai_compat(
                "https://api.deepseek.com/v1/chat/completions",
                self.model.replace("deepseek/", ""),
                prompt,
            )

        # Generic OpenAI-compatible fallback
        base = os.environ.get("FEED_LLM_BASE_URL", "https://api.deepseek.com")
        return self._call_openai_compat(
            urljoin(base, "/v1/chat/completions"),
            self.model,
            prompt,
        )

    def _call_openai_compat(self, url: str, model: str, prompt: str) -> str:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a veteran finance newsletter editor. Write like a human, not an AI.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _format_metrics(markets: Dict) -> str:
        lines: List[str] = []
        for market, mkt_data in markets.items():
            lines.append(f"\n### {market.upper()}")
            for sym, met in mkt_data["metrics"].items():
                if not met:
                    continue
                lines.append(f"  {sym}:")
                for k, v in met.items():
                    if v is None:
                        continue
                    if isinstance(v, float):
                        lines.append(f"    {k}: {v:.2f}")
                    else:
                        lines.append(f"    {k}: {v}")
        return "\n".join(lines)
