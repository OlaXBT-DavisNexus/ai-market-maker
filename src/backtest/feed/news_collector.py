"""Fetch crypto/equity news from free RSS feeds (no API key)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

import requests

# ── public RSS feeds (zero auth) ────────────────────────────────────────

RSS_SOURCES: Dict[str, str] = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
    "cointelegraph": "https://cointelegraph.com/rss",
    "blockworks": "https://blockworks.co/feed/",
    "decrypt": "https://decrypt.co/feed",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "newsbtc": "https://www.newsbtc.com/feed/",
    "bitcoinmagazine": "https://bitcoinmagazine.com/feed",
}

CRYPTO_NEWS_API = "https://cryptocurrency.cv/api/news"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    tickers: List[str] = field(default_factory=list)


def fetch_rss(url: str, timeout: float = 15) -> List[NewsItem]:
    """Fetch and parse a single RSS feed into NewsItems."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "AIMM/1.0"})
        resp.raise_for_status()
    except Exception as exc:
        print(f"[WARN] RSS fetch failed {url}: {exc}")
        return []

    items: List[NewsItem] = []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return items

    for item_elem in root.iter("item"):
        title_el = item_elem.find("title")
        link_el = item_elem.find("link")
        date_el = item_elem.find("pubDate")
        desc_el = item_elem.find("description")

        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue

        link = (link_el.text or "").strip() if link_el is not None else ""

        pub_date = None
        if date_el is not None and date_el.text:
            try:
                pub_date = datetime.strptime(date_el.text.strip(), "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                pub_date = datetime.now(timezone.utc)

        summary = (desc_el.text or "").strip() if desc_el is not None else ""

        items.append(
            NewsItem(
                title=title,
                url=link,
                source=url,
                published=pub_date or datetime.now(timezone.utc),
                summary=summary,
            )
        )

    return items


def fetch_cryptocurrency_cv(ticker: str | None = None, limit: int = 10) -> List[NewsItem]:
    """Fetch news from the free cryptocurrency.cv API."""
    params = {"limit": str(limit)}
    if ticker:
        params["ticker"] = ticker
    try:
        resp = requests.get(CRYPTO_NEWS_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[WARN] cryptocurrency.cv fetch failed: {exc}")
        return []

    items: List[NewsItem] = []
    for art in data.get("articles", []):
        items.append(
            NewsItem(
                title=art.get("title", ""),
                url=art.get("url", ""),
                source=art.get("source", "cryptocurrency.cv"),
                published=datetime.fromisoformat(art["created_at"])
                if art.get("created_at")
                else datetime.now(timezone.utc),
                summary=art.get("description", ""),
                tickers=art.get("tickers", []),
            )
        )
    return items


def collect_headlines(sources: List[str] | None = None, max_per_source: int = 5) -> List[NewsItem]:
    """Collect the latest headlines from all RSS feeds + API."""
    items: List[NewsItem] = []

    rss_to_use = {k: v for k, v in RSS_SOURCES.items() if sources is None or k in sources}
    for _name, url in rss_to_use.items():
        fetched = fetch_rss(url)[:max_per_source]
        items.extend(fetched)

    # crypto news API
    apis = fetch_cryptocurrency_cv(limit=max_per_source)
    items.extend(apis)

    items.sort(key=lambda x: x.published, reverse=True)
    return items
