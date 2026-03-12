"""
ClinicalTrials.gov Collector Module
Fetches clinical trial updates from ClinicalTrials.gov API.
"""
import requests
from datetime import datetime, timedelta
from typing import Optional
import pytz
import time


from src.collectors.base import IntelItem, SourceType, BaseCollector
from src.config.settings import TIMEZONE


# Major pharma/biotech sponsors to track
TRACKED_SPONSORS = [
    "Eli Lilly",
    "Novo Nordisk",
    "Pfizer",
    "Moderna",
    "Johnson & Johnson",
    "AbbVie",
    "Merck",
    "AstraZeneca",
    "Roche",
    "Bristol-Myers Squibb",
    "Amgen",
    "Gilead",
    "Regeneron",
    "Vertex",
    "BioNTech",
    "Sanofi",
    "GSK",
    "Takeda",
    "Biogen",
    "Novartis",
]

# High-interest therapeutic areas
THERAPEUTIC_AREAS = {
    "obesity": ["obesity", "weight loss", "weight management", "GLP-1", "tirzepatide", "semaglutide"],
    "diabetes": ["diabetes", "type 2 diabetes", "T2D", "glycemic"],
    "oncology": ["cancer", "oncology", "tumor", "carcinoma", "lymphoma", "leukemia"],
    "neurology": ["alzheimer", "parkinson", "multiple sclerosis", "ALS", "dementia"],
    "cardiovascular": ["cardiovascular", "heart failure", "hypertension", "atherosclerosis"],
    "immunology": ["autoimmune", "rheumatoid arthritis", "lupus", "psoriasis", "IBD"],
    "infectious": ["vaccine", "COVID", "influenza", "RSV", "HIV"],
    "gene_therapy": ["gene therapy", "CRISPR", "CAR-T", "cell therapy"],
}

# Trial phases and their significance
PHASE_PRIORITY = {
    "PHASE3": 5,      # Most important - near approval
    "PHASE2_3": 4,
    "PHASE2": 3,
    "PHASE1_2": 2,
    "PHASE1": 1,
    "EARLY_PHASE1": 0,
    "NA": 0,
}


