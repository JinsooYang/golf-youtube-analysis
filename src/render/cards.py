"""
cards.py — Generate still card images using Pillow.

Each card is saved as a PNG and then converted to a video segment by
ffmpeg_utils.image_to_video().  Keeping image generation separate from
ffmpeg lets us debug cards independently and avoid ffmpeg's drawtext
escaping issues with Korean text.

Card types
----------
  make_title_card        — video opening title
  make_hook_card         — single comment display (Shorts hook or narrative bridge)
  make_section_card      — act/section divider for master highlight
  make_cta_card          — call-to-action end card
  make_placeholder_card  — red warning card for missing/low-confidence timestamps
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Pillow import guard ────────────────────────────────────────────────────────

try:
    from PIL import Image, ImageDraw, ImageFont
    _PILLOW_OK = True
except ImportError:
    _PILLOW_OK = False


def _require_pillow() -> None:
    if not _PILLOW_OK:
        raise ImportError(
            "Pillow is required for card generation.\n"
            "Install: pip install Pillow>=10.0.0"
        )


# ── Default dimensions ─────────────────────────────────────────────────────────

DEFAULT_W = 1280
DEFAULT_H = 720

# ── Font sizes ─────────────────────────────────────────────────────────────────

FS_HUGE     = 72
FS_TITLE    = 56
FS_SUBTITLE = 38
FS_BODY     = 30
FS_SMALL    = 22
FS_TINY     = 18

# ── Color palette ──────────────────────────────────────────────────────────────

WHITE       = (255, 255, 255)
OFF_WHITE   = (230, 230, 230)
BLACK       = (0,   0,   0  )
NEAR_BLACK  = (12,  12,  18 )
ACCENT_GOLD = (255, 200, 50 )
MUTED_GREY  = (160, 160, 160)
DARK_BLUE   = (18,  40,  90 )
DARK_GREEN  = (18,  72,  36 )
DARK_RED    = (110, 18,  18 )
DARK_ORANGE = (90,  48,  12 )
DARK_PURPLE = (40,  28,  70 )

# Act colour mapping (index → background)
ACT_COLORS: list[tuple] = [
    DARK_BLUE,
    DARK_GREEN,
    DARK_ORANGE,
    DARK_RED,
    DARK_PURPLE,
]


# ── Font loader ────────────────────────────────────────────────────────────────

def _font(font_path: Optional[Path], size: int) -> "ImageFont.FreeTypeFont":
    _require_pillow()
    if font_path and Path(font_path).exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception as e:
            logger.warning("could not load font %s at size %d: %s", font_path, size, e)
    return ImageFont.load_default()


# ── Text layout helpers ────────────────────────────────────────────────────────

def _measure(draw: "ImageDraw.ImageDraw", text: str, font) -> tuple[int, int]:
    """Return (width, height) of rendered text."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        size = getattr(font, "size", 16)
        return len(text) * size // 2, size


