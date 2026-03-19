"""
News Collector Module
Fetches financial news from RSS feeds, NewsAPI, and stock-specific sources.
"""
import feedparser
import requests
from datetime import datetime, timedelta
from typing import Optional
import pytz
from dataclasses import dataclass, field
import re
import yaml


from src.config.settings import (
    NEWS_RSS_FEEDS,
    STOCK_NEWS_SOURCES,
    NEWS_API_KEY,
    NEWSAPI_SOURCES,
    TIMEZONE,
    HOURS_LOOKBACK,
    MAX_NEWS_ITEMS,
    CONFIG_DIR,
)


@dataclass
class NewsItem:
    """Represents a single news article."""
    title: str
    source: str
    url: str
    published: datetime
    summary: str = ""
    category: str = ""
    related_tickers: list = field(default_factory=list)
    is_analyst_rating: bool = False
    sentiment: str = ""  # bullish, bearish, neutral


class NewsCollector:
    """Collects news from multiple sources."""

    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)
        self.cutoff_time = datetime.now(self.tz) - timedelta(hours=HOURS_LOOKBACK)
        self.watchlist_symbols = self._load_watchlist_symbols()

    def _load_watchlist_symbols(self) -> set:
        """Load all stock symbols from watchlist."""
        symbols = set()
        stocks_file = CONFIG_DIR / "stocks.yaml"
        try:
            with open(stocks_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                for category, stocks in data.get("watchlist", {}).items():
                    for stock in stocks:
                        symbols.add(stock["symbol"])
        except Exception as e:
            print(f"Error loading watchlist: {e}")
        return symbols

    def collect_all(self) -> list[NewsItem]:
        """Collect news from all sources."""
        all_news = []

        # Collect from RSS feeds
        rss_news = self._collect_rss_feeds()
        all_news.extend(rss_news)

        # Collect from NewsAPI if available
        if NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here":
            api_news = self._collect_newsapi()
            all_news.extend(api_news)

        # Sort by publish time (newest first)
        all_news.sort(key=lambda x: x.published, reverse=True)

        # Remove duplicates based on title similarity
        all_news = self._deduplicate(all_news)

        # Tag related tickers
        all_news = self._tag_related_tickers(all_news)

        # Limit to max items
        return all_news[:MAX_NEWS_ITEMS]

    def collect_stock_specific_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """Collect news specific to given stock symbols."""
        stock_news = {}

        for symbol in symbols:
            news_items = []

            # Try Yahoo Finance RSS
            try:
                url = STOCK_NEWS_SOURCES["yahoo_finance"].format(symbol=symbol)
                items = self._parse_rss_feed(url, f"Yahoo/{symbol}", "stock_news")
                news_items.extend(items[:5])  # Limit per source
            except Exception as e:
                pass  # Silently skip if feed unavailable

            if news_items:
                stock_news[symbol] = news_items

        return stock_news

    def _collect_rss_feeds(self) -> list[NewsItem]:
        """Collect news from RSS feeds."""
        news_items = []

        for source_name, feeds in NEWS_RSS_FEEDS.items():
            for category, url in feeds.items():
                try:
                    items = self._parse_rss_feed(url, source_name, category)
                    news_items.extend(items)
                except Exception as e:
                    # Only print error for expected feeds
                    if source_name in ["wsj", "ft", "nyt"]:
                        print(f"Error fetching RSS from {source_name}/{category}: {e}")

        return news_items

    def _parse_rss_feed(self, url: str, source: str, category: str) -> list[NewsItem]:
        """Parse a single RSS feed."""
        items = []

        try:
            # Use requests with timeout, then parse the content
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            feed = feedparser.parse(resp.content)
        except Exception:
            return items

        for entry in feed.entries:
            try:
                # Parse published time
                published = self._parse_time(entry)
                if published is None:
                    # Use current time if no publish time
                    published = datetime.now(self.tz)

                # Skip if older than cutoff (but be lenient)
                if published < self.cutoff_time - timedelta(hours=6):
                    continue

                # Check if this is an analyst rating
                is_analyst = "analyst" in category.lower() or "rating" in entry.get("title", "").lower()

                item = NewsItem(
                    title=entry.get("title", "").strip(),
                    source=source.upper(),
                    url=entry.get("link", ""),
                    published=published,
                    summary=self._clean_summary(entry.get("summary", "")),
                    category=category,
                    is_analyst_rating=is_analyst,
                )

                if item.title:  # Only add if title exists
                    items.append(item)

            except Exception as e:
                continue

        return items

    def _parse_time(self, entry) -> Optional[datetime]:
        """Parse published time from feed entry."""
        time_fields = ["published_parsed", "updated_parsed", "created_parsed"]

        for field in time_fields:
            time_struct = entry.get(field)
            if time_struct:
                try:
                    dt = datetime(*time_struct[:6])
                    if dt.tzinfo is None:
                        dt = self.tz.localize(dt)
                    return dt.astimezone(self.tz)
                except Exception:
                    continue

        # Try parsing string dates
        date_fields = ["published", "updated", "created"]
        for field in date_fields:
            date_str = entry.get(field, "")
            if date_str:
                try:
                    from dateutil import parser
                    dt = parser.parse(date_str)
                    if dt.tzinfo is None:
                        dt = self.tz.localize(dt)
                    return dt.astimezone(self.tz)
                except Exception:
                    continue

        return None

    def _clean_summary(self, summary: str) -> str:
        """Clean HTML tags from summary."""
        clean = re.sub(r"<[^>]+>", "", summary)
        clean = re.sub(r"\s+", " ", clean).strip()
        # Remove common RSS boilerplate
        clean = re.sub(r"Continue reading.*$", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"Read more.*$", "", clean, flags=re.IGNORECASE)
        return clean[:500] if len(clean) > 500 else clean

    def _collect_newsapi(self) -> list[NewsItem]:
        """Collect news from NewsAPI."""
        if not NEWS_API_KEY or NEWS_API_KEY == "your_newsapi_key_here":
            return []

        news_items = []
        base_url = "https://newsapi.org/v2/top-headlines"

        params = {
            "apiKey": NEWS_API_KEY,
            "sources": NEWSAPI_SOURCES,
            "pageSize": 20,
        }

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            for article in data.get("articles", []):
                published_str = article.get("publishedAt", "")
                if published_str:
                    published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    published = published.astimezone(self.tz)

                    if published >= self.cutoff_time:
                        item = NewsItem(
                            title=article.get("title", "").strip(),
                            source=article.get("source", {}).get("name", "NewsAPI"),
                            url=article.get("url", ""),
                            published=published,
                            summary=article.get("description", "") or "",
                            category="finance",
                        )
                        news_items.append(item)

        except Exception as e:
            print(f"Error fetching from NewsAPI: {e}")

        return news_items

    def _deduplicate(self, items: list[NewsItem]) -> list[NewsItem]:
        """Remove duplicate news items based on title similarity."""
        seen_titles = set()
        unique_items = []

        for item in items:
            # Normalize title for comparison
            normalized = re.sub(r'[^\w\s]', '', item.title.lower())[:50]
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique_items.append(item)

        return unique_items

    def _tag_related_tickers(self, items: list[NewsItem]) -> list[NewsItem]:
        """Tag news items with related stock tickers from watchlist."""
        # Common company name to ticker mapping
        company_mappings = {
            # Tech giants
            "apple": "AAPL", "microsoft": "MSFT", "amazon": "AMZN",
            "google": "GOOGL", "alphabet": "GOOGL", "meta": "META",
            "facebook": "META", "nvidia": "NVDA", "tesla": "TSLA",
            "netflix": "NFLX", "paypal": "PYPL", "amd": "AMD",
            "intel": "INTC", "qualcomm": "QCOM", "broadcom": "AVGO",
            # Consumer
            "walmart": "WMT", "coca-cola": "KO", "nike": "NKE",
            "airbnb": "ABNB", "booking": "BKNG", "expedia": "EXPE",
            "carnival": "CCL", "hilton": "HLT", "marriott": "MAR",
            # China
            "pinduoduo": "PDD", "alibaba": "BABA", "baidu": "BIDU",
            # Healthcare / Pharma
            "moderna": "MRNA", "pfizer": "PFE", "gilead": "GILD",
            "unitedhealth": "UNH", "eli lilly": "LLY", "lilly": "LLY",
            "johnson & johnson": "JNJ", "j&j": "JNJ",
            "abbvie": "ABBV", "astrazeneca": "AZN",
            "thermo fisher": "TMO", "intuitive surgical": "ISRG",
            "veeva": "VEEV", "humira": "ABBV", "ozempic": "LLY",
            "mounjaro": "LLY", "zepbound": "LLY", "wegovy": "LLY",
        }

        for item in items:
            text = f"{item.title} {item.summary}".lower()
            related = []

            # Check for ticker symbols directly (e.g., $AAPL or AAPL)
            for symbol in self.watchlist_symbols:
                if re.search(rf'\b{symbol}\b', text, re.IGNORECASE) or f"${symbol.lower()}" in text:
                    related.append(symbol)

            # Check for company names
            for company, ticker in company_mappings.items():
                if company in text and ticker in self.watchlist_symbols:
                    if ticker not in related:
                        related.append(ticker)

            item.related_tickers = related[:5]  # Limit to 5 tickers per article

        return items

    def get_news_by_ticker(self, items: list[NewsItem], ticker: str) -> list[NewsItem]:
        """Filter news items related to a specific ticker."""
        return [item for item in items if ticker in item.related_tickers]

    def get_analyst_ratings(self, items: list[NewsItem]) -> list[NewsItem]:
        """Get analyst rating news items."""
        return [item for item in items if item.is_analyst_rating]


def main():
    """Test the news collector."""
    collector = NewsCollector()
    news = collector.collect_all()

    print(f"\n=== Collected {len(news)} news items ===\n")

    # Group by source
    by_source = {}
    for item in news:
        if item.source not in by_source:
            by_source[item.source] = 0
        by_source[item.source] += 1

    print("By source:")
    for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")

    print("\n--- Sample news ---\n")
    for item in news[:10]:
        tickers = f" [{', '.join(item.related_tickers)}]" if item.related_tickers else ""
        print(f"[{item.source}] {item.title}{tickers}")
        print(f"  Time: {item.published.strftime('%Y-%m-%d %H:%M')}")
        print()


if __name__ == "__main__":
    main()
