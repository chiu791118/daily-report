"""
Global settings and configuration for Daily Market Digest.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_DIR = PROJECT_ROOT / "src" / "config"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

FMP_API_KEY = os.getenv("FMP_API_KEY")
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY")

# Webshare Proxy (optional - for YouTube transcript fetching)
WEBSHARE_PROXY_USERNAME = os.getenv("WEBSHARE_PROXY_USERNAME")
WEBSHARE_PROXY_PASSWORD = os.getenv("WEBSHARE_PROXY_PASSWORD")

# News RSS Feeds - Expanded sources
NEWS_RSS_FEEDS = {
    # === 主流財經媒體 ===
    "wsj": {
        "markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "world": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "business": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
        "tech": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
    },
    "bloomberg": {
        "markets": "https://feeds.bloomberg.com/markets/news.rss",
        "technology": "https://feeds.bloomberg.com/technology/news.rss",
        "politics": "https://feeds.bloomberg.com/politics/news.rss",
    },
    "reuters": {
        "business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
        "markets": "https://www.reutersagency.com/feed/?best-topics=markets&post_type=best",
        "tech": "https://www.reutersagency.com/feed/?best-topics=tech&post_type=best",
    },
    "ft": {
        "home": "https://www.ft.com/?format=rss",
        "markets": "https://www.ft.com/markets?format=rss",
        "companies": "https://www.ft.com/companies?format=rss",
    },
    "nyt": {
        "business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "economy": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
        "technology": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    },
    "cnbc": {
        "top": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "world": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
        "investing": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    },
    "seekingalpha": {
        "market_news": "https://seekingalpha.com/market_currents.xml",
        "top_ideas": "https://seekingalpha.com/tag/top-ideas.xml",
    },
    "benzinga": {
        "news": "https://www.benzinga.com/feeds/news",
        "analyst_ratings": "https://www.benzinga.com/feeds/analyst-ratings",
    },
    # === 科技/AI ===
    "techcrunch": {
        "ai": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "startups": "https://techcrunch.com/category/startups/feed/",
    },
    "theverge": {
        "tech": "https://www.theverge.com/rss/index.xml",
    },
    "arstechnica": {
        "tech": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    },
    "wired": {
        "business": "https://www.wired.com/feed/category/business/latest/rss",
        "gear": "https://www.wired.com/feed/category/gear/latest/rss",
    },
    # === 醫療/生技 ===
    "statnews": {
        "pharma": "https://www.statnews.com/feed/",
    },
    "fiercepharma": {
        "news": "https://www.fiercepharma.com/rss/xml",
    },
    "fiercebiotech": {
        "news": "https://www.fiercebiotech.com/rss/xml",
    },
    "biopharmadive": {
        "news": "https://www.biopharmadive.com/feeds/news/",
    },
    # === 電動車/能源 ===
    "electrek": {
        "ev": "https://electrek.co/feed/",
    },
    "cleantechnica": {
        "energy": "https://cleantechnica.com/feed/",
    },
    "insideevs": {
        "news": "https://insideevs.com/rss/news/",
    },
    # === 半導體 ===
    "tomshardware": {
        "news": "https://www.tomshardware.com/feeds/all",
    },
    "anandtech": {
        "news": "https://www.anandtech.com/rss/",
    },
    # === 早期信號 (Hacker News) ===
    "hackernews": {
        "front": "https://hnrss.org/frontpage",
        "best": "https://hnrss.org/best",
    },
}

# Stock-specific news sources (for individual ticker lookups)
STOCK_NEWS_SOURCES = {
    "yahoo_finance": "https://finance.yahoo.com/rss/headline?s={symbol}",
    "seeking_alpha": "https://seekingalpha.com/api/sa/combined/{symbol}.xml",
}

# NewsAPI settings (backup)
NEWSAPI_SOURCES = "bloomberg,business-insider,financial-times,the-wall-street-journal,cnbc"
NEWSAPI_CATEGORIES = ["business", "technology"]

# Gemini settings
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_TEMPERATURE = 0.3
GEMINI_MAX_OUTPUT_TOKENS = 16384  # Increased for deeper analysis

# Report settings
MAX_NEWS_ITEMS = 30  # Increased for more comprehensive coverage
MAX_YOUTUBE_VIDEOS = 10
HOURS_LOOKBACK = 24  # Look back 24 hours for new content

# Stock filtering settings
MIN_PRICE_CHANGE_PERCENT = 3.0  # Only show stocks with >= 3% change

# Timezone
TIMEZONE = "Asia/Taipei"
US_EASTERN_TZ = "US/Eastern"

# Economic calendar settings
ECONOMIC_CALENDAR_COUNTRIES = [
    c.strip() for c in os.getenv("ECONOMIC_CALENDAR_COUNTRIES", "United States").split(",")
    if c.strip()
]
ECONOMIC_CALENDAR_IMPORTANCE_MIN = int(os.getenv("ECONOMIC_CALENDAR_IMPORTANCE_MIN", "2"))

# Universe settings
UNIVERSE_INCLUDE_SP500 = os.getenv("UNIVERSE_INCLUDE_SP500", "true").lower() in ("1", "true", "yes", "y")
UNIVERSE_ETF_HOLDINGS = [
    s.strip().upper() for s in os.getenv("UNIVERSE_ETF_HOLDINGS", "QQQ,IWM,SOXX").split(",")
    if s.strip()
]
UNIVERSE_CACHE_HOURS = int(os.getenv("UNIVERSE_CACHE_HOURS", "24"))
