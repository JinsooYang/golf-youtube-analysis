"""
shorts_renderer.py — Render draft Shorts videos from shorts_sequences.

For each Shorts sequence in highlight_package.json:

  1. Hook card    — comment text on dark background
  2. Clip + overlay × N — trimmed clip with comment burned in
     • auto-rendered when: confidence ∈ {high, medium}
                           AND needs_manual_timestamp_mapping = False
     • placeholder card otherwise (red ⚠ card)
  3. CTA card     — call-to-action end card

All intermediate files use identical H.264/AAC/25fps encoding so the final
concat uses stream copy (fast, lossless within the intermediate quality).

Output: {output_dir}/{concept_id}.mp4
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from src.render.ffmpeg_utils import (
    trim_clip, image_to_video, add_image_overlay, concat_clips, valid_timestamp,
)
from src.render.cards import (
    make_hook_card, make_cta_card, make_placeholder_card,
)
from src.render.overlay import make_comment_overlay
from src.render.rolling_chat import render_rolling_chat_clip

logger = logging.getLogger(__name__)

# Confidence levels that allow automatic clip rendering
AUTO_CONFIDENCE = {"high", "medium"}

# Card durations (seconds)
HOOK_DURATION        = 3.5
CTA_DURATION         = 3.5
PLACEHOLDER_DURATION = 4.0


def render_all_shorts(
    package: dict,
    source_video: Path,
    output_dir: Path,
    font_path: Optional[Path] = None,
    min_confidence: str = "medium",
    width: int = 1280,
    height: int = 720,
    max_chat_lines: int = 8,
    chat_update_interval: float = 1.0,
) -> list[dict]:
    """
    Render all Shorts sequences from a highlight package.

    Returns a list of result dicts (one per sequence):
      concept_id, title, output_path, status,
      clips_rendered, clips_skipped, note

    Parameters
    ----------
    max_chat_lines        : max chat messages visible at once in spike Shorts
    chat_update_interval  : chat panel update granularity in seconds
    """
    sequences = package.get("shorts_sequences", [])
    if not sequences:
        logger.warning("no shorts_sequences in package — nothing to render")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for seq in sequences:
        cid = seq.get("concept_id", "unknown")
        logger.info("rendering Shorts: %s", cid)
        try:
            result = _render_one(
                sequence             = seq,
                source_video         = source_video,
                output_dir           = output_dir,
                font_path            = font_path,
                min_confidence       = min_confidence,
                width                = width,
                height               = height,
                max_chat_lines       = max_chat_lines,
                chat_update_interval = chat_update_interval,
            )
        except Exception as exc:
            logger.error("Shorts [%s] failed: %s", cid, exc, exc_info=True)
            result = {
                "concept_id":     cid,
                "title":          seq.get("title", cid),
                "output_path":    None,
                "status":         "error",
                "clips_rendered": 0,
                "clips_skipped":  0,
                "note":           str(exc)[:200],
            }
        results.append(result)

    return results


def _render_one(
    sequence: dict,
    source_video: Path,
    output_dir: Path,
    font_path: Optional[Path],
    min_confidence: str,
    width: int,
    height: int,
    max_chat_lines: int = 8,
    chat_update_interval: float = 1.0,
) -> dict:
    # Route spike sequences to the dedicated rolling-chat renderer
    if sequence.get("sequence_type") == "spike":
        return _render_spike_short(
            sequence             = sequence,
            source_video         = source_video,
            output_dir           = output_dir,
            font_path            = font_path,
            width                = width,
            height               = height,
            max_chat_lines       = max_chat_lines,
            chat_update_interval = chat_update_interval,
        )
    concept_id = sequence.get("concept_id", "short")
    title      = sequence.get("title", concept_id)
    overlays   = sequence.get("overlays", [])
    hook_data  = sequence.get("hook_comment", {})
    cta_text   = sequence.get("cta", "여러분의 생각은? 댓글로 남겨주세요 \U0001f447")

    output_path     = output_dir / f"{concept_id}.mp4"
    clips_rendered  = 0
    clips_skipped   = 0
    manual_notes: list[str] = []

    with tempfile.TemporaryDirectory(prefix=f"sh_{concept_id}_") as tmpdir:
        tmp      = Path(tmpdir)
        segments: list[Path] = []
        seen_segs: set[str]  = set()

        # ── Hook card ──────────────────────────────────────────────────────────
        hook_img = make_hook_card(
            text      = hook_data.get("text", title)[:200],
            author    = hook_data.get("author", ""),
            likes     = hook_data.get("likes", 0),
            dst       = tmp / "hook.png",
            width     = width,
            height    = height,
            font_path = font_path,
        )
        segments.append(image_to_video(hook_img, HOOK_DURATION, tmp / "hook.mp4", width, height))

        # ── Per-overlay clips ──────────────────────────────────────────────────
        for i, ov in enumerate(overlays):
            seg_id     = ov.get("matched_segment_id")
            start      = valid_timestamp(ov.get("matched_start"))
            end        = valid_timestamp(ov.get("matched_end"))
            confidence = ov.get("matching_confidence", "none")
            needs_manual = bool(ov.get("needs_manual_timestamp_mapping", True))
            text       = ov.get("text", "")
            author     = ov.get("author", "")
            likes      = int(ov.get("likes", 0))
            category   = ov.get("category", "")

            # Deduplicate clips from the same segment
            if seg_id and seg_id in seen_segs:
                continue
            if seg_id:
                seen_segs.add(seg_id)

            can_render = (
                seg_id is not None
                and start is not None
                and end is not None
                and not needs_manual
                and confidence in AUTO_CONFIDENCE
            )

            if can_render:
                try:
                    raw  = tmp / f"clip_{i:02d}_raw.mp4"
                    ovid = tmp / f"clip_{i:02d}_ov.mp4"
                    trim_clip(source_video, start, end, raw, width, height)

                    ov_img = make_comment_overlay(
                        text      = text[:200],
                        author    = author,
                        likes     = likes,
                        category  = category,
                        dst       = tmp / f"ov_{i:02d}.png",
                        width     = width,
                        height    = height,
                        font_path = font_path,
                        position  = "bottom",
                    )
                    add_image_overlay(raw, ov_img, ovid)
                    segments.append(ovid)
                    clips_rendered += 1

                except Exception as exc:
                    logger.warning("clip %d render error (%s) — inserting placeholder", i, exc)
                    ph = _placeholder(
                        f"클립 렌더링 오류: {exc}", seg_id or "",
                        i, tmp, width, height, font_path,
                    )
                    segments.append(ph)
                    clips_skipped += 1
                    manual_notes.append(f"clip {i}: {str(exc)[:60]}")
            else:
                reason = _skip_reason(needs_manual, confidence, seg_id)
                ph = _placeholder(reason, seg_id or "", i, tmp, width, height, font_path)
                segments.append(ph)
                clips_skipped += 1
                manual_notes.append(reason)

        # ── CTA card ───────────────────────────────────────────────────────────
        cta_img = make_cta_card(
            text      = cta_text,
            dst       = tmp / "cta.png",
            width     = width,
            height    = height,
            font_path = font_path,
        )
        segments.append(image_to_video(cta_img, CTA_DURATION, tmp / "cta.mp4", width, height))

        # ── Concatenate ────────────────────────────────────────────────────────
        concat_clips(segments, output_path)

    status = "ok" if clips_rendered > 0 else "placeholder_only"
    note = ""
    if manual_notes:
        shown = "; ".join(manual_notes[:3])
        tail  = f" 외 {len(manual_notes) - 3}건" if len(manual_notes) > 3 else ""
        note  = f"수동 편집 필요: {shown}{tail}"

    logger.info("Shorts [%s]: rendered=%d skipped=%d → %s", concept_id, clips_rendered, clips_skipped, output_path)

    return {
        "concept_id":     concept_id,
        "title":          title,
        "output_path":    str(output_path),
        "status":         status,
        "clips_rendered": clips_rendered,
        "clips_skipped":  clips_skipped,
        "note":           note,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _skip_reason(needs_manual: bool, confidence: str, seg_id: Optional[str]) -> str:
    if not seg_id:
        return "매칭 세그먼트 없음 — 타임스탬프 수동 입력 필요"
    if needs_manual:
        return f"일반 댓글: 타임스탬프 없음 (세그먼트: {seg_id})"
    return f"낮은 신뢰도 ({confidence}) — 수동 확인 후 편집"


def _placeholder(
    reason: str,
    segment_id: str,
    idx: int,
    tmp: Path,
    width: int,
    height: int,
    font_path: Optional[Path],
) -> Path:
    ph_img = make_placeholder_card(
        reason     = reason,
        segment_id = segment_id,
        dst        = tmp / f"ph_{idx:02d}.png",
        width      = width,
        height     = height,
        font_path  = font_path,
    )
    return image_to_video(ph_img, PLACEHOLDER_DURATION, tmp / f"ph_{idx:02d}.mp4", width, height)


# ── Spike-driven Short renderer ────────────────────────────────────────────────

def _render_spike_short(
    sequence: dict,
    source_video: Path,
    output_dir: Path,
    font_path: Optional[Path],
    width: int,
    height: int,
    max_chat_lines: int = 8,
    chat_update_interval: float = 0.5,
) -> dict:
    """
    Render one spike-driven Short.

    Output is exactly: clipped source video + rolling live chat overlay.
    No hook card, no CTA card — starts and ends with the raw footage.
    """
    concept_id = sequence.get("concept_id", "spike")
    title      = sequence.get("title", concept_id)
    clip_start = sequence.get("clip_start")
    clip_end   = sequence.get("clip_end")
    messages   = sequence.get("rolling_chat_messages", [])

    output_path = output_dir / f"{concept_id}.mp4"

    if clip_start is None or clip_end is None:
        logger.error("spike Short [%s]: missing clip_start / clip_end", concept_id)
        return {
            "concept_id": concept_id, "title": title,
            "output_path": None, "status": "error",
            "clips_rendered": 0, "clips_skipped": 1,
            "note": "missing clip_start or clip_end in sequence data",
        }

    clip_rendered = False
    with tempfile.TemporaryDirectory(prefix=f"sp_{concept_id}_") as tmpdir:
        tmp      = Path(tmpdir)
        clip_out = tmp / "rolling_clip.mp4"

        try:
            render_rolling_chat_clip(
                source_video        = source_video,
                clip_start          = float(clip_start),
                clip_end            = float(clip_end),
                messages            = messages,
                output_path         = clip_out,
                tmp                 = tmp,
                idx                 = 0,
                width               = width,
                height              = height,
                font_path           = font_path,
                update_interval_sec = chat_update_interval,
                max_visible_lines   = max_chat_lines,
            )
            # Move final output out of the temp dir
            import shutil
            shutil.move(str(clip_out), str(output_path))
            clip_rendered = True
        except Exception as exc:
            logger.error("spike [%s] clip render failed: %s", concept_id, exc, exc_info=True)

    status = "ok" if clip_rendered else "error"
    note   = (
        f"스파이크 @ {sequence.get('spike_anchor_time', '?')}s · "
        f"{len(messages)}개 메시지 · "
        f"클립 {clip_start}–{clip_end}s"
    )
    logger.info("spike Short [%s]: %s → %s", concept_id, status, output_path)

    return {
        "concept_id":     concept_id,
        "title":          title,
        "output_path":    str(output_path) if clip_rendered else None,
        "status":         status,
        "clips_rendered": 1 if clip_rendered else 0,
        "clips_skipped":  0 if clip_rendered else 1,
        "note":           note,
    }
