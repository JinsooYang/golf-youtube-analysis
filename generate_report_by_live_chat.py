"""
Live-chat-based Highlight Insight PDF Report

Input files (all from output/):
  - live_chat_normalized.csv        (required)
  - highlight_package.json          (required — contains spike_moments)
  - spike_moments.csv               (fallback if highlight_package missing)

Optional, for transcript-based "why" context:
  - lesson_{VIDEO_ID}/segments.json  (produced by youtube_extractor.sh when subtitles exist)

Run: python generate_report_by_live_chat.py
Output: output/live_chat_insight_report.pdf
"""

import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.graphics.shapes import Drawing, Rect, Line, String as GString

# ── Paths ─────────────────────────────────────────────────────────────────────
FONT_DIR   = Path("fonts")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Font registration ─────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont("KR",      str(FONT_DIR / "NanumGothic-Regular.ttf")))
pdfmetrics.registerFont(TTFont("KR-Bold", str(FONT_DIR / "NanumGothic-Bold.ttf")))
pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR-Bold")

# ── Brand colours ─────────────────────────────────────────────────────────────
BLUE        = colors.HexColor("#2563EB")
BLUE_LIGHT  = colors.HexColor("#EFF6FF")
BLUE_MID    = colors.HexColor("#BFDBFE")
SLATE       = colors.HexColor("#334155")
SLATE_LIGHT = colors.HexColor("#F8FAFC")
SLATE_MID   = colors.HexColor("#E2E8F0")
ORANGE      = colors.HexColor("#EA580C")
GREEN       = colors.HexColor("#16A34A")
RED         = colors.HexColor("#DC2626")
GREY        = colors.HexColor("#64748B")
WHITE       = colors.white
BLACK       = colors.HexColor("#0F172A")

PW, PH = A4
M = 18 * mm


# ── Style helpers ─────────────────────────────────────────────────────────────

def S(name, **kw) -> ParagraphStyle:
    base = dict(fontName="KR", fontSize=9, leading=15, textColor=BLACK,
                spaceBefore=0, spaceAfter=0, wordWrap="CJK")
    base.update(kw)
    return ParagraphStyle(name, **base)


STYLES = {
    "h1":        S("h1",  fontName="KR-Bold", fontSize=22, leading=30,
                   textColor=BLUE, spaceAfter=4),
    "subtitle":  S("sub", fontSize=10, textColor=GREY, spaceAfter=10),
    "h2":        S("h2",  fontName="KR-Bold", fontSize=13, leading=18,
                   textColor=BLUE, spaceBefore=8, spaceAfter=4),
    "h3":        S("h3",  fontName="KR-Bold", fontSize=10, leading=15,
                   textColor=SLATE, spaceBefore=6, spaceAfter=3),
    "body":      S("body", fontSize=9, leading=15, spaceAfter=4,
                   alignment=TA_JUSTIFY),
    "body_left": S("bodyl", fontSize=9, leading=15, spaceAfter=4),
    "small":     S("sm",  fontSize=8, leading=12, textColor=GREY),
    "tag":       S("tag", fontName="KR-Bold", fontSize=8, textColor=BLUE),
    "num_big":   S("nb",  fontName="KR-Bold", fontSize=28, leading=34,
                   textColor=BLUE, alignment=TA_CENTER),
    "num_label": S("nl",  fontSize=8, textColor=GREY, alignment=TA_CENTER),
}


# ── Page template ─────────────────────────────────────────────────────────────

def make_doc(path: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M + 8 * mm, bottomMargin=M + 8 * mm,
        title="라이브 채팅 기반 하이라이트 인사이트 리포트",
        author="GTOUR Analysis",
    )
    fw = PW - 2 * M

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(0.6)
        canvas.line(M, PH - M - 4 * mm, PW - M, PH - M - 4 * mm)
        canvas.setFont("KR-Bold", 7.5)
        canvas.setFillColor(BLUE)
        canvas.drawString(M, PH - M - 1.5 * mm, "라이브 채팅 기반 하이라이트 인사이트")
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawRightString(PW - M, PH - M - 1.5 * mm, "Live Chat Spike Report")
        canvas.setStrokeColor(SLATE_MID)
        canvas.line(M, M + 5 * mm, PW - M, M + 5 * mm)
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(PW / 2, M + 1.5 * mm, str(doc.page))
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(
        id="normal",
        frames=[Frame(M, M + 9 * mm, fw, PH - 2 * M - 18 * mm, id="main")],
        onPage=header_footer,
    )])
    return doc


# ── Utility flowables ─────────────────────────────────────────────────────────

def rule(color=SLATE_MID, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color,
                      spaceAfter=4, spaceBefore=4)

def vspace(h_mm=4):
    return Spacer(1, h_mm * mm)

def section_heading(text: str):
    return [vspace(3), Paragraph(text, STYLES["h2"]), rule(BLUE_MID, 1), vspace(1)]

def bullet(text: str, indent=0):
    style = ParagraphStyle(
        "blt_", fontName="KR", fontSize=9, leading=15,
        leftIndent=12 + indent, firstLineIndent=0,
        spaceAfter=2, wordWrap="CJK", textColor=BLACK,
    )
    return Paragraph("• " + text, style)

def stat_table(items: list) -> Table:
    n = len(items)
    w = (PW - 2 * M) / n
    data = [
        [Paragraph(str(v), STYLES["num_big"]) for _, v in items],
        [Paragraph(lbl, STYLES["num_label"]) for lbl, _ in items],
    ]
    t = Table(data, colWidths=[w] * n, rowHeights=[30 * mm, 8 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",       (0, 0), (-1, -1), 0.5, BLUE_MID),
        ("TOPPADDING",    (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
    ]))
    return t

def info_table(headers: list, rows: list, col_widths=None) -> Table:
    fw = PW - 2 * M
    col_widths = [fw * r for r in col_widths] if col_widths else [fw / len(headers)] * len(headers)
    header_cells = [Paragraph(h, ParagraphStyle(
        "th", fontName="KR-Bold", fontSize=8.5, leading=13,
        textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK")) for h in headers]
    body_rows = [[Paragraph(str(c), ParagraphStyle(
        "td", fontName="KR", fontSize=8.5, leading=14,
        textColor=BLACK, wordWrap="CJK")) for c in row] for row in rows]
    t = Table([header_cells] + body_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, -1), "KR"),
        ("FONTNAME",      (0, 0), (-1, 0),  "KR-Bold"),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("ALIGN",         (0, 1), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LINEBELOW",     (0, 0), (-1, 0),  1,   BLUE),
    ]))
    return t

def chat_card(timestamp: str, author: str, text: str, accent=BLUE) -> list:
    """Compact card for a single live-chat message."""
    fw = PW - 2 * M
    ts_w = 18 * mm
    rest_w = fw - ts_w - 3 * mm
    ts_style = ParagraphStyle("ts_", fontName="KR-Bold", fontSize=7.5,
        textColor=accent, alignment=TA_CENTER, leading=12)
    auth_style = ParagraphStyle("ca_", fontName="KR-Bold", fontSize=7.5,
        textColor=GREY, leading=11)
    txt_style = ParagraphStyle("ct_", fontName="KR", fontSize=8.5, leading=14,
        textColor=BLACK, wordWrap="CJK")
    left_t = Table([[Paragraph(timestamp, ts_style)]], colWidths=[ts_w])
    left_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLUE_LIGHT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    right_t = Table(
        [[Paragraph(author, auth_style)],
         [Paragraph(text,   txt_style)]],
        colWidths=[rest_w]
    )
    right_t.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("BACKGROUND",    (0, 0), (-1, -1), SLATE_LIGHT),
    ]))
    outer = Table([[left_t, right_t]], colWidths=[ts_w, rest_w + 3 * mm])
    outer.setStyle(TableStyle([
        ("VALIGN",          (0, 0), (-1, -1), "TOP"),
        ("GRID",            (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 0),
        ("TOPPADDING",      (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 0),
    ]))
    return [outer, vspace(1.5)]

def bar_chart(items: list, max_val: int, color=BLUE, accent_idx: int = -1) -> Table:
    fw = PW - 2 * M
    label_w = 52 * mm
    bar_w = fw - label_w - 22 * mm
    val_w = 22 * mm
    rows = []
    for i, (label, val) in enumerate(items):
        fill_ratio = val / max_val if max_val > 0 else 0
        fill_px = int(bar_w * fill_ratio)
        empty_px = int(bar_w) - fill_px
        bar_color = ORANGE if i == accent_idx else color
        lbl_weight = "KR-Bold" if i == accent_idx else "KR"
        lbl = Paragraph(str(label), ParagraphStyle(
            "brl", fontName=lbl_weight, fontSize=8.5, leading=13,
            textColor=BLACK, wordWrap="CJK"))
        bar_inner = Table([[" ", " "]], colWidths=[fill_px or 1, empty_px or 1], rowHeights=[10])
        bar_inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), bar_color),
            ("BACKGROUND", (1, 0), (1, 0), SLATE_MID),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        val_p = Paragraph(str(val), ParagraphStyle(
            "brv", fontName="KR-Bold", fontSize=8, textColor=GREY, alignment=TA_RIGHT))
        rows.append([lbl, bar_inner, val_p])
    t = Table(rows, colWidths=[label_w, bar_w, val_w])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SLATE_LIGHT]),
    ]))
    return t

def callout(text: str, accent=BLUE) -> Table:
    data = [[Paragraph(str(text), ParagraphStyle(
        "cal", fontName="KR", fontSize=9, leading=15,
        textColor=BLACK, wordWrap="CJK", alignment=TA_JUSTIFY))]]
    t = Table(data, colWidths=[PW - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLUE_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE",    (0, 0), (-1, -1), 3, accent),
    ]))
    return t

def note_box(text: str) -> Table:
    data = [[Paragraph(str(text), ParagraphStyle(
        "nb_", fontName="KR", fontSize=8.5, leading=14,
        textColor=GREY, wordWrap="CJK"))]]
    t = Table(data, colWidths=[PW - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), SLATE_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    return t

def buzz_box(buzz: dict) -> Table:
    """
    Compact coloured summary box showing the dominant spike topic and buzz type.

    Colour coding
    -------------
    BLUE   — broadcast_event  (on-screen golf event drove the spike)
    GREEN  — participant_driven  (channel host / guest creator is the focus)
    ORANGE — mixed  (both broadcast event and participant discussion)
    GREY   — general  (no clear pattern; chatter density only)
    """
    _BG = {
        "broadcast_event":    BLUE_LIGHT,
        "participant_driven": colors.HexColor("#DCFCE7"),
        "mixed":              colors.HexColor("#FFF7ED"),
        "general":            SLATE_LIGHT,
    }
    color    = buzz.get("buzz_color", GREY)
    bg       = _BG.get(buzz.get("buzz_type", "general"), SLATE_LIGHT)
    headline = buzz.get("headline", "—")
    btype    = buzz.get("buzz_type_label", "—")
    ev_pct   = int(buzz.get("ev_ratio", 0) * 100)
    int_pct  = int(buzz.get("int_ratio", 0) * 100)
    pname    = buzz.get("participant_in_chat")
    prole    = buzz.get("participant_role", "")

    tag_parts = [f"[{btype}]", f"이벤트 {ev_pct}% / 내부 {int_pct}%"]
    if pname:
        tag_parts.append(f"{pname}({prole}) 참여")
    tag_line = "  ·  ".join(tag_parts)

    narrative = buzz.get("narrative", "")

    title_s = ParagraphStyle(
        "_bzt", fontName="KR-Bold", fontSize=10, leading=14,
        textColor=color, wordWrap="CJK")
    tag_s = ParagraphStyle(
        "_bztg", fontName="KR", fontSize=7.5, leading=11,
        textColor=GREY, wordWrap="CJK")
    narr_s = ParagraphStyle(
        "_bzn", fontName="KR", fontSize=9, leading=14,
        textColor=BLACK, wordWrap="CJK")

    rows = [
        [Paragraph("▶ " + headline, title_s)],
        [Paragraph(tag_line, tag_s)],
    ]
    if narrative:
        rows.append([Paragraph(narrative, narr_s)])

    t = Table(rows, colWidths=[PW - 2 * M])
    n = len(rows)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("LINEBEFORE",    (0, 0), (-1, -1), 3, color),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (0, 0),   6),
        ("BOTTOMPADDING", (0, 0), (0, 0),   1),
        ("TOPPADDING",    (0, 1), (0, 1),   1),
        ("BOTTOMPADDING", (0, 1), (0, 1),   1),
        ("TOPPADDING",    (0, n-1), (0, n-1), 3),
        ("BOTTOMPADDING", (0, n-1), (0, n-1), 7),
    ]))
    return t


