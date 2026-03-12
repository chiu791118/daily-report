"""
SEC EDGAR Collector Module
Fetches SEC filings (8-K, 10-Q, 10-K) from EDGAR.
"""
import feedparser
import requests
from datetime import datetime, timedelta
from typing import Optional
import pytz
import re
import time


from src.collectors.base import IntelItem, SourceType, BaseCollector
from src.config.settings import TIMEZONE


# CIK mapping for major companies (can be extended)
# CIK is SEC's Central Index Key for company identification
COMPANY_CIK_MAP = {
    # Tech / AI
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "NVDA": "0001045810",
    "AMD": "0000002488",
    "INTC": "0000050863",
    "TSLA": "0001318605",
    "NFLX": "0001065280",
    # Semiconductor
    "TSM": "0001046179",
    "AVGO": "0001730168",
    "QCOM": "0000804328",
    "MU": "0000723125",
    "AMAT": "0000006951",
    "LRCX": "0000707549",
    # Healthcare
    "LLY": "0000059478",
    "NVO": "0000353278",
    "MRNA": "0001682852",
    "PFE": "0000078003",
    "JNJ": "0000200406",
    "ABBV": "0001551152",
    "MRK": "0000310158",
    "UNH": "0000731766",
    "ISRG": "0001035267",
    # Consumer
    "WMT": "0000104169",
    "COST": "0000909832",
    "NKE": "0000320187",
    "SBUX": "0000829224",
    "MCD": "0000063908",
    # Finance
    "JPM": "0000019617",
    "GS": "0000886982",
    "BAC": "0000070858",
    "V": "0001403161",
    "MA": "0001141391",
    # Energy
    "XOM": "0000034088",
    "CVX": "0000093410",
    # Industrial
    "CAT": "0000018230",
    "HON": "0000773840",
    "GE": "0000040545",
    # Travel
    "DAL": "0000027904",
    "UAL": "0000100517",
    "BA": "0000012927",
    "BKNG": "0001075531",
    "ABNB": "0001559720",
}

