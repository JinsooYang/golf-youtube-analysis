"""
rolling_chat.py — Render a video clip with a real-time rolling live chat overlay.

Used for spike-driven Shorts: chat messages appear as a continuously rolling
feed, timed so the panel is always visibly moving during playback.

Sync model
----------
Messages are sorted by ``timestamp_seconds`` (absolute video offset) and
assigned a *display offset* within the clip using the following rules:

1. Base offset = clamp(timestamp_seconds − clip_start, 0, clip_duration)
2. Enforce minimum spacing: each message must appear at least
   ``update_interval_sec`` after the previous one in display time.
3. If the message list is dense enough that spacing them at
   ``update_interval_sec`` would overflow the clip duration, fall back to
   even distribution: ``i × (clip_duration / n_messages)``.

The result is that every message gets its own visible keyframe even when
real chat timestamps cluster tightly (which is exactly the situation during
a spike — many messages in a very short window).

Each keyframe spans from its display offset to the next message's display
offset (or to clip_end for the last one).

Example — 15 s clip, 1 s interval, 12 messages clustered at t=8–10 s:
    Without fix: panel shows 0 msgs until t=8, then all 12 at once → static
    With fix:    messages spread at t=0,1.25,2.5,…,13.75 → always rolling

Fallback
--------
If messages have no ``timestamp_seconds`` key, the function falls back to
the legacy equal-phase model (n_phases parameter).
"""

from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path
from typing import Optional

from src.render.ffmpeg_utils import trim_clip, add_image_overlay, concat_clips
from src.render.overlay import make_chat_panel_overlay

logger = logging.getLogger(__name__)


def render_rolling_chat_clip(
    source_video: Path,
    clip_start: float,
    clip_end: float,
    messages: list[dict],
    output_path: Path,
    tmp: Path,
    idx: int,
    width: int,
    height: int,
    font_path: Optional[Path],
    # Real-time sync params
    update_interval_sec: float = 0.5,
    max_visible_lines: int = 8,
    # Fallback phase params (used when timestamps are missing)
    n_phases: int = 3,
) -> Path:
    """
    Render a source clip with a rolling live chat overlay.

    Parameters
    ----------
    source_video        : path to the full source .mp4
    clip_start          : clip start in seconds (absolute video offset)
    clip_end            : clip end in seconds (absolute video offset)
    messages            : chat messages, each dict with keys:
                              timestamp_seconds  (enables real-time sync)
                              text, author, likes
    output_path         : destination .mp4 path
    tmp                 : temp directory for intermediate files
    idx                 : numeric index used to name temp files uniquely
    width / height      : output dimensions (must match source video)
    font_path           : TTF font for text rendering (None → Pillow default)
    update_interval_sec : minimum seconds between chat panel updates.
                          Smaller = more keyframes = smoother rolling.
                          Default: 0.5 s
    max_visible_lines   : max messages visible in the panel at once.
                          Default: 8
    n_phases            : fallback phase count when timestamps are absent

    Returns
    -------
    output_path (same as input, guaranteed to exist on success)
    """
    duration = clip_end - clip_start
    if duration <= 0:
        raise ValueError(
            f"clip_end ({clip_end}) must be greater than clip_start ({clip_start})"
        )

    if not messages:
        logger.debug("rolling_chat: no messages — rendering plain clip")
        trim_clip(source_video, clip_start, clip_end, output_path, width, height)
        return output_path

    has_timestamps = any("timestamp_seconds" in m for m in messages)

    if has_timestamps:
        return _render_timestamp_sync(
            source_video        = source_video,
            clip_start          = clip_start,
            clip_end            = clip_end,
            messages            = messages,
            output_path         = output_path,
            tmp                 = tmp,
            idx                 = idx,
            width               = width,
            height              = height,
            font_path           = font_path,
            update_interval_sec = update_interval_sec,
            max_visible_lines   = max_visible_lines,
        )
    else:
        return _render_phased(
            source_video      = source_video,
            clip_start        = clip_start,
            clip_end          = clip_end,
            messages          = messages,
            output_path       = output_path,
            tmp               = tmp,
            idx               = idx,
            width             = width,
            height            = height,
            font_path         = font_path,
            n_phases          = n_phases,
            max_visible_lines = max_visible_lines,
        )


# ── Real-time timestamp-synced rendering ───────────────────────────────────────

