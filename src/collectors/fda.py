"""
FDA Collector Module
Fetches FDA approvals, warning letters, and regulatory updates.
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


# FDA RSS Feeds
FDA_RSS_FEEDS = {
    "drug_approvals": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drugs/rss.xml",
    "drug_safety": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drug-safety/rss.xml",
    "medical_devices": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medical-devices/rss.xml",
    "biologics": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/vaccines-blood-biologics/rss.xml",
    "press_releases": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
    "recalls": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
}

# openFDA API endpoints
OPENFDA_BASE = "https://api.fda.gov"
OPENFDA_ENDPOINTS = {
    "drug_approvals": "/drug/drugsfda.json",
    "drug_labels": "/drug/label.json",
    "device_recalls": "/device/recall.json",
    "adverse_events": "/drug/event.json",
}

# Approval types and their significance
APPROVAL_TYPES = {
    "New Drug Application": "NDA",
    "Biologics License Application": "BLA",
    "Abbreviated New Drug Application": "ANDA",  # Generic
    "Supplemental New Drug Application": "sNDA",
    "Supplemental Biologics License Application": "sBLA",
}

# High-priority drug categories
PRIORITY_CATEGORIES = [
    "Breakthrough Therapy",
    "Fast Track",
    "Priority Review",
    "Accelerated Approval",
    "Orphan Drug",
]


class FDACollector(BaseCollector):
    """
    Collects FDA regulatory updates:
    - Drug approvals (NDA, BLA)
    - Safety communications
    - Warning letters
    - Device approvals and recalls
    """

    def __init__(self):
        super().__init__()
        self.tz = pytz.timezone(TIMEZONE)

    def collect_all(
        self,
        days_lookback: int = 7,
        max_results: int = 100,
    ) -> list[IntelItem]:
        """
        Collect all FDA updates from RSS feeds.

        Args:
            days_lookback: How far back to look
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)
        all_items = []

        # Collect from RSS feeds
        for feed_name, feed_url in FDA_RSS_FEEDS.items():
            try:
                items = self._parse_rss_feed(feed_url, feed_name, cutoff_time)
                all_items.extend(items)
                time.sleep(0.2)  # Rate limiting
            except Exception as e:
                print(f"Error fetching FDA {feed_name}: {e}")

        # Sort by date
        all_items.sort(key=lambda x: x.published, reverse=True)

        return all_items[:max_results]

    def collect_drug_approvals(
        self,
        days_lookback: int = 30,
        max_results: int = 50,
    ) -> list[IntelItem]:
        """
        Collect recent drug approvals from openFDA API.

        Args:
            days_lookback: How far back to look
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        cutoff_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y%m%d")
        items = []

        try:
            # Query openFDA for recent approvals
            params = {
                "search": f"submissions.submission_status_date:[{cutoff_date} TO *]",
                "limit": max_results,
            }

            response = requests.get(
                f"{OPENFDA_BASE}{OPENFDA_ENDPOINTS['drug_approvals']}",
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                for result in data.get("results", []):
                    try:
                        item = self._parse_openfda_approval(result)
                        if item:
                            items.append(item)
                    except Exception as e:
                        continue

        except Exception as e:
            print(f"Error fetching drug approvals from openFDA: {e}")

        # Fallback to RSS if API fails
        if not items:
            print("Falling back to RSS feed for drug approvals")
            items = self._parse_rss_feed(
                FDA_RSS_FEEDS["drug_approvals"],
                "drug_approvals",
                datetime.now(self.tz) - timedelta(days=days_lookback)
            )

        return items

    def collect_safety_alerts(
        self,
        days_lookback: int = 14,
        max_results: int = 30,
    ) -> list[IntelItem]:
        """
        Collect drug safety communications and recalls.

        Args:
            days_lookback: How far back to look
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)
        all_items = []

        # Drug safety
        try:
            safety_items = self._parse_rss_feed(
                FDA_RSS_FEEDS["drug_safety"],
                "drug_safety",
                cutoff_time
            )
            all_items.extend(safety_items)
        except Exception as e:
            print(f"Error fetching drug safety: {e}")

        # Recalls
        try:
            recall_items = self._parse_rss_feed(
                FDA_RSS_FEEDS["recalls"],
                "recalls",
                cutoff_time
            )
            all_items.extend(recall_items)
        except Exception as e:
            print(f"Error fetching recalls: {e}")

        all_items.sort(key=lambda x: x.published, reverse=True)
        return all_items[:max_results]

    def collect_press_releases(
        self,
        days_lookback: int = 7,
        max_results: int = 20,
    ) -> list[IntelItem]:
        """
        Collect FDA press releases (often contain major announcements).

        Args:
            days_lookback: How far back to look
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)

        items = self._parse_rss_feed(
            FDA_RSS_FEEDS["press_releases"],
            "press_releases",
            cutoff_time
        )

        return items[:max_results]

    def _parse_rss_feed(
        self,
        url: str,
        feed_type: str,
        cutoff_time: datetime,
    ) -> list[IntelItem]:
        """Parse FDA RSS feed."""
        items = []

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"Error parsing RSS feed: {e}")
            return items

        for entry in feed.entries:
            try:
                # Parse date
                published = self._parse_date(entry)
                if published and published < cutoff_time:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("description", "")

                # Clean summary
                summary = self._clean_html(summary)

                # Determine category and significance
                category = self._categorize_item(title, summary, feed_type)

                # Create IntelItem
                item = IntelItem(
                    title=title,
                    source="FDA",
                    source_type=SourceType.REGULATORY,
                    url=link,
                    published=published or datetime.now(self.tz),
                    summary=summary[:500] if summary else "",
                    category=category,
                    industries=["healthcare"],
                    metadata={
                        "feed_type": feed_type,
                        "is_approval": "approv" in title.lower(),
                        "is_safety": feed_type in ["drug_safety", "recalls"],
                        "is_breakthrough": any(p.lower() in title.lower() for p in PRIORITY_CATEGORIES),
                    }
                )

                # Tag entities
                item = self.tag_entities(item)

                # Extract drug/company names
                self._extract_drug_company(item, title, summary)

                items.append(item)

            except Exception as e:
                continue

        return items

    def _parse_openfda_approval(self, result: dict) -> Optional[IntelItem]:
        """Parse a drug approval from openFDA API."""
        try:
            # Extract basic info
            brand_name = result.get("openfda", {}).get("brand_name", [""])[0]
            generic_name = result.get("openfda", {}).get("generic_name", [""])[0]
            manufacturer = result.get("openfda", {}).get("manufacturer_name", [""])[0]
            application_number = result.get("application_number", "")

            # Get submission info
            submissions = result.get("submissions", [])
            latest_submission = submissions[0] if submissions else {}
            submission_type = latest_submission.get("submission_type", "")
            submission_status = latest_submission.get("submission_status", "")
            submission_date = latest_submission.get("submission_status_date", "")

            # Parse date
            published = None
            if submission_date:
                try:
                    published = datetime.strptime(submission_date, "%Y%m%d")
                    published = self.tz.localize(published)
                except Exception:
                    pass

            if not published:
                published = datetime.now(self.tz)

            # Build title
            drug_name = brand_name or generic_name or "Unknown Drug"
            title = f"[{submission_type}] {drug_name} - {submission_status}"

            # Build summary
            summary_parts = []
            if manufacturer:
                summary_parts.append(f"Manufacturer: {manufacturer}")
            if generic_name and brand_name:
                summary_parts.append(f"Generic: {generic_name}")
            if application_number:
                summary_parts.append(f"Application: {application_number}")

            item = IntelItem(
                title=title,
                source="FDA",
                source_type=SourceType.REGULATORY,
                url=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={application_number.replace('NDA', '').replace('BLA', '').replace('ANDA', '')}",
                published=published,
                summary=" | ".join(summary_parts),
                category=submission_type,
                industries=["healthcare"],
                metadata={
                    "application_number": application_number,
                    "brand_name": brand_name,
                    "generic_name": generic_name,
                    "manufacturer": manufacturer,
                    "submission_type": submission_type,
                    "submission_status": submission_status,
                }
            )

            # Tag entities
            item = self.tag_entities(item)

            if manufacturer:
                item.related_entities.append(manufacturer)

            return item

        except Exception as e:
            return None

    def _parse_date(self, entry) -> Optional[datetime]:
        """Parse date from feed entry."""
        time_fields = ["published_parsed", "updated_parsed"]

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

        # Try string parsing
        for field in ["published", "updated"]:
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

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean text."""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _categorize_item(self, title: str, summary: str, feed_type: str) -> str:
        """Categorize the FDA item."""
        text = f"{title} {summary}".lower()

        # Check for approval types
        for full_name, abbrev in APPROVAL_TYPES.items():
            if full_name.lower() in text or abbrev.lower() in text:
                return abbrev

        # Check for priority designations
        for priority in PRIORITY_CATEGORIES:
            if priority.lower() in text:
                return priority

        # Default categories based on feed type
        category_map = {
            "drug_approvals": "Drug Approval",
            "drug_safety": "Safety Alert",
            "medical_devices": "Device",
            "biologics": "Biologic",
            "press_releases": "Press Release",
            "recalls": "Recall",
        }

        return category_map.get(feed_type, "Other")

    def _extract_drug_company(self, item: IntelItem, title: str, summary: str):
        """Extract drug names and company names from text."""
        text = f"{title} {summary}"

        # Common patterns for drug names (capitalized words followed by common suffixes)
        drug_patterns = [
            r'\b([A-Z][a-z]+(?:mab|nib|lib|zumab|tinib|parin|tide|glutide))\b',
            r'\b([A-Z][a-z]+(?:vir|cin|mycin|cycline))\b',
        ]

        for pattern in drug_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in item.related_entities:
                    item.related_entities.append(match)


def main():
    """Test the FDA collector."""
    collector = FDACollector()

    print("\n=== All FDA Updates ===\n")
    updates = collector.collect_all(days_lookback=7, max_results=15)

    for item in updates[:10]:
        print(f"[{item.category}] {item.title[:70]}...")
        print(f"  Date: {item.published.strftime('%Y-%m-%d')}")
        print(f"  Entities: {item.related_entities[:3]}")
        print(f"  URL: {item.url}")
        print()

    print("\n=== Drug Approvals ===\n")
    approvals = collector.collect_drug_approvals(days_lookback=30, max_results=10)

    for item in approvals[:5]:
        print(f"{item.title}")
        print(f"  {item.summary[:100]}...")
        print()

    print("\n=== Safety Alerts ===\n")
    safety = collector.collect_safety_alerts(days_lookback=14, max_results=5)

    for item in safety[:5]:
        print(f"[SAFETY] {item.title[:70]}...")
        print(f"  {item.url}")
        print()


if __name__ == "__main__":
    main()