# 8-K Item descriptions (most important ones)
ITEM_8K_DESCRIPTIONS = {
    "1.01": "Entry into Material Agreement",
    "1.02": "Termination of Material Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition/Disposition",
    "2.02": "Results of Operations (Earnings)",
    "2.03": "Creation of Direct Financial Obligation",
    "2.04": "Triggering Events for Acceleration",
    "2.05": "Costs for Exit/Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting",
    "3.02": "Unregistered Sales of Equity",
    "3.03": "Material Modification of Securities",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Financial Statements",
    "5.01": "Changes in Control",
    "5.02": "Departure/Election of Directors/Officers",
    "5.03": "Amendments to Articles/Bylaws",
    "5.04": "Temporary Suspension of Trading",
    "5.05": "Amendments to Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to Vote",
    "5.08": "Shareholder Nominations",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


class SECEdgarCollector(BaseCollector):
    """
    Collects SEC EDGAR filings.
    - 8-K: Material events (most time-sensitive)
    - 10-Q: Quarterly reports
    - 10-K: Annual reports
    """

    # SEC requires user-agent header
    HEADERS = {
        "User-Agent": "DailyMarketDigest/1.0 (contact@example.com)",
        "Accept-Encoding": "gzip, deflate",
    }

    # RSS feed URLs
    RECENT_FILINGS_RSS = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form_type}&company=&dateb=&owner=include&count={count}&output=atom"
    COMPANY_FILINGS_RSS = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=include&count={count}&output=atom"

    # Full-text search API (for more detailed queries)
    SEARCH_API = "https://efts.sec.gov/LATEST/search-index"

    def __init__(self):
        super().__init__()
        self.tz = pytz.timezone(TIMEZONE)

    def collect_recent_filings(
        self,
        form_types: list = None,
        hours_lookback: int = 168,  # 1 week
        max_per_type: int = 50,
    ) -> list[IntelItem]:
        """
        Collect recent filings across all companies.

        Args:
            form_types: List of form types to collect (default: ["8-K", "10-Q", "10-K"])
            hours_lookback: How far back to look
            max_per_type: Max filings per form type

        Returns:
            List of IntelItem objects
        """
        if form_types is None:
            form_types = ["8-K", "10-Q", "10-K"]

        cutoff_time = datetime.now(self.tz) - timedelta(hours=hours_lookback)
        all_items = []

        for form_type in form_types:
            try:
                url = self.RECENT_FILINGS_RSS.format(
                    form_type=form_type,
                    count=max_per_type
                )
                items = self._parse_edgar_rss(url, form_type, cutoff_time)
                all_items.extend(items)
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                print(f"Error fetching {form_type} filings: {e}")

        # Sort by date (newest first)
        all_items.sort(key=lambda x: x.published, reverse=True)

        return all_items

    def collect_company_filings(
        self,
        tickers: list = None,
        form_types: list = None,
        days_lookback: int = 30,
    ) -> list[IntelItem]:
        """
        Collect filings for specific companies.

        Args:
            tickers: List of stock tickers (uses COMPANY_CIK_MAP)
            form_types: List of form types
            days_lookback: How far back to look

        Returns:
            List of IntelItem objects
        """
        if tickers is None:
            tickers = list(COMPANY_CIK_MAP.keys())
        if form_types is None:
            form_types = ["8-K", "10-Q"]

        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)
        all_items = []

        for ticker in tickers:
            cik = COMPANY_CIK_MAP.get(ticker)
            if not cik:
                continue

            for form_type in form_types:
                try:
                    url = self.COMPANY_FILINGS_RSS.format(
                        cik=cik,
                        form_type=form_type,
                        count=10
                    )
                    items = self._parse_edgar_rss(
                        url, form_type, cutoff_time, ticker=ticker
                    )
                    all_items.extend(items)
                    time.sleep(0.1)  # Rate limiting
                except Exception as e:
                    print(f"Error fetching {ticker} {form_type}: {e}")

        # Sort by date (newest first)
        all_items.sort(key=lambda x: x.published, reverse=True)

        return all_items

    def _parse_edgar_rss(
        self,
        url: str,
        form_type: str,
        cutoff_time: datetime,
        ticker: str = None,
    ) -> list[IntelItem]:
        """Parse SEC EDGAR RSS feed."""
        items = []

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"Error parsing feed: {e}")
            return items

        for entry in feed.entries:
            try:
                # Parse date
                published = self._parse_date(entry)
                if published and published < cutoff_time:
                    continue

                # Extract company info from title
                title = entry.get("title", "")
                company_name, extracted_form = self._parse_title(title)

                # Extract CIK from link
                link = entry.get("link", "")
                cik = self._extract_cik(link)

                # Determine ticker if not provided
                if not ticker and cik:
                    ticker = self._cik_to_ticker(cik)

                # Get filing summary/description
                summary = entry.get("summary", "")

                # For 8-K, try to extract items
                items_reported = []
                if form_type == "8-K":
                    items_reported = self._extract_8k_items(summary)

                # Create IntelItem
                item = IntelItem(
                    title=f"[{form_type}] {company_name}",
                    source="SEC",
                    source_type=SourceType.SEC_FILING,
                    url=link,
                    published=published or datetime.now(self.tz),
                    summary=self._format_summary(form_type, items_reported, summary),
                    category=form_type,
                    related_tickers=[ticker] if ticker else [],
                    metadata={
                        "form_type": form_type,
                        "cik": cik,
                        "company_name": company_name,
                        "items": items_reported,
                    }
                )

                # Tag additional entities
                item = self.tag_entities(item)
                items.append(item)

            except Exception as e:
                continue

        return items

    def _parse_date(self, entry) -> Optional[datetime]:
        """Parse date from feed entry."""
        date_fields = ["updated_parsed", "published_parsed"]

        for field in date_fields:
            time_struct = entry.get(field)
            if time_struct:
                try:
                    dt = datetime(*time_struct[:6])
                    if dt.tzinfo is None:
                        dt = pytz.UTC.localize(dt)
                    return dt.astimezone(self.tz)
                except Exception:
                    continue

        # Try string parsing
        for field in ["updated", "published"]:
            date_str = entry.get(field, "")
            if date_str:
                try:
                    from dateutil import parser
                    dt = parser.parse(date_str)
                    if dt.tzinfo is None:
                        dt = pytz.UTC.localize(dt)
                    return dt.astimezone(self.tz)
                except Exception:
                    continue

        return None

    def _parse_title(self, title: str) -> tuple:
        """Parse company name and form type from title."""
        # Title format: "8-K - Company Name Inc (0001234567) (Filer)"
        match = re.match(r'([\d\-A-Z/]+)\s*-\s*(.+?)\s*\(', title)
        if match:
            form_type = match.group(1).strip()
            company_name = match.group(2).strip()
            return company_name, form_type
        return title, ""

    def _extract_cik(self, url: str) -> str:
        """Extract CIK from URL."""
        match = re.search(r'CIK=(\d+)', url, re.IGNORECASE)
        if match:
            return match.group(1).zfill(10)
        match = re.search(r'/(\d{10})/', url)
        if match:
            return match.group(1)
        return ""

    def _cik_to_ticker(self, cik: str) -> str:
        """Convert CIK to ticker symbol."""
        cik_padded = cik.zfill(10)
        for ticker, company_cik in COMPANY_CIK_MAP.items():
            if company_cik == cik_padded:
                return ticker
        return ""

    def _extract_8k_items(self, text: str) -> list:
        """Extract 8-K item numbers from text."""
        items = []
        # Match patterns like "Item 2.02" or "2.02"
        pattern = r'Item\s*(\d+\.\d+)|(?:^|\s)(\d+\.\d+)(?:\s|$)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        for match in matches:
            item_num = match[0] or match[1]
            if item_num in ITEM_8K_DESCRIPTIONS:
                items.append(f"Item {item_num}")

        return list(set(items))

    def _format_summary(
        self,
        form_type: str,
        items_reported: list,
        raw_summary: str
    ) -> str:
        """Format a human-readable summary."""
        parts = []

        if form_type == "8-K" and items_reported:
            item_descs = []
            for item in items_reported:
                item_num = item.replace("Item ", "")
                if item_num in ITEM_8K_DESCRIPTIONS:
                    item_descs.append(f"{item}: {ITEM_8K_DESCRIPTIONS[item_num]}")
            if item_descs:
                parts.append("Items: " + "; ".join(item_descs))

        elif form_type == "10-Q":
            parts.append("Quarterly Report")

        elif form_type == "10-K":
            parts.append("Annual Report")

        # Clean raw summary
        if raw_summary:
            clean = re.sub(r'<[^>]+>', '', raw_summary)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean and len(clean) > 20:
                parts.append(clean[:300])

        return " | ".join(parts) if parts else ""


def main():
    """Test the SEC EDGAR collector."""
    collector = SECEdgarCollector()

    print("\n=== Recent 8-K Filings ===\n")
    filings = collector.collect_recent_filings(
        form_types=["8-K"],
        hours_lookback=72,
        max_per_type=20
    )

    for item in filings[:10]:
        print(f"[{item.category}] {item.title}")
        print(f"  Date: {item.published.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Tickers: {item.related_tickers}")
        if item.metadata.get("items"):
            print(f"  Items: {item.metadata['items']}")
        print(f"  URL: {item.url}")
        print()

    print("\n=== Company-Specific Filings ===\n")
    company_filings = collector.collect_company_filings(
        tickers=["NVDA", "TSLA", "LLY"],
        form_types=["8-K"],
        days_lookback=30
    )

    for item in company_filings[:5]:
        print(f"[{item.category}] {item.title}")
        print(f"  Date: {item.published.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Summary: {item.summary[:100]}...")
        print()


if __name__ == "__main__":
    main()