def _wrap(draw: "ImageDraw.ImageDraw", text: str, font, max_w: int) -> list[str]:
    """Wrap text to fit within max_w pixels. Returns list of lines."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        w, _ = _measure(draw, candidate, font)
        if w <= max_w or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_block(
    draw: "ImageDraw.ImageDraw",
    lines: list[str],
    font,
    start_y: int,
    canvas_w: int,
    color: tuple,
    line_gap: int = 8,
    align: str = "center",
    x_offset: int = 0,
) -> int:
    """
    Draw a block of lines. Returns the y position after the last line.
    align: "center" | "left"
    """
    y = start_y
    for line in lines:
        w, h = _measure(draw, line, font)
        if align == "center":
            x = (canvas_w - w) // 2 + x_offset
        else:
            x = x_offset
        draw.text((x, y), line, font=font, fill=color)
        y += h + line_gap
    return y


def _block_height(draw, lines, font, line_gap=8) -> int:
    total = 0
    for line in lines:
        _, h = _measure(draw, line, font)
        total += h + line_gap
    return max(total - line_gap, 0)


# ── Card makers ────────────────────────────────────────────────────────────────

def make_title_card(
    title: str,
    subtitle: str = "",
    dst: Path | str = None,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    font_path: Optional[Path] = None,
) -> Path:
    """Dark opening title card with accent bar."""
    _require_pillow()
    img  = Image.new("RGB", (width, height), NEAR_BLACK)
    draw = ImageDraw.Draw(img)

    margin   = width // 10
    usable_w = width - 2 * margin

    f_title = _font(font_path, FS_TITLE)
    f_sub   = _font(font_path, FS_SUBTITLE)

    title_lines = _wrap(draw, title, f_title, usable_w)
    sub_lines   = _wrap(draw, subtitle, f_sub, usable_w) if subtitle else []

    title_h = _block_height(draw, title_lines, f_title, 10)
    sub_h   = (_block_height(draw, sub_lines, f_sub, 8) + 24) if sub_lines else 0
    total_h = title_h + sub_h

    start_y = (height - total_h) // 2

    # Accent vertical bar
    draw.rectangle([margin - 18, start_y - 12, margin - 10, start_y + total_h + 12], fill=ACCENT_GOLD)

    y = _draw_block(draw, title_lines, f_title, start_y, width, WHITE, 10)

    if sub_lines:
        _draw_block(draw, sub_lines, f_sub, y + 24, width, MUTED_GREY, 8)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst))
    return dst


def make_hook_card(
    text: str,
    author: str = "",
    likes: int = 0,
    dst: Path | str = None,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    font_path: Optional[Path] = None,
    label: str = "💬 시청자 반응",
) -> Path:
    """Comment display card for Shorts hook or narrative bridge."""
    _require_pillow()
    img  = Image.new("RGB", (width, height), NEAR_BLACK)
    draw = ImageDraw.Draw(img)

    margin   = width // 10
    usable_w = width - 2 * margin

    f_label = _font(font_path, FS_SMALL)
    f_body  = _font(font_path, FS_BODY)
    f_meta  = _font(font_path, FS_TINY)

    # Label
    label_y = height // 7
    _draw_block(draw, [label], f_label, label_y, width, ACCENT_GOLD, align="center")

    # Quote mark
    f_quote = _font(font_path, 80)
    draw.text((margin - 10, label_y + 28), "\u201c", font=f_quote, fill=ACCENT_GOLD)

    # Body text
    body_lines = _wrap(draw, text, f_body, usable_w)[:5]
    body_h     = _block_height(draw, body_lines, f_body, 10)
    body_y     = (height - body_h) // 2 - 16
    y = _draw_block(draw, body_lines, f_body, body_y, width, WHITE, 10)

    # Meta line
    meta_parts = []
    if author:
        meta_parts.append(f"— {author}")
    if likes:
        meta_parts.append(f"  \u2665 {likes}")
    if meta_parts:
        _draw_block(draw, ["".join(meta_parts)], f_meta, y + 18, width, MUTED_GREY, align="center")

    # Bottom rule
    draw.rectangle([margin, height - 40, width - margin, height - 38], fill=ACCENT_GOLD)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst))
    return dst


def make_section_card(
    section_name: str,
    description: str = "",
    emoji: str = "",
    dst: Path | str = None,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    font_path: Optional[Path] = None,
    bg_color: tuple = DARK_BLUE,
) -> Path:
    """Act / section divider card for the master highlight."""
    _require_pillow()
    img  = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin   = width // 10
    usable_w = width - 2 * margin

    f_name = _font(font_path, FS_TITLE)
    f_desc = _font(font_path, FS_SUBTITLE)

    heading = f"{emoji} {section_name}".strip() if emoji else section_name
    name_lines = _wrap(draw, heading, f_name, usable_w)
    name_h     = _block_height(draw, name_lines, f_name, 10)

    desc_lines = _wrap(draw, description, f_desc, usable_w) if description else []
    desc_h     = (_block_height(draw, desc_lines, f_desc, 8) + 28) if desc_lines else 0

    total_h = name_h + desc_h
    start_y = (height - total_h) // 2

    # Top rule
    draw.rectangle([margin, start_y - 24, width - margin, start_y - 20], fill=WHITE)

    y = _draw_block(draw, name_lines, f_name, start_y, width, WHITE, 10)

    # Bottom rule
    draw.rectangle([margin, y + 14, width - margin, y + 18], fill=WHITE)

    if desc_lines:
        _draw_block(draw, desc_lines, f_desc, y + 32, width, OFF_WHITE, 8)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst))
    return dst


def make_cta_card(
    text: str = "여러분의 생각은? 댓글로 남겨주세요 \U0001f447",
    channel: str = "",
    dst: Path | str = None,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    font_path: Optional[Path] = None,
) -> Path:
    """Call-to-action end card."""
    _require_pillow()
    img  = Image.new("RGB", (width, height), NEAR_BLACK)
    draw = ImageDraw.Draw(img)

    margin   = width // 10
    usable_w = width - 2 * margin

    f_cta  = _font(font_path, FS_TITLE)
    f_ch   = _font(font_path, FS_SMALL)
    f_hint = _font(font_path, FS_SMALL)

    cta_lines = _wrap(draw, text, f_cta, usable_w)
    cta_h     = _block_height(draw, cta_lines, f_cta, 12)
    start_y   = (height - cta_h) // 2 - 20

    y = _draw_block(draw, cta_lines, f_cta, start_y, width, WHITE, 12)

    if channel:
        ch_lines = _wrap(draw, channel, f_ch, usable_w)
        _draw_block(draw, ch_lines, f_ch, y + 28, width, ACCENT_GOLD, 8)

    # Subscribe hint at bottom
    hint = "\u2665 구독 & 좋아요"
    draw.rectangle([margin, height - 52, width - margin, height - 50], fill=ACCENT_GOLD)
    _draw_block(draw, [hint], f_hint, height - 44, width, ACCENT_GOLD)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst))
    return dst


def make_placeholder_card(
    reason: str,
    segment_id: str = "",
    dst: Path | str = None,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    font_path: Optional[Path] = None,
) -> Path:
    """
    Red warning card for segments that require manual editing.

    This card is inserted whenever a clip cannot be rendered automatically
    due to missing or low-confidence timestamps.  It is clearly visible to
    the editor so no slot is silently dropped.
    """
    _require_pillow()
    img  = Image.new("RGB", (width, height), DARK_RED)
    draw = ImageDraw.Draw(img)

    margin   = width // 10
    usable_w = width - 2 * margin

    f_warn = _font(font_path, FS_TITLE)
    f_body = _font(font_path, FS_BODY)
    f_seg  = _font(font_path, FS_SMALL)

    # Warning heading
    warn_text  = "\u26a0  수동 편집 필요"
    warn_lines = _wrap(draw, warn_text, f_warn, usable_w)
    warn_h     = _block_height(draw, warn_lines, f_warn, 10)

    reason_lines = _wrap(draw, reason, f_body, usable_w)
    reason_h     = _block_height(draw, reason_lines, f_body, 8)

    total_h = warn_h + 28 + reason_h
    start_y = (height - total_h) // 2

    y = _draw_block(draw, warn_lines, f_warn, start_y, width, WHITE, 10)
    _draw_block(draw, reason_lines, f_body, y + 28, width, OFF_WHITE, 8)

    if segment_id:
        seg_text = f"세그먼트: {segment_id}"
        _draw_block(draw, [seg_text], f_seg, height - 60, width, MUTED_GREY)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst))
    return dst