class ClinicalTrialsCollector(BaseCollector):
    """
    Collects clinical trial updates from ClinicalTrials.gov.

    Focus on:
    - Phase 2/3 trials (most market-relevant)
    - Major pharma sponsors
    - High-interest therapeutic areas (obesity, oncology, etc.)
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self):
        super().__init__()
        self.tz = pytz.timezone(TIMEZONE)

    def collect_recent_updates(
        self,
        conditions: list = None,
        sponsors: list = None,
        phases: list = None,
        days_lookback: int = 7,
        max_results: int = 100,
    ) -> list[IntelItem]:
        """
        Collect recently updated clinical trials.

        Args:
            conditions: Medical conditions to filter
            sponsors: Sponsor companies to filter
            phases: Trial phases to filter (default: Phase 2, 3)
            days_lookback: How far back to look for updates
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        if phases is None:
            phases = ["PHASE2", "PHASE3", "PHASE2_3"]

        cutoff_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
        all_items = []

        # Build query
        query_parts = []

        # Filter by update date
        query_parts.append(f"AREA[LastUpdatePostDate]RANGE[{cutoff_date},MAX]")

        # Filter by phase
        if phases:
            phase_query = " OR ".join([f"AREA[Phase]{phase}" for phase in phases])
            query_parts.append(f"({phase_query})")

        # Filter by sponsor
        if sponsors:
            sponsor_query = " OR ".join([f'AREA[LeadSponsorName]CONTAINS "{s}"' for s in sponsors])
            query_parts.append(f"({sponsor_query})")

        # Filter by condition
        if conditions:
            cond_query = " OR ".join([f'AREA[Condition]CONTAINS "{c}"' for c in conditions])
            query_parts.append(f"({cond_query})")

        query = " AND ".join(query_parts) if query_parts else ""

        try:
            items = self._fetch_studies(query, max_results)
            all_items.extend(items)
        except Exception as e:
            print(f"Error fetching clinical trials: {e}")

        # Sort by phase priority and date
        all_items.sort(
            key=lambda x: (
                PHASE_PRIORITY.get(x.metadata.get("phase", ""), 0),
                x.published
            ),
            reverse=True
        )

        return all_items

    def collect_sponsor_trials(
        self,
        sponsors: list = None,
        phases: list = None,
        statuses: list = None,
        max_per_sponsor: int = 20,
    ) -> list[IntelItem]:
        """
        Collect trials for specific sponsors.

        Args:
            sponsors: List of sponsor names (default: TRACKED_SPONSORS)
            phases: Trial phases to filter
            statuses: Trial statuses (RECRUITING, COMPLETED, etc.)
            max_per_sponsor: Max trials per sponsor

        Returns:
            List of IntelItem objects
        """
        if sponsors is None:
            sponsors = TRACKED_SPONSORS[:10]  # Top 10 sponsors

        if phases is None:
            phases = ["PHASE2", "PHASE3"]

        if statuses is None:
            statuses = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"]

        all_items = []

        for sponsor in sponsors:
            try:
                query_parts = [f'AREA[LeadSponsorName]CONTAINS "{sponsor}"']

                if phases:
                    phase_query = " OR ".join([f"AREA[Phase]{p}" for p in phases])
                    query_parts.append(f"({phase_query})")

                if statuses:
                    status_query = " OR ".join([f"AREA[OverallStatus]{s}" for s in statuses])
                    query_parts.append(f"({status_query})")

                query = " AND ".join(query_parts)
                items = self._fetch_studies(query, max_per_sponsor)
                all_items.extend(items)

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"Error fetching trials for {sponsor}: {e}")

        return all_items

    def collect_therapeutic_area(
        self,
        area: str,
        phases: list = None,
        days_lookback: int = 30,
        max_results: int = 50,
    ) -> list[IntelItem]:
        """
        Collect trials for a specific therapeutic area.

        Args:
            area: Therapeutic area key (e.g., "obesity", "oncology")
            phases: Trial phases to filter
            days_lookback: How far back to look
            max_results: Maximum results

        Returns:
            List of IntelItem objects
        """
        keywords = THERAPEUTIC_AREAS.get(area, [area])

        return self.collect_recent_updates(
            conditions=keywords,
            phases=phases,
            days_lookback=days_lookback,
            max_results=max_results,
        )

    def _fetch_studies(
        self,
        query: str,
        max_results: int,
    ) -> list[IntelItem]:
        """Fetch studies from ClinicalTrials.gov API."""
        items = []

        params = {
            "query.term": query,
            "pageSize": min(max_results, 100),
            "fields": (
                "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,"
                "LeadSponsorName,Condition,InterventionName,InterventionType,"
                "StartDate,PrimaryCompletionDate,LastUpdatePostDate,"
                "BriefSummary,EnrollmentCount"
            ),
        }

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            for study in data.get("studies", []):
                try:
                    item = self._parse_study(study)
                    if item:
                        items.append(item)
                except Exception as e:
                    continue

        except Exception as e:
            print(f"Error fetching studies: {e}")

        return items

    def _parse_study(self, study: dict) -> Optional[IntelItem]:
        """Parse a single study from API response."""
        protocol = study.get("protocolSection", {})

        # Identification
        id_module = protocol.get("identificationModule", {})
        nct_id = id_module.get("nctId", "")
        title = id_module.get("briefTitle", "") or id_module.get("officialTitle", "")

        # Status
        status_module = protocol.get("statusModule", {})
        status = status_module.get("overallStatus", "")
        last_update = status_module.get("lastUpdatePostDateStruct", {}).get("date", "")

        # Design
        design_module = protocol.get("designModule", {})
        phases = design_module.get("phases", [])
        phase = phases[0] if phases else "NA"
        enrollment = design_module.get("enrollmentInfo", {}).get("count", 0)

        # Sponsor
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")

        # Conditions
        conditions_module = protocol.get("conditionsModule", {})
        conditions = conditions_module.get("conditions", [])

        # Interventions
        interventions_module = protocol.get("armsInterventionsModule", {})
        interventions = []
        for intervention in interventions_module.get("interventions", []):
            name = intervention.get("name", "")
            int_type = intervention.get("type", "")
            if name:
                interventions.append(f"{name} ({int_type})" if int_type else name)

        # Description
        desc_module = protocol.get("descriptionModule", {})
        summary = desc_module.get("briefSummary", "")

        # Parse date
        published = self._parse_date(last_update)

        # Determine therapeutic area
        therapeutic_areas = self._detect_therapeutic_area(conditions, title, summary)

        # Create IntelItem
        item = IntelItem(
            title=f"[{phase}] {title}",
            source="ClinicalTrials.gov",
            source_type=SourceType.CLINICAL_TRIAL,
            url=f"https://clinicaltrials.gov/study/{nct_id}",
            published=published or datetime.now(self.tz),
            summary=self._format_summary(status, lead_sponsor, conditions, interventions, enrollment),
            full_text=summary,
            category=phase,
            industries=["healthcare"] + therapeutic_areas,
            metadata={
                "nct_id": nct_id,
                "phase": phase,
                "status": status,
                "sponsor": lead_sponsor,
                "conditions": conditions,
                "interventions": interventions,
                "enrollment": enrollment,
            }
        )

        # Tag entities
        item = self.tag_entities(item)

        # Add sponsor as related entity
        if lead_sponsor and lead_sponsor not in item.related_entities:
            item.related_entities.append(lead_sponsor)

        return item

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from API response."""
        if not date_str:
            return None

        try:
            # Format: "2024-01-15" or "January 15, 2024"
            for fmt in ["%Y-%m-%d", "%B %d, %Y", "%B %Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return self.tz.localize(dt)
                except ValueError:
                    continue
        except Exception:
            pass

        return None

    def _detect_therapeutic_area(
        self,
        conditions: list,
        title: str,
        summary: str,
    ) -> list:
        """Detect therapeutic areas from trial information."""
        areas = set()
        text = " ".join(conditions + [title, summary]).lower()

        for area, keywords in THERAPEUTIC_AREAS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    areas.add(area)
                    break

        return list(areas)

    def _format_summary(
        self,
        status: str,
        sponsor: str,
        conditions: list,
        interventions: list,
        enrollment: int,
    ) -> str:
        """Format a human-readable summary."""
        parts = []

        if status:
            parts.append(f"Status: {status}")

        if sponsor:
            parts.append(f"Sponsor: {sponsor}")

        if conditions:
            parts.append(f"Conditions: {', '.join(conditions[:3])}")

        if interventions:
            parts.append(f"Interventions: {', '.join(interventions[:3])}")

        if enrollment:
            parts.append(f"Enrollment: {enrollment}")

        return " | ".join(parts)


def main():
    """Test the ClinicalTrials collector."""
    collector = ClinicalTrialsCollector()

    print("\n=== Recent Phase 3 Trials ===\n")
    trials = collector.collect_recent_updates(
        phases=["PHASE3"],
        days_lookback=14,
        max_results=20
    )

    for trial in trials[:10]:
        print(f"[{trial.metadata.get('phase')}] {trial.title[:70]}...")
        print(f"  Status: {trial.metadata.get('status')}")
        print(f"  Sponsor: {trial.metadata.get('sponsor')}")
        print(f"  URL: {trial.url}")
        print()

    print("\n=== Obesity Trials ===\n")
    obesity_trials = collector.collect_therapeutic_area(
        area="obesity",
        phases=["PHASE2", "PHASE3"],
        days_lookback=30,
        max_results=10
    )

    for trial in obesity_trials[:5]:
        print(f"{trial.title[:70]}...")
        print(f"  Interventions: {trial.metadata.get('interventions', [])[:2]}")
        print(f"  Sponsor: {trial.metadata.get('sponsor')}")
        print()

    print("\n=== Eli Lilly Trials ===\n")
    lilly_trials = collector.collect_sponsor_trials(
        sponsors=["Eli Lilly"],
        phases=["PHASE2", "PHASE3"],
        max_per_sponsor=10
    )

    for trial in lilly_trials[:5]:
        print(f"[{trial.metadata.get('status')}] {trial.title[:60]}...")
        print(f"  Conditions: {trial.metadata.get('conditions', [])[:2]}")
        print()


if __name__ == "__main__":
    main()
