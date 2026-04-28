"""Finance feed publisher — one-shot runnable script.

Pull market data → news → generate article → stdout.
"""

from .generator import FeedArticleGenerator


def run(markets=None, topic="market overview") -> str:
    """Generate and return a fully formatted feed article.

    Usage:
        from backtest.feed.publisher import run
        article = run(markets=["crypto"], topic="BTC volatility")
        print(article)
    """
    gen = FeedArticleGenerator(markets=markets)
    return gen.generate(topic=topic)


if __name__ == "__main__":
    import sys

    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "market overview"
    print(run(topic=topic))
