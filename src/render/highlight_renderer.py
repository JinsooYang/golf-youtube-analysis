"""
highlight_renderer.py — Render one draft master highlight video.

Follows the 5-act master_plan structure:

  title_card
  opening_hook card
  → for each act:
      section_card
      anchor clip + overlay  (or placeholder if timing uncertain)
      bridge comment cards   (hook-style display, no clip)
  → turning_points section card
      top turning-point clips + overlays (or placeholders)
  → closing note card
  → CTA card

All clips that cannot be auto-rendered (regular comments with
needs_manual_timestamp_mapping=True, or low confidence) receive a
red placeholder card.  No timestamps are fabricated.

Output: {output_dir}/master_highlight.mp4
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
    make_title_card, make_section_card, make_hook_card,
    make_cta_card, make_placeholder_card, ACT_COLORS,
)
from src.render.overlay import make_comment_overlay

logger = logging.getLogger(__name__)

AUTO_CONFIDENCE      = {"high", "medium"}
TITLE_DURATION       = 4.0
SECTION_DURATION     = 3.0
HOOK_DURATION        = 3.5
CTA_DURATION         = 4.0
PLACEHOLDER_DURATION = 4.0


def render_master_highlight(
    master_plan: dict,
    source_video: Path,
    output_dir: Path,
    font_path: Optional[Path] = None,
    min_confidence: str = "medium",
    width: int = 1280,
    height: int = 720,
) -> dict:
    """
    Render the master highlight draft video.

    Returns result dict:
      output_path, status, clips_rendered, clips_skipped, acts_rendered, note
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "master_highlight.mp4"

    meta         = master_plan.get("meta", {})
    video_title  = meta.get("video_title", "하이라이트")
    acts         = master_plan.get("acts", [])
    turning_pts  = master_plan.get("turning_points", [])
    opening_hook = master_plan.get("opening_hook")
    closing_note = master_plan.get("closing_note")
    titles       = master_plan.get("title_suggestions", [])

    title_text = titles[0] if titles else video_title

    clips_rendered = 0
    clips_skipped  = 0
    acts_rendered  = 0
    manual_notes: list[str] = []

    with tempfile.TemporaryDirectory(prefix="master_hl_") as tmpdir:
        tmp = Path(tmpdir)
        segments: list[Path] = []
        idx = 0   # global counter for unique filenames

        # ── Title card ─────────────────────────────────────────────────────────
        ti = make_title_card(
            title     = title_text,
            subtitle  = video_title if video_title != title_text else "",
            dst       = tmp / "title.png",
            width     = width,
            height    = height,
            font_path = font_path,
        )
        segments.append(image_to_video(ti, TITLE_DURATION, tmp / "title.mp4", width, height))
        idx += 1

        # ── Opening hook ───────────────────────────────────────────────────────
        if opening_hook:
            oh = make_hook_card(
                text      = opening_hook.get("text", "")[:200],
                author    = opening_hook.get("author", ""),
                likes     = int(opening_hook.get("likes", 0)),
                dst       = tmp / "opening_hook.png",
                width     = width,
                height    = height,
                font_path = font_path,
                label     = "\U0001f4ac 오프닝 — 이 경기를 한마디로",
            )
            segments.append(image_to_video(oh, HOOK_DURATION + 0.5, tmp / "opening_hook.mp4", width, height))
            idx += 1

        # ── Acts ───────────────────────────────────────────────────────────────
        for act_num, act in enumerate(acts):
            act_id    = act.get("act_id", f"act_{act_num}")
            act_name  = act.get("act_name", f"막 {act_num + 1}")
            act_emoji = act.get("emoji", "")
            act_desc  = act.get("description", "")
            anchor    = act.get("anchor_comment")
            bridges   = act.get("bridge_comments", [])
            count     = act.get("comment_count", 0)

            if count == 0:
                continue

            acts_rendered += 1
            bg = ACT_COLORS[act_num % len(ACT_COLORS)]

            # Section card
            sc = make_section_card(
                section_name = act_name,
                description  = act_desc,
                emoji        = act_emoji,
                dst          = tmp / f"{act_id}_sec.png",
                width        = width,
                height       = height,
                font_path    = font_path,
                bg_color     = bg,
            )
            segments.append(image_to_video(sc, SECTION_DURATION, tmp / f"{act_id}_sec.mp4", width, height))
            idx += 1

            # Anchor clip
            if anchor:
                seg, cr, cs, mn = _render_comment_clip(
                    comment      = anchor,
                    source_video = source_video,
                    tmp          = tmp,
                    idx          = idx,
                    width        = width,
                    height       = height,
                    font_path    = font_path,
                    label        = f"[{act_name}] 핵심 반응",
                )
                if seg:
                    segments.append(seg)
                clips_rendered += cr
                clips_skipped  += cs
                manual_notes.extend(mn)
                idx += 1

            # Bridge comments — display as hook cards (no clip attempt)
            for b in bridges[:2]:
                bi = make_hook_card(
                    text      = b.get("text", "")[:200],
                    author    = b.get("author", ""),
                    likes     = int(b.get("likes", 0)),
                    dst       = tmp / f"bridge_{idx:03d}.png",
                    width     = width,
                    height    = height,
                    font_path = font_path,
                    label     = f"\U0001f4ac {act_name} — 시청자 반응",
                )
                segments.append(image_to_video(bi, HOOK_DURATION, tmp / f"bridge_{idx:03d}.mp4", width, height))
                idx += 1

        # ── Turning points ─────────────────────────────────────────────────────
        priority_pts = [
            tp for tp in turning_pts
            if tp.get("narrative_weight") in ("critical", "high")
        ]

        if priority_pts:
            tp_sec = make_section_card(
                section_name = "핵심 전환점",
                description  = "경기 흐름을 바꾼 결정적 순간",
                emoji        = "\u2b50",
                dst          = tmp / "tp_sec.png",
                width        = width,
                height       = height,
                font_path    = font_path,
                bg_color     = (90, 48, 12),
            )
            segments.append(image_to_video(tp_sec, SECTION_DURATION, tmp / "tp_sec.mp4", width, height))
            idx += 1

            for tp in priority_pts[:3]:
                seg, cr, cs, mn = _render_comment_clip(
                    comment      = tp,
                    source_video = source_video,
                    tmp          = tmp,
                    idx          = idx,
                    width        = width,
                    height       = height,
                    font_path    = font_path,
                    label        = f"\u2b50 전환점 ({tp.get('narrative_weight', '')})",
                )
                if seg:
                    segments.append(seg)
                clips_rendered += cr
                clips_skipped  += cs
                manual_notes.extend(mn)
                idx += 1

        # ── Closing note ───────────────────────────────────────────────────────
        if closing_note:
            cn = make_hook_card(
                text      = closing_note.get("text", "")[:200],
                author    = closing_note.get("author", ""),
                likes     = int(closing_note.get("likes", 0)),
                dst       = tmp / "closing.png",
                width     = width,
                height    = height,
                font_path = font_path,
                label     = "\U0001f4ac 클로징 — 시청자가 남긴 말",
            )
            segments.append(image_to_video(cn, HOOK_DURATION + 0.5, tmp / "closing.mp4", width, height))
            idx += 1

        # ── CTA card ───────────────────────────────────────────────────────────
        cta = make_cta_card(
            text      = "이 경기, 어떻게 보셨나요? 댓글로 남겨주세요 \U0001f447",
            dst       = tmp / "cta.png",
            width     = width,
            height    = height,
            font_path = font_path,
        )
        segments.append(image_to_video(cta, CTA_DURATION, tmp / "cta.mp4", width, height))

        # ── Concatenate ────────────────────────────────────────────────────────
        concat_clips(segments, output_path)

    status = "ok" if clips_rendered > 0 else "cards_only"
    note = ""
    if manual_notes:
        shown = "; ".join(manual_notes[:3])
        tail  = f" 외 {len(manual_notes) - 3}건" if len(manual_notes) > 3 else ""
        note  = f"수동 편집 필요: {shown}{tail}"

    logger.info(
        "master highlight: rendered=%d skipped=%d acts=%d → %s",
        clips_rendered, clips_skipped, acts_rendered, output_path,
    )
    return {
        "output_path":    str(output_path),
        "status":         status,
        "clips_rendered": clips_rendered,
        "clips_skipped":  clips_skipped,
        "acts_rendered":  acts_rendered,
        "note":           note,
    }