def mini_reaction_table(reaction_profile: list) -> Table:
    """Compact horizontal table showing reaction type counts."""
    if not reaction_profile:
        return note_box("반응 유형 데이터 없음")
    top = reaction_profile[:5]
    max_c = top[0][1] if top else 1
    fw = PW - 2 * M
    col_w = fw / len(top)
    pct_row = []
    lbl_row = []
    for label, cnt in top:
        pct = int(cnt / max_c * 100)
        pct_row.append(Paragraph(str(cnt), ParagraphStyle(
            "rn", fontName="KR-Bold", fontSize=10, textColor=ORANGE,
            alignment=TA_CENTER, leading=14)))
        lbl_row.append(Paragraph(label, ParagraphStyle(
            "rl", fontName="KR", fontSize=7.5, textColor=GREY,
            alignment=TA_CENTER, leading=11, wordWrap="CJK")))
    t = Table([pct_row, lbl_row], colWidths=[col_w] * len(top),
              rowHeights=[16 * mm, 10 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF7ED")),
        ("BACKGROUND", (0, 1), (-1, 1), SLATE_LIGHT),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",       (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# ── Density sparkline chart ───────────────────────────────────────────────────

def density_sparkline(
    timeline: list,
    spike_times: list,
    fw: float,
) -> Drawing:
    """
    Compact time-series bar chart: x = video timestamp, y = chat density.

    Renders as a Drawing (directly usable as a ReportLab Flowable).

    timeline    : [(second_offset, count), ...] sorted by time
    spike_times : [anchor_time_sec, ...] for top-N spikes — drawn as orange lines
    fw          : available page width in points
    """
    CHART_H = 28 * mm
    AXIS_H  =  7 * mm   # room for x-axis time labels
    YLAB_W  =  8 * mm   # room for y-axis peak label
    TOTAL_H = CHART_H + AXIS_H
    plot_w  = fw - YLAB_W

    d = Drawing(fw, TOTAL_H)

    if not timeline:
        return d

    max_cnt = max(cnt for _, cnt in timeline)
    n       = len(timeline)
    bar_w   = plot_w / n

    # Background panel
    d.add(Rect(YLAB_W, AXIS_H, plot_w, CHART_H,
               fillColor=SLATE_LIGHT, strokeColor=SLATE_MID, strokeWidth=0.3))

    # Bars — each bucket is one bar
    for i, (sec, cnt) in enumerate(timeline):
        bar_h = max(0.5, (cnt / max_cnt) * CHART_H)
        x = YLAB_W + i * bar_w
        d.add(Rect(x + 0.2, AXIS_H, bar_w - 0.4, bar_h,
                   fillColor=BLUE_MID, strokeColor=None))

    # Spike markers — thin orange vertical lines at anchor times
    if timeline and spike_times:
        total_sec = timeline[-1][0] + 120   # last bucket start + 2-min bucket width
        for spike_ts in spike_times:
            frac = min(1.0, spike_ts / total_sec)
            x    = YLAB_W + frac * plot_w
            d.add(Line(x, AXIS_H, x, AXIS_H + CHART_H,
                       strokeColor=ORANGE, strokeWidth=1.0))

    # X-axis baseline
    d.add(Line(YLAB_W, AXIS_H, YLAB_W + plot_w, AXIS_H,
               strokeColor=SLATE_MID, strokeWidth=0.4))

    # X-axis time labels — ~7 evenly-spaced ticks
    label_step = max(1, n // 7)
    for i in range(0, n, label_step):
        sec = timeline[i][0]
        h   = int(sec) // 3600
        m   = (int(sec) % 3600) // 60
        lbl = f"{h}:{m:02d}"
        x   = YLAB_W + i * bar_w + bar_w / 2
        s   = GString(x, 1.5 * mm, lbl)
        s.fontName   = "KR"
        s.fontSize   = 5.5
        s.fillColor  = GREY
        s.textAnchor = "middle"
        d.add(s)

    # Peak count label on y-axis
    pk = GString(YLAB_W - 1, AXIS_H + CHART_H - 4, str(max_cnt))
    pk.fontName   = "KR"
    pk.fontSize   = 5.5
    pk.fillColor  = GREY
    pk.textAnchor = "end"
    d.add(pk)

    # Zero baseline label
    zero = GString(YLAB_W - 1, AXIS_H + 1, "0")
    zero.fontName   = "KR"
    zero.fontSize   = 5.5
    zero.fillColor  = GREY
    zero.textAnchor = "end"
    d.add(zero)

    return d


# ── Format helpers ────────────────────────────────────────────────────────────

def fmt_seconds(sec) -> str:
    try:
        sec = int(float(sec))
    except (TypeError, ValueError):
        return "--:--"
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return "{:d}:{:02d}:{:02d}".format(h, m, s)

def safe_str(val, fallback="—") -> str:
    if val is None:
        return fallback
    s = str(val).strip()
    return s if s else fallback


def _ko_p(word: str, vowel_form: str, consonant_form: str) -> str:
    """Return correct Korean particle based on the final syllable of word."""
    if not word:
        return vowel_form
    last = word[-1]
    if '\uAC00' <= last <= '\uD7A3':
        # No final consonant (종성 없음) → vowel form
        if (ord(last) - 0xAC00) % 28 == 0:
            return vowel_form
        return consonant_form
    return vowel_form  # non-Hangul fallback


# ── Reaction & event knowledge base ───────────────────────────────────────────

# Compiled patterns for normalization
_KK_RE = re.compile(r"^ㅋ+$")
_HH_RE = re.compile(r"^ㅎ+$")
_TT_RE = re.compile(r"^[ㅠㅜ]+$")
_OO_RE = re.compile(r"^ㅇ+$")
_AA_RE = re.compile(r"^ㅏ+$|^ㅓ+$|^아+$|^어+$")  # elongated vowels/exclamations

# Maps: (canonical token → display label, reaction category)
REACTION_TOKENS: dict[str, tuple[str, str]] = {
    "웃음(ㅋ)":   ("웃음(ㅋ)",    "웃음·재미"),
    "웃음(ㅎ)":   ("웃음(ㅎ)",    "웃음·가벼운"),
    "안타까움(ㅠ)": ("안타까움(ㅠ)", "안타까움·슬픔"),
    "와":         ("와",          "탄성·놀람"),
    "헐":         ("헐",          "충격·당황"),
    "대박":       ("대박",        "감탄·대박"),
    "역전":       ("역전",        "역전 장면"),
    "동타":       ("동타",        "동타 장면"),
    "역시":       ("역시",        "기대 충족"),
    "화이팅":     ("화이팅",      "응원·격려"),
    "아":         ("아",          "탄식·긴장"),
    "진짜":       ("진짜",        "강조·감탄"),
    "ㅠ":         ("안타까움(ㅠ)", "안타까움·슬픔"),
}

# Golf game events — maps raw tokens → canonical event name
GOLF_EVENTS: dict[str, str] = {
    "OB": "OB", "ob": "OB", "오비": "OB", "아웃": "OB",
    "버디": "버디", "이글": "이글", "알바": "알바트로스", "홀인원": "홀인원",
    "파": "파", "보기": "보기", "더블": "더블보기", "트리플": "트리플보기",
    "동타": "동타(타이)", "역전": "역전", "연장": "연장전", "우승": "우승",
    "퍼트": "퍼트", "퍼터": "퍼터", "드라이버": "드라이버 샷",
    "뒷땅": "뒷땅", "티샷": "티샷", "어프로치": "어프로치",
    "그린": "그린", "러프": "러프", "페어웨이": "페어웨이",
    "18홀": "18번홀", "17홀": "17번홀", "16홀": "16번홀", "15홀": "15번홀",
    "최종홀": "최종홀", "막홀": "최종홀",
    "샷": "샷",
}

_REACTION_SET = set(REACTION_TOKENS.keys())
_EVENT_SET    = set(GOLF_EVENTS.keys())

# Korean stopwords — common words that look like names but aren't
_KR_STOPWORDS = {
    "내일", "오늘", "어제", "진짜", "대박", "나이스", "아니", "이게", "뭐", "왜",
    "어디", "얼마", "언제", "어떻게", "이거", "저거", "그거", "맞아", "맞네",
    "좋다", "좋아", "이야", "이제", "이분", "이번", "이런", "그런", "저런",
    "우리", "여기", "거기", "저기", "하나", "두개", "세개", "몇개", "몇번",
    "마지막", "처음", "정말", "너무", "완전", "그냥", "아직", "계속", "그리고",
    "하지만", "근데", "그런데", "그러면", "그래서", "다시", "언더", "오버",
    "캐디", "경기", "갤러리", "라운드", "홀아웃", "그린이",
    "자막", "유튜브", "라이브", "중계", "댓글", "영상", "채널", "구독",
    # Generic title words that look like names when captured as group(1)
    "프로", "선수", "코치", "감독",
}

# Matches (name)(title) pattern — adjacent, for chat messages (e.g. 이성훈선수, 문서형프로)
_TITLE_RE = re.compile(
    r'([\uAC00-\uD7A3]{2,5})(프로님|선수님|형님|프로|선수|형|님|코치|감독)'
)
# Same pattern with optional space — for subtitle/commentary text where natural
# Korean spacing separates name and title (e.g. "이성훈 선수", "김용석 선수가")
_TITLE_RE_SPACED = re.compile(
    r'([\uAC00-\uD7A3]{2,5})\s*(프로님|선수님|형님|프로|선수|형|님|코치|감독)'
)

# ── Player alias / identity table ─────────────────────────────────────────────
#
# Maps every chat nickname / honorific variant to a single canonical identity.
# Add new entries as new players appear in broadcasts.
#
PLAYER_ALIASES: dict[str, str] = {
    # 문서형  — golf YouTube creator, sometimes participates in chat directly
    "문서형님":   "문서형",
    "문서형프로": "문서형",
    "문프로님":   "문서형",
    "문스터형":   "문서형",
    "문서형":     "문서형",
    # 골과장님  — GOLFZON staff player
    "골과장님":   "골과장님",
    "과장님":     "골과장님",
    # 이성훈  — professional player
    "이성훈프로":   "이성훈 프로",
    "이성훈프로님": "이성훈 프로",
    "이성훈선수":   "이성훈 프로",
    "성훈프로":     "이성훈 프로",
    # 하기원  — professional player
    "하기원프로":   "하기원 프로",
    "하기원선수":   "하기원 프로",
    "하프로님":     "하기원 프로",
    # 공태현  — professional player
    "공태현프로":   "공태현 프로",
    "공태현선수":   "공태현 프로",
    # 이용희  — professional player
    "이용희프로":   "이용희 프로",
    "이용희선수":   "이용희 프로",
    # 장태형
    "장태형":       "장태형",
    # 홍택이형
    "홍택이형":     "홍택이형",
    # 이장님  — chat nickname (appears during eagle scene)
    "이장님":       "이장님",
    # 김용석  — in-tournament player named in commentary
    "김용석":       "김용석 선수",
    "김용석선수":   "김용석 선수",
    "김용석프로":   "김용석 선수",
    # 김영석  — YouTube auto-subtitle ASR error for 김용석 (ㅗ→ㅕ vowel confusion)
    #           The commentator says "김용석" but the ASR transcribes "김영석".
    #           Map it to the correct player so commentary extraction is accurate.
    "김영석":       "김용석 선수",
    "김영석선수":   "김용석 선수",
    "김영석프로":   "김용석 선수",
}


def resolve_canonical(raw_name: str) -> str:
    """Map a raw name/nickname to its canonical identity (falls back to raw_name)."""
    return PLAYER_ALIASES.get(raw_name, raw_name)


# ── Entity registry ───────────────────────────────────────────────────────────
#
# Maps canonical identities to metadata including role classification and
# author_patterns (substrings matched against the chat 'author' field to detect
# whether the entity is actively sending messages in the live chat).
#
# Roles
# -----
#   channel_host        — the YouTube channel's own presenter / staff
#   channel_participant — guest creator or recurring special participant
#   professional_player — KPGA/tour golfer appearing on-screen
#   unknown             — unclassified; falls back to mention-count analysis only
#
ENTITY_REGISTRY: dict[str, dict] = {
    "골과장님": {
        "role": "channel_host",
        "role_label": "채널 호스트",
        "description": "GOLFZON 채널 진행자",
        "aliases": ["골과장님", "과장님"],
        "author_patterns": ["골과장", "golfzon"],
    },
    "골사원": {
        "role": "channel_host",
        "role_label": "채널 호스트",
        "description": "GOLFZON 채널 진행자 (2)",
        "aliases": ["골사원"],
        "author_patterns": ["골사원"],
    },
    "문서형": {
        "role": "channel_participant",
        "role_label": "채널 참여 크리에이터",
        "description": "골프 유튜버, 방송 참여 크리에이터",
        "aliases": ["문서형님", "문서형프로", "문프로님", "문스터형", "문서형"],
        "author_patterns": ["문서형"],
    },
    "이성훈 프로": {
        "role": "professional_player",
        "role_label": "프로 선수",
        "description": "KPGA 투어 프로 선수",
        "aliases": ["이성훈프로", "이성훈프로님", "이성훈선수", "성훈프로"],
        "author_patterns": [],
    },
    "하기원 프로": {
        "role": "professional_player",
        "role_label": "프로 선수",
        "description": "KPGA 투어 프로 선수",
        "aliases": ["하기원프로", "하기원선수", "하프로님"],
        "author_patterns": [],
    },
    "공태현 프로": {
        "role": "professional_player",
        "role_label": "프로 선수",
        "description": "KPGA 투어 프로 선수",
        "aliases": ["공태현프로", "공태현선수"],
        "author_patterns": [],
    },
    "이용희 프로": {
        "role": "professional_player",
        "role_label": "프로 선수",
        "description": "KPGA 투어 프로 선수",
        "aliases": ["이용희프로", "이용희선수"],
        "author_patterns": [],
    },
    "김용석 선수": {
        "role": "professional_player",
        "role_label": "프로 선수",
        "description": "투어 선수",
        # 김영석 = YouTube auto-subtitle ASR error (ㅗ/ㅕ vowel confusion)
        "aliases": ["김용석", "김용석선수", "김용석프로", "김영석", "김영석선수"],
        "author_patterns": [],
    },
}


def detect_active_participants(text_msgs: list[dict]) -> dict[str, dict]:
    """
    Check ENTITY_REGISTRY author_patterns against actual chat author names.
    Returns {canonical_name: entity_info} for entities actively chatting.
    Only entities with non-empty author_patterns are checked.
    """
    active: dict[str, dict] = {}
    for canonical, info in ENTITY_REGISTRY.items():
        patterns = [p.lower() for p in info.get("author_patterns", [])]
        if not patterns:
            continue
        for m in text_msgs:
            author = (m.get("author") or "").lower()
            if any(p in author for p in patterns):
                active[canonical] = info
                break
    return active


# ── Chat message classifier ───────────────────────────────────────────────────
#
# Distinguishes messages that are reacting to the broadcast/on-screen event
# from messages that are conversations happening inside the chat itself.
#
_AT_RE = re.compile(r'@\S')          # direct @reply to another user
_DIRECT_Q_RE = re.compile(           # "문프로님 내일 ..." style direct address + question
    r'[\uAC00-\uD7A3]{2,5}(프로님?|선수님?|형님?|님)\s*.{0,30}[?？]'
)
# Words that signal chat-internal conversations (logistics / meta / personal)
_LOGISTICS_WORDS = {
    "내일", "모레", "언제", "어디서", "어디", "몇시", "예약", "코스",
    "볼스", "볼스코어", "라운드예약", "내주", "다음주", "방문", "연락",
    "인스타", "구독", "멤버십", "후원", "슈퍼챗", "채팅", "댓글",
    "유튜브", "영상올려", "편집", "업로드", "언제나와",
}
# Golf / broadcast words that strongly suggest event-reaction
_BROADCAST_WORDS = (set(GOLF_EVENTS.keys()) | {
    "이글", "버디", "OB", "홀인원", "파", "보기", "역전", "우승",
    "나이스샷", "나이스", "장타", "퍼트", "드라이버", "그린", "홀",
    "라운드", "스코어", "언더", "오버", "해설", "선수", "경기",
}) - _KR_STOPWORDS


def classify_message(msg: dict) -> str:
    """
    Classify a chat message as one of:
      'event'    — reacting to what is happening on-screen / in commentary
      'internal' — conversation within the chat (address to participant,
                   logistics, direct @reply, meta-discussion)
      'mixed'    — contains both signals; included in event analysis but
                   also shown in the internal layer

    Rules (in priority order):
      1. @reply → internal
      2. Direct-question pattern "(name)(호칭) …?" → internal
      3. Contains logistics/meta words but no broadcast words → internal
      4. Contains broadcast/golf event words → event
      5. Pure reaction tokens (ㅋ/와/대박 …) → event
      6. Everything else → mixed (ambiguous; treated as event for reaction
         scoring but flagged for the internal layer too)
    """
    text = (msg.get("text") or "").strip()
    if not text:
        return "mixed"

    # 1. @-reply
    if _AT_RE.search(text):
        return "internal"

    # 2. Direct question to named person
    if _DIRECT_Q_RE.search(text):
        return "internal"

    words = set(text.split())

    # 3. Logistics without any broadcast content
    has_logistics  = bool(words & _LOGISTICS_WORDS)
    has_broadcast  = bool(words & _BROADCAST_WORDS)
    if has_logistics and not has_broadcast:
        return "internal"

    # 4. Broadcast / golf-event keywords present
    if has_broadcast:
        return "event"

    # 5. Pure reaction tokens
    tokens = [t for t in (normalize_word(w) for w in text.split()) if t]
    if tokens and all(t in _REACTION_SET for t in tokens):
        return "event"

    # 6. Ambiguous
    return "mixed"


def normalize_word(word: str):
    """
    Normalize a single token.
    - ㅋ+ of any length  → 'ㅋ' canonical (all map to same '웃음(ㅋ)' category)
    - ㅎ+               → 'ㅎ'
    - ㅠ+/ㅜ+           → 'ㅠ'
    - Pure vowel noise  → None (drop)
    - Single char       → None
    Returns canonical string or None.
    """
    w = word.strip()
    if not w:
        return None
    if _KK_RE.match(w):
        return "웃음(ㅋ)"
    if _HH_RE.match(w):
        return "웃음(ㅎ)"
    if _TT_RE.match(w):
        return "안타까움(ㅠ)"
    if _OO_RE.match(w) or _AA_RE.match(w):
        return None   # pure noise
    if len(w) == 1:
        return None
    return w


def tokenize_message(text: str) -> list[str]:
    """Split message text into normalized tokens, dropping noise."""
    tokens = []
    for raw in str(text).split():
        nw = normalize_word(raw)
        if nw:
            tokens.append(nw)
    return tokens


def classify_reactions(messages: list[dict]) -> list[tuple[str, int]]:
    """
    Count reaction-category occurrences in a list of message dicts.
    Returns sorted (category_label, count) list.
    """
    counter: Counter = Counter()
    for m in messages:
        for tok in tokenize_message(m.get("text", "") or ""):
            if tok in _REACTION_SET:
                _, category = REACTION_TOKENS[tok]
                counter[category] += 1
            elif tok in ("와", "와아", "와~"):
                counter["탄성·놀람"] += 1
            elif tok in ("헐", "헐ㄷ", "헐ㅋ"):
                counter["충격·당황"] += 1
    return counter.most_common()


def extract_mentions_and_events(
    primary_msgs: list[dict],
    context_msgs: list[dict] | None = None,
    min_count: int = 1,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """
    From a list of message dicts, return:
      player_candidates: names detected via (name)(title) pattern, ranked by frequency
      event_mentions: known golf event keywords with counts

    primary_msgs  — tight window (anchor±10s): main evidence for player/event detection
    context_msgs  — broader window (buildup+peak): fallback if primary yields nothing
    """
    if context_msgs is None:
        context_msgs = primary_msgs

    def _extract(msgs):
        title_counter: Counter = Counter()
        event_counter: Counter = Counter()
        for m in msgs:
            text = m.get("text", "") or ""
            # Title-pattern player detection with canonical resolution
            for match in _TITLE_RE.finditer(text):
                name  = match.group(1)
                title = match.group(2)
                if name not in _KR_STOPWORDS:
                    raw       = name + title
                    canonical = resolve_canonical(raw)
                    title_counter[canonical] += 1
            # Event keywords via tokenizer
            for tok in tokenize_message(text):
                if tok in _EVENT_SET:
                    event_counter[GOLF_EVENTS[tok]] += 1
        return title_counter, event_counter

    title_ctr, event_ctr = _extract(primary_msgs)

    # If tight window found nothing, widen to full context
    if not title_ctr and not event_ctr:
        title_ctr, event_ctr = _extract(context_msgs)

    player_cands = [
        (name, cnt) for name, cnt in title_counter.most_common(8)
        if cnt >= min_count
    ] if (title_counter := title_ctr) else []

    return player_cands, event_ctr.most_common(8)


def generate_narrative(
    player_cands: list,
    event_mentions: list,
    reaction_profile: list,
    message_count: int,
    commentary_ctx: dict | None = None,
    primary_player: str | None = None,
) -> dict:
    """
    Build a structured 3-part narrative connecting commentary evidence to chat
    reaction.  Returns a dict rather than a plain string so the PDF card can
    render each part separately.

    Evidence hierarchy
    ------------------
    cause  : What triggered the spike.
             If subtitles are available, the pre-spike commentary window is
             the primary source (commentator described the event before viewers
             could type).  Player names and event keywords extracted from tight
             chat window supplement or cross-validate.
             If no subtitles, chat-based inference is used with lower confidence.

    reaction : How viewers responded, derived entirely from live chat
               during the spike window: reaction category counts +
               message volume.

    interpretation : One sentence explicitly connecting cause → reaction.
                     Phrased to distinguish "confirmed by two signals" from
                     "inferred from chat only" or "weak evidence".

    short  : Compact one-liner for the overview table (≤ 40 chars).
    """
    # primary_player wins over raw player_cands[0] for scene subject
    top_player = primary_player or (player_cands[0][0] if player_cands else None)
    top_event  = event_mentions[0][0] if event_mentions else None
    top_react  = reaction_profile[0][0] if reaction_profile else None

    players_str = (
        f"{player_cands[0][0]}·{player_cands[1][0]}" if len(player_cands) >= 2
        else (top_player or "")
    )

    # ── Determine subject (player + event or fallback) ────────────────────────
    if players_str and top_event:
        subject_chat = f"{players_str}의 {top_event}"
    elif players_str:
        subject_chat = f"{players_str} 관련 장면"
    elif top_event:
        subject_chat = f"{top_event} 장면"
    else:
        subject_chat = None

    ctx          = commentary_ctx or {}
    has_comm     = ctx.get("has_content", False)
    ev_src       = ctx.get("evidence_source", "none")
    pre_text     = ctx.get("pre_text", "").strip()
    conc_text    = ctx.get("concurrent_text", "").strip()
    # The strongest commentary signal: pre-spike preferred, concurrent as fallback
    best_comm    = pre_text or conc_text

    # ── CAUSE ─────────────────────────────────────────────────────────────────
    if has_comm:
        # Commentary is available → lead with it, append chat-derived subject
        snippet = best_comm[:90].rstrip()
        if snippet and not snippet.endswith(("다", "요", "죠", ".", "。")):
            snippet += "..."
        comm_label = (
            "스파이크 직전 해설"  if ev_src in ("pre_spike", "both")
            else "스파이크 중 해설"
        )
        if subject_chat:
            cause = f"[{comm_label}] 「{snippet}」\n→ 채팅 기반 보완: {subject_chat}"
        else:
            cause = f"[{comm_label}] 「{snippet}」"
    elif subject_chat:
        cause = f"{subject_chat}  (자막 없음 — 채팅 텍스트 기반 추론)"
    else:
        cause = "근거 불충분 — 채팅량만으로 선정된 구간"

    # ── REACTION ──────────────────────────────────────────────────────────────
    if reaction_profile:
        rx_parts = [f"{cat}({cnt})" for cat, cnt in reaction_profile[:3]]
        reaction = f"{message_count}개 메시지 / 반응 유형: {', '.join(rx_parts)}"
    else:
        reaction = f"{message_count}개 메시지 (반응 유형 미분류)"

    # ── INTERPRETATION ────────────────────────────────────────────────────────
    if has_comm and subject_chat and top_react:
        confidence = "해설 + 채팅 두 신호 일치"
        interpretation = (
            f"{confidence}: {subject_chat} 장면에서 해설자가 해당 상황을 묘사했고, "
            f"시청자들은 {top_react}으로 즉각 반응했습니다."
        )
    elif has_comm and top_react:
        interpretation = (
            f"해설 맥락이 존재하나 선수/이벤트 특정 불가. "
            f"채팅에서는 {top_react} 반응({message_count}개)이 관측됩니다."
        )
    elif has_comm:
        interpretation = (
            "해설 맥락 존재. 채팅 반응 유형 미분류 — "
            "메시지 수만으로 스파이크 선정."
        )
    elif subject_chat and top_react:
        interpretation = (
            f"자막 없음 — 채팅 텍스트만으로 추론: {subject_chat}에서 "
            f"{top_react} 반응 집중. 실제 인과관계 확인 필요."
        )
    else:
        interpretation = (
            "자막 없음 + 채팅 텍스트 근거 불충분. "
            "메시지 밀집도만으로 스파이크 선정된 구간 — 수동 검토 권장."
        )

    # ── SHORT (for table) ─────────────────────────────────────────────────────
    if subject_chat and top_react:
        short = f"{subject_chat} → {top_react}"
    elif subject_chat:
        short = subject_chat
    elif best_comm:
        short = best_comm[:35] + ("..." if len(best_comm) > 35 else "")
    else:
        short = "반응 구간"

    return {
        "cause":          cause,
        "reaction":       reaction,
        "interpretation": interpretation,
        "short":          short,
        "has_commentary": has_comm,
        "evidence_source": ev_src,
    }


def load_segments(video_id: str) -> list[dict]:
    """Load lesson_{video_id}/segments.json if available (produced by youtube_extractor.sh)."""
    if not video_id or video_id in ("—", ""):
        return []
    seg_path = Path(f"lesson_{video_id}") / "segments.json"
    if not seg_path.exists():
        return []
    try:
        segs = json.loads(seg_path.read_text(encoding="utf-8"))
        return segs if isinstance(segs, list) else []
    except Exception:
        return []


def extract_commentary_players(commentary_ctx: dict) -> list[str]:
    """
    Extract canonical player names from commentary text (pre-spike + concurrent).

    This is the PRIMARY source for determining who the on-screen scene is about.
    Commentary is produced before or simultaneous with the event, so names
    mentioned here are almost always the on-screen subject — not conversational
    references like chat messages can be.

    Returns list in order of first appearance, deduplicated.
    """
    combined = (
        (commentary_ctx.get("pre_text") or "") + " " +
        (commentary_ctx.get("concurrent_text") or "")
    )
    seen: set[str] = set()
    result: list[str] = []
    # Use the spaced variant: subtitle text uses natural Korean spacing
    # (e.g. "이성훈 선수", "김용석 선수가") unlike chat where they are adjacent.
    for match in _TITLE_RE_SPACED.finditer(combined):
        name = match.group(1)
        if name in _KR_STOPWORDS:
            continue
        # Reconstruct without space for alias lookup
        canonical = resolve_canonical(name + match.group(2))
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


# ── Commentary event context filter ─────────────────────────────────────────
#
# These patterns in the ±30-char window around an event token indicate the word
# is NOT describing the current on-screen moment:
#
#   해야 / 하면       — subjunctive/conditional  "should win" / "if [event] happens"
#   했을 때           — comparative past        "when [someone] won before"
#   안 하 / 를 못     — negative conditional    "if he doesn't win"
#   두 개 / 세 개     — enumeration (past)      "scored two eagles [in round 1]"
#   두 번             — counted repetition      "drove it twice"
#   잖아요 / 잖습니다 — confirmatory past       "he made two eagles, you know"
#   때도              — comparative past        "also in [past round]..."
#   아냈고 / 았고     — past-tense continuation "achieved and then..."
#
_COMM_NOT_CURRENT_RE = re.compile(
    r'(해야|하면|했을\s*때|안\s+하|를\s*못|두\s+개|세\s+개|두\s+번|잖아요|잖습니다|때도|아냈고|았고\s)'
)


def _extract_comm_events(commentary_ctx: dict) -> list[str]:
    """
    Extract canonical golf event names from commentary text.

    Uses pre_text + concurrent_text (NOT all_text) to stay close to the
    triggering moment and avoid background discussion context.

    For each candidate event token, checks a ±30-char window against
    _COMM_NOT_CURRENT_RE.  If the context is hypothetical, conditional, or
    a past-reference count/comparison, the occurrence is skipped.
    Only declarative present-tense descriptions of the current event are kept.

    Example: "이글이 나왔습니다" → kept.
    Example: "이글 두 개 잡았잖아요 (round 1)" → skipped (두 개 + 잖아요).
    Example: "우승해야 된다" → skipped (해야).
    """
    # Tight window: pre-spike + concurrent only
    text = (
        (commentary_ctx.get("pre_text")       or "") + " " +
        (commentary_ctx.get("concurrent_text") or "")
    )
    seen: set[str] = set()
    result: list[str] = []

    for tok in text.split():
        if tok not in _EVENT_SET:
            continue
        ev = GOLF_EVENTS[tok]
        if ev in seen:
            continue

        # Find every occurrence of this token in text and check context
        search_start = 0
        current_event_found = False
        while True:
            idx = text.find(tok, search_start)
            if idx == -1:
                break
            # Extract surrounding context window
            window = text[max(0, idx - 30): idx + 40]
            if not _COMM_NOT_CURRENT_RE.search(window):
                current_event_found = True
                break
            search_start = idx + 1

        if current_event_found:
            seen.add(ev)
            result.append(ev)

    return result


_COMM_EXCITE_WORDS = {
    "굉장히", "정말", "대단", "소름", "인상적", "대박", "놀랍",
    "완벽", "최고", "환상적", "역대급", "믿을", "어마어마",
}
_COMM_TENSE_WORDS = {
    "아슬", "위험", "아깝", "간신히", "겨우", "아 진짜", "불안",
}


def _detect_comm_mood(commentary_ctx: dict) -> str | None:
    """
    Detect the dominant emotional tone in commentary text.
    Returns a short Korean phrase for use in narrative sentences, or None if flat.
    """
    text = (
        (commentary_ctx.get("pre_text") or "") + " " +
        (commentary_ctx.get("concurrent_text") or "")
    )
    excite = sum(1 for w in _COMM_EXCITE_WORDS if w in text)
    tense  = sum(1 for w in _COMM_TENSE_WORDS  if w in text)
    if excite >= 3:
        return "강한 탄성과 흥분"
    if excite >= 2:
        return "놀라움과 감탄"
    if excite >= 1:
        return "감탄과 집중"
    if tense >= 1:
        return "긴장감"
    return None


def get_segment_context(
    segments: list[dict], anchor: float, window_start: float, window_end: float,
) -> dict:
    """
    Extract commentator speech around a spike into two separate windows.

    Windows
    -------
    pre_spike   : segments whose text ends ≤ anchor, starting no earlier than
                  anchor − 15s.  This is the causal window — "what was about to
                  happen / what the commentator was describing just before the
                  crowd reacted".  15s is chosen because commentators typically
                  describe a shot 5–15s before viewer chat volume peaks (viewer
                  reaction lag).

    concurrent  : segments overlapping [window_start, window_end].  These
                  describe what was happening during the full spike.

    The split matters because:
    - pre_spike  → strongest causal evidence (what triggered the reaction)
    - concurrent → confirms or adds detail (what commentator said during chaos)

    Conflict / weak evidence handling
    ----------------------------------
    - If pre_spike is empty but concurrent is not, concurrent is promoted to
      causal evidence with lower confidence.
    - If both are empty, has_content = False signals the caller to fall back
      to chat-only inference.
    - Text is trimmed to 300 chars per window to avoid overflowing the PDF card.

    Returns dict
    ------------
    pre_text        : str   commentary 15s before anchor
    concurrent_text : str   commentary during spike window
    all_text        : str   combined (wider context, for fallback)
    has_content     : bool
    evidence_source : str   "pre_spike" | "concurrent" | "both" | "none"
    """
    # Pre-spike causal window: anchor−15s → anchor
    pre_start = max(0.0, anchor - 15.0)
    pre_segs  = [
        s for s in segments
        if s.get("end",   0) >= pre_start
        and s.get("start", 0) <= anchor
        and s.get("text", "").strip()
    ]

    # Concurrent window: window_start → window_end
    conc_segs = [
        s for s in segments
        if s.get("end",   0) >= window_start
        and s.get("start", 0) <= window_end
        and s.get("text", "").strip()
    ]

    # Wide fallback: anchor−60s → window_end+10s  (for all_text only)
    wide_start = max(0.0, anchor - 60.0)
    wide_segs  = [
        s for s in segments
        if s.get("end",   0) >= wide_start
        and s.get("start", 0) <= window_end + 10
        and s.get("text", "").strip()
    ]

    pre_text        = " ".join(s["text"].strip() for s in pre_segs)[:300]
    concurrent_text = " ".join(s["text"].strip() for s in conc_segs)[:300]
    all_text        = " ".join(s["text"].strip() for s in wide_segs)[:400]

    has_pre  = bool(pre_text.strip())
    has_conc = bool(concurrent_text.strip())

    if has_pre and has_conc:
        evidence_source = "both"
    elif has_pre:
        evidence_source = "pre_spike"
    elif has_conc:
        evidence_source = "concurrent"
    else:
        evidence_source = "none"

    return {
        "pre_text":        pre_text,
        "concurrent_text": concurrent_text,
        "all_text":        all_text,
        "has_content":     has_pre or has_conc,
        "evidence_source": evidence_source,
    }


def build_buzz_summary(
    player_cands: list,
    event_mentions: list,
    peak_event: list,
    peak_internal: list,
    commentary_ctx: dict,
    active_participants: dict,
    reaction_profile: list | None = None,
    primary_player: str | None = None,
) -> dict:
    """
    Synthesise the dominant buzz type for a spike and generate a compact headline.

    Buzz types
    ----------
    broadcast_event     — spike driven by on-screen event (golf shot / score change)
    participant_driven  — spike driven by chat discussion of a known active participant
                         (channel host or guest creator detected as chatting)
    mixed               — both broadcast event and participant signals present
    general             — no clear pattern; audience chatter without specific focus

    Detection logic
    ---------------
    - broadcast_event: event_mentions exist OR commentary context is present,
      AND event-layer chat ratio ≥ 40 %
    - participant_driven: a known active participant (channel_host or
      channel_participant role) appears in player_cands OR internal chat text,
      AND internal-layer chat ratio ≥ 30 %
    - mixed: both thresholds met simultaneously
    - general: neither threshold met
    """
    ev_count  = len(peak_event)
    int_count = len(peak_internal)
    total     = max(ev_count + int_count, 1)
    ev_ratio  = ev_count / total
    int_ratio = 1.0 - ev_ratio

    has_event_mention = bool(event_mentions)
    has_commentary    = commentary_ctx.get("has_content", False)

    # Detect whether a known active participant is the focal topic
    participant_in_chat: str | None = None
    if active_participants:
        # Priority 1: active participant appears by name in player_cands
        for name, _ in player_cands:
            if name in active_participants:
                participant_in_chat = name
                break
        # Priority 2: scan internal chat text for participant aliases
        if participant_in_chat is None:
            for name, info in active_participants.items():
                aliases = info.get("aliases", [name])
                for m in peak_internal:
                    text = m.get("text", "") or ""
                    if any(a in text for a in aliases):
                        participant_in_chat = name
                        break
                if participant_in_chat:
                    break

    has_broadcast   = (has_event_mention or has_commentary) and ev_ratio >= 0.4
    has_participant = participant_in_chat is not None and int_ratio >= 0.3

    if has_broadcast and has_participant:
        buzz_type       = "mixed"
        buzz_type_label = "이벤트 + 참여자 반응 혼합"
        buzz_color      = ORANGE
    elif has_broadcast:
        buzz_type       = "broadcast_event"
        buzz_type_label = "방송 이벤트 반응"
        buzz_color      = BLUE
    elif has_participant:
        buzz_type       = "participant_driven"
        buzz_type_label = "참여자 중심 화제"
        buzz_color      = GREEN
    else:
        buzz_type       = "general"
        buzz_type_label = "일반 반응"
        buzz_color      = GREY

    # primary_player: commentary-derived wins over chat-derived
    top_player = primary_player or (player_cands[0][0] if player_cands else None)

    # Commentary-derived event (more reliable than chat event mentions)
    comm_events  = _extract_comm_events(commentary_ctx)
    comm_mood    = _detect_comm_mood(commentary_ctx)
    top_comm_event = comm_events[0] if comm_events else None

    # Chat-derived event as fallback
    top_chat_event = event_mentions[0][0] if event_mentions else None
    top_event      = top_comm_event or top_chat_event

    # Role label for the participant (shown in the buzz box tag line)
    participant_role: str | None = None
    if participant_in_chat and participant_in_chat in active_participants:
        participant_role = active_participants[participant_in_chat].get("role_label", "")

    # ── Compact headline (factual: who + what) ────────────────────────────────
    if top_player and top_event:
        headline = f"{top_player}의 {top_event}"
    elif top_player:
        headline = f"{top_player} 관련 장면"
    elif top_event:
        headline = f"{top_event} 장면"
    elif has_commentary:
        headline = "해설 기반 이벤트"
    else:
        headline = "채팅 밀집 구간"

    # ── Analytical narrative (synthesised, not a subtitle quote) ─────────────
    top_react = reaction_profile[0][0] if reaction_profile else None

    # Helpers for grammatically correct Korean particles
    def _ga(w: str) -> str:   return _ko_p(w, "가",  "이")    # subject: 이/가
    def _ro(w: str) -> str:   return _ko_p(w, "로",  "으로")  # directional: 으로/로
    def _eul(w: str) -> str:  return _ko_p(w, "를",  "을")    # object: 을/를

    # Reaction description combining viewer chat + commentator mood
    if comm_mood and top_react:
        rx_desc = (f"해설진은 {comm_mood}을 표했고, "
                   f"시청자들도 {top_react}{_ro(top_react)} 즉각 반응했습니다")
    elif comm_mood:
        rx_desc = f"해설진과 시청자 모두 {comm_mood}을 표했습니다"
    elif top_react:
        rx_desc = f"시청자들{_ga('들')} {top_react}{_ro(top_react)} 즉각 반응했습니다"
    else:
        rx_desc = "채팅에 반응이 집중됐습니다"

    if buzz_type == "broadcast_event":
        if top_player and top_event:
            narrative = (
                f"{top_player}{_ga(top_player)} 인상적인 {top_event}"
                f"{_eul(top_event)} 기록하며, {rx_desc}."
            )
        elif top_player:
            narrative = f"{top_player} 관련 장면에서, {rx_desc}."
        elif top_event:
            narrative = f"{top_event} 장면에서, {rx_desc}."
        else:
            narrative = f"방송 이벤트 구간에서, {rx_desc}."

    elif buzz_type == "participant_driven":
        if participant_in_chat and top_react:
            narrative = (
                f"{participant_in_chat}{_ga(participant_in_chat)} 채팅에 직접 참여하며 "
                f"시청자들과 소통한 구간으로, "
                f"채팅 내 {top_react} 분위기가 형성됐습니다."
            )
        elif participant_in_chat:
            narrative = (
                f"{participant_in_chat}의 채팅 참여가 시청자들의 반응을 이끌어낸 구간입니다."
            )
        else:
            narrative = "참여자 중심의 채팅 대화가 반응 스파이크를 형성한 구간입니다."

    elif buzz_type == "mixed":
        if top_player and top_event and participant_in_chat:
            narrative = (
                f"{top_player}의 {top_event} 장면과 {participant_in_chat}의 채팅 참여가 "
                f"겹치며, {rx_desc}."
            )
        elif top_player and participant_in_chat:
            narrative = (
                f"{top_player} 관련 방송 장면과 {participant_in_chat}의 채팅 참여가 "
                f"동시에 맞물려 반응이 집중됐습니다."
            )
        elif participant_in_chat:
            narrative = (
                f"방송 이벤트와 {participant_in_chat}의 채팅 참여가 동시에 활성화되며, "
                f"{rx_desc}."
            )
        else:
            narrative = f"방송 이벤트와 참여자 대화가 동시에 채팅을 활성화하며, {rx_desc}."

    else:  # general
        if top_react:
            narrative = (
                f"특정 선수나 이벤트 없이 채팅 밀집도만으로 선정된 구간으로, "
                f"주된 반응은 {top_react}입니다."
            )
        else:
            narrative = "특정 이벤트나 참여자 없이 채팅 밀집도만으로 선정된 구간입니다."

    return {
        "headline":           headline,
        "narrative":          narrative,
        "buzz_type":          buzz_type,
        "buzz_type_label":    buzz_type_label,
        "buzz_color":         buzz_color,
        "ev_ratio":           round(ev_ratio, 2),
        "int_ratio":          round(int_ratio, 2),
        "participant_in_chat": participant_in_chat,
        "participant_role":   participant_role,
        "top_player":         top_player,
        "top_event":          top_event,
    }


def enrich_spike(spike: dict, text_msgs: list[dict], segments: list[dict],
                 active_participants: dict | None = None) -> dict:
    """
    Attach 'enriched' analysis dict to a spike, combining commentary + chat evidence.

    Evidence windows
    ----------------
    Commentary (subtitles):
      pre_spike   anchor−15s → anchor      Primary causal signal.  Commentator
                                           speech ends just before crowd reacts.
      concurrent  window_start → window_end Confirmatory / adds detail.

    Chat:
      tight       anchor−10s → anchor+5s   Primary source for player/event names.
                                           This narrow window avoids picking up
                                           unrelated chatter before/after the moment.
      peak        window_start → window_end Full reaction window for scoring.
      buildup     ws−30s → window_start    Background context shown in the PDF card.

    Conflict / weak evidence
    -------------------------
    - Commentary empty + chat has players/events  → chat-only inference, labelled.
    - Commentary present + chat has no names      → commentary drives cause;
                                                   chat supplies reaction only.
    - Both empty                                  → "근거 불충분" label, spike kept
                                                   because density alone qualifies.

    Stores spike['enriched'] with:
      player_cands      — names from tight chat window (title-pattern)
      event_mentions    — golf events from tight window
      reaction_profile  — reaction categories during peak window
      dominant_reaction — top category
      narrative         — short one-liner for overview table
      narrative_parts   — dict {cause, reaction, interpretation, short, ...}
      commentary_ctx    — structured commentary dict from get_segment_context()
      buildup_messages  — substantive, deduped messages from 90s before spike
      peak_messages     — deduped sample from spike window
    """
    anchor = float(spike.get("anchor_time", 0))
    ws     = float(spike.get("window_start", 0))
    we     = float(spike.get("window_end", 0))

    # ── Chat windows ──────────────────────────────────────────────────────────
    tight_start  = max(0.0, anchor - 10.0)
    tight_end    = anchor + 5.0
    tight_msgs   = [m for m in text_msgs if tight_start <= m["timestamp_seconds"] <= tight_end]

    buildup_start = max(0.0, ws - 30.0)
    buildup_msgs  = [m for m in text_msgs if buildup_start <= m["timestamp_seconds"] < ws]
    peak_msgs     = [m for m in text_msgs if ws <= m["timestamp_seconds"] <= we]
    context_msgs  = buildup_msgs + peak_msgs   # broad fallback for player extraction

    # ── Commentary windows ────────────────────────────────────────────────────
    commentary_ctx = (
        get_segment_context(segments, anchor, ws, we)
        if segments
        else {"pre_text": "", "concurrent_text": "", "all_text": "",
              "has_content": False, "evidence_source": "none"}
    )

    # ── Classify peak messages into event-reaction vs. chat-internal ────────────
    peak_event    = [m for m in peak_msgs if classify_message(m) in ("event", "mixed")]
    peak_internal = [m for m in peak_msgs if classify_message(m) in ("internal", "mixed")]

    # Reaction profile uses only event-layer messages so chat-to-chat noise
    # doesn't inflate or distort the reaction category counts.
    reaction_profile = classify_reactions(peak_event)

    # ── Player / event detection ────────────────────────────────────────────────
    #
    # Source priority for "who the scene is about":
    #
    #   1. Commentary (subtitles): extract names from pre-spike + concurrent text.
    #      These are the on-screen subjects — the commentator is describing them.
    #
    #   2. Event-layer chat only (tight window, internal messages excluded):
    #      Viewers reacting to what they see on screen.  Internal messages
    #      (chat-to-chat questions like "문프로님 내일…") are stripped out here
    #      because they describe a chat conversation, not the broadcast event.
    #
    #   3. Broad context fallback: if both narrow windows are empty, widen to
    #      the full peak window (event-layer only).
    #
    # Commentary players are put first in player_cands with an artificial high
    # count so downstream sorting (headline, narrative) uses them first.
    #
    comm_players = extract_commentary_players(commentary_ctx)

    tight_event_msgs   = [m for m in tight_msgs   if classify_message(m) in ("event", "mixed")]
    context_event_msgs = [m for m in context_msgs if classify_message(m) in ("event", "mixed")]
    chat_player_cands, event_mentions = extract_mentions_and_events(
        tight_event_msgs, context_event_msgs, min_count=1
    )

    # Merged list: commentary players first (score=99), then chat-only additions
    comm_player_set = set(comm_players)
    player_cands = (
        [(name, 99) for name in comm_players] +
        [(name, cnt) for name, cnt in chat_player_cands if name not in comm_player_set]
    )

    # primary_player = the single most authoritative subject of the scene
    primary_player: str | None = comm_players[0] if comm_players else (
        chat_player_cands[0][0] if chat_player_cands else None
    )

    # ── Combined narrative ────────────────────────────────────────────────────
    narrative_parts = generate_narrative(
        player_cands, event_mentions, reaction_profile,
        len(peak_event),
        commentary_ctx,
        primary_player=primary_player,
    )

    # ── Informative buildup messages (pre-spike context) ─────────────────────
    def _dedup_msgs(source, max_n):
        seen, out = set(), []
        for m in reversed(source[-60:]):
            t = m.get("text", "").strip()
            if t and t not in seen and len(t) > 3:
                seen.add(t)
                out.append(m)
            if len(out) >= max_n:
                break
        out.reverse()
        return out

    def _is_noise(m):
        t = m.get("text", "").strip()
        return (not t or len(t) <= 3
                or _KK_RE.match(t) or _HH_RE.match(t) or _TT_RE.match(t))

    informative_buildup = [m for m in buildup_msgs if not _is_noise(m)]
    deduped_buildup = _dedup_msgs(informative_buildup, 5)

    # ── Sample of peak event-layer messages ───────────────────────────────────
    seen_p, peak_event_sample = set(), []
    for m in peak_event:
        t = m.get("text", "").strip()
        if t and t not in seen_p and len(t) > 1:
            seen_p.add(t)
            peak_event_sample.append(m)
        if len(peak_event_sample) >= 5:
            break

    # ── Sample of peak internal-layer messages ────────────────────────────────
    seen_i, peak_internal_sample = set(), []
    for m in peak_internal:
        t = m.get("text", "").strip()
        if t and t not in seen_i and len(t) > 1:
            seen_i.add(t)
            peak_internal_sample.append(m)
        if len(peak_internal_sample) >= 4:
            break

    # ── Buzz / topic summary ─────────────────────────────────────────────────
    buzz_summary = build_buzz_summary(
        player_cands, event_mentions,
        peak_event, peak_internal,
        commentary_ctx, active_participants or {},
        reaction_profile,
        primary_player=primary_player,
    )

    spike["enriched"] = {
        "player_cands":       player_cands,
        "event_mentions":     event_mentions,
        "reaction_profile":   reaction_profile[:6],
        "dominant_reaction":  reaction_profile[0][0] if reaction_profile else "—",
        "narrative":          narrative_parts["short"],
        "narrative_parts":    narrative_parts,
        "commentary_ctx":     commentary_ctx,
        "comm_players":       comm_players,       # names extracted from commentary text
        "primary_player":     primary_player,     # authoritative scene subject
        "buildup_messages":   deduped_buildup,
        "peak_messages":      peak_event_sample,  # event-layer only
        "peak_internal":      peak_internal_sample,
        "event_msg_count":    len(peak_event),
        "internal_msg_count": len(peak_internal),
        "buzz_summary":       buzz_summary,
    }
    return spike


def build_player_analysis(
    text_msgs: list[dict], spike_moments: list[dict]
) -> list[dict]:
    """
    Player-centred analysis: independent of spike detection.

    For each player (detected via title-pattern across ALL chat messages):
      - Mention count and mention event clusters
      - Reaction volume attributed to that player via a ±reaction window
      - Reaction type breakdown (8 categories)
      - Sentiment profile (긍정/유머/응원/안타까움/긴장/복합)
      - Opportunity score: quality of reactions per appearance,
        penalised for high mention count, to surface under-recognised players

    Reaction attribution window
    ---------------------------
    Rather than only counting reactions co-occurring in the same message as a
    name, we look at all chat messages within
        mention_time − LOOKBACK_SEC  →  mention_time + LOOKAHEAD_SEC
    This captures the crowd reacting to what they just saw, which typically
    arrives 2–15 seconds after the relevant on-screen moment.

    To avoid double-counting when the same player is mentioned in bursts, we
    first cluster mentions that are within CLUSTER_GAP_SEC of each other into
    a single "appearance event", then draw one reaction window per cluster.
    Messages that fall in multiple clusters are deduplicated by (ts, author, text).
    """
    LOOKBACK_SEC   = 10.0   # reactions this far before the mention count
    LOOKAHEAD_SEC  = 30.0   # reactions this far after the mention count
    CLUSTER_GAP_SEC = 60.0  # mentions within this gap form one "appearance event"

    # Positive / negative / tense category sets
    _POS  = {"감탄·대박", "기대 충족", "응원·격려", "웃음·재미", "웃음·가벼운",
             "탄성·놀람", "역전 장면"}
    _NEG  = {"안타까움·슬픔", "탄식·긴장"}
    _TENSE = {"충격·당황", "동타 장면"}

    # ── 1. Collect all mention timestamps per player ──────────────────────────
    mention_times: dict[str, list[float]] = {}

    for m in text_msgs:
        text = m.get("text", "") or ""
        ts   = m["timestamp_seconds"]
        for match in _TITLE_RE.finditer(text):
            name = match.group(1)
            if name in _KR_STOPWORDS:
                continue
            raw       = name + match.group(2)
            canonical = resolve_canonical(raw)   # merge aliases → one identity
            mention_times.setdefault(canonical, []).append(ts)

    if not mention_times:
        return []

    # ── 2. For each player, cluster and attribute reactions ───────────────────
    raw: list[dict] = []

    for canonical, times in mention_times.items():
        times = sorted(times)

        # Cluster nearby mentions into "appearance events"
        clusters: list[list[float]] = [[times[0]]]
        for ts in times[1:]:
            if ts - clusters[-1][-1] <= CLUSTER_GAP_SEC:
                clusters[-1].append(ts)
            else:
                clusters.append([ts])

        # Gather reactions for each appearance event (deduplicated across clusters)
        reaction_ctr: Counter = Counter()
        seen_msgs: set = set()

        for cluster in clusters:
            anchor_ts   = cluster[len(cluster) // 2]   # median of cluster
            win_start   = max(0.0, anchor_ts - LOOKBACK_SEC)
            win_end     = anchor_ts + LOOKAHEAD_SEC

            for m in text_msgs:
                mts = m["timestamp_seconds"]
                if not (win_start <= mts <= win_end):
                    continue
                key = (mts, m.get("author", ""), m.get("text", ""))
                if key in seen_msgs:
                    continue
                seen_msgs.add(key)
                for tok in tokenize_message(m.get("text", "") or ""):
                    if tok in _REACTION_SET:
                        _, cat = REACTION_TOKENS[tok]
                        reaction_ctr[cat] += 1

        mention_count  = len(times)
        mention_events = len(clusters)
        total_rx       = sum(reaction_ctr.values())
        pos_rx  = sum(reaction_ctr.get(c, 0) for c in _POS)
        neg_rx  = sum(reaction_ctr.get(c, 0) for c in _NEG)
        tense_rx = sum(reaction_ctr.get(c, 0) for c in _TENSE)
        pos_ratio = pos_rx / total_rx if total_rx else 0.0
        rx_per_event = total_rx / mention_events if mention_events else 0.0

        # Dominant sentiment label
        dom = reaction_ctr.most_common(1)[0][0] if reaction_ctr else None
        if dom in {"웃음·재미", "웃음·가벼운"}:
            sentiment = "유머·재미"
        elif dom == "탄성·놀람":
            sentiment = "놀람·흥분"
        elif dom == "감탄·대박":
            sentiment = "감탄·대박"
        elif dom == "응원·격려":
            sentiment = "응원·격려"
        elif dom in {"안타까움·슬픔", "탄식·긴장"}:
            sentiment = "안타까움"
        elif dom in {"충격·당황"}:
            sentiment = "긴장·충격"
        elif pos_ratio >= 0.6:
            sentiment = "긍정적"
        elif tense_rx > pos_rx and tense_rx > neg_rx:
            sentiment = "긴장감"
        else:
            sentiment = "복합적"

        # Opportunity score: quality × intensity, not yet normalised
        # raw = (reactions per event) × (0.4 + 0.6 × pos_ratio)
        # The 0.4 floor keeps players with any reaction in the picture even if
        # categorisation is imperfect; 0.6 weight rewards positive signal quality.
        opp_raw = rx_per_event * (0.4 + 0.6 * pos_ratio)

        raw.append({
            "name":            canonical,
            "mention_count":   mention_count,
            "mention_events":  mention_events,
            "total_rx":        total_rx,
            "rx_per_event":    round(rx_per_event, 1),
            "rx_per_mention":  round(total_rx / max(mention_count, 1), 2),
            "top_reactions":   reaction_ctr.most_common(5),
            "reaction_ctr":    dict(reaction_ctr),
            "pos_rx":          pos_rx,
            "neg_rx":          neg_rx,
            "tense_rx":        tense_rx,
            "pos_ratio":       round(pos_ratio, 2),
            "sentiment":       sentiment,
            "spike_ranks":     [],
            "opp_raw":         opp_raw,
            "opportunity_score": None,   # filled after normalisation
        })

    # Sort by mention count (main ranking)
    raw.sort(key=lambda x: x["mention_count"], reverse=True)

    # ── 3. Spike association ──────────────────────────────────────────────────
    for rank, spike in enumerate(spike_moments, 1):
        ws = float(spike.get("window_start", 0))
        we = float(spike.get("window_end",   0))
        spike_players: set[str] = set()
        for m in text_msgs:
            if not (ws <= m["timestamp_seconds"] <= we):
                continue
            text = m.get("text", "") or ""
            for match in _TITLE_RE.finditer(text):
                name = match.group(1)
                if name in _KR_STOPWORDS:
                    continue
                spike_players.add(name + match.group(2))
        spike_players_canonical = {resolve_canonical(n) for n in spike_players}
        for p in raw:
            if p["name"] in spike_players_canonical and rank not in p["spike_ranks"]:
                p["spike_ranks"].append(rank)

    for p in raw:
        p["spike_ranks"] = sorted(p["spike_ranks"])[:4]

    # ── 4. Normalise opportunity scores ──────────────────────────────────────
    # Eligible = players with ≥ 2 mention events (enough data to be meaningful)
    eligible = [p for p in raw if p["mention_events"] >= 2]
    max_opp  = max((p["opp_raw"] for p in eligible), default=0.0)

    for p in raw:
        if p["mention_events"] >= 2 and max_opp > 0:
            p["opportunity_score"] = round(p["opp_raw"] / max_opp * 100)
        # else remains None

    return raw[:15]


# ── Data loader ───────────────────────────────────────────────────────────────

def load_data() -> dict:
    """Load all report inputs from output/ files and enrich spike moments."""
    d: dict = {}

    # ── 1. live_chat_normalized.csv ───────────────────────────────────────────
    chat_path = OUTPUT_DIR / "live_chat_normalized.csv"
    if not chat_path.exists():
        print("ERROR: output/live_chat_normalized.csv not found.")
        print("       Run: python extract_live_chat.py <URL>")
        sys.exit(1)

    messages = []
    with open(chat_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                row["timestamp_seconds"] = float(row.get("timestamp_seconds") or 0)
            except ValueError:
                row["timestamp_seconds"] = 0.0
            row["message_type"] = row.get("message_type", "text") or "text"
            messages.append(row)

    d["messages"]      = messages
    d["total_messages"] = len(messages)
    d["unique_chatters"] = len({m.get("author", "") for m in messages if m.get("author")})

    first = messages[0] if messages else {}
    d["video_id"]  = safe_str(first.get("video_id"))
    d["video_url"] = safe_str(first.get("video_url"))

    max_ts = max((m["timestamp_seconds"] for m in messages), default=0.0)
    d["video_duration_sec"]  = max_ts
    d["video_duration_text"] = fmt_seconds(max_ts)

    text_msgs = [m for m in messages if m["message_type"] == "text"]
    d["text_message_count"] = len(text_msgs)

    # Detect which registered entities are actively chatting (matched by author name)
    active_participants = detect_active_participants(text_msgs)
    d["active_participants"] = active_participants

    # ── 2. highlight_package.json (spike_moments.csv fallback) ───────────────
    hp_path       = OUTPUT_DIR / "highlight_package.json"
    spike_csv_path = OUTPUT_DIR / "spike_moments.csv"

    spike_moments, title_suggestions, shorts_sequences, hp_meta = [], [], [], {}

    if hp_path.exists():
        hp = json.loads(hp_path.read_text(encoding="utf-8"))
        hp_meta = hp.get("meta", {})
        raw_spikes = hp.get("spike_moments", [])
        spike_moments = sorted(raw_spikes, key=lambda x: x.get("weighted_score", 0), reverse=True)
        mp = hp.get("master_plan") or {}
        title_suggestions = mp.get("title_suggestions", []) if isinstance(mp, dict) else []
        shorts_sequences  = hp.get("shorts_sequences", [])
    elif spike_csv_path.exists():
        print("WARNING: Using spike_moments.csv fallback (top_messages unavailable)")
        with open(spike_csv_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                spike_moments.append({
                    "anchor_time":    float(row.get("anchor_time",    0) or 0),
                    "window_start":   float(row.get("window_start",   0) or 0),
                    "window_end":     float(row.get("window_end",     0) or 0),
                    "message_count":  int(float(row.get("message_count", 0) or 0)),
                    "weighted_score": float(row.get("weighted_score", 0) or 0),
                    "top_messages":   [],
                })
        spike_moments.sort(key=lambda x: x["weighted_score"], reverse=True)
    else:
        print("WARNING: No spike data found. Run highlight_pipeline.py first.")

    d["spike_moments"]     = spike_moments
    d["title_suggestions"] = title_suggestions
    d["shorts_sequences"]  = shorts_sequences
    d["hp_meta"]           = hp_meta
    d["spike_count"]       = len(spike_moments)
    d["top_spike"]         = spike_moments[0] if spike_moments else None

    # ── 3. Segments (optional, for transcript context) ────────────────────────
    segments = load_segments(d["video_id"])
    d["has_segments"] = len(segments) > 0
    d["segment_count"] = len(segments)

    # ── 4. Enrich each spike with "why" analysis ──────────────────────────────
    for spike in spike_moments:
        enrich_spike(spike, text_msgs, segments, active_participants)

    # ── 5. Chat density by 2-minute buckets ───────────────────────────────────
    bucket_sec = 120
    buckets: dict = {}
    for m in text_msgs:
        idx = int(m["timestamp_seconds"] // bucket_sec)
        buckets[idx] = buckets.get(idx, 0) + 1
    density = sorted(
        [(fmt_seconds(idx * bucket_sec), cnt) for idx, cnt in buckets.items()],
        key=lambda x: x[1], reverse=True
    )
    d["chat_density_by_minute"] = density[:20]
    # Time-ordered version for the sparkline chart (x=time, y=density)
    d["chat_density_timeline"] = [
        (idx * bucket_sec, cnt)
        for idx, cnt in sorted(buckets.items())
    ]

    # ── 6. Normalized keyword frequency across all spike windows ─────────────
    kw_counter: Counter = Counter()
    event_counter: Counter = Counter()
    for spike in spike_moments:
        ws, we = spike.get("window_start", 0), spike.get("window_end", 0)
        for m in text_msgs:
            if ws <= m["timestamp_seconds"] <= we:
                for tok in tokenize_message(m.get("text", "") or ""):
                    if tok in _EVENT_SET:
                        event_counter[GOLF_EVENTS[tok]] += 1
                    elif tok not in _REACTION_SET:
                        kw_counter[tok] += 1
                    else:
                        # keep reaction tokens in their canonical form
                        kw_counter[tok] += 1

    d["top_spike_keywords"] = kw_counter.most_common(15)
    d["top_spike_events"]   = event_counter.most_common(10)

    # Reaction summary across all spikes
    reaction_total: Counter = Counter()
    for spike in spike_moments:
        for cat, cnt in spike.get("enriched", {}).get("reaction_profile", []):
            reaction_total[cat] += cnt
    d["overall_reaction_profile"] = reaction_total.most_common(8)

    # ── 7. Player mention analysis ────────────────────────────────────────────
    d["player_analysis"] = build_player_analysis(text_msgs, spike_moments)

    return d


# ── Chat two-column helper ────────────────────────────────────────────────────

def side_by_side_chat(
    left_msgs: list[dict],
    right_msgs: list[dict],
    left_label: str,
    right_label: str,
    left_accent=BLUE,
    right_accent=ORANGE,
    max_each: int = 5,
) -> Table:
    """
    Render two lists of chat messages side-by-side in a 50/50 two-column table.
    Uses compact single-line rows instead of the full chat_card layout to save
    vertical space.
    """
    fw   = PW - 2 * M
    col_w = (fw - 3 * mm) / 2

    lbl_s = lambda accent: ParagraphStyle(
        "_sbl", fontName="KR-Bold", fontSize=7.5, textColor=accent,
        leading=11, wordWrap="CJK")
    msg_s = ParagraphStyle(
        "_sms", fontName="KR", fontSize=7.5, leading=12,
        textColor=BLACK, wordWrap="CJK", spaceAfter=1)
    empty_s = ParagraphStyle(
        "_sem", fontName="KR", fontSize=7.5, leading=12, textColor=GREY)

    def _col(label, msgs, accent):
        rows = [[Paragraph(label, lbl_s(accent))]]
        shown = [m for m in msgs if m.get("text", "").strip()][:max_each]
        if shown:
            for m in shown:
                ts   = fmt_seconds(m["timestamp_seconds"])
                auth = safe_str(m.get("author", ""))[:14]
                txt  = safe_str(m.get("text", ""))[:55]
                rows.append([Paragraph(f"[{ts}]  {auth}: {txt}", msg_s)])
        else:
            rows.append([Paragraph("(없음)", empty_s)])
        t = Table(rows, colWidths=[col_w])
        bg = BLUE_LIGHT if accent == BLUE else colors.HexColor("#FFF7ED")
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), bg),
            ("BACKGROUND",    (0, 1), (-1, -1), SLATE_LIGHT),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("GRID",          (0, 0), (-1, -1), 0.3, SLATE_MID),
        ]))
        return t

    left_t  = _col(left_label, left_msgs, left_accent)
    right_t = _col(right_label, right_msgs, right_accent)

    outer = Table([[left_t, right_t]], colWidths=[col_w, col_w + 3 * mm])
    outer.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return outer


# ── Story builder ─────────────────────────────────────────────────────────────

def build_story(d: dict) -> list:
    story = []
    P = Paragraph

    # ═══════════════════════════════════════════════════════════════
    # PAGE 1 — Cover + Stats
    # ═══════════════════════════════════════════════════════════════
    story.append(P("라이브 채팅 기반<br/>하이라이트 인사이트 리포트", STYLES["h1"]))
    story.append(P(
        "Video: " + d["video_id"] +
        " \u00b7 실시간 반응의 밀집 구간에서 무슨 일이 있었는지를 해석합니다",
        STYLES["subtitle"]))
    story.append(rule(BLUE, 1.5))
    story.append(vspace(3))

    # Meta table
    fw = PW - 2 * M
    col_w = fw / 4
    ml = ParagraphStyle("mt_l", fontName="KR-Bold", fontSize=8, textColor=GREY, wordWrap="CJK")
    mv = ParagraphStyle("mt_v", fontName="KR",      fontSize=8.5, textColor=BLACK, wordWrap="CJK")
    seg_note = ("있음 (" + str(d["segment_count"]) + "개 세그먼트)") if d["has_segments"] else "없음 — 채팅 기반 추론"
    meta_tbl = Table([
        [P("Video ID",   ml), P(d["video_id"],           mv), P("채팅 메시지",  ml), P(str(d["total_messages"]), mv)],
        [P("영상 길이",   ml), P(d["video_duration_text"], mv), P("스파이크 수",  ml), P(str(d["spike_count"]),    mv)],
        [P("고유 시청자", ml), P(str(d["unique_chatters"]),mv), P("자막/세그먼트",ml), P(seg_note,                mv)],
    ], colWidths=[col_w * 0.55, col_w * 1.45, col_w * 0.55, col_w * 1.45])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "KR"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("BACKGROUND",    (0, 0), (-1, -1), SLATE_LIGHT),
        ("BACKGROUND",    (0, 0), (0, -1), BLUE_LIGHT),
        ("BACKGROUND",    (2, 0), (2, -1), BLUE_LIGHT),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    story.append(meta_tbl)
    story.append(vspace(4))

    top_cnt = str(d["top_spike"]["message_count"]) if d["top_spike"] else "—"
    story.append(stat_table([
        ("총 메시지",   d["total_messages"]),
        ("고유 시청자", d["unique_chatters"]),
        ("스파이크",    d["spike_count"]),
        ("최대 반응",   top_cnt),
    ]))
    story.append(vspace(5))

    story.extend(section_heading("실시간 반응 핵심 요약"))

    if d["spike_moments"]:
        top3 = d["spike_moments"][:3]
        lines = []
        for i, sp in enumerate(top3, 1):
            enriched = sp.get("enriched", {})
            ts  = fmt_seconds(sp.get("anchor_time", 0))
            cnt = sp.get("message_count", 0)
            np_ = enriched.get("narrative_parts", {})
            # Prefer interpretation sentence for cover summary; fall back to short
            summary = np_.get("interpretation") or enriched.get("narrative", "—")
            # Trim to one sentence for cover
            summary = summary.split("—")[0].split("\n")[0].strip()
            lines.append(f"{i}위  {ts}  ({cnt}개)  {summary}")
        story.append(callout("\n".join(lines), ORANGE))
    else:
        story.append(callout("스파이크 데이터가 없습니다. highlight_pipeline.py를 먼저 실행하십시오."))

    story.append(vspace(3))
    if not d["has_segments"]:
        story.append(note_box(
            "자막/세그먼트 파일이 없습니다. "
            "해석은 채팅 메시지 내용만으로 추론됩니다. "
            "youtube_extractor.sh를 실행하면 자막 기반 해석이 가능합니다."
        ))
    else:
        story.append(note_box(
            "자막 세그먼트 " + str(d["segment_count"]) + "개가 로드됐습니다. "
            "스파이크 구간 해석에 해설자 음성이 함께 활용됩니다."
        ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 2 — Density Timeline + Spike Overview Table
    # ═══════════════════════════════════════════════════════════════
    story.extend(section_heading("1.  채팅 밀집도 타임라인"))
    story.append(P(
        "영상 전체의 2분 단위 채팅 밀집도입니다 (x=시간, y=메시지 수). "
        "주황색 세로선이 감지된 반응 스파이크 위치입니다.",
        STYLES["body"]))
    story.append(vspace(2))

    _timeline = d.get("chat_density_timeline", [])
    _spike_ts = [float(sp["anchor_time"]) for sp in d["spike_moments"]]
    if _timeline:
        story.append(density_sparkline(_timeline, _spike_ts, PW - 2 * M))
    story.append(vspace(2))
    story.append(note_box(
        "막대 = 2분 구간 채팅 수  ·  주황선 = 스파이크 앵커 위치  ·  "
        "스파이크는 60초 슬라이딩 창으로 별도 감지됩니다."
    ))
    story.append(vspace(4))

    story.extend(section_heading("2.  스파이크 구간 전체 목록"))

    if d["spike_moments"]:
        rows = []
        for rank, sp in enumerate(d["spike_moments"][:10], 1):  # top 10 only
            enriched = sp.get("enriched", {})
            np_      = enriched.get("narrative_parts", {})
            bz_      = enriched.get("buzz_summary", {})
            rec = "★" + str(rank) if rank <= 3 else ("권장" if rank <= 6 else "참고")
            ev_src = np_.get("evidence_source", "none")
            has_c  = np_.get("has_commentary", False)
            if has_c and ev_src in ("both", "pre_spike"):
                indicator = "◎"
            elif has_c:
                indicator = "○"
            else:
                indicator = "△"
            # Use buzz headline if available — it's more informative than short
            short = bz_.get("headline") or np_.get("short", enriched.get("narrative", "—"))
            short = short[:40]
            rows.append([
                str(rank),
                fmt_seconds(sp.get("anchor_time", 0)),   # center time only
                str(sp.get("message_count", 0)),
                "{:.0f}".format(sp.get("weighted_score", 0)),
                indicator,
                short,
                rec,
            ])
        story.append(info_table(
            ["순위", "중심", "메시지", "스코어", "근거", "핵심 장면", "추천"],
            rows,
            col_widths=[0.06, 0.11, 0.09, 0.08, 0.05, 0.42, 0.19],
        ))
        story.append(vspace(2))
        story.append(note_box(
            "근거: ◎ = 자막(직전) + 채팅  ·  ○ = 자막(중) + 채팅  ·  △ = 채팅 텍스트만.  "
            "Top 10 표시 / 전체 " + str(d["spike_count"]) + "개 스파이크 감지."
        ))
    else:
        story.append(P("스파이크 데이터가 없습니다.", STYLES["small"]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGES 3-4 — Spike Interpretation Cards (top 5)
    # ═══════════════════════════════════════════════════════════════
    story.extend(section_heading("3.  스파이크 구간 해석 — 무슨 일이 있었나?"))
    story.append(P(
        "각 스파이크 카드는 세 파트로 구성됩니다:  "
        "<b>① 원인·이벤트 맥락</b> (해설/자막 우선, 없을 경우 채팅 텍스트 추론)  ·  "
        "<b>② 시청자 반응</b> (채팅 분석)  ·  "
        "<b>③ 해석</b> (두 신호의 연결고리).",
        STYLES["body"]))
    story.append(vspace(3))

    # ── 5-spike quick-summary block ───────────────────────────────────────────
    # Compact overview of all top-5 spikes so the reader can grasp the full
    # picture before diving into per-spike detail cards.
    _top5 = d["spike_moments"][:5]
    if _top5:
        story.append(P("Top 5 스파이크 한눈에 보기", ParagraphStyle(
            "_t5h", fontName="KR-Bold", fontSize=10, leading=14,
            textColor=BLUE, spaceBefore=4, spaceAfter=3)))

        _fw5 = PW - 2 * M
        _rk_w = 12 * mm
        _ts_w = 18 * mm
        _bt_w = 36 * mm
        _nr_w = _fw5 - _rk_w - _ts_w - _bt_w

        _rk_s  = ParagraphStyle("_5rk", fontName="KR-Bold", fontSize=9,
                                textColor=WHITE, alignment=TA_CENTER, leading=14)
        _ts_s  = ParagraphStyle("_5ts", fontName="KR",      fontSize=8.5,
                                textColor=WHITE, alignment=TA_CENTER, leading=14,
                                wordWrap="CJK")
        _bt_s  = ParagraphStyle("_5bt", fontName="KR-Bold", fontSize=8,
                                textColor=WHITE, alignment=TA_CENTER, leading=14,
                                wordWrap="CJK")
        _nr_s  = ParagraphStyle("_5nr", fontName="KR",      fontSize=8.5,
                                textColor=BLACK, leading=14, wordWrap="CJK")

        _BT_BG = {
            "broadcast_event":    BLUE,
            "participant_driven": GREEN,
            "mixed":              ORANGE,
            "general":            GREY,
        }

        sum_rows = []
        sum_style = [
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [WHITE, SLATE_LIGHT]),
        ]

        for i, sp5 in enumerate(_top5):
            _e5   = sp5.get("enriched", {})
            _bz5  = _e5.get("buzz_summary", {})
            _btype = _bz5.get("buzz_type", "general")
            _bcol  = _BT_BG.get(_btype, GREY)
            _blab  = _bz5.get("buzz_type_label", "—")
            _hl5   = _bz5.get("headline", "—")
            _narr5 = _bz5.get("narrative", "")
            _ts5   = fmt_seconds(sp5.get("anchor_time", 0))
            _cnt5  = sp5.get("message_count", 0)

            cell_text = f"<b>{_hl5}</b>"
            if _narr5:
                cell_text += f"<br/><font size='8' color='#475569'>{_narr5}</font>"

            sum_rows.append([
                Paragraph(f"#{i+1}", _rk_s),
                Paragraph(f"{_ts5}<br/>({_cnt5}개)", _ts_s),
                Paragraph(_blab, _bt_s),
                Paragraph(cell_text, _nr_s),
            ])
            # Color the first three columns per buzz type
            row_i = i
            sum_style.extend([
                ("BACKGROUND", (0, row_i), (2, row_i), _bcol),
                ("TEXTCOLOR",  (0, row_i), (2, row_i), WHITE),
            ])

        sum_tbl = Table(sum_rows, colWidths=[_rk_w, _ts_w, _bt_w, _nr_w])
        sum_tbl.setStyle(TableStyle(sum_style))
        story.append(sum_tbl)
        story.append(vspace(2))
        story.append(note_box(
            "색상: 파랑=방송 이벤트 반응  ·  초록=참여자 중심 화제  ·  "
            "주황=이벤트+참여자 혼합  ·  회색=일반 반응.  "
            "아래 카드에서 각 스파이크의 상세 분석을 확인하십시오."
        ))
        story.append(vspace(4))

    # Helper: section label inside a card
    def _card_label(text: str, color=BLUE) -> Paragraph:
        return Paragraph(text, ParagraphStyle(
            "_cl", fontName="KR-Bold", fontSize=8, textColor=color,
            leading=12, spaceBefore=4, spaceAfter=1))

    # Helper: evidence-source badge
    def _evidence_badge(ev_src: str, has_comm: bool) -> str:
        if not has_comm:
            return "근거: 채팅 텍스트만 (자막 없음)"
        if ev_src == "both":
            return "근거: 스파이크 직전 해설 + 스파이크 중 해설 + 채팅"
        if ev_src == "pre_spike":
            return "근거: 스파이크 직전 해설 (가장 강한 인과 신호) + 채팅"
        if ev_src == "concurrent":
            return "근거: 스파이크 중 해설 (인과 신호 약함) + 채팅"
        return "근거: 없음 (밀집도만으로 선정)"

    for rank, sp in enumerate(d["spike_moments"][:5], 1):
        enriched       = sp.get("enriched", {})
        anchor         = sp.get("anchor_time",  0)
        ws             = sp.get("window_start", 0)
        we             = sp.get("window_end",   0)
        cnt            = sp.get("message_count", 0)
        score          = sp.get("weighted_score", 0)
        duration       = int(float(we) - float(ws))
        reaction_profile = enriched.get("reaction_profile", [])
        player_cands     = enriched.get("player_cands", [])
        event_mentions   = enriched.get("event_mentions", [])
        buildup_msgs     = enriched.get("buildup_messages", [])
        peak_msgs        = enriched.get("peak_messages", [])
        np_              = enriched.get("narrative_parts", {})
        comm_ctx         = enriched.get("commentary_ctx", {})

        cause_text    = np_.get("cause",          "—")
        reaction_text = np_.get("reaction",        "—")
        interp_text   = np_.get("interpretation",  "—")
        has_comm      = np_.get("has_commentary",  False)
        ev_src        = np_.get("evidence_source", "none")

        accent = ORANGE if rank == 1 else BLUE

        block = []

        # ── Card header ───────────────────────────────────────────────────────
        header_txt = (
            "#" + str(rank) + "  " + fmt_seconds(anchor)
            + "  —  " + str(cnt) + "개 반응 / 스코어 " + "{:.0f}".format(score)
            + "  /  구간: " + fmt_seconds(ws) + "–" + fmt_seconds(we)
            + " (" + str(duration) + "초)"
        )
        block.append(P(header_txt, STYLES["h3"]))
        block.append(rule(accent, 1.0))

        # Evidence badge
        badge = _evidence_badge(ev_src, has_comm)
        block.append(P(badge, STYLES["small"]))
        block.append(vspace(1))

        # ── Buzz / Topic summary ──────────────────────────────────────────────
        buzz = enriched.get("buzz_summary", {})
        if buzz:
            block.append(buzz_box(buzz))
            block.append(vspace(1.5))

        # ── Part ①  Cause / event context ────────────────────────────────────
        block.append(_card_label("① 원인 / 이벤트 맥락", accent))

        # Show pre-spike commentary if available
        pre_text  = comm_ctx.get("pre_text",  "").strip()
        conc_text = comm_ctx.get("concurrent_text", "").strip()
        if pre_text:
            block.append(note_box(
                "[해설 — 스파이크 직전 15초]  " + pre_text
            ))
            block.append(vspace(1))
        if conc_text and conc_text != pre_text:
            block.append(note_box(
                "[해설 — 스파이크 구간 중]  " + conc_text
            ))
            block.append(vspace(1))
        if not pre_text and not conc_text:
            block.append(note_box("자막/세그먼트 없음 — 채팅 텍스트로 추론"))
            block.append(vspace(1))

        # Chat-derived evidence (players + events)
        tag_parts = []
        if player_cands:
            tag_parts.append("채팅 언급 선수: " + "  ".join(
                f"{w}({c})" for w, c in player_cands[:4]))
        if event_mentions:
            tag_parts.append("채팅 이벤트 키워드: " + "  ".join(
                f"{ev}({c})" for ev, c in event_mentions[:4]))
        if tag_parts:
            block.append(P(" / ".join(tag_parts), STYLES["small"]))
            block.append(vspace(2))

        # ── Part ②  Audience reaction ─────────────────────────────────────────
        block.append(_card_label("② 시청자 반응 (채팅)", ORANGE))

        if reaction_profile:
            block.append(mini_reaction_table(reaction_profile))
            block.append(vspace(1))

        # ── Chat: side-by-side buildup (left) | event peak (right) ──────────────
        peak_internal = enriched.get("peak_internal", [])
        ev_cnt        = enriched.get("event_msg_count", len(peak_msgs))
        int_cnt       = enriched.get("internal_msg_count", 0)

        block.append(side_by_side_chat(
            left_msgs   = buildup_msgs,
            right_msgs  = peak_msgs,
            left_label  = f"빌드업 채팅 (직전 30초)  [{len(buildup_msgs)}개]",
            right_label = f"이벤트 반응 채팅  [{ev_cnt}개]",
            left_accent  = BLUE,
            right_accent = ORANGE,
        ))

        # ── Chat-internal layer — compact horizontal rows ─────────────────────
        if peak_internal:
            block.append(vspace(1.5))
            # Deduplicate
            seen_i, shown_i = set(), []
            for m in peak_internal:
                t = m.get("text", "").strip()
                if t and t not in seen_i:
                    seen_i.add(t)
                    shown_i.append(m)
                if len(shown_i) >= 5:
                    break

            hdr_s = ParagraphStyle(
                "_ich", fontName="KR-Bold", fontSize=7.5, textColor=GREY,
                leading=11, wordWrap="CJK")
            row_s = ParagraphStyle(
                "_icr", fontName="KR", fontSize=7.5, leading=12,
                textColor=BLACK, wordWrap="CJK")
            fw_int = PW - 2 * M
            ts_w, au_w, tx_w = 16 * mm, 28 * mm, fw_int - 44 * mm
            int_rows = [[
                Paragraph(f"채팅 내부 대화 [{int_cnt}개]", hdr_s),
                Paragraph("", hdr_s), Paragraph("", hdr_s),
            ]]
            for m in shown_i:
                ts   = fmt_seconds(m["timestamp_seconds"])
                auth = safe_str(m.get("author", ""))[:16]
                txt  = safe_str(m.get("text", ""))[:80]
                int_rows.append([
                    Paragraph(ts,   row_s),
                    Paragraph(auth, row_s),
                    Paragraph(txt,  row_s),
                ])
            int_tbl = Table(int_rows, colWidths=[ts_w, au_w, tx_w])
            int_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),  SLATE_LIGHT),
                ("BACKGROUND",    (0, 1), (-1, -1), WHITE),
                ("SPAN",          (0, 0), (-1, 0)),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                ("GRID",          (0, 0), (-1, -1), 0.3, SLATE_MID),
                ("TEXTCOLOR",     (0, 0), (-1, 0),  GREY),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
            ]))
            block.append(int_tbl)

        block.append(vspace(2))

        # ── Part ③  Interpretation ────────────────────────────────────────────
        block.append(_card_label("③ 해석 — 두 신호의 연결", GREEN))
        block.append(callout(interp_text, GREEN))
        block.append(vspace(5))

        story.append(KeepTogether(block[:8]))
        story.extend(block[8:])

    # ═══════════════════════════════════════════════════════════════
    # SECTION 3-S — Marketing Opportunity Players
    # ═══════════════════════════════════════════════════════════════
    _pa = d.get("player_analysis", [])
    if _pa:
        story.append(PageBreak())
        story.extend(section_heading("3-S.  마케팅 기회 선수 — 스포트라이트 확대 후보"))
        story.append(P(
            "이 섹션은 <b>언급량 최다 선수가 아니면서도 강한 시청자 반응을 이끌어낸</b> 선수를 발굴합니다.  "
            "이미 인지도가 높은 선수보다는, 추가 노출 시 반응 성장 잠재력이 큰 "
            "<b>신인·비주류·저인지 선수</b>를 콘텐츠·마케팅 기회 관점에서 추천합니다.",
            STYLES["body"]))
        story.append(vspace(2))

        story.append(callout(
            "마케팅 기회 점수 = (언급 1건당 반응 수) × (0.4 + 0.6 × 긍정 비율)"
            " × (1 + 0.2 × 스파이크 연계 수)  ÷  log₂(언급 수 + 2)\n"
            "높은 점수: 언급 빈도는 낮아도 등장할 때마다 강하고 긍정적인 반응을 유발하는 선수\n"
            "기존 강자(언급 횟수 상위 2인): 점수는 표시하되 기회 후보 카드에서는 제외",
            BLUE
        ))
        story.append(vspace(3))

        # ── Compute marketing opportunity score ───────────────────────────────
        for _p in _pa:
            _spike_bonus = min(len(_p["spike_ranks"]), 3)
            _p["_mkt_raw"] = (
                _p["rx_per_mention"]
                * (0.4 + 0.6 * _p["pos_ratio"])
                * (1.0 + 0.2 * _spike_bonus)
                / math.log2(_p["mention_count"] + 2)
            )
        _mkt_max = max((_p["_mkt_raw"] for _p in _pa), default=0.0)
        for _p in _pa:
            _p["_mkt_score"] = round(_p["_mkt_raw"] / _mkt_max * 100) if _mkt_max > 0 else 0

        # Top-2 by mention count = "established / already dominant"
        _by_mc = sorted(_pa, key=lambda x: x["mention_count"], reverse=True)
        _dominant = {_by_mc[i]["name"] for i in range(min(2, len(_by_mc)))}
        _sorted_mkt = sorted(_pa, key=lambda x: x["_mkt_score"], reverse=True)

        # ── Overview table ─────────────────────────────────────────────────────
        story.append(P("마케팅 기회 점수 순위", ParagraphStyle(
            "_mkt_hd", fontName="KR-Bold", fontSize=10, leading=14,
            textColor=BLUE, spaceBefore=2, spaceAfter=3)))

        _ov_rows = []
        for _p in _sorted_mkt[:10]:
            _flag  = "기존 강자" if _p["name"] in _dominant else "★ 기회"
            _spstr = ", ".join(f"#{r}" for r in _p["spike_ranks"]) if _p["spike_ranks"] else "—"
            _ov_rows.append([
                _flag,
                _p["name"],
                str(_p["mention_count"]),
                f"{_p['rx_per_mention']:.2f}",
                f"{int(_p['pos_ratio'] * 100)}%",
                _spstr,
                str(_p["_mkt_score"]),
            ])
        story.append(info_table(
            ["구분", "선수", "언급\n횟수", "언급당\n반응", "긍정\n비율", "스파이크\n연계", "기회\n점수"],
            _ov_rows,
            col_widths=[0.12, 0.20, 0.09, 0.10, 0.09, 0.18, 0.10],
        ))
        story.append(vspace(2))
        story.append(note_box(
            "★ 기회: 언급 횟수 기준 상위 2인을 제외한 선수.  "
            "기회 점수는 '등장 빈도 대비 반응 강도·긍정성·스파이크 연계'를 종합합니다.  "
            "점수가 높을수록 추가 노출 시 시청자 반응 성장 가능성이 높습니다."
        ))
        story.append(vspace(4))

        # ── Per-player opportunity cards (top 3 opportunity candidates) ────────
        _opp_cands = [_p for _p in _sorted_mkt if _p["name"] not in _dominant][:3]

        _SENT_HEX = {
            "유머·재미": "#F59E0B",
            "놀람·흥분": "#7C3AED",
            "감탄·대박": "#059669",
            "응원·격려": "#16A34A",
            "안타까움":  "#DC2626",
            "긴장·충격": "#EA580C",
            "긴장감":    "#EA580C",
            "긍정적":    "#16A34A",
            "복합적":    "#64748B",
        }

        def _mkt_reason(_p, _all_pa):
            _parts = []
            _mc_median = sorted(_q["mention_count"] for _q in _all_pa)[len(_all_pa) // 2]
            _rpe_avg   = sum(_q["rx_per_mention"] for _q in _all_pa) / len(_all_pa)
            if _p["mention_count"] <= _mc_median:
                _parts.append("언급 횟수가 데이터셋 중앙값 이하 (저인지)")
            if _p["rx_per_mention"] > _rpe_avg:
                _parts.append(
                    f"언급 1건당 반응량({_p['rx_per_mention']:.2f})이 평균 이상")
            if _p["pos_ratio"] >= 0.55:
                _parts.append(f"긍정 반응 비율 {int(_p['pos_ratio'] * 100)}%로 높음")
            if _p["spike_ranks"]:
                _sr_str = ", ".join(f"#{r}위" for r in _p["spike_ranks"][:2])
                _parts.append(f"핵심 스파이크 구간에 연계 ({_sr_str})")
            return "  ·  ".join(_parts) if _parts else "복합 지표 기준 상위 선수"

        def _mkt_suggestion(_p):
            _sent = _p["sentiment"]
            _sp   = _p["spike_ranks"]
            _spn  = f" (스파이크 #{_sp[0]} 연계)" if _sp else ""
            if _sent in ("감탄·대박", "놀람·흥분"):
                return f"기술·샷 중심 하이라이트 클립{_spn} — '이 선수의 이 장면' 단독 포맷 추천"
            elif _sent == "유머·재미":
                return f"캐릭터·재미 중심 숏츠{_spn} — 팬 친화적 인트로 소재로 활용"
            elif _sent == "응원·격려":
                return f"내러티브 성장·팬 스토리텔링{_spn} — 팬층 확대 소재로 적합"
            elif _sent == "긍정적":
                return f"종합 하이라이트 출연 비중 확대{_spn} — 다양한 편집 포맷 테스트"
            else:
                return f"자연스러운 반응 클립 발굴{_spn} — 다양한 포맷으로 테스트 권장"

        if _opp_cands:
            story.append(P("주요 기회 후보 — 상세 카드", ParagraphStyle(
                "_opp_subhd", fontName="KR-Bold", fontSize=10, leading=14,
                textColor=GREEN, spaceBefore=2, spaceAfter=3)))

            _fw_s = PW - 2 * M
            _cw4  = (_fw_s - 4 * mm) / 4

            _mv_s = ParagraphStyle("_mv", fontName="KR-Bold", fontSize=11,
                                   leading=14, textColor=BLUE, alignment=TA_CENTER)
            _ml_s = ParagraphStyle("_ml", fontName="KR", fontSize=7.5,
                                   leading=11, textColor=GREY,
                                   alignment=TA_CENTER, wordWrap="CJK")

            for _p in _opp_cands:
                _obc = []
                _sent_hex = _SENT_HEX.get(_p["sentiment"], "#64748B")
                _sp_str   = (
                    "  ".join(f"#{r}위 스파이크" for r in _p["spike_ranks"])
                    if _p["spike_ranks"] else "—"
                )
                _rx_tags  = "  ·  ".join(
                    f"{_cat}({_cnt})" for _cat, _cnt in _p["top_reactions"][:3]
                ) if _p["top_reactions"] else "—"

                # Card header
                _obc.append(P(
                    f"★  {_p['name']}  ·  기회 점수 {_p['_mkt_score']}/100",
                    ParagraphStyle("_och", fontName="KR-Bold", fontSize=10,
                                   leading=15, textColor=GREEN, spaceBefore=5)
                ))
                _obc.append(rule(GREEN, 0.8))

                # 4-cell stat row
                def _sc(_val, _lbl):
                    return Table(
                        [[Paragraph(str(_val), _mv_s)],
                         [Paragraph(_lbl,     _ml_s)]],
                        colWidths=[_cw4], rowHeights=[13 * mm, 8 * mm])

                _sr = Table([[
                    _sc(str(_p["mention_count"]),          "언급 횟수"),
                    _sc(f"{_p['rx_per_mention']:.2f}",     "언급당 반응"),
                    _sc(f"{int(_p['pos_ratio']*100)}%",    "긍정 비율"),
                    _sc(str(_p["total_rx"]),               "총 반응량"),
                ]], colWidths=[_cw4] * 4)
                _sr.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), SLATE_LIGHT),
                    ("GRID",          (0, 0), (-1, -1), 0.3, SLATE_MID),
                    ("TOPPADDING",    (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
                ]))
                _obc.append(_sr)
                _obc.append(vspace(1))

                _obc.append(P(
                    f"주요 반응 패턴: "
                    f"<b><font color='{_sent_hex}'>{_p['sentiment']}</font></b>"
                    f"  ·  반응 상세: {_rx_tags}",
                    STYLES["small"]
                ))
                _obc.append(P(f"스파이크 연계: {_sp_str}", STYLES["small"]))
                _obc.append(vspace(1))

                _obc.append(callout(
                    f"<b>기회 이유:</b>  {_mkt_reason(_p, _pa)}\n\n"
                    f"<b>콘텐츠·마케팅 제안:</b>  {_mkt_suggestion(_p)}",
                    GREEN
                ))
                _obc.append(vspace(4))

                story.append(KeepTogether(_obc[:4]))
                story.extend(_obc[4:])

        story.append(note_box(
            "상세 선수별 반응 데이터(반응 분포 차트·기회 점수 전체 목록)는 "
            "섹션 8-B / 8-C를 참조하십시오."
        ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 5 — Keyword & Reaction Analysis
    # ═══════════════════════════════════════════════════════════════
    story.extend(section_heading("4.  스파이크 구간 키워드 분석"))
    story.append(P(
        "ㅋ+, ㅎ+, ㅠ+ 등 반복 패턴은 동일 반응으로 통합했습니다. "
        "게임 이벤트 키워드(OB, 버디 등)는 별도 집계합니다.",
        STYLES["body"]))
    story.append(vspace(2))

    kw_data = d["top_spike_keywords"]
    if kw_data:
        max_kw = kw_data[0][1]
        story.append(bar_chart(kw_data[:12], max_kw, ORANGE, accent_idx=0))
    story.append(vspace(4))

    # Golf events
    ev_data = d["top_spike_events"]
    if ev_data:
        story.extend(section_heading("5.  스파이크 구간 골프 이벤트"))
        story.append(info_table(
            ["이벤트", "언급 횟수"],
            [(ev, str(cnt)) for ev, cnt in ev_data],
            col_widths=[0.65, 0.35],
        ))
        story.append(vspace(4))

    # Overall reaction profile
    if d["overall_reaction_profile"]:
        story.extend(section_heading("6.  전체 스파이크 반응 유형 합계"))
        story.append(P(
            "모든 스파이크 구간에서 감지된 반응 유형의 누적 합계입니다. "
            "어떤 감정이 이 영상 전체에서 가장 많이 표출됐는지를 보여줍니다.",
            STYLES["body"]))
        story.append(vspace(2))
        max_rc = d["overall_reaction_profile"][0][1]
        story.append(bar_chart(
            [(cat, cnt) for cat, cnt in d["overall_reaction_profile"]],
            max_rc, GREEN, accent_idx=0
        ))
        story.append(vspace(4))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 6 — Shorts & Title Recommendations
    # ═══════════════════════════════════════════════════════════════
    story.extend(section_heading("7.  Shorts & 제목 추천"))

    if d["title_suggestions"]:
        story.append(P("추천 제목 후보", STYLES["h3"]))
        for t in d["title_suggestions"]:
            story.append(bullet(safe_str(t)))
        story.append(vspace(4))

    if d["shorts_sequences"]:
        story.append(P("Shorts 시퀀스 기획안", STYLES["h3"]))
        rows = []
        for s in d["shorts_sequences"]:
            dur = safe_str(s.get("estimated_duration_sec", ""))
            rows.append([
                safe_str(s.get("title", "")),
                safe_str(s.get("description", "")),
                (dur + "초") if dur != "—" else "—",
            ])
        story.append(info_table(["제목", "설명", "예상 길이"], rows,
                                col_widths=[0.30, 0.55, 0.15]))
        story.append(vspace(4))

    story.append(note_box(
        "스파이크 기반 Shorts 후보는 메시지 밀집도로 선정됩니다. "
        "최종 편집 여부는 영상을 직접 확인하십시오."
    ))
    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGES — Player-centred Analysis  (independent of spike detection)
    # ═══════════════════════════════════════════════════════════════
    player_list = d.get("player_analysis", [])

    story.extend(section_heading("8.  선수별 시청자 반응 분석"))
    story.append(P(
        "스파이크 분석과 독립적인 <b>선수 중심 분석</b>입니다.  "
        "채팅 전체에서 '이름+호칭(프로/선수/형/님)' 패턴으로 선수를 추출하고, "
        "각 언급 시점 전후 ±30초 창의 반응을 해당 선수에게 귀속시킵니다.  "
        "이 방식은 같은 메시지에 이름과 반응이 함께 있지 않아도 반응을 포착합니다.",
        STYLES["body"]))
    story.append(vspace(3))

    if not player_list:
        story.append(note_box(
            "채팅에서 '이름+호칭' 패턴이 감지되지 않았습니다.  "
            "선수 이름이 호칭 없이 언급되거나 채팅량이 너무 적을 경우 발생합니다."
        ))
        story.append(PageBreak())
    else:
        # ── 8-A. Dual-bar overview: mentions + reaction volume ────────────────
        story.extend(section_heading("8-A.  언급 횟수 및 반응량 순위"))
        story.append(P(
            "왼쪽: 전체 채팅에서의 언급 횟수 (인지도 지표).  "
            "오른쪽: 해당 선수가 언급된 시간대에서 수집된 총 반응 수 (시청자 에너지 지표).",
            STYLES["body"]))
        story.append(vspace(2))

        top10 = player_list[:10]
        fw    = PW - 2 * M
        max_mc = max(p["mention_count"] for p in top10)
        max_rx = max(p["total_rx"]      for p in top10) or 1

        # Build two-column layout: left = mention chart, right = reaction chart
        half_w = fw / 2 - 3 * mm
        lbl_w  = 32 * mm
        bar_left_w  = half_w - lbl_w - 14 * mm
        val_w  = 14 * mm

        def _dual_bar_row(label, mention, total_rx, max_mc_, max_rx_):
            """One row: [label | mention bar | rx bar]"""
            def _seg(fill, empty, color):
                t = Table([[" ", " "]], colWidths=[max(fill, 1), max(empty, 1)],
                          rowHeights=[9])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (0, 0), color),
                    ("BACKGROUND", (1, 0), (1, 0), SLATE_MID),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                ]))
                return t

            m_fill  = int(bar_left_w * mention  / max_mc_) if max_mc_ > 0 else 0
            rx_fill = int(bar_left_w * total_rx / max_rx_) if max_rx_ > 0 else 0

            lbl_p = Paragraph(label, ParagraphStyle(
                "_dbl", fontName="KR", fontSize=8, leading=12,
                textColor=BLACK, wordWrap="CJK"))
            mc_p  = Paragraph(str(mention), ParagraphStyle(
                "_dbm", fontName="KR-Bold", fontSize=7.5, textColor=BLUE,
                alignment=TA_RIGHT, leading=12))
            rx_p  = Paragraph(str(total_rx), ParagraphStyle(
                "_dbr", fontName="KR-Bold", fontSize=7.5, textColor=ORANGE,
                alignment=TA_RIGHT, leading=12))

            return [lbl_p,
                    _seg(m_fill,  int(bar_left_w) - m_fill,  BLUE),   mc_p,
                    _seg(rx_fill, int(bar_left_w) - rx_fill, ORANGE), rx_p]

        col_ws = [lbl_w, bar_left_w, val_w, bar_left_w, val_w]
        hdr_ps = ParagraphStyle("_dbh", fontName="KR-Bold", fontSize=7.5,
                                textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK")
        header_row = [
            Paragraph("선수", hdr_ps),
            Paragraph("언급 횟수", hdr_ps), Paragraph("", hdr_ps),
            Paragraph("반응량", hdr_ps),    Paragraph("", hdr_ps),
        ]
        data_rows = [
            _dual_bar_row(p["name"], p["mention_count"], p["total_rx"], max_mc, max_rx)
            for p in top10
        ]
        dual_tbl = Table([header_row] + data_rows, colWidths=col_ws)
        dual_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (0, -1),  5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
            ("GRID",          (0, 0), (-1, -1), 0.3, SLATE_MID),
        ]))
        story.append(dual_tbl)
        story.append(vspace(2))
        story.append(note_box(
            "언급 횟수 = 채팅에서 해당 선수 이름+호칭이 등장한 횟수 (인지도).  "
            "반응량 = 언급 전후 ±30초 창에서 집계된 감탄·웃음·탄성 등 반응 토큰 수 (흥미도).  "
            "두 지표 간 격차가 클수록 '언급 대비 반응이 강한' 또는 '반응 대비 언급이 적은' 선수입니다."
        ))
        story.append(PageBreak())

        # ── 8-B. Per-player reaction profile cards ────────────────────────────
        story.extend(section_heading("8-B.  선수별 반응 프로파일"))
        story.append(P(
            "각 선수에 대해: 반응 유형 분포 / 감성 프로파일 / 반응 집중도 / 스파이크 연계.",
            STYLES["body"]))
        story.append(vspace(3))

        # Sentiment → color mapping
        _SENT_COLOR = {
            "유머·재미":   colors.HexColor("#F59E0B"),
            "놀람·흥분":   colors.HexColor("#7C3AED"),
            "감탄·대박":   colors.HexColor("#059669"),
            "응원·격려":   GREEN,
            "안타까움":    RED,
            "긴장·충격":   ORANGE,
            "긴장감":      ORANGE,
            "긍정적":      GREEN,
            "복합적":      GREY,
        }

        for i, p in enumerate(player_list[:10]):
            name      = p["name"]
            mc        = p["mention_count"]
            events    = p["mention_events"]
            total_rx  = p["total_rx"]
            rpe       = p["rx_per_event"]
            pos_r     = p["pos_ratio"]
            sent      = p["sentiment"]
            top_rx    = p["top_reactions"]
            spikes    = p["spike_ranks"]
            opp       = p["opportunity_score"]

            accent      = ORANGE if i == 0 else BLUE
            sent_color  = _SENT_COLOR.get(sent, GREY)

            block = []

            # Header line
            rank_star = "★ " if i < 3 else ""
            block.append(P(
                f"{rank_star}{i+1}.  {name}",
                ParagraphStyle("_ph", fontName="KR-Bold", fontSize=10, leading=15,
                               textColor=accent, spaceBefore=6)
            ))
            block.append(rule(accent, 0.8))

            # Stat row: 4-cell mini table
            def _stat_cell(label, val, color=BLACK):
                return Table(
                    [[Paragraph(str(val), ParagraphStyle(
                          "_sv", fontName="KR-Bold", fontSize=11, leading=15,
                          textColor=color, alignment=TA_CENTER))],
                     [Paragraph(label, ParagraphStyle(
                          "_sl", fontName="KR", fontSize=7.5, leading=11,
                          textColor=GREY, alignment=TA_CENTER, wordWrap="CJK"))]],
                    colWidths=[fw / 5],
                    rowHeights=[14 * mm, 8 * mm],
                )

            pos_pct = f"{int(pos_r * 100)}%"
            opp_str = str(opp) if opp is not None else "—"
            stat_cells = [
                _stat_cell("언급 횟수", mc, BLUE),
                _stat_cell("등장 이벤트", events, SLATE),
                _stat_cell("총 반응량", total_rx, ORANGE),
                _stat_cell("이벤트당 반응", f"{rpe:.1f}", GREEN),
                _stat_cell("긍정 비율", pos_pct, sent_color),
            ]
            stat_row_tbl = Table([stat_cells], colWidths=[fw / 5] * 5)
            stat_row_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
                ("GRID",       (0, 0), (-1, -1), 0.4, BLUE_MID),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            block.append(stat_row_tbl)
            block.append(vspace(2))

            # Reaction type breakdown (horizontal pill table, up to 5 types)
            if top_rx:
                rx_cols = min(len(top_rx), 5)
                cw      = fw / rx_cols
                n_row, l_row = [], []
                for cat, cnt in top_rx[:rx_cols]:
                    n_row.append(Paragraph(str(cnt), ParagraphStyle(
                        "_rxn", fontName="KR-Bold", fontSize=9, textColor=ORANGE,
                        alignment=TA_CENTER, leading=13)))
                    l_row.append(Paragraph(cat, ParagraphStyle(
                        "_rxl", fontName="KR", fontSize=7.5, textColor=GREY,
                        alignment=TA_CENTER, leading=11, wordWrap="CJK")))
                rx_t = Table([n_row, l_row], colWidths=[cw] * rx_cols,
                             rowHeights=[11 * mm, 8 * mm])
                rx_t.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#FFF7ED")),
                    ("BACKGROUND",    (0, 1), (-1, 1), SLATE_LIGHT),
                    ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
                    ("TOPPADDING",    (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                block.append(P("반응 유형 분포:", STYLES["small"]))
                block.append(rx_t)
                block.append(vspace(1))

            # Sentiment + spike tags
            spike_str = (
                "  ·  스파이크 연계: " + ", ".join(f"#{r}위" for r in spikes)
                if spikes else ""
            )
            opp_str2  = (f"  ·  기회 점수: {opp}/100" if opp is not None else "")
            block.append(P(
                f"감성 프로파일: <b>{sent}</b>{spike_str}{opp_str2}",
                ParagraphStyle("_pi2", fontName="KR", fontSize=8, leading=13,
                               textColor=GREY, wordWrap="CJK")
            ))
            block.append(vspace(4))

            story.append(KeepTogether(block[:4]))
            story.extend(block[4:])

        story.append(PageBreak())

        # ── 8-C. Opportunity table ────────────────────────────────────────────
        story.extend(section_heading("8-C.  발굴 기회 분석 — 저인지·고반응 선수"))
        story.append(P(
            "<b>기회 점수(Opportunity Score)</b>는 '언급량은 적지만 등장할 때마다 강하고 "
            "긍정적인 시청자 반응을 이끌어내는' 선수를 찾기 위한 지표입니다.  "
            "이런 선수는 콘텐츠 노출을 늘렸을 때 시청자 반응이 빠르게 성장할 가능성이 있습니다.",
            STYLES["body"]))
        story.append(vspace(2))

        # Score definition callout
        story.append(callout(
            "기회 점수 = (이벤트당 반응 수) × (0.4 + 0.6 × 긍정 비율)  →  0–100 정규화\n"
            "높은 점수: 등장 빈도는 낮아도 시청자가 즉각·긍정적으로 반응하는 선수\n"
            "낮은 점수: 자주 언급되지만 반응 강도·긍정성이 평균 이하인 선수",
            BLUE
        ))
        story.append(vspace(3))

        # Eligible players: ≥ 2 mention events, has opportunity score
        eligible_opp = [
            p for p in player_list
            if p["opportunity_score"] is not None
        ]
        eligible_opp.sort(key=lambda x: x["opportunity_score"], reverse=True)

        if eligible_opp:
            rows_opp = []
            median_mc = sorted(p["mention_count"] for p in eligible_opp)[len(eligible_opp) // 2]
            for p in eligible_opp:
                flag = "★" if p["mention_count"] <= median_mc else ""
                rows_opp.append([
                    flag + p["name"],
                    str(p["mention_count"]),
                    str(p["total_rx"]),
                    f"{p['rx_per_event']:.1f}",
                    f"{int(p['pos_ratio'] * 100)}%",
                    p["sentiment"],
                    str(p["opportunity_score"]),
                ])
            story.append(info_table(
                ["선수", "언급수", "반응량", "이벤트당\n반응", "긍정\n비율", "감성", "기회\n점수"],
                rows_opp,
                col_widths=[0.24, 0.09, 0.09, 0.10, 0.09, 0.17, 0.10],
            ))
            story.append(vspace(2))
            story.append(note_box(
                "★ 표시 = 데이터셋 내 중앙값 이하 언급 횟수 (저인지 후보).  "
                "기회 점수 상위 + ★ 조합이 '발굴 우선 검토' 선수입니다.  "
                "최소 2회 이상 언급 이벤트가 있는 선수만 포함됩니다."
            ))
        else:
            story.append(note_box(
                "기회 점수를 계산할 수 있는 선수가 없습니다 "
                "(언급 이벤트 2회 미만). 더 긴 영상이나 더 많은 채팅 데이터가 필요합니다."
            ))

        story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 9 — Data requirements + Limitations
    # ═══════════════════════════════════════════════════════════════
    story.extend(section_heading("추가 데이터 요구사항 및 분석 한계"))

    story.append(P("<b>두 신호 연결 방식</b>", STYLES["h3"]))
    story.append(P(
        "각 스파이크는 <b>해설/자막</b>과 <b>채팅</b>을 독립적인 증거로 취급하여 연결합니다:",
        STYLES["body"]))
    for item in [
        "자막 — 스파이크 직전 15초 (causal window): 시청자가 채팅을 입력하기 전에 "
        "해설자는 이미 해당 장면을 묘사하고 있습니다. 이 창이 인과 신호로 가장 강합니다.",
        "자막 — 스파이크 구간 중 (concurrent window): 반응과 동시에 진행된 해설입니다. "
        "직전 창이 비어 있을 때 보조 증거로 사용됩니다.",
        "채팅 — anchor±10초 (tight window): 선수명·이벤트 키워드 추출의 1차 소스. "
        "이 창이 비어 있으면 전체 스파이크 창(60초)으로 확장합니다.",
        "채팅 — 전체 스파이크 창 (60초): 반응 유형(웃음·탄성·안타까움 등) 집계.",
        "근거 표시 ◎/○/△: 두 신호가 모두 존재하면 ◎, 자막만 있으면 ○, 채팅만이면 △.",
    ]:
        story.append(bullet(item))
    story.append(vspace(3))

    story.append(P("<b>충돌·약한 근거 처리</b>", STYLES["h3"]))
    for item in [
        "자막 있음 + 채팅 선수명 없음: 해설이 원인을 주도, 채팅은 반응 유형만 공급.",
        "자막 없음 + 채팅 선수명 있음: 채팅 텍스트 추론, '자막 없음' 명시, 인과관계 확인 권장.",
        "자막 없음 + 채팅 선수명도 없음: '근거 불충분' 레이블, 밀집도만으로 선정된 구간 표시.",
        "채팅 '내일/오늘/진짜' 등 일반 단어는 스톱워드로 걸러져 선수명으로 오인되지 않습니다.",
    ]:
        story.append(bullet(item))
    story.append(vspace(3))

    story.append(P("<b>자막/세그먼트로 해석 품질 향상</b>", STYLES["h3"]))
    for item in [
        "youtube_extractor.sh를 실행하면 VTT 자막을 segments.json으로 변환합니다.",
        "segments.json이 lesson_{VIDEO_ID}/ 에 있으면 자동으로 로드됩니다.",
        "스파이크 직전 15초 해설이 카드 ① 원인 항목에 표시되고 해석에 반영됩니다.",
        "해설자가 선수명·장면을 언급하면 채팅과 교차검증되어 해석 신뢰도가 높아집니다.",
    ]:
        story.append(bullet(item))
    story.append(vspace(4))

    story.append(P("<b>엔티티 레지스트리 및 Buzz 유형 판별</b>", STYLES["h3"]))
    story.append(P(
        "각 스파이크에는 <b>Buzz / Topic 요약 박스</b>가 표시됩니다.  "
        "박스 색상과 레이블은 스파이크가 어떤 종류의 반응으로 구성됐는지를 나타냅니다:",
        STYLES["body"]))
    for item in [
        "방송 이벤트 반응 (파란색): 골프 이벤트(버디·이글·OB 등) 또는 해설 맥락이 스파이크를 주도.",
        "참여자 중심 화제 (초록색): 채널 호스트·게스트 크리에이터가 채팅에 직접 참여하는 구간.",
        "혼합 (주황색): 이벤트 반응과 참여자 대화가 동시에 강하게 나타나는 구간.",
        "일반 반응 (회색): 특정 패턴이 없는 채팅 밀집 구간.",
        "엔티티 레지스트리에는 채널 호스트(골과장님·골사원), 참여 크리에이터(문서형), "
        "프로 선수들이 역할(role)과 함께 등록되어 있습니다.  "
        "채팅 발신자 이름에서 author_patterns 매칭으로 실시간 참여 여부를 자동 감지합니다.",
    ]:
        story.append(bullet(item))
    story.append(vspace(3))

    story.append(P("<b>분석 한계</b>", STYLES["h3"]))
    for lim in [
        "라이브 채팅 전용: VOD 댓글 분석은 generate_report_by_comment.py를 별도 실행하십시오.",
        "스파이크 = 밀집도 기반: 반응 품질(긍정/부정)이 아닌 메시지 수로 피크를 감지합니다.",
        "반응 유형 분류는 규칙 기반입니다. 문맥에 따른 반어·복합 감정은 포착되지 않습니다.",
        "타임스탬프 정밀도: yt-dlp 기준이며 실제 편집점과 수초 차이가 있을 수 있습니다.",
        "인접 스파이크 병합: 최소 간격(윈도우 절반) 내 스파이크는 하나로 통합됩니다.",
        "자막 ASR 오류: YouTube 자동생성 자막은 발음이 유사한 이름을 오인식할 수 있습니다. "
        "예: '김용석' → '김영석' (ㅗ/ㅕ 모음 혼동). PLAYER_ALIASES에 알려진 ASR 오류를 "
        "수동 등록하면 정정됩니다.",
        "이벤트 키워드 맥락 필터: '우승/이글' 등이 가정·비교 문맥에서 등장하면 "
        "현재 이벤트에서 제외됩니다. 완벽한 문맥 판단은 아니므로 수동 검토가 권장됩니다.",
    ]:
        story.append(bullet(lim))

    return story


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("[live_chat_report] 데이터 로딩 중...")
    d = load_data()
    print(f"[live_chat_report] 스파이크 {d['spike_count']}개 로드 / "
          f"세그먼트: {'있음' if d['has_segments'] else '없음'}")

    print("[live_chat_report] 리포트 생성 중...")
    story = build_story(d)

    out_path = str(OUTPUT_DIR / "live_chat_insight_report.pdf")
    doc = make_doc(out_path)
    doc.build(story)
    size_kb = Path(out_path).stat().st_size // 1024
    print(f"[live_chat_report] 완료: {out_path}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
