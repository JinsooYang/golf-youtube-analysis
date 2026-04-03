"""
spike_detector.py — Detect reaction spikes in live chat replay data.

Uses a sliding window to find video timestamps where viewers were reacting
most intensely, independent of individual message content or classification.

A "spike" is a contiguous time window whose reaction density (message count
weighted by likes) is a local maximum compared to adjacent windows.
These correspond to "crowd went wild" moments — instants where many viewers
sent messages simultaneously.

Spike moments complement the comment-driven highlight pipeline:
- Comment pipeline:  best individual messages → top-N per category
- Spike detection:   raw density peaks → top-N most-reacted moments

Output is serializable dicts suitable for inclusion in highlight_package.json
and writing to spike_moments.csv.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_WINDOW_SEC   = 60.0   # sliding window width in seconds
DEFAULT_STEP_SEC     = 10.0   # step between consecutive windows
DEFAULT_TOP_N        = 20     # max spikes to return (after dedup)
DEFAULT_MIN_MESSAGES = 3      # window must have at least this many messages


# ── Public API ─────────────────────────────────────────────────────────────────

def detect_spikes(
    live_chat_df: Optional[pd.DataFrame],
    window_sec: float = DEFAULT_WINDOW_SEC,
    step_sec: float = DEFAULT_STEP_SEC,
    top_n: int = DEFAULT_TOP_N,
    min_messages: int = DEFAULT_MIN_MESSAGES,
) -> list[dict]:
    """
    Find reaction spike windows in live chat data.

    Parameters
    ----------
    live_chat_df  : DataFrame with at minimum a ``timestamp_seconds`` column.
                    ``likes`` column is used as weight when present.
    window_sec    : Width of the sliding window in seconds.
    step_sec      : Step size between consecutive windows.
    top_n         : Maximum number of spikes to return (after dedup).
    min_messages  : A window must contain at least this many messages.

    Returns
    -------
    List of dicts sorted by ``weighted_score`` descending, deduplicated so
    that no two spikes overlap.  Each dict has:
        anchor_time     (float)  — midpoint of spike window; use as clip anchor
        window_start    (float)
        window_end      (float)
        message_count   (int)
        weighted_score  (float)  — sum of per-message weights (likes or 1.0)
        top_messages    (list)   — up to 5 highest-weight messages in window,
                                   each with text / author / likes /
                                   timestamp_seconds
    """
    if live_chat_df is None or live_chat_df.empty:
        return []

    df = live_chat_df.copy()
    if "timestamp_seconds" not in df.columns:
        logger.warning("spike_detector: no timestamp_seconds column — skipping")
        return []

    # Keep only rows with valid timestamps
    df = df[df["timestamp_seconds"] >= 0].copy()
    if df.empty:
        return []

    df["timestamp_seconds"] = df["timestamp_seconds"].astype(float)

    # Per-message weight: likes (floored at 1) when available, else 1
    if "likes" in df.columns:
        df["_weight"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).clip(lower=1)
    else:
        df["_weight"] = 1.0

    ts_min = float(df["timestamp_seconds"].min())
    ts_max = float(df["timestamp_seconds"].max())

    # Build window start positions
    window_starts: list[float] = []
    t = ts_min
    while t <= ts_max:
        window_starts.append(t)
        t += step_sec
    if not window_starts:
        return []

    # ── Score every window ─────────────────────────────────────────────────────
    raw_windows: list[dict] = []

    for w_start in window_starts:
        w_end = w_start + window_sec
        mask  = (df["timestamp_seconds"] >= w_start) & (df["timestamp_seconds"] < w_end)
        msgs  = df[mask]
        count = len(msgs)
        if count < min_messages:
            continue

        weighted_score = float(msgs["_weight"].sum())
        anchor         = (w_start + w_end) / 2.0

        # Top messages in this window (highest weight first)
        top_cols = [c for c in ["text", "author", "likes", "timestamp_seconds"] if c in msgs.columns]
        top_msgs = (
            msgs
            .sort_values("_weight", ascending=False)
            .head(5)
            [top_cols]
            .to_dict(orient="records")
        )

        raw_windows.append({
            "anchor_time":    round(anchor, 1),
            "window_start":   round(w_start, 1),
            "window_end":     round(w_end, 1),
            "message_count":  count,
            "weighted_score": round(weighted_score, 2),
            "top_messages":   top_msgs,
        })

    if not raw_windows:
        logger.info("spike_detector: no windows met min_messages=%d threshold", min_messages)
        return []

    # Sort by score descending, then deduplicate overlapping windows
    raw_windows.sort(key=lambda w: w["weighted_score"], reverse=True)
    selected = _deduplicate(raw_windows, min_gap_sec=window_sec / 2.0)

    result = selected[:top_n]
    logger.info(
        "spike_detector: %d spikes selected from %d candidates "
        "(%.0f–%.0fs, %d messages total)",
        len(result), len(raw_windows), ts_min, ts_max, len(df),
    )
    return result


# ── Internal helpers ───────────────────────────────────────────────────────────

def _deduplicate(windows: list[dict], min_gap_sec: float) -> list[dict]:
    """
    Greedy non-overlap selection.

    Iterates windows (already sorted by score desc) and keeps a window
    only if its anchor_time is at least ``min_gap_sec`` away from every
    already-kept window's anchor.
    """
    kept: list[dict] = []
    for w in windows:
        anchor = w["anchor_time"]
        if all(abs(anchor - k["anchor_time"]) >= min_gap_sec for k in kept):
            kept.append(w)
    return kept