# ── Per-comment clip helper ────────────────────────────────────────────────────

def _render_comment_clip(
    comment: dict,
    source_video: Path,
    tmp: Path,
    idx: int,
    width: int,
    height: int,
    font_path: Optional[Path],
    label: str = "",
) -> tuple[Optional[Path], int, int, list[str]]:
    """
    Try to render a trimmed clip for a comment record.

    Returns (segment_path | None, clips_rendered, clips_skipped, manual_notes).
    A placeholder is returned (not None) even on failure, so the slot is
    always filled in the output video.
    """
    seg_id       = comment.get("matched_segment_id")
    start        = valid_timestamp(comment.get("matched_start"))
    end          = valid_timestamp(comment.get("matched_end"))
    needs_manual = bool(comment.get("needs_manual_timestamp_mapping", True))
    confidence   = comment.get("matching_confidence", "none")
    text         = comment.get("text", "")
    author       = comment.get("author", "")
    likes        = int(comment.get("likes", 0))
    category     = comment.get("category", "")

    can_render = (
        seg_id is not None
        and start is not None
        and end is not None
        and not needs_manual
        and confidence in AUTO_CONFIDENCE
    )

    if can_render:
        raw  = tmp / f"clip_{idx:03d}_raw.mp4"
        comp = tmp / f"clip_{idx:03d}_comp.mp4"
        try:
            trim_clip(source_video, start, end, raw, width, height)
            ov_img = make_comment_overlay(
                text      = text[:200],
                author    = author,
                likes     = likes,
                category  = label or category,
                dst       = tmp / f"ov_{idx:03d}.png",
                width     = width,
                height    = height,
                font_path = font_path,
            )
            add_image_overlay(raw, ov_img, comp)
            return comp, 1, 0, []

        except Exception as exc:
            logger.warning("clip %d render failed: %s", idx, exc)
            ph = _ph(f"렌더링 오류: {str(exc)[:80]}", seg_id or "", idx, tmp, width, height, font_path)
            return ph, 0, 1, [f"clip {idx}: {str(exc)[:60]}"]
    else:
        reason = _skip_reason(needs_manual, confidence, seg_id)
        ph = _ph(reason, seg_id or "", idx, tmp, width, height, font_path)
        return ph, 0, 1, [reason]


def _skip_reason(needs_manual: bool, confidence: str, seg_id) -> str:
    if not seg_id:
        return "매칭 세그먼트 없음"
    if needs_manual:
        return f"일반 댓글: 타임스탬프 없음 ({seg_id})"
    return f"낮은 신뢰도 ({confidence})"


def _ph(
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
        dst        = tmp / f"ph_{idx:03d}.png",
        width      = width,
        height     = height,
        font_path  = font_path,
    )
    return image_to_video(ph_img, PLACEHOLDER_DURATION, tmp / f"ph_{idx:03d}.mp4", width, height)
