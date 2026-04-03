"""
overlay.py — Generate transparent comment overlay images using Pillow.

The overlay is a full-frame RGBA PNG (same dimensions as the target video).
It is composited on top of a clip by ffmpeg_utils.add_image_overlay() using
ffmpeg's overlay filter with alpha blending.

Keeping text rendering in Pillow avoids ffmpeg drawtext's escaping issues
with Korean characters and gives predictable layout across platforms.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
    _PILLOW_OK = True
except ImportError:
    _PILLOW_OK = False


def _require_pillow() -> None:
    if not _PILLOW_OK:
        raise ImportError(
            "Pillow is required for overlay generation.\n"
            "Install: pip install Pillow>=10.0.0"
        )


# ── Main overlay function ──────────────────────────────────────────────────────

def make_comment_overlay(
    text: str,
    author: str = "",
    likes: int = 0,
    category: str = "",
    dst: Path | str = None,
    width: int = 1280,
    height: int = 720,
    font_path: Optional[Path] = None,
    position: str = "bottom",
) -> Path:
    """
    Create a full-frame transparent PNG overlay with comment text.

    Parameters
    ----------
    text:      comment body (truncated to ~200 chars before calling)
    author:    comment author name
    likes:     like count
    category:  highlight category (shown as a small badge)
    dst:       output PNG path
    width:     frame width  (must match source video)
    height:    frame height (must match source video)
    font_path: path to TTF font (None → Pillow default)
    position:  "bottom" | "top" | "center"
    """
    _require_pillow()

    # ── Sizes / constants ──────────────────────────────────────────────────────
    margin    = 36
    box_pad_x = 18
    box_pad_y = 12
    max_lines = 4
    font_size = 26
    meta_size = 17
    badge_size = 16
    line_gap  = 6

    # Colours (RGBA)
    BOX_BG    = (0,   0,   0,   185)
    WHITE     = (255, 255, 255, 240)
    GOLD      = (255, 200,  50, 220)
    GREY      = (175, 175, 175, 210)

    f_body  = _load_font(font_path, font_size)
    f_meta  = _load_font(font_path, meta_size)
    f_badge = _load_font(font_path, badge_size)

    # ── Build a scratch image for measuring ───────────────────────────────────
    scratch = Image.new("RGBA", (1, 1))
    sdraw   = ImageDraw.Draw(scratch)

    usable_w  = width - 2 * margin - 2 * box_pad_x
    body_lines = _wrap(sdraw, text, f_body, usable_w)[:max_lines]

    # ── Measure total box height ───────────────────────────────────────────────
    badge_h = (badge_size + line_gap) if category else 0
    body_h  = sum(_h(sdraw, ln, f_body) + line_gap for ln in body_lines)
    meta_h  = (meta_size + line_gap) if (author or likes) else 0
    box_h   = box_pad_y + badge_h + body_h + meta_h + box_pad_y

    # ── Position ───────────────────────────────────────────────────────────────
    box_w = width - 2 * margin
    if position == "bottom":
        box_y = height - box_h - margin
    elif position == "top":
        box_y = margin
    else:
        box_y = (height - box_h) // 2
    box_x = margin

    # ── Draw ──────────────────────────────────────────────────────────────────
    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Background box
    box_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(box_layer)
    bdraw.rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        fill=BOX_BG,
    )
    img = Image.alpha_composite(img, box_layer)

    draw = ImageDraw.Draw(img)

    y = box_y + box_pad_y

    # Category badge
    if category:
        badge = f"[{category}]"
        draw.text((box_x + box_pad_x, y), badge, font=f_badge, fill=GOLD)
        y += badge_size + line_gap

    # Comment text
    for line in body_lines:
        draw.text((box_x + box_pad_x, y), line, font=f_body, fill=WHITE)
        y += _h(draw, line, f_body) + line_gap

    # Meta line
    meta_parts = []
    if author:
        meta_parts.append(f"— {author}")
    if likes:
        meta_parts.append(f"  \u2665 {likes}")
    if meta_parts:
        draw.text(
            (box_x + box_pad_x, y),
            "".join(meta_parts),
            font=f_meta,
            fill=GREY,
        )

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst), "PNG")
    return dst


# ── Chat panel overlay ─────────────────────────────────────────────────────────

def make_chat_panel_overlay(
    messages: list[dict],
    dst: Path | str,
    width: int = 1280,
    height: int = 720,
    font_path: Optional[Path] = None,
    max_messages: int = 8,
) -> Path:
    """
    Create a semi-transparent live chat panel overlay.

    The panel is placed in the bottom-right corner of the frame — an area
    that typically contains the least important content in golf broadcast
    footage (scoreboards are usually bottom-left or top).

    Messages are shown oldest-at-top → newest-at-bottom, matching the
    natural flow of a live chat feed.

    Parameters
    ----------
    messages    : list of dicts with keys: text, author, likes.
                  Shown in order (caller is responsible for sorting).
    dst         : output PNG path (full-frame RGBA, same size as video)
    max_messages: cap on how many messages to render (newest = last in list)
    """
    _require_pillow()

    msgs = messages[-max_messages:] if len(messages) > max_messages else list(messages)
    if not msgs:
        # Write a fully transparent frame so add_image_overlay is a no-op
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(dst), "PNG")
        return dst

    # ── Sizing ─────────────────────────────────────────────────────────────────
    PANEL_W     = min(300, width // 4)
    HEADER_H    = 26
    MSG_PAD_Y   = 4
    MSG_PAD_X   = 8
    LINE_GAP    = 3
    AUTHOR_SIZE = 13
    TEXT_SIZE   = 15
    PANEL_MARGIN = 14         # gap from right/bottom edge

    f_author = _load_font(font_path, AUTHOR_SIZE)
    f_text   = _load_font(font_path, TEXT_SIZE)
    f_header = _load_font(font_path, AUTHOR_SIZE)

    # Measure message block heights using a scratch image
    scratch  = Image.new("RGBA", (1, 1))
    sdraw    = ImageDraw.Draw(scratch)
    usable_w = PANEL_W - 2 * MSG_PAD_X

    msg_heights: list[int] = []
    msg_wrapped: list[tuple[str, list[str]]] = []   # (author, wrapped_lines)
    for m in msgs:
        author = str(m.get("author", ""))[:24]
        text   = str(m.get("text",   ""))[:120]
        lines  = _wrap(sdraw, text, f_text, usable_w)[:3]
        a_h    = _h(sdraw, author or "A", f_author) + 1 if author else 0
        t_h    = sum(_h(sdraw, ln, f_text) + LINE_GAP for ln in lines)
        entry_h = MSG_PAD_Y + a_h + t_h + MSG_PAD_Y
        msg_heights.append(entry_h)
        msg_wrapped.append((author, lines))

    PANEL_H = HEADER_H + sum(msg_heights) + MSG_PAD_Y

    # ── Position (bottom-right) ────────────────────────────────────────────────
    panel_x = width  - PANEL_W - PANEL_MARGIN
    panel_y = height - PANEL_H - PANEL_MARGIN

    # ── Colours ────────────────────────────────────────────────────────────────
    PANEL_BG  = (15,  15,  20,  195)   # near-black, 76% opaque
    HEADER_BG = (20,  90, 200,  210)   # blue tinted header bar
    AUTHOR_C  = (130, 200, 255, 240)   # light blue for author name
    TEXT_C    = (240, 240, 240, 235)   # near-white for message text
    SEP_C     = (50,  50,  60,  180)   # subtle separator
    HEADER_TC = (255, 255, 255, 240)   # white header text

    # ── Draw ──────────────────────────────────────────────────────────────────
    img   = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Background panel
    bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    bd.rectangle(
        [panel_x, panel_y, panel_x + PANEL_W, panel_y + PANEL_H],
        fill=PANEL_BG,
    )
    img = Image.alpha_composite(img, bg)

    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle(
        [panel_x, panel_y, panel_x + PANEL_W, panel_y + HEADER_H],
        fill=HEADER_BG,
    )
    draw.text(
        (panel_x + MSG_PAD_X, panel_y + 4),
        "\U0001f4ac 라이브",
        font=f_header,
        fill=HEADER_TC,
    )

    # Messages
    y = panel_y + HEADER_H
    for i, ((author, lines), entry_h) in enumerate(zip(msg_wrapped, msg_heights)):
        if i > 0:
            draw.line(
                [(panel_x + 4, y), (panel_x + PANEL_W - 4, y)],
                fill=SEP_C, width=1,
            )

        cy = y + MSG_PAD_Y
        if author:
            draw.text((panel_x + MSG_PAD_X, cy), author, font=f_author, fill=AUTHOR_C)
            cy += _h(draw, author, f_author) + 1

        for line in lines:
            draw.text((panel_x + MSG_PAD_X, cy), line, font=f_text, fill=TEXT_C)
            cy += _h(draw, line, f_text) + LINE_GAP

        y += entry_h

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst), "PNG")
    return dst


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        w = _w(draw, candidate, font)
        if w <= max_w or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _w(draw, text: str, font) -> int:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * getattr(font, "size", 14) // 2


def _h(draw, text: str, font) -> int:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[3] - bbox[1]
    except Exception:
        return getattr(font, "size", 14)


def _load_font(font_path: Optional[Path], size: int):
    if font_path and Path(font_path).exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    return ImageFont.load_default()
