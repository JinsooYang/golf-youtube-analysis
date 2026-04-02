"""
YouTube Data API v3 client.

Handles video ID extraction from various URL formats, comment thread
fetching with full pagination, and graceful API error handling.
"""

import os
import re
import time

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# Covers: watch?v=, youtu.be/, /live/, /shorts/, /embed/
_VIDEO_ID_PATTERNS = [
    r"[?&]v=([A-Za-z0-9_-]{11})",
    r"youtu\.be/([A-Za-z0-9_-]{11})",
    r"youtube\.com/(?:live|shorts|embed)/([A-Za-z0-9_-]{11})",
]


class YouTubeClient:
    """Thin wrapper around the YouTube Data API v3."""

    def __init__(self) -> None:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "YOUTUBE_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        self._youtube = build("youtube", "v3", developerKey=api_key)

    # ------------------------------------------------------------------
    # URL parsing
    # ------------------------------------------------------------------

    def extract_video_id(self, url: str) -> str:
        """
        Extract the 11-character video ID from any common YouTube URL.

        Raises ValueError if no ID can be found.
        """
        for pattern in _VIDEO_ID_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        # Last resort: maybe the user passed just a raw ID
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
            return url.strip()
        raise ValueError(
            f"Cannot extract a YouTube video ID from: {url}\n"
            "Supported formats: watch?v=, youtu.be/, /live/, /shorts/"
        )

    # ------------------------------------------------------------------
    # Comment fetching
    # ------------------------------------------------------------------

    def fetch_comments(
        self,
        video_id: str,
        max_results: int = 500,
        include_replies: bool = True,
    ) -> list[dict]:
        """
        Fetch top-level comment threads (and optionally their replies).

        Parameters
        ----------
        video_id:        11-character YouTube video ID.
        max_results:     Maximum number of *top-level* comments to fetch.
        include_replies: Whether to also fetch reply comments.

        Returns
        -------
        List of comment dicts ready for DataFrame construction.
        """
        comments: list[dict] = []
        page_token: str | None = None
        top_level_fetched = 0

        while top_level_fetched < max_results:
            batch = min(100, max_results - top_level_fetched)
            try:
                response = (
                    self._youtube.commentThreads()
                    .list(
                        part="snippet,replies",
                        videoId=video_id,
                        maxResults=batch,
                        pageToken=page_token,
                        textFormat="plainText",
                        order="relevance",
                    )
                    .execute()
                )
            except HttpError as exc:
                self._handle_http_error(exc)
                break

            for item in response.get("items", []):
                top_snippet = item["snippet"]["topLevelComment"]["snippet"]
                thread_id = item["id"]
                total_replies = item["snippet"].get("totalReplyCount", 0)

                comments.append(
                    _build_comment_dict(
                        comment_id=item["snippet"]["topLevelComment"]["id"],
                        parent_comment_id=None,
                        snippet=top_snippet,
                        is_reply=False,
                        reply_count=total_replies,
                    )
                )
                top_level_fetched += 1

                if include_replies and total_replies > 0:
                    inline = item.get("replies", {}).get("comments", [])
                    if len(inline) < total_replies:
                        # API only returns up to 5 inline; fetch the rest
                        reply_items = self._fetch_all_replies(thread_id)
                    else:
                        reply_items = inline

                    for reply in reply_items:
                        comments.append(
                            _build_comment_dict(
                                comment_id=reply["id"],
                                parent_comment_id=thread_id,
                                snippet=reply["snippet"],
                                is_reply=True,
                                reply_count=0,
                            )
                        )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

            time.sleep(0.05)  # stay well within quota

        return comments

    def _fetch_all_replies(self, thread_id: str) -> list[dict]:
        """Fetch every reply for a comment thread via comments.list."""
        replies: list[dict] = []
        page_token: str | None = None

        while True:
            try:
                response = (
                    self._youtube.comments()
                    .list(
                        part="snippet",
                        parentId=thread_id,
                        maxResults=100,
                        pageToken=page_token,
                        textFormat="plainText",
                    )
                    .execute()
                )
            except HttpError as exc:
                print(f"    [Warning] Could not fetch replies for {thread_id}: {exc}")
                break

            replies.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
            time.sleep(0.05)

        return replies

    @staticmethod
    def _handle_http_error(exc: HttpError) -> None:
        status = exc.resp.status
        if status == 400:
            print(
                "\n  [API 400] Bad request — most likely an invalid API key.\n"
                "  Check that YOUTUBE_API_KEY in your .env file is set to a real key,\n"
                "  not the placeholder 'your_api_key_here'."
            )
        elif status == 403:
            print(
                "\n  [API 403] Comments are disabled for this video, "
                "or the API key lacks permission."
            )
        elif status == 404:
            print("\n  [API 404] Video not found. Check the URL / video ID.")
        elif status == 429:
            print("\n  [API 429] Quota exceeded. Try again tomorrow.")
        else:
            print(f"\n  [API Error {status}] {exc}")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_comment_dict(
    comment_id: str,
    parent_comment_id: str | None,
    snippet: dict,
    is_reply: bool,
    reply_count: int,
) -> dict:
    """Normalize a raw API snippet into a flat dict."""
    return {
        "comment_id": comment_id,
        "parent_comment_id": parent_comment_id,
        "author": snippet.get("authorDisplayName", ""),
        "text": snippet.get("textDisplay", ""),
        "published_at": snippet.get("publishedAt", ""),
        "updated_at": snippet.get("updatedAt", ""),
        "like_count": int(snippet.get("likeCount", 0)),
        "is_reply": is_reply,
        "reply_count": reply_count,
    }
