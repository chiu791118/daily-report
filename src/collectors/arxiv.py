"""
arXiv Collector Module
Fetches AI/ML research papers from arXiv.
"""
import feedparser
import requests
from datetime import datetime, timedelta
from typing import Optional
import pytz
import re
import time
from urllib.parse import quote


from src.collectors.base import IntelItem, SourceType, BaseCollector
from src.config.settings import TIMEZONE


# Important arXiv categories for AI/ML
ARXIV_CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "Computation and Language (NLP)",
    "cs.CV": "Computer Vision",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.RO": "Robotics",
    "cs.HC": "Human-Computer Interaction",
    "cs.IR": "Information Retrieval",
    "stat.ML": "Machine Learning (Statistics)",
}

# Keywords to identify high-signal papers
HIGH_SIGNAL_KEYWORDS = [
    # Model types
    "large language model", "llm", "gpt", "transformer",
    "foundation model", "multimodal", "vision-language",
    # Capabilities
    "reasoning", "chain-of-thought", "in-context learning",
    "instruction tuning", "rlhf", "alignment",
    "agent", "autonomous", "tool use",
    # Efficiency
    "efficient", "compression", "quantization", "pruning",
    "distillation", "mixture of experts", "moe",
    # Safety
    "safety", "alignment", "jailbreak", "adversarial",
    "hallucination", "factuality",
    # Applications
    "code generation", "copilot", "programming",
    "medical", "clinical", "drug discovery",
    "robotics", "embodied",
]

# Major AI labs and affiliations
AI_AFFILIATIONS = {
    "google": ["Google", "DeepMind", "Google Research", "Google Brain"],
    "openai": ["OpenAI"],
    "anthropic": ["Anthropic"],
    "meta": ["Meta", "FAIR", "Meta AI"],
    "microsoft": ["Microsoft", "Microsoft Research", "MSR"],
    "nvidia": ["NVIDIA", "Nvidia Research"],
    "stanford": ["Stanford", "Stanford University"],
    "mit": ["MIT", "Massachusetts Institute of Technology"],
    "berkeley": ["Berkeley", "UC Berkeley", "BAIR"],
    "cmu": ["CMU", "Carnegie Mellon"],
    "tsinghua": ["Tsinghua", "清華"],
    "peking": ["Peking University", "北京大學", "PKU"],
}


