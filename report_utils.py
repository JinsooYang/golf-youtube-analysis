"""Shared PDF utilities for report generation (fonts, colours, flowable helpers)."""

import csv
import json
import re
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

# ── Paths ─────────────────────────────────────────────────────────────────────
FONT_DIR = Path("fonts")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Font registration ─────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont("KR", str(FONT_DIR / "NanumGothic-Regular.ttf")))
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
M = 18 * mm  # margin


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
    "quote":     S("qt",  fontSize=9, leading=15, textColor=SLATE,
                   leftIndent=10, rightIndent=10,
                   borderPadding=(6, 8, 6, 8), alignment=TA_JUSTIFY),
    "footer":    S("ft",  fontSize=7.5, textColor=GREY, alignment=TA_LEFT),
    "footer_r":  S("ftr", fontSize=7.5, textColor=GREY, alignment=TA_RIGHT),
    "tag":       S("tag", fontName="KR-Bold", fontSize=8, textColor=BLUE),
    "num_big":   S("nb",  fontName="KR-Bold", fontSize=28, leading=34,
                   textColor=BLUE, alignment=TA_CENTER),
    "num_label": S("nl",  fontSize=8, textColor=GREY, alignment=TA_CENTER),
    "bullet":    S("blt", fontSize=9, leading=15, leftIndent=12,
                   spaceAfter=3),
}


# ── Page templates ────────────────────────────────────────────────────────────

def make_doc(path: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        path,
        pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M + 8 * mm, bottomMargin=M + 8 * mm,
        title="유튜브 댓글 기반 마케팅 인사이트 리포트",
        author="GTOUR Analysis",
    )
    fw = PW - 2 * M

    def header_footer(canvas, doc):
        canvas.saveState()
        # Top rule
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(0.6)
        canvas.line(M, PH - M - 4 * mm, PW - M, PH - M - 4 * mm)
        # Header text
        canvas.setFont("KR-Bold", 7.5)
        canvas.setFillColor(BLUE)
        canvas.drawString(M, PH - M - 1.5 * mm, "YouTube 댓글 기반 마케팅 인사이트")
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawRightString(PW - M, PH - M - 1.5 * mm, "2026 샤브20 GTOUR 슈퍼매치")
        # Bottom rule
        canvas.setStrokeColor(SLATE_MID)
        canvas.line(M, M + 5 * mm, PW - M, M + 5 * mm)
        # Page number
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(PW / 2, M + 1.5 * mm, str(doc.page))
        canvas.restoreState()

    normal = PageTemplate(
        id="normal",
        frames=[Frame(M, M + 9 * mm, fw, PH - 2 * M - 18 * mm, id="main")],
        onPage=header_footer,
    )
    doc.addPageTemplates([normal])
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
    return Paragraph(f"• &nbsp;{text}", style)


def tag_box(label: str, value: str, col=BLUE):
    """Small coloured tag pair."""
    data = [[Paragraph(label, STYLES["tag"]),
             Paragraph(value, STYLES["body_left"])]]
    t = Table(data, colWidths=["35%", "65%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE_LIGHT),
        ("FONTNAME",   (0, 0), (-1, -1), "KR"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",       (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    return t


def stat_table(items: list[tuple]) -> Table:
    """items = [(label, value), …]  → horizontal stat cards."""
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
    if col_widths is None:
        col_widths = [fw / len(headers)] * len(headers)
    else:
        col_widths = [fw * r for r in col_widths]

    header_cells = [Paragraph(h, ParagraphStyle(
        "th", fontName="KR-Bold", fontSize=8.5, leading=13,
        textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK")) for h in headers]

    body_rows = []
    for row in rows:
        body_rows.append([
            Paragraph(str(c), ParagraphStyle(
                "td", fontName="KR", fontSize=8.5, leading=14,
                textColor=BLACK, wordWrap="CJK"))
            for c in row
        ])

    t = Table([header_cells] + body_rows, colWidths=col_widths,
              repeatRows=1)
    style = [
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
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LINEBELOW",     (0, 0), (-1, 0),  1,   BLUE),
    ]
    t.setStyle(TableStyle(style))
    return t


def quote_card(likes: str, author: str, text: str, accent=BLUE):
    fw = PW - 2 * M
    likes_style = ParagraphStyle(
        "lk", fontName="KR-Bold", fontSize=11, textColor=accent,
        alignment=TA_CENTER, leading=16)
    likes_label = ParagraphStyle(
        "lkl", fontName="KR", fontSize=7.5, textColor=GREY,
        alignment=TA_CENTER)
    author_style = ParagraphStyle(
        "auth", fontName="KR-Bold", fontSize=8, textColor=GREY, leading=12)
    text_style = ParagraphStyle(
        "qt2", fontName="KR", fontSize=9, leading=15, textColor=SLATE,
        wordWrap="CJK", alignment=TA_JUSTIFY)

    left = [[Paragraph(likes, likes_style), Paragraph("likes", likes_label)]]
    right = [[Paragraph(author, author_style)], [Paragraph(text, text_style)]]

    lw = 18 * mm
    rw = fw - lw - 3 * mm

    lt = Table(left, colWidths=[lw], rowHeights=[None])
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), BLUE_LIGHT),
        ("VALIGN",     (0, 0), (0, -1), "MIDDLE"),
        ("ALIGN",      (0, 0), (0, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    rt = Table(right, colWidths=[rw])
    rt.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (-1, -1), SLATE_LIGHT),
    ]))
    outer = Table([[lt, rt]], colWidths=[lw, rw + 3 * mm])
    outer.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("GRID",    (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return [outer, vspace(2)]


def bar_chart(items: list[tuple[str, int]], max_val: int,
              color=BLUE, accent_idx: int = -1) -> Table:
    """Simple horizontal bar chart as a table."""
    fw = PW - 2 * M
    label_w = 52 * mm
    bar_w = fw - label_w - 22 * mm
    val_w = 22 * mm

    rows = []
    for i, (label, val) in enumerate(items):
        fill_ratio = val / max_val
        fill_px = int(bar_w * fill_ratio)
        empty_px = bar_w - fill_px

        bar_color = ORANGE if (i == accent_idx) else color
        label_weight = "KR-Bold" if (i == accent_idx) else "KR"

        lbl = Paragraph(label, ParagraphStyle(
            "brl", fontName=label_weight, fontSize=8.5, leading=13,
            textColor=BLACK, wordWrap="CJK"))
        # bar as filled table
        bar_inner = Table(
            [[" ", " "]],
            colWidths=[fill_px or 1, empty_px or 1],
            rowHeights=[10],
        )
        bar_inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), bar_color),
            ("BACKGROUND", (1, 0), (1, 0), SLATE_MID),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        val_p = Paragraph(str(val), ParagraphStyle(
            "brv", fontName="KR-Bold", fontSize=8, textColor=GREY,
            alignment=TA_RIGHT))
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
    """Highlighted callout box."""
    data = [[Paragraph(text, ParagraphStyle(
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
    data = [[Paragraph(text, ParagraphStyle(
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