def _render_timestamp_sync(
    source_video: Path,
    clip_start: float,
    clip_end: float,
    messages: list[dict],
    output_path: Path,
    tmp: Path,
    idx: int,
    width: int,
    height: int,
    font_path: Optional[Path],
    update_interval_sec: float,
    max_visible_lines: int,
) -> Path:
    """
    Render clip with chat panel updating at every message arrival.

    Each message gets its own keyframe so the panel is always visibly rolling.
    Message display offsets are spaced by at least update_interval_sec;
    dense clusters are distributed evenly across the clip duration.
    """
    duration = clip_end - clip_start
    interval = max(0.1, update_interval_sec)

    # ── Sort messages by original timestamp ───────────────────────────────────
    msgs_sorted = sorted(
        messages,
        key=lambda m: float(m.get("timestamp_seconds", clip_start)),
    )
    n = len(msgs_sorted)

    # ── Assign display offsets ────────────────────────────────────────────────
    # Strategy:
    #   1. Base offset = clamp(ts - clip_start, 0, duration)
    #   2. Enforce minimum spacing of `interval` between messages
    #   3. If that spacing overflows duration, use even distribution instead

    # Check if even the ideal spacing fits
    needs_even_spread = (n * interval) > duration

    if needs_even_spread:
        # Even distribution: message i appears at i/(n) * duration
        # (first message at t=0, last message just before clip end)
        step = duration / n
        display_offsets = [i * step for i in range(n)]
        logger.debug(
            "rolling_chat: %d messages dense for %.0fs clip "
            "(%.1fs interval) → even spread (step=%.2fs)",
            n, duration, interval, step,
        )
    else:
        # Use real timestamps with minimum spacing enforced
        display_offsets: list[float] = []
        for m in msgs_sorted:
            ts = float(m.get("timestamp_seconds", clip_start))
            base = max(0.0, min(ts - clip_start, duration))
            if display_offsets:
                base = max(base, display_offsets[-1] + interval)
            # Clamp to clip duration (leave 0.1 s margin at the end)
            base = min(base, duration - 0.1)
            display_offsets.append(base)
        logger.debug(
            "rolling_chat: %d messages, timestamp-based offsets "
            "(interval=%.1fs, range=%.1f–%.1fs)",
            n, interval,
            display_offsets[0] if display_offsets else 0,
            display_offsets[-1] if display_offsets else 0,
        )

    # ── Build keyframes: one per message ─────────────────────────────────────
    # Keyframe i: abs_start = clip_start + display_offsets[i]
    #             abs_end   = clip_start + display_offsets[i+1]  (or clip_end)
    #             panel shows msgs_sorted[0 … i] (most recent max_visible_lines)
    sub_clips: list[Path] = []

    for ki in range(n):
        kf_abs_start = clip_start + display_offsets[ki]
        kf_abs_end   = clip_start + display_offsets[ki + 1] if ki + 1 < n else clip_end

        if kf_abs_end <= kf_abs_start + 0.05:
            # Degenerate window — skip (can happen at very end of clip)
            continue

        visible_msgs = msgs_sorted[: ki + 1][-max_visible_lines:]

        raw_path = tmp / f"rc_{idx:02d}_k{ki:03d}_raw.mp4"
        ov_path  = tmp / f"rc_{idx:02d}_k{ki:03d}_ov.png"
        ov_out   = tmp / f"rc_{idx:02d}_k{ki:03d}_out.mp4"

        trim_clip(source_video, kf_abs_start, kf_abs_end, raw_path, width, height)
        make_chat_panel_overlay(
            messages     = visible_msgs,
            dst          = ov_path,
            width        = width,
            height       = height,
            font_path    = font_path,
            max_messages = max_visible_lines,
        )
        add_image_overlay(raw_path, ov_path, ov_out)
        sub_clips.append(ov_out)

    # Handle leading silence: if first message doesn't appear at t=0,
    # prepend a plain video segment with an empty chat panel.
    first_offset = display_offsets[0] if display_offsets else 0.0
    if first_offset > 0.1:
        raw_lead  = tmp / f"rc_{idx:02d}_lead_raw.mp4"
        ov_lead   = tmp / f"rc_{idx:02d}_lead_ov.png"
        out_lead  = tmp / f"rc_{idx:02d}_lead_out.mp4"
        trim_clip(source_video, clip_start, clip_start + first_offset, raw_lead, width, height)
        # Empty panel with just the "💬 라이브" header
        make_chat_panel_overlay(
            messages  = [],
            dst       = ov_lead,
            width     = width,
            height    = height,
            font_path = font_path,
        )
        add_image_overlay(raw_lead, ov_lead, out_lead)
        sub_clips.insert(0, out_lead)

    logger.debug(
        "rolling_chat ts-sync: %d messages → %d sub-clips rendered",
        n, len(sub_clips),
    )

    if not sub_clips:
        trim_clip(source_video, clip_start, clip_end, output_path, width, height)
        return output_path

    if len(sub_clips) == 1:
        shutil.move(str(sub_clips[0]), str(output_path))
    else:
        concat_clips(sub_clips, output_path)

    return output_path


# ── Legacy equal-phase fallback ────────────────────────────────────────────────

def _render_phased(
    source_video: Path,
    clip_start: float,
    clip_end: float,
    messages: list[dict],
    output_path: Path,
    tmp: Path,
    idx: int,
    width: int,
    height: int,
    font_path: Optional[Path],
    n_phases: int,
    max_visible_lines: int,
) -> Path:
    """Phase-based fallback for messages without timestamp_seconds."""
    duration      = clip_end - clip_start
    actual_phases = min(n_phases, max(1, len(messages)))
    phase_dur     = duration / actual_phases
    n_msgs        = len(messages)
    sub_clips: list[Path] = []

    for phase_idx in range(actual_phases):
        visible      = max(1, math.ceil((phase_idx + 1) / actual_phases * n_msgs))
        visible_msgs = messages[:visible][-max_visible_lines:]

        sub_start = clip_start + phase_idx * phase_dur
        sub_end   = clip_start + (phase_idx + 1) * phase_dur

        raw_path = tmp / f"rc_{idx:02d}_p{phase_idx}_raw.mp4"
        ov_path  = tmp / f"rc_{idx:02d}_p{phase_idx}_ov.png"
        ov_out   = tmp / f"rc_{idx:02d}_p{phase_idx}_out.mp4"

        trim_clip(source_video, sub_start, sub_end, raw_path, width, height)
        make_chat_panel_overlay(
            messages     = visible_msgs,
            dst          = ov_path,
            width        = width,
            height       = height,
            font_path    = font_path,
            max_messages = max_visible_lines,
        )
        add_image_overlay(raw_path, ov_path, ov_out)
        sub_clips.append(ov_out)

    if len(sub_clips) == 1:
        shutil.move(str(sub_clips[0]), str(output_path))
    else:
        concat_clips(sub_clips, output_path)

    return output_path
