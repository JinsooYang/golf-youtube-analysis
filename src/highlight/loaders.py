"""
loaders.py — Input loading for the highlight pipeline.

Handles three input sources:
  1. segments.json   — produced by youtube_extractor.sh
  2. comments CSV    — produced by main.py  (comments_cleaned.csv)
  3. live chat CSV   — optional; expected schema documented below

Live chat CSV expected columns (flexible — missing columns are tolerated):
  timestamp_seconds, author, text, [likes], [message_type]

If the live chat file is absent or malformed, the pipeline continues with
comment-only mode and marks all matches as needing manual verification.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Required columns that must be present in comments CSV
_REQUIRED_COMMENT_COLS = {"comment_id", "text", "author", "like_count"}

# Minimum columns accepted in a live-chat CSV
_LIVE_CHAT_TIME_COLS = ["timestamp_seconds", "time_seconds", "offset_seconds"]
_LIVE_CHAT_TEXT_COLS = ["text", "message", "content"]


def load_segments(path: str | Path) -> list[dict]:
    """
    Load segments.json produced by youtube_extractor.sh.

    Returns a list of segment dicts.  Each dict is guaranteed to have:
        id    (str)   — e.g. "seg_0001"
        start (float) — seconds
        end   (float) — seconds
        text  (str)

    Optional 'words' key (list of {word, time}) is preserved if present.
    Missing or malformed file returns an empty list and logs a warning.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("segments file not found: %s — running without segments", path)
        return []

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("could not parse segments file %s: %s", path, exc)
        return []

    segments: list[dict] = []
    for i, raw in enumerate(data):
        seg: dict = {
            "id":    raw.get("id", f"seg_{i + 1:04d}"),
            "start": float(raw.get("start", 0.0)),
            "end":   float(raw.get("end", 0.0)),
            "text":  str(raw.get("text", "")),
        }
        if "words" in raw:
            seg["words"] = raw["words"]
        segments.append(seg)

    logger.info("loaded %d segments from %s", len(segments), path)
    return segments


def load_comments(path: str | Path) -> pd.DataFrame:
    """
    Load a comments CSV produced by main.py (comments_cleaned.csv).

    Normalises column types and ensures all required columns exist.
    Returns an empty DataFrame (with correct schema) on failure.
    """
    path = Path(path)
    if not path.exists():
        logger.error("comments file not found: %s", path)
        return _empty_comments_df()

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        logger.error("could not read comments CSV %s: %s", path, exc)
        return _empty_comments_df()

    missing = _REQUIRED_COMMENT_COLS - set(df.columns)
    if missing:
        logger.error(
            "comments CSV is missing required columns: %s — cannot continue", missing
        )
        return _empty_comments_df()

    # Normalise types
    df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce").fillna(0).astype(int)
    df["text"]       = df["text"].fillna("").astype(str)
    df["author"]     = df["author"].fillna("").astype(str)
    df["comment_id"] = df["comment_id"].fillna("").astype(str)

    if "is_reply" in df.columns:
        df["is_reply"] = df["is_reply"].map(
            lambda v: str(v).strip().lower() in ("true", "1", "yes")
        )
    else:
        df["is_reply"] = False

    if "reply_count" in df.columns:
        df["reply_count"] = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0).astype(int)

    # Drop empty text rows
    df = df[df["text"].str.strip() != ""].reset_index(drop=True)

    logger.info("loaded %d comments from %s", len(df), path)
    return df


def load_live_chat(path: Optional[str | Path]) -> Optional[pd.DataFrame]:
    """
    Load an optional live-chat CSV.

    Returns None if path is None, file is absent, or schema is unusable.
    Otherwise returns a DataFrame with at minimum these columns:
        timestamp_seconds (float)
        text              (str)
        author            (str)
        likes             (int)
        source_type       (str) — always "live_chat"

    The caller can check ``df is not None`` to decide whether to use
    timestamp-based matching.
    """
    if path is None:
        return None

    path = Path(path)
    if not path.exists():
        logger.warning("live chat file not found: %s — skipping", path)
        return None

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        logger.warning("could not read live chat CSV %s: %s — skipping", path, exc)
        return None

    # Locate timestamp column
    ts_col = next((c for c in _LIVE_CHAT_TIME_COLS if c in df.columns), None)
    if ts_col is None:
        logger.warning(
            "live chat CSV has no recognised timestamp column "
            "(%s) — skipping", _LIVE_CHAT_TIME_COLS
        )
        return None

    # Locate text column
    txt_col = next((c for c in _LIVE_CHAT_TEXT_COLS if c in df.columns), None)
    if txt_col is None:
        logger.warning("live chat CSV has no recognised text column — skipping")
        return None

    df = df.rename(columns={ts_col: "timestamp_seconds", txt_col: "text"})

    if "author" not in df.columns:
        df["author"] = "unknown"
    if "likes" in df.columns:
        df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
    else:
        df["likes"] = 0

    df["timestamp_seconds"] = pd.to_numeric(
        df["timestamp_seconds"], errors="coerce"
    ).fillna(-1.0).astype(float)

    # Drop rows with invalid timestamps or empty text
    df = df[(df["timestamp_seconds"] >= 0) & (df["text"].str.strip() != "")]
    df = df.reset_index(drop=True)

    # Synthesise comment_id for live chat rows
    df["comment_id"] = ["lc_" + str(i) for i in range(len(df))]
    df["source_type"] = "live_chat"
    df["like_count"]  = df["likes"]

    logger.info("loaded %d live-chat messages from %s", len(df), path)
    return df


# ── Helpers ────────────────────────────────────────────────────────────────────

def _empty_comments_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "comment_id", "author", "text", "like_count",
        "is_reply", "reply_count", "published_at",
    ])
