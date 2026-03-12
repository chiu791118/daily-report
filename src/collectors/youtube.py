"""
YouTube Collector Module
Fetches latest videos and transcripts from tracked channels.
"""
import yaml
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
import pytz

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from youtube_transcript_api.proxies import WebshareProxyConfig


from src.config.settings import (
    YOUTUBE_API_KEY,
    CONFIG_DIR,
    TIMEZONE,
    HOURS_LOOKBACK,
    MAX_YOUTUBE_VIDEOS,
    WEBSHARE_PROXY_USERNAME,
    WEBSHARE_PROXY_PASSWORD,
)


@dataclass
class YouTubeVideo:
    """Represents a YouTube video."""
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    published: datetime
    description: str = ""
    duration: str = ""
    view_count: int = 0
    thumbnail_url: str = ""
    transcript: str = ""
    category: str = ""
    focus_areas: list = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class YouTubeCollector:
    """Collects videos from tracked YouTube channels."""

    def __init__(self):
        if not YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY not set in environment")

        self.youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        self.tz = pytz.timezone(TIMEZONE)
        self.cutoff_time = datetime.now(self.tz) - timedelta(hours=HOURS_LOOKBACK)
        self.channels = self._load_channels()

    def _load_channels(self) -> dict:
        """Load channel configuration from YAML."""
        channels_file = CONFIG_DIR / "channels.yaml"
        with open(channels_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def collect_all(self) -> list[YouTubeVideo]:
        """Collect recent videos from all tracked channels."""
        all_videos = []

        for category, channels in self.channels.get("channels", {}).items():
            for channel_info in channels:
                try:
                    videos = self._get_channel_videos(channel_info, category)
                    all_videos.extend(videos)
                except Exception as e:
                    print(f"Error fetching videos from {channel_info['name']}: {e}")

        # Sort by publish time (newest first)
        all_videos.sort(key=lambda x: x.published, reverse=True)

        # Limit to max videos
        return all_videos[:MAX_YOUTUBE_VIDEOS]

    def _get_channel_videos(self, channel_info: dict, category: str) -> list[YouTubeVideo]:
        """Get recent videos from a specific channel."""
        videos = []
        channel_id = channel_info["channel_id"]
        channel_name = channel_info["name"]
        focus_areas = channel_info.get("focus", [])

        try:
            # Get uploads playlist ID
            channel_response = self.youtube.channels().list(
                part="contentDetails",
                id=channel_id
            ).execute()

            if not channel_response.get("items"):
                return []

            uploads_playlist_id = (
                channel_response["items"][0]
                ["contentDetails"]["relatedPlaylists"]["uploads"]
            )

            # Get recent videos from uploads playlist
            playlist_response = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=10  # Get last 10 videos to filter by time
            ).execute()

            video_ids = []
            video_snippets = {}

            for item in playlist_response.get("items", []):
                snippet = item["snippet"]
                video_id = snippet["resourceId"]["videoId"]
                published_str = snippet["publishedAt"]
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                published = published.astimezone(self.tz)

                # Only include videos within the lookback period
                if published >= self.cutoff_time:
                    video_ids.append(video_id)
                    video_snippets[video_id] = {
                        "title": snippet["title"],
                        "description": snippet.get("description", ""),
                        "published": published,
                        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    }

            # Get video details (duration, view count)
            if video_ids:
                details_response = self.youtube.videos().list(
                    part="contentDetails,statistics",
                    id=",".join(video_ids)
                ).execute()

                video_details = {
                    item["id"]: item
                    for item in details_response.get("items", [])
                }

                for video_id in video_ids:
                    snippet = video_snippets[video_id]
                    details = video_details.get(video_id, {})

                    video = YouTubeVideo(
                        video_id=video_id,
                        title=snippet["title"],
                        channel_name=channel_name,
                        channel_id=channel_id,
                        published=snippet["published"],
                        description=snippet["description"][:500],
                        duration=self._parse_duration(
                            details.get("contentDetails", {}).get("duration", "")
                        ),
                        view_count=int(
                            details.get("statistics", {}).get("viewCount", 0)
                        ),
                        thumbnail_url=snippet["thumbnail"],
                        category=category,
                        focus_areas=focus_areas,
                    )
                    videos.append(video)

        except Exception as e:
            print(f"Error fetching channel {channel_name}: {e}")

        return videos

    def _parse_duration(self, duration: str) -> str:
        """Parse ISO 8601 duration to human readable format."""
        import re
        if not duration:
            return ""

        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return duration

        hours, minutes, seconds = match.groups()
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds and not hours:  # Only show seconds if no hours
            parts.append(f"{seconds}s")

        return " ".join(parts) or "0m"

    def _create_transcript_api(self, use_proxy: bool = True):
        """Create YouTubeTranscriptApi instance with optional proxy."""
        if use_proxy and WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD:
            return YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=WEBSHARE_PROXY_USERNAME,
                    proxy_password=WEBSHARE_PROXY_PASSWORD,
                )
            )
        return YouTubeTranscriptApi()

    def get_transcript(self, video_id: str) -> str:
        """Get transcript for a video using the new API (v1.2+).

        Attempts in order:
        1. With Webshare proxy (if configured)
        2. Without proxy (fallback)
        """
        # Try with proxy first if available
        if WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD:
            result = self._fetch_transcript(video_id, use_proxy=True)
            if result:
                return result
            print(f"   Proxy failed for {video_id}, trying direct...")

        # Fallback to direct connection
        return self._fetch_transcript(video_id, use_proxy=False)

    def _fetch_transcript(self, video_id: str, use_proxy: bool) -> str:
        """Fetch transcript with or without proxy."""
        try:
            ytt_api = self._create_transcript_api(use_proxy)
            transcript = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
            text = " ".join([snippet.text for snippet in transcript])
            return text

        except TranscriptsDisabled:
            print(f"   Transcripts disabled for video {video_id}")
        except VideoUnavailable:
            print(f"   Video {video_id} unavailable")
        except NoTranscriptFound:
            try:
                ytt_api = self._create_transcript_api(use_proxy)
                transcript = ytt_api.fetch(video_id)
                text = " ".join([snippet.text for snippet in transcript])
                return text
            except Exception:
                print(f"   No transcript available for video {video_id}")
        except Exception as e:
            print(f"   Transcript error for {video_id}: {e}")

        return ""

    def collect_with_transcripts(self) -> list[YouTubeVideo]:
        """Collect videos and fetch transcripts for each."""
        videos = self.collect_all()

        for video in videos:
            video.transcript = self.get_transcript(video.video_id)
            # Truncate transcript if too long (for API limits)
            if len(video.transcript) > 50000:
                video.transcript = video.transcript[:50000] + "... [truncated]"

        return videos


def main():
    """Test the YouTube collector."""
    try:
        collector = YouTubeCollector()
        videos = collector.collect_all()

        print(f"\n=== Found {len(videos)} new videos ===\n")
        for video in videos:
            print(f"[{video.channel_name}] {video.title}")
            print(f"  Duration: {video.duration} | Views: {video.view_count:,}")
            print(f"  Published: {video.published.strftime('%Y-%m-%d %H:%M')}")
            print(f"  URL: {video.url}")
            print()

    except ValueError as e:
        print(f"Error: {e}")
        print("Please set YOUTUBE_API_KEY in your .env file")


if __name__ == "__main__":
    main()