class ArxivCollector(BaseCollector):
    """
    Collects AI/ML research papers from arXiv.

    Key categories:
    - cs.AI: Artificial Intelligence
    - cs.LG: Machine Learning
    - cs.CL: Computation and Language (NLP)
    - cs.CV: Computer Vision
    """

    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self):
        super().__init__()
        self.tz = pytz.timezone(TIMEZONE)

    def collect_recent_papers(
        self,
        categories: list = None,
        max_results: int = 100,
        days_lookback: int = 7,
    ) -> list[IntelItem]:
        """
        Collect recent papers from specified categories.

        Args:
            categories: arXiv categories (default: cs.AI, cs.LG, cs.CL)
            max_results: Maximum papers to fetch
            days_lookback: How far back to look

        Returns:
            List of IntelItem objects
        """
        if categories is None:
            categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV"]

        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)

        # Build category query
        cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
        query = f"({cat_query})"

        items = self._fetch_papers(query, max_results, cutoff_time)

        # Sort by date and relevance score
        items.sort(key=lambda x: (x.published, self._relevance_score(x)), reverse=True)

        return items

    def search_papers(
        self,
        keywords: list,
        categories: list = None,
        max_results: int = 50,
        days_lookback: int = 14,
    ) -> list[IntelItem]:
        """
        Search for papers with specific keywords.

        Args:
            keywords: Search keywords
            categories: Limit to specific categories
            max_results: Maximum results
            days_lookback: How far back to look

        Returns:
            List of IntelItem objects
        """
        cutoff_time = datetime.now(self.tz) - timedelta(days=days_lookback)

        # Build search query
        keyword_query = " OR ".join([f'all:"{kw}"' for kw in keywords])

        if categories:
            cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
            query = f"({keyword_query}) AND ({cat_query})"
        else:
            query = keyword_query

        items = self._fetch_papers(query, max_results, cutoff_time)

        # Sort by relevance
        items.sort(key=lambda x: self._relevance_score(x), reverse=True)

        return items

    def collect_high_signal_papers(
        self,
        max_results: int = 50,
        days_lookback: int = 7,
    ) -> list[IntelItem]:
        """
        Collect papers likely to be high-signal based on keywords and affiliations.

        Returns:
            List of high-signal IntelItem objects
        """
        # Get recent papers from main categories
        all_papers = self.collect_recent_papers(
            categories=["cs.AI", "cs.LG", "cs.CL"],
            max_results=max_results * 2,
            days_lookback=days_lookback,
        )

        # Filter and score
        scored_papers = []
        for paper in all_papers:
            score = self._relevance_score(paper)
            if score > 0:
                scored_papers.append((score, paper))

        # Sort by score and return top papers
        scored_papers.sort(key=lambda x: x[0], reverse=True)

        return [paper for score, paper in scored_papers[:max_results]]

    def _fetch_papers(
        self,
        query: str,
        max_results: int,
        cutoff_time: datetime,
    ) -> list[IntelItem]:
        """Fetch papers from arXiv API."""
        items = []

        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30
            )
            response.raise_for_status()

            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                try:
                    item = self._parse_entry(entry, cutoff_time)
                    if item:
                        items.append(item)
                except Exception as e:
                    continue

            time.sleep(3)  # arXiv rate limiting (3 seconds between requests)

        except Exception as e:
            print(f"Error fetching arXiv papers: {e}")

        return items

    def _parse_entry(
        self,
        entry,
        cutoff_time: datetime,
    ) -> Optional[IntelItem]:
        """Parse a single arXiv entry."""
        # Parse date
        published = self._parse_date(entry)
        if published and published < cutoff_time:
            return None

        # Extract arxiv ID
        arxiv_id = entry.get("id", "").split("/abs/")[-1]

        # Extract authors
        authors = []
        for author in entry.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        # Extract categories
        categories = []
        for tag in entry.get("tags", []):
            term = tag.get("term", "")
            if term and term in ARXIV_CATEGORIES:
                categories.append(term)

        # Get title and abstract
        title = entry.get("title", "").replace("\n", " ").strip()
        abstract = entry.get("summary", "").replace("\n", " ").strip()

        # Detect affiliations from author names and abstract
        affiliations = self._detect_affiliations(authors, abstract)

        # Create IntelItem
        item = IntelItem(
            title=title,
            source="arXiv",
            source_type=SourceType.RESEARCH_PAPER,
            url=entry.get("link", f"https://arxiv.org/abs/{arxiv_id}"),
            published=published or datetime.now(self.tz),
            summary=abstract[:500] + "..." if len(abstract) > 500 else abstract,
            full_text=abstract,
            category=", ".join(categories[:3]),
            industries=["ai"],
            metadata={
                "arxiv_id": arxiv_id,
                "authors": authors[:10],
                "categories": categories,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "affiliations": affiliations,
            }
        )

        # Tag entities mentioned in title/abstract
        item = self.tag_entities(item)

        return item

    def _parse_date(self, entry) -> Optional[datetime]:
        """Parse date from entry."""
        # Try published date first
        published_str = entry.get("published", "")
        if published_str:
            try:
                # arXiv format: 2024-01-15T12:00:00Z
                dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                return dt.astimezone(self.tz)
            except Exception:
                pass

        # Try updated date
        updated_str = entry.get("updated", "")
        if updated_str:
            try:
                dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                return dt.astimezone(self.tz)
            except Exception:
                pass

        return None

    def _detect_affiliations(self, authors: list, abstract: str) -> list:
        """Detect research lab affiliations from author names and abstract."""
        affiliations = set()
        text = " ".join(authors) + " " + abstract

        for lab_key, lab_names in AI_AFFILIATIONS.items():
            for name in lab_names:
                if name.lower() in text.lower():
                    affiliations.add(lab_key)
                    break

        return list(affiliations)

    def _relevance_score(self, item: IntelItem) -> int:
        """
        Calculate relevance score for a paper.
        Higher score = more likely to be high-signal.
        """
        score = 0
        text = f"{item.title} {item.summary}".lower()

        # Check for high-signal keywords
        for keyword in HIGH_SIGNAL_KEYWORDS:
            if keyword.lower() in text:
                score += 2

        # Bonus for major lab affiliations
        affiliations = item.metadata.get("affiliations", [])
        major_labs = ["google", "openai", "anthropic", "meta", "microsoft", "nvidia"]
        for lab in major_labs:
            if lab in affiliations:
                score += 3

        # Bonus for being in primary categories
        categories = item.metadata.get("categories", [])
        primary_cats = ["cs.AI", "cs.LG", "cs.CL"]
        for cat in primary_cats:
            if cat in categories:
                score += 1

        return score


def main():
    """Test the arXiv collector."""
    collector = ArxivCollector()

    print("\n=== Recent AI Papers ===\n")
    papers = collector.collect_recent_papers(
        categories=["cs.AI", "cs.LG"],
        max_results=20,
        days_lookback=7
    )

    for paper in papers[:10]:
        print(f"[{paper.category}] {paper.title[:80]}...")
        print(f"  Date: {paper.published.strftime('%Y-%m-%d')}")
        print(f"  Authors: {', '.join(paper.metadata.get('authors', [])[:3])}")
        if paper.metadata.get("affiliations"):
            print(f"  Labs: {paper.metadata['affiliations']}")
        print(f"  URL: {paper.url}")
        print()

    print("\n=== High-Signal Papers ===\n")
    high_signal = collector.collect_high_signal_papers(
        max_results=10,
        days_lookback=7
    )

    for paper in high_signal[:5]:
        print(f"[HIGH] {paper.title[:70]}...")
        print(f"  Labs: {paper.metadata.get('affiliations', [])}")
        print(f"  Entities: {paper.related_entities}")
        print()

    print("\n=== Keyword Search: 'agent' ===\n")
    agent_papers = collector.search_papers(
        keywords=["autonomous agent", "AI agent"],
        max_results=10,
        days_lookback=14
    )

    for paper in agent_papers[:5]:
        print(f"{paper.title[:70]}...")
        print(f"  {paper.url}")
        print()


if __name__ == "__main__":
    main()
