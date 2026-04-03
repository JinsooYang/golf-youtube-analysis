"""
normalizer.py — Convert raw chat events into a flat, schema-stable record list.

Output schema (every record has all keys; missing values are None / "" / 0):

  message_id          str   — yt-dlp / YouTube internal ID
  timestamp_seconds   float — video offset in seconds (from videoOffsetTimeMsec ÷ 1000)
                              NULL when videoOffsetTimeMsec is absent
  timestamp_text      str   — formatted "HH:MM:SS" display string (empty when null)
  timestamp_usecs     str   — epoch microseconds as string (raw from YouTube)
  author              str   — display name  ← named 'author' for load_live_chat compat
  author_name         str   — alias of author
  author_channel_id   str   — YouTube channel ID (may be empty)
  text                str   — message body   ← named 'text' for load_live_chat compat
  message_text        str   — alias of text
  message_type        str   — "text" | "superchat" | "membership" | "paid_sticker" | "other"
  superchat_amount    str   — "$5.00" or empty
  likes               int   — always 0 (YouTube live chat has no per-message likes)
  like_count          int   — alias of likes (for packager.py compat)
  video_id            str
  video_url           str
  source              str   — always "live_chat_replay"
  source_type         str   — always "live_chat"  (for load_live_chat compat)

Integration compatibility
--------------------------
The fields `text`, `timestamp_seconds`, `author`, `likes` / `like_count` and
`source_type` match exactly what src/highlight/loaders.load_live_chat() expects.
The normalized CSV can be passed directly to --live-chat with no transformation.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SOURCE        = "live_chat_replay"
_SOURCE_TYPE   = "live_chat"


def normalize_events(
    raw_events: list[dict],
    video_id: str,
    video_url: str,
) -> list[dict]:
    """
    Convert a list of raw parser events into normalized flat records.

    Records are sorted by timestamp_seconds (None-last).
    """
    records: list[dict] = []
    null_ts_count = 0

    for ev in raw_events:
        offset_ms = ev.get("video_offset_ms")

        if offset_ms is not None:
            ts_seconds: Optional[float] = round(float(offset_ms) / 1000.0, 3)
            ts_text = _format_seconds(ts_seconds)
        else:
            ts_seconds = None
            ts_text    = ""
            null_ts_count += 1

        author   = ev.get("author_name", "") or ""
        text     = ev.get("message_text", "") or ""

        record = {
            # ── Identity ──────────────────────────────────────────────────────
            "message_id":         ev.get("message_id", ""),
            # ── Timing ───────────────────────────────────────────────────────
            "timestamp_seconds":  ts_seconds,
            "timestamp_text":     ts_text,
            "timestamp_usecs":    ev.get("timestamp_usecs", "") or "",
            # ── Author ────────────────────────────────────────────────────────
            "author":             author,       # primary: for load_live_chat
            "author_name":        author,       # alias
            "author_channel_id":  ev.get("author_channel_id", "") or "",
            # ── Content ───────────────────────────────────────────────────────
            "text":               text,         # primary: for load_live_chat
            "message_text":       text,         # alias
            "message_type":       ev.get("message_type", "other"),
            "superchat_amount":   ev.get("superchat_amount", "") or "",
            # ── Engagement ───────────────────────────────────────────────────
            "likes":              0,            # primary: for load_live_chat
            "like_count":         0,            # alias: for packager.py
            # ── Video reference ───────────────────────────────────────────────
            "video_id":           video_id,
            "video_url":          video_url,
            # ── Source ────────────────────────────────────────────────────────
            "source":             _SOURCE,
            "source_type":        _SOURCE_TYPE, # for load_live_chat compat
        }
        records.append(record)

    if null_ts_count:
        logger.warning(
            "%d/%d messages have no videoOffsetTimeMsec — "
            "timestamp_seconds will be null for those rows",
            null_ts_count, len(raw_events),
        )

    # Sort by timestamp; None goes last
    records.sort(key=lambda r: (r["timestamp_seconds"] is None, r["timestamp_seconds"] or 0))

    logger.info(
        "normalized %d records (%d with valid timestamps, %d without)",
        len(records), len(records) - null_ts_count, null_ts_count,
    )
    return records


def filter_for_highlight(records: list[dict]) -> list[dict]:
    """
    Return only the records useful for the highlight pipeline.

    Keeps: "text" and "superchat" messages with valid timestamps.
    Drops: membership joins, paid stickers, system messages, and any record
           with timestamp_seconds = None (cannot be used for clip matching).
    """
    kept = [
        r for r in records
        if r["message_type"] in ("text", "superchat")
        and r["timestamp_seconds"] is not None
        and r["text"].strip()
    ]
    logger.info(
        "filtered %d → %d records (highlight-relevant, timestamped, non-empty)",
        len(records), len(kept),
    )
    return kept


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_seconds(seconds: float) -> str:
    """Format float seconds as HH:MM:SS display string."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
