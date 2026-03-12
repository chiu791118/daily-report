"""
Notion Output Module
Integrates with Notion API to publish reports.
(Phase 2 - To be implemented after markdown workflow is stable)
"""
from datetime import datetime
from typing import Optional
import pytz

from src.config.settings import (
    NOTION_API_KEY,
    NOTION_DATABASE_ID,
    TIMEZONE,
)
from src.utils.trading_days import get_previous_trading_day


class NotionPublisher:
    """Publishes reports to Notion."""

    def __init__(self):
        if not NOTION_API_KEY or not NOTION_DATABASE_ID:
            raise ValueError(
                "NOTION_API_KEY and NOTION_DATABASE_ID must be set in environment"
            )

        from notion_client import Client
        self.client = Client(auth=NOTION_API_KEY)
        self.database_id = NOTION_DATABASE_ID
        self.tz = pytz.timezone(TIMEZONE)

        # Cache database properties for later use
        self._db_properties = self._get_database_properties()

    def _get_database_properties(self) -> set:
        """Get the set of property names that exist in the database."""
        try:
            db_info = self.client.databases.retrieve(database_id=self.database_id)
            properties = db_info.get("properties", {})
            if properties:
                return set(properties.keys())
            return {"Name", "Date", "Select", "Tags"}
        except Exception as e:
            print(f"Warning: Could not retrieve database properties: {e}")
            return {"Name", "Date", "Select", "Tags"}

    def create_daily_page(
        self,
        title: str,
        content: str,
        report_type: str = "pre-market",
        date_str: Optional[str] = None,
        tags: list[str] = None,
    ) -> str:
        """Create a new page in Notion database.

        Args:
            title: Page title
            content: Markdown content for the page
            report_type: Type of report (pre-market, post-market)
            date_str: Date string in YYYY-MM-DD format. If None, uses current date.
            tags: List of tags to add to the page

        Returns:
            URL of the created Notion page
        """
        # Use provided date or current date
        if date_str:
            page_date = date_str
        else:
            page_date = datetime.now(self.tz).strftime("%Y-%m-%d")

        # Convert markdown to Notion blocks
        blocks = self._markdown_to_blocks(content)

        # Build properties dict - only include properties that exist in the database
        properties = {
            "Name": {
                "title": [
                    {"text": {"content": title}}
                ]
            },
        }

        # Add optional properties only if they exist in the database
        if "Date" in self._db_properties:
            properties["Date"] = {"date": {"start": page_date}}
        # Support both "Type" and "Select" as property names
        if "Type" in self._db_properties:
            properties["Type"] = {"select": {"name": report_type}}
        elif "Select" in self._db_properties:
            properties["Select"] = {"select": {"name": report_type}}
        if "Tags" in self._db_properties:
            properties["Tags"] = {"multi_select": [{"name": tag} for tag in (tags or [])]}

        try:
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=blocks,
            )

            page_id = response["id"]
            page_url = response["url"]
            print(f"Created Notion page: {page_url}")
            return page_url

        except Exception as e:
            print(f"Error creating Notion page: {e}")
            print(f"  Database ID: {self.database_id}")
            print(f"  Title: {title}")
            print(f"  Report type: {report_type}")
            raise

    def _markdown_to_blocks(self, markdown: str) -> list:
        """Convert markdown content to Notion blocks."""
        blocks = []
        lines = markdown.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Headers
            if line.startswith("# "):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            elif line.startswith("## "):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith("### "):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                    }
                })

            # Horizontal rule
            elif line.strip() == "---":
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                })

            # Bullet list
            elif line.strip().startswith("- "):
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line.strip()[2:]}}]
                    }
                })

            # Quote
            elif line.strip().startswith("> "):
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": line.strip()[2:]}}]
                    }
                })

            # Fenced code block (```)
            elif line.strip().startswith("```"):
                code_lines = []
                language = line.strip()[3:] or "plain text"
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                # i now points to the closing ```, will be incremented at end of loop

                code_content = "\n".join(code_lines)
                # Truncate if too long (Notion has 2000 char limit)
                if len(code_content) > 1900:
                    code_content = code_content[:1900] + "\n... (truncated)"

                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code_content}}],
                        "language": language if language in ["python", "javascript", "json", "bash", "sql", "plain text"] else "plain text"
                    }
                })

            # Table (simplified - convert to code block)
            elif line.strip().startswith("|"):
                table_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                i -= 1  # Adjust for the outer loop increment

                table_content = "\n".join(table_lines)
                # Truncate if too long (Notion has 2000 char limit)
                if len(table_content) > 1900:
                    table_content = table_content[:1900] + "\n... (truncated)"

                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": table_content}}],
                        "language": "plain text"
                    }
                })

            # Regular paragraph
            else:
                # Truncate long text (Notion has a 2000 char limit per block)
                text = line.strip()
                if len(text) > 1900:
                    text = text[:1900] + "..."

                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    }
                })

            i += 1

        return blocks[:100]  # Notion has a limit of 100 blocks per request

    def find_page_by_title(self, title: str) -> Optional[dict]:
        """Find a page by its title.

        Args:
            title: The exact title to search for (e.g., "260202_Pre-market")

        Returns:
            Page object if found, None otherwise
        """
        try:
            # Use search endpoint to find pages by title
            response = self.client.search(
                query=title,
                filter={
                    "property": "object",
                    "value": "page"
                }
            )

            # Find exact title match in results
            for page in response.get("results", []):
                page_title = ""
                props = page.get("properties", {})
                name_prop = props.get("Name", {})
                title_list = name_prop.get("title", [])
                if title_list:
                    page_title = title_list[0].get("plain_text", "")

                if page_title == title:
                    return page

            return None

        except Exception as e:
            print(f"Error finding page by title '{title}': {e}")
            return None

    def get_page_content(self, page_id: str) -> str:
        """Get the text content of a Notion page.

        Args:
            page_id: The Notion page ID

        Returns:
            The page content as plain text
        """
        try:
            blocks = self.client.blocks.children.list(block_id=page_id)
            content_parts = []

            for block in blocks.get("results", []):
                block_type = block.get("type")
                block_data = block.get(block_type, {})

                # Extract text from rich_text blocks
                rich_text = block_data.get("rich_text", [])
                if rich_text:
                    text = "".join([t.get("plain_text", "") for t in rich_text])

                    # Add markdown formatting based on block type
                    if block_type == "heading_1":
                        content_parts.append(f"# {text}")
                    elif block_type == "heading_2":
                        content_parts.append(f"## {text}")
                    elif block_type == "heading_3":
                        content_parts.append(f"### {text}")
                    elif block_type == "bulleted_list_item":
                        content_parts.append(f"- {text}")
                    elif block_type == "numbered_list_item":
                        content_parts.append(f"1. {text}")
                    elif block_type == "quote":
                        content_parts.append(f"> {text}")
                    elif block_type == "code":
                        content_parts.append(f"```\n{text}\n```")
                    else:
                        content_parts.append(text)

                elif block_type == "divider":
                    content_parts.append("---")

            return "\n\n".join(content_parts)

        except Exception as e:
            print(f"Error getting page content for {page_id}: {e}")
            return ""

    def get_pre_market_content(self, trading_date: str) -> str:
        """Get pre-market report content for a specific trading date.

        Args:
            trading_date: Date in YYYY-MM-DD format

        Returns:
            The pre-market report content, or empty string if not found
        """
        # Convert YYYY-MM-DD to YYMMDD format for title
        title_date = datetime.strptime(trading_date, "%Y-%m-%d").strftime("%y%m%d")
        title = f"{title_date}_Pre-market"

        print(f"   Searching Notion for: {title}")

        page = self.find_page_by_title(title)
        if page:
            page_id = page["id"]
            print(f"   Found page: {page.get('url', page_id)}")
            return self.get_page_content(page_id)

        print(f"   No pre-market report found in Notion for {trading_date}")
        return ""

    def get_yesterday_pre_market(self, trading_date: str) -> dict:
        """Get yesterday's pre-market report with fallback logic.

        Implements fallback strategy:
        1. Calculate previous trading day (skip weekends)
        2. Try to fetch from Notion
        3. If fails, try previous 2-3 days
        4. Return unavailable marker if all attempts fail

        Args:
            trading_date: Current trading date in YYYY-MM-DD format

        Returns:
            dict with keys:
                - content: str - The report content
                - available: bool - Whether content is available
                - source: str - "notion" | "fallback" | "unavailable"
                - fallback_note: str - Explanation if using fallback
                - date: str - The date of the report that was found
        """
        current_date = datetime.strptime(trading_date, "%Y-%m-%d")

        # Try to find yesterday's report (with up to 3 trading days lookback)
        for lookback in range(1, 4):
            try_date = get_previous_trading_day(current_date, lookback)
            try_date_str = try_date.strftime("%Y-%m-%d")

            print(f"   Trying to fetch pre-market report for: {try_date_str}")

            content = self.get_pre_market_content(try_date_str)
            if content:
                if lookback == 1:
                    return {
                        "content": content,
                        "available": True,
                        "source": "notion",
                        "fallback_note": "",
                        "date": try_date_str,
                    }
                else:
                    return {
                        "content": content,
                        "available": True,
                        "source": "fallback",
                        "fallback_note": f"使用 {try_date_str} 的報告作為參考（{lookback} 個交易日前）",
                        "date": try_date_str,
                    }

        # All attempts failed
        return {
            "content": "",
            "available": False,
            "source": "unavailable",
            "fallback_note": "昨日報告不可用，變化判斷基於較長時間框架",
            "date": "",
        }

    def update_page(self, page_id: str, content: str) -> None:
        """Update existing Notion page content."""
        blocks = self._markdown_to_blocks(content)

        try:
            # First, delete existing blocks
            existing_blocks = self.client.blocks.children.list(block_id=page_id)
            for block in existing_blocks.get("results", []):
                self.client.blocks.delete(block_id=block["id"])

            # Then add new blocks
            self.client.blocks.children.append(
                block_id=page_id,
                children=blocks,
            )
            print(f"Updated Notion page: {page_id}")

        except Exception as e:
            print(f"Error updating Notion page: {e}")
            raise


def main():
    """Test the Notion publisher."""
    try:
        publisher = NotionPublisher()

        # Test creating a page
        test_content = """# 測試報告

## 市場概況

今日市場表現平穩。

- S&P 500: +0.5%
- NASDAQ: +0.8%
- Dow: +0.3%

---

## 結論

繼續觀察市場動態。
"""

        url = publisher.create_daily_page(
            title="測試每日摘要",
            content=test_content,
            report_type="test",
            tags=["測試", "自動化"],
        )
        print(f"Created page: {url}")

    except ValueError as e:
        print(f"Error: {e}")
        print("Please set NOTION_API_KEY and NOTION_DATABASE_ID in your .env file")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
