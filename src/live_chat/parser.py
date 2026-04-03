"""
parser.py — Parse yt-dlp live chat JSONL output into raw event dicts.

yt-dlp writes the live chat as a newline-delimited JSON file (JSONL).
Each line is one replay action batch from YouTube's innertube API.

The structure of each line:

  {
    "replayChatItemAction": {
      "actions": [
        {
          "addChatItemAction": {
            "item": {
              "liveChatTextMessageRenderer": { ... }   ← regular message
              OR
              "liveChatPaidMessageRenderer":  { ... }  ← Super Chat
              OR
              "liveChatMembershipItemRenderer": { ... } ← membership
              OR
              "liveChatPaidStickerRenderer":   { ... }  ← paid sticker
              OR
              "liveChatViewerEngagementMessageRenderer": { ... }  ← system (skip)
            }
          }
        }
      ],
      "videoOffsetTimeMsec": "12345"   ← ms from video start (KEY FIELD)
    }
  }

Some lines also have a leading "clickTrackingParams" key — still valid.
Some lines are metadata/header responses from YouTube — skip them.

Returns a list of RawChatEvent dicts, one per parsed message.
Lines that cannot be parsed are counted but do not raise exceptions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Known renderer type names ──────────────────────────────────────────────────

_TEXT_RENDERER       = "liveChatTextMessageRenderer"
_PAID_RENDERER       = "liveChatPaidMessageRenderer"
_MEMBERSHIP_RENDERER = "liveChatMembershipItemRenderer"
_STICKER_RENDERER    = "liveChatPaidStickerRenderer"
_ENGAGEMENT_RENDERER = "liveChatViewerEngagementMessageRenderer"
_AUTOMOD_RENDERER    = "liveChatAutoModMessageRenderer"

# Renderers we actually want to capture
_WANTED_RENDERERS = {
    _TEXT_RENDERER,
    _PAID_RENDERER,
    _MEMBERSHIP_RENDERER,
    _STICKER_RENDERER,
}

# Message type mapping (renderer name → clean type string)
_TYPE_MAP = {
    _TEXT_RENDERER:       "text",
    _PAID_RENDERER:       "superchat",
    _MEMBERSHIP_RENDERER: "membership",
    _STICKER_RENDERER:    "paid_sticker",
}


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class ParseStats:
    lines_read: int = 0
    lines_skipped: int = 0        # blank or header lines
    lines_error: int = 0          # invalid JSON or unexpected structure
    events_extracted: int = 0
    events_by_type: dict = field(default_factory=dict)


# ── Main parser ────────────────────────────────────────────────────────────────

def parse_live_chat_file(path: Path | str) -> tuple[list[dict], ParseStats]:
    """
    Parse a yt-dlp live_chat JSONL file.

    Returns (events, stats) where events is a list of raw event dicts and
    stats contains parse statistics.

    Each event dict has these keys (all values may be None if unavailable):
      renderer_type     str   — e.g. "liveChatTextMessageRenderer"
      message_type      str   — "text" | "superchat" | "membership" | "paid_sticker" | "other"
      message_id        str
      video_offset_ms   int   — milliseconds from video start (None if absent)
      timestamp_usecs   str   — epoch microseconds as string (None if absent)
      author_name       str
      author_channel_id str
      message_text      str   — extracted from runs[] (empty for stickers/memberships)
      superchat_amount  str   — e.g. "$5.00" (empty if not a Super Chat)
      raw               dict  — the original renderer dict for debugging
    """
    path  = Path(path)
    stats = ParseStats()
    events: list[dict] = []

    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            stats.lines_read += 1
            line = line.strip()

            if not line:
                stats.lines_skipped += 1
                continue

            # Parse JSON
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.debug("line %d: JSON error — %s", stats.lines_read, exc)
                stats.lines_error += 1
                continue

            # Skip non-replay lines (metadata/header objects)
            if "replayChatItemAction" not in obj:
                stats.lines_skipped += 1
                continue

            replay_action = obj["replayChatItemAction"]

            # videoOffsetTimeMsec — key field for clip matching
            raw_offset = replay_action.get("videoOffsetTimeMsec")
            try:
                video_offset_ms = int(raw_offset) if raw_offset is not None else None
            except (TypeError, ValueError):
                video_offset_ms = None

            # Process each action in the batch
            for action in replay_action.get("actions", []):
                add_action = action.get("addChatItemAction", {})
                item       = add_action.get("item", {})
                if not item:
                    continue

                event = _parse_item(item, video_offset_ms)
                if event is None:
                    continue

                events.append(event)
                stats.events_extracted += 1
                t = event["message_type"]
                stats.events_by_type[t] = stats.events_by_type.get(t, 0) + 1

    logger.info(
        "parsed %d lines → %d events (%d skipped, %d errors)",
        stats.lines_read, stats.events_extracted, stats.lines_skipped, stats.lines_error,
    )
    if stats.events_by_type:
        logger.info("event types: %s", stats.events_by_type)

    return events, stats


# ── Item parsers ───────────────────────────────────────────────────────────────

def _parse_item(item: dict, video_offset_ms: Optional[int]) -> Optional[dict]:
    """
    Parse a single chat item dict.
    Returns None for renderer types we don't capture (engagement messages etc.).
    """
    renderer_type = None
    renderer      = None

    # Find which renderer is in this item
    for key in item:
        if key in _WANTED_RENDERERS:
            renderer_type = key
            renderer      = item[key]
            break
        if key in (_ENGAGEMENT_RENDERER, _AUTOMOD_RENDERER):
            return None  # silently skip system messages

    if renderer is None or renderer_type is None:
        # Unknown renderer type — skip
        return None

    message_type = _TYPE_MAP.get(renderer_type, "other")

    return {
        "renderer_type":    renderer_type,
        "message_type":     message_type,
        "message_id":       renderer.get("id", ""),
        "video_offset_ms":  video_offset_ms,
        "timestamp_usecs":  renderer.get("timestampUsecs"),
        "author_name":      _get_simple_text(renderer.get("authorName", {})),
        "author_channel_id": renderer.get("authorExternalChannelId", ""),
        "message_text":     _extract_text(renderer),
        "superchat_amount": _get_superchat_amount(renderer, renderer_type),
        "raw":              renderer,
    }


def _extract_text(renderer: dict) -> str:
    """Extract plain text from a message renderer's runs array."""
    # Regular messages use "message.runs"
    message = renderer.get("message", {})
    runs    = message.get("runs", []) if message else []

    if not runs:
        # Membership items sometimes use "headerSubtext.runs"
        header = renderer.get("headerSubtext", {})
        runs   = header.get("runs", []) if header else []

    parts: list[str] = []
    for run in runs:
        if "text" in run:
            parts.append(run["text"])
        elif "emoji" in run:
            # Emoji runs: try to get the alt text or the first shortcut
            emoji    = run["emoji"]
            shortcuts = emoji.get("shortcuts", [])
            alt_text = emoji.get("emojiId", "")
            if shortcuts:
                parts.append(shortcuts[0])
            elif alt_text:
                parts.append(f"[{alt_text}]")
            else:
                parts.append("[emoji]")
    return "".join(parts)


def _get_simple_text(obj: dict) -> str:
    if not obj:
        return ""
    return obj.get("simpleText", "")


def _get_superchat_amount(renderer: dict, renderer_type: str) -> str:
    if renderer_type not in (_PAID_RENDERER, _STICKER_RENDERER):
        return ""
    purchase = renderer.get("purchaseAmountText", {})
    return _get_simple_text(purchase)
