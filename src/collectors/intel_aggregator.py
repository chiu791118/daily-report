"""
Intel Aggregator Module
Aggregates data from all collectors into a unified intelligence feed.
"""
from datetime import datetime, timedelta
from typing import Optional
import pytz


from src.collectors.base import IntelItem, SourceType
from src.collectors.news import NewsCollector, NewsItem
from src.collectors.sec_edgar import SECEdgarCollector
from src.collectors.arxiv import ArxivCollector
from src.collectors.clinical_trials import ClinicalTrialsCollector
from src.collectors.fda import FDACollector
from src.collectors.entity_matcher import EntityMatcher
from src.config.settings import TIMEZONE


class IntelAggregator:
    """
    Aggregates intelligence from all data sources.

    Data Sources:
    - News (RSS feeds, NewsAPI)
    - SEC EDGAR (8-K, 10-Q, 10-K)
    - arXiv (AI/ML papers)
    - ClinicalTrials.gov
    - FDA (approvals, safety alerts)
    """

    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)
        self.entity_matcher = EntityMatcher()

        # Initialize collectors
        self.news_collector = NewsCollector()
        self.sec_collector = SECEdgarCollector()
        self.arxiv_collector = ArxivCollector()
        self.trials_collector = ClinicalTrialsCollector()
        self.fda_collector = FDACollector()

    def collect_all(
        self,
        days_lookback: int = 7,
        include_news: bool = True,
        include_sec: bool = True,
        include_arxiv: bool = True,
        include_trials: bool = True,
        include_fda: bool = True,
    ) -> list[IntelItem]:
        """
        Collect intelligence from all sources.

        Args:
            days_lookback: How far back to look
            include_*: Flags to enable/disable specific sources

        Returns:
            List of IntelItem objects, sorted by date
        """
        all_items = []
        hours_lookback = days_lookback * 24

        # 1. News
        if include_news:
            print("📰 Collecting news...")
            try:
                news_items = self.news_collector.collect_all()
                intel_items = self._convert_news_items(news_items)
                all_items.extend(intel_items)
                print(f"   Found {len(intel_items)} news items")
            except Exception as e:
                print(f"   ⚠️ News collection error: {e}")

        # 2. SEC EDGAR
        if include_sec:
            print("📋 Collecting SEC filings...")
            try:
                sec_items = self.sec_collector.collect_recent_filings(
                    form_types=["8-K", "10-Q"],
                    hours_lookback=hours_lookback,
                    max_per_type=50
                )
                all_items.extend(sec_items)
                print(f"   Found {len(sec_items)} SEC filings")
            except Exception as e:
                print(f"   ⚠️ SEC collection error: {e}")

        # 3. arXiv
        if include_arxiv:
            print("📄 Collecting arXiv papers...")
            try:
                arxiv_items = self.arxiv_collector.collect_high_signal_papers(
                    max_results=30,
                    days_lookback=days_lookback
                )
                all_items.extend(arxiv_items)
                print(f"   Found {len(arxiv_items)} high-signal papers")
            except Exception as e:
                print(f"   ⚠️ arXiv collection error: {e}")

        # 4. Clinical Trials
        if include_trials:
            print("💊 Collecting clinical trials...")
            try:
                trial_items = self.trials_collector.collect_recent_updates(
                    phases=["PHASE2", "PHASE3"],
                    days_lookback=days_lookback,
                    max_results=30
                )
                all_items.extend(trial_items)
                print(f"   Found {len(trial_items)} trial updates")
            except Exception as e:
                print(f"   ⚠️ Clinical trials collection error: {e}")

        # 5. FDA
        if include_fda:
            print("🏥 Collecting FDA updates...")
            try:
                fda_items = self.fda_collector.collect_all(
                    days_lookback=days_lookback,
                    max_results=30
                )
                all_items.extend(fda_items)
                print(f"   Found {len(fda_items)} FDA updates")
            except Exception as e:
                print(f"   ⚠️ FDA collection error: {e}")

        # Sort by date (newest first)
        all_items.sort(key=lambda x: x.published, reverse=True)

        print(f"\n✅ Total: {len(all_items)} intelligence items collected")

        return all_items

    def collect_by_industry(
        self,
        industries: list,
        days_lookback: int = 7,
    ) -> dict[str, list[IntelItem]]:
        """
        Collect and organize intelligence by industry.

        Args:
            industries: List of industry keys (e.g., ["ai", "healthcare"])
            days_lookback: How far back to look

        Returns:
            Dict mapping industry to list of IntelItems
        """
        all_items = self.collect_all(days_lookback=days_lookback)

        # Organize by industry
        by_industry = {ind: [] for ind in industries}
        by_industry["other"] = []

        for item in all_items:
            matched = False
            for industry in item.industries:
                if industry in by_industry:
                    by_industry[industry].append(item)
                    matched = True

            if not matched:
                by_industry["other"].append(item)

        return by_industry

    def _convert_news_items(self, news_items: list[NewsItem]) -> list[IntelItem]:
        """Convert NewsItem objects to IntelItem objects."""
        intel_items = []

        for news in news_items:
            # Detect industries from content
            tickers, entities, industries = self.entity_matcher.find_matches(
                f"{news.title} {news.summary}"
            )

            item = IntelItem(
                title=news.title,
                source=news.source,
                source_type=SourceType.NEWS,
                url=news.url,
                published=news.published,
                summary=news.summary,
                category=news.category,
                industries=industries,
                related_tickers=list(set(news.related_tickers + tickers)),
                related_entities=entities,
                metadata={
                    "is_analyst_rating": news.is_analyst_rating,
                    "original_sentiment": news.sentiment,
                }
            )
            intel_items.append(item)

        return intel_items

    def get_summary_stats(self, items: list[IntelItem]) -> dict:
        """Get summary statistics for collected items."""
        stats = {
            "total": len(items),
            "by_source_type": {},
            "by_industry": {},
            "by_source": {},
            "top_entities": {},
            "top_tickers": {},
        }

        entity_counts = {}
        ticker_counts = {}

        for item in items:
            # By source type
            st = item.source_type.value
            stats["by_source_type"][st] = stats["by_source_type"].get(st, 0) + 1

            # By source
            stats["by_source"][item.source] = stats["by_source"].get(item.source, 0) + 1

            # By industry
            for ind in item.industries:
                stats["by_industry"][ind] = stats["by_industry"].get(ind, 0) + 1

            # Count entities
            for entity in item.related_entities:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1

            # Count tickers
            for ticker in item.related_tickers:
                ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

        # Top entities and tickers
        stats["top_entities"] = dict(
            sorted(entity_counts.items(), key=lambda x: -x[1])[:20]
        )
        stats["top_tickers"] = dict(
            sorted(ticker_counts.items(), key=lambda x: -x[1])[:20]
        )

        return stats

    def format_for_prompt(
        self,
        items: list[IntelItem],
        max_items: int = 100,
        include_full_text: bool = False,
    ) -> str:
        """
        Format intelligence items for LLM prompt.

        Args:
            items: List of IntelItem objects
            max_items: Maximum items to include
            include_full_text: Whether to include full text (vs just summary)

        Returns:
            Formatted string for prompt
        """
        lines = []

        # Group by source type for better organization
        by_type = {}
        for item in items[:max_items]:
            st = item.source_type.value
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(item)

        # Format each group
        type_labels = {
            "news": "📰 新聞",
            "sec_filing": "📋 SEC 財報",
            "research_paper": "📄 研究論文",
            "clinical_trial": "💊 臨床試驗",
            "regulatory": "🏥 監管公告",
        }

        for source_type, type_items in by_type.items():
            label = type_labels.get(source_type, source_type)
            lines.append(f"\n## {label} ({len(type_items)} 則)\n")

            for item in type_items:
                # Date
                date_str = item.published.strftime("%m/%d")

                # Entities/tickers
                entities = item.related_entities[:3]
                tickers = item.related_tickers[:3]
                tags = []
                if tickers:
                    tags.append(f"${', $'.join(tickers)}")
                if entities:
                    tags.extend(entities)
                tag_str = f" [{', '.join(tags[:4])}]" if tags else ""

                # Content
                content = item.full_text if include_full_text and item.full_text else item.summary
                content = content[:300] + "..." if len(content) > 300 else content

                lines.append(f"- **[{date_str}] [{item.source}]** {item.title}{tag_str}")
                if content:
                    lines.append(f"  {content}")
                lines.append("")

        return "\n".join(lines)


def main():
    """Test the intel aggregator."""
    aggregator = IntelAggregator()

    print("\n" + "="*60)
    print("Testing Intel Aggregator")
    print("="*60)

    # Collect all
    items = aggregator.collect_all(
        days_lookback=7,
        include_news=True,
        include_sec=True,
        include_arxiv=True,
        include_trials=True,
        include_fda=True,
    )

    # Get stats
    stats = aggregator.get_summary_stats(items)

    print("\n--- Summary Statistics ---")
    print(f"Total items: {stats['total']}")

    print("\nBy source type:")
    for st, count in sorted(stats["by_source_type"].items(), key=lambda x: -x[1]):
        print(f"  {st}: {count}")

    print("\nBy industry:")
    for ind, count in sorted(stats["by_industry"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {count}")

    print("\nTop entities:")
    for entity, count in list(stats["top_entities"].items())[:10]:
        print(f"  {entity}: {count}")

    print("\nTop tickers:")
    for ticker, count in list(stats["top_tickers"].items())[:10]:
        print(f"  {ticker}: {count}")

    # Format sample for prompt
    print("\n--- Sample Prompt Format ---")
    sample = aggregator.format_for_prompt(items[:20])
    print(sample[:2000])


if __name__ == "__main__":
    main()
