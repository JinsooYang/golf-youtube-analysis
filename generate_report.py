"""
Marketing Insight PDF Report Generator
2026 샤브20 GTOUR 슈퍼매치 — YouTube Comment Analysis

Run:
    python generate_report.py
Output:
    output/marketing_insight_report.pdf
"""

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


# ── Report content ────────────────────────────────────────────────────────────

def build_story() -> list:
    story = []
    P = Paragraph  # shorthand

    # ═══════════════════════════════════════════════════════════════
    # PAGE 1 — Cover / Executive Summary
    # ═══════════════════════════════════════════════════════════════
    story.append(P("유튜브 댓글 기반<br/>마케팅 인사이트 리포트", STYLES["h1"]))
    story.append(P(
        "2026 샤브20 GTOUR 슈퍼매치 &nbsp;·&nbsp; 시청자 반응에서 다음 콘텐츠 기회를 도출",
        STYLES["subtitle"]))
    story.append(rule(BLUE, 1.2))
    story.append(vspace(2))

    # Meta table
    fw = PW - 2 * M
    meta = Table([
        [P("분석 대상", STYLES["tag"]),
         P("2026 샤브20 GTOUR 슈퍼매치", STYLES["body_left"]),
         P("Video ID", STYLES["tag"]),
         P("Ef5fYM-WiPA", STYLES["body_left"])],
        [P("데이터 범위", STYLES["tag"]),
         P("일반 댓글 128개 + 답글 27개", STYLES["body_left"]),
         P("기준", STYLES["tag"]),
         P("좋아요 수, 언급량, 원댓글 문맥 수동 검토", STYLES["body_left"])],
    ], colWidths=[fw * 0.14, fw * 0.36, fw * 0.14, fw * 0.36])
    meta.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), BLUE_LIGHT),
        ("BACKGROUND",    (2, 0), (2, -1), BLUE_LIGHT),
        ("FONTNAME",      (0, 0), (-1, -1), "KR"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    story.append(meta)
    story.append(vspace(5))

    # Stat cards
    story.append(stat_table([
        ("전체 댓글 수", "155"), ("고유 작성자", "131"),
        ("총 좋아요", "367"), ("최대 좋아요", "23"),
    ]))
    story.append(vspace(6))

    # Executive summary
    story += section_heading("핵심 요약")
    story.append(callout(
        "이번 경기 댓글 반응의 핵심은 <b>&#8220;응원&#8221;이 아니라 &#8220;극적 반전&#8221;</b>이었습니다. "
        "3타 차로 앞서가던 팀이 17번홀 OB 한 방에 순식간에 무너진 장면이 "
        "시청자 감정을 집중시켰고, 가장 많은 좋아요를 받은 댓글들은 "
        "선수의 감정 기복·태도·판단력에 대한 냉정한 평가였습니다. "
        "자동 분석에서 '지배적 감정'으로 집계된 화이팅/응원 토큰은 "
        "<b>언급 빈도는 높지만 감정 강도(좋아요)에서는 상위권이 아닙니다.</b>"
    ))
    story.append(vspace(3))

    bullets_exec = [
        "언급량 1위는 <b>안예인</b>이지만, 고좋아요 반응은 <b>공태현의 멘탈·태도 논란</b>과 "
        "<b>이용희의 하드캐리 서사</b>에 집중됐습니다.",
        "<b>17번홀 OB + 뒷땅</b>이 경기의 결정적 전환점으로 다수의 댓글이 구체적으로 지목했습니다. "
        "이 장면은 클립 1순위입니다.",
        "<b>이용희 본인 계정(@이용희프로)</b>이 댓글 쓰레드에 직접 참여했습니다. "
        "팬 직접 소통 콘텐츠로 확장 가능한 시그널입니다.",
        "다음 콘텐츠는 '누가 잘했나' 결과보다, "
        "<b>'왜 무너졌는가·어떻게 뒤집혔는가·누가 버텼는가'</b>를 "
        "스토리로 푸는 편이 반응을 더 끌어낼 가능성이 큽니다.",
        "응원·격려 댓글과 논란성 댓글이 공존하므로, 클립 선정 시 "
        "<b>브랜드 톤 관리</b>가 필요합니다 — 논란 클립보다 복기·분석형 포맷이 안전합니다.",
    ]
    for b in bullets_exec:
        story.append(bullet(b))
    story.append(vspace(3))
    story.append(note_box(
        "⚠ 이 리포트는 종료된 라이브의 <b>일반 댓글만</b> 분석했습니다. "
        "라이브채팅 리플레이는 공식 API만으로 안정적으로 수집하기 어렵습니다. "
        "시점별 반응 폭증 분석은 라이브채팅 로그 확보 후 별도 진행이 필요합니다."
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 2 — Reaction Structure
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("1.  반응 구조: 무엇에 시청자가 실제로 반응했는가")

    story.append(P(
        "자동 요약이 '응원 분위기'를 주된 톤으로 분류한 것은 <b>ㅋㅋ·화이팅 같은 고빈도 "
        "단어 때문</b>입니다. 그러나 실제 상위 좋아요 댓글을 원문 맥락으로 재독하면 "
        "반응의 중심은 아래 네 축으로 구성됩니다.",
        STYLES["body"]))
    story.append(vspace(3))

    reaction_tbl = info_table(
        ["반응 유형", "구체적 신호", "좋아요 집중도", "콘텐츠 시사점"],
        [
            ["극적 반전·불신",
             "이걸 뒤집네 / 3타 차이가... / 드라마네 / 끝까지 짜릿하네요",
             "★★★★★",
             "역전 서사 자체가 핵심 훅. '마지막 홀까지 모른다' 포맷 유효"],
            ["실수·멘탈 붕괴",
             "OB, 뒷땅, 퍼터 연속 실패, 한 방에 KO / 멘탈 나갔네요",
             "★★★★☆",
             "결정적 실수 장면 + '왜 그 선택이었나' 해설 묶음으로 시청 유지 ↑"],
            ["태도·운영 비판",
             "프로답지 못한 마무리 / 시간 끌기 비매너 / 감정 기복이 너무 심해서",
             "★★★★☆",
             "논쟁 포인트 명확 → 조회 유입에 유리. 단, 브랜드 톤 세심 관리 필요"],
            ["응원·격려",
             "화이팅, 수고, 아쉽지만, 다음엔 우승",
             "★★☆☆☆",
             "팬덤 유지에 필요하나 반응 강도는 낮음. 승부 서사와 묶을 때 강화됨"],
            ["웃음·희화화",
             "ㅋㅋㅋㅋ오비에 뒷땅에 웃기다 / 레전드네 / 이걸 역전패하는것도",
             "★★★☆☆",
             "숏폼 유입 창구로 적합. 장기 브랜드 이미지에는 과도한 소비 주의"],
        ],
        col_widths=[0.14, 0.30, 0.14, 0.42],
    )
    story.append(KeepTogether([reaction_tbl]))
    story.append(vspace(5))

    # Bar charts side by side
    story.append(P("선수별 언급량 (댓글 기준)  vs  반응 유형별 좋아요 합계 추정",
                   STYLES["h3"]))
    story.append(vspace(2))

    fw = PW - 2 * M
    half = (fw - 6 * mm) / 2

    # Left: mention count per player
    mention_items = [("안예인", 16), ("이용희", 10), ("공태현", 9), ("고수진", 6)]
    mention_max = 20

    # Right: like-weight per theme
    like_items = [
        ("극적 반전·불신", 62),
        ("실수·멘탈 붕괴", 78),
        ("태도·운영 비판", 80),
        ("응원·격려", 35),
        ("웃음·희화화", 42),
    ]
    like_max = 90

    lbl_left = P("선수별 언급량", ParagraphStyle(
        "cl", fontName="KR-Bold", fontSize=8, textColor=BLUE,
        alignment=TA_CENTER))
    lbl_right = P("반응 유형별 좋아요 합계 (추정)", ParagraphStyle(
        "cr", fontName="KR-Bold", fontSize=8, textColor=ORANGE,
        alignment=TA_CENTER))

    def mini_bar(items, max_val, color, label_w_mm=28):
        lw = label_w_mm * mm
        bw = half - lw - 12 * mm
        vw = 12 * mm
        rows = []
        for lbl, val in items:
            fill = int(bw * val / max_val)
            empty = bw - fill
            bar = Table([[" ", " "]], colWidths=[fill or 1, empty or 1],
                        rowHeights=[8])
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), color),
                ("BACKGROUND", (1, 0), (1, 0), SLATE_MID),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))
            lp = Paragraph(lbl, ParagraphStyle(
                "mb", fontName="KR", fontSize=8, leading=11, textColor=BLACK,
                wordWrap="CJK"))
            vp = Paragraph(str(val), ParagraphStyle(
                "mv", fontName="KR-Bold", fontSize=7.5, textColor=GREY,
                alignment=TA_RIGHT))
            rows.append([lp, bar, vp])
        t = Table(rows, colWidths=[lw, bw, vw])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SLATE_LIGHT]),
        ]))
        return t

    left_block = Table([[lbl_left], [mini_bar(mention_items, mention_max, BLUE)]],
                       colWidths=[half])
    left_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    right_block = Table([[lbl_right], [mini_bar(like_items, like_max, ORANGE, 34)]],
                        colWidths=[half])
    right_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FFF7ED")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    charts = Table([[left_block, "", right_block]],
                   colWidths=[half, 6 * mm, half])
    charts.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(charts)
    story.append(vspace(3))
    story.append(note_box(
        "읽는 법: 언급량은 안예인이 가장 높지만, 반응 강도(좋아요 합산)는 "
        "'태도·운영 비판'과 '실수·멘탈 붕괴' 테마가 더 높습니다. "
        "'많이 말한 것'과 '강하게 반응한 것'은 다릅니다."
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 3 — Player-Level Insight
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("2.  선수·인물별 시청자 인식 분석")

    story.append(P(
        "같은 경기에서도 선수마다 시청자가 형성하는 서사는 전혀 다릅니다. "
        "아래는 원댓글 맥락을 읽어 추출한 인물별 인식 구조입니다.",
        STYLES["body"]))
    story.append(vspace(3))

    # 이용희
    story.append(KeepTogether([
        P("이용희  ·  하드캐리 + 침착함의 아이콘", STYLES["h3"]),
        rule(GREEN, 0.8),
        P(
            "버디를 잡고도 과도하게 기뻐하지 않는 <b>차분한 경기 운영</b>이 "
            "시청자에게 강한 인상을 남겼습니다. "
            "'<b>이용희 혼자 하드캐리 눈물겹다. 거의 2:1로 싸우는 느낌</b>' (9 likes), "
            "'<b>오늘 경기로 이용희 팬됐어요</b>' 같은 반응은 이번 경기를 계기로 "
            "신규 팬층이 유입됐음을 시사합니다. "
            "특히 <b>@이용희프로 본인 계정이 댓글 쓰레드에 직접 참여</b>해 "
            "'팀전은 못하면 둘다잘못, 잘하면 둘다잘한거'라고 답글을 달았습니다. "
            "이 행동 자체가 팬 신뢰도를 높이는 강력한 신호입니다.",
            STYLES["body"]),
        vspace(2),
        P("콘텐츠 기회:", STYLES["h3"]),
        bullet("'이용희 혼자 버틴 경기였나?' — 경기 흐름 복기 영상"),
        bullet("선수 본인이 댓글/팬 반응에 직접 반응하는 소통 포맷"),
        bullet("'역전승 당사자 이용희가 말하는 그날의 심리' 인터뷰형"),
        vspace(4),
    ]))

    # 공태현
    story.append(KeepTogether([
        P("공태현  ·  논란 + 부상 서사 + 팬 이탈 위기", STYLES["h3"]),
        rule(RED, 0.8),
        P(
            "가장 복잡한 인식 구조를 가진 선수입니다. "
            "비판 댓글은 두 레이어로 분리됩니다. "
            "첫째, <b>경기력 비판</b>: '이제 진짜 안되겠다' (15 likes), "
            "'왠만한 아마한테도 질 듯' (11 likes), '퍼터를 다 놓치네'. "
            "둘째, <b>태도·감정 기복 비판</b>: 최상위 좋아요 댓글(23 likes)이 "
            "굿샷 시 과도한 텐션과 OB 후 표정 급변을 날카롭게 지적했습니다. "
            "그러나 <b>부상 이후 상황에 대한 동정·이해 댓글</b>도 동시에 존재합니다. "
            "팬 이탈과 잔류가 동시에 진행 중입니다.",
            STYLES["body"]),
        vspace(2),
        P("콘텐츠 기회 (주의 필요):", STYLES["h3"]),
        bullet("'공태현 경기 운영, 왜 비판받았나 — 3가지 장면 복기' "
               "(논란을 회피하지 않고 정면 인정하는 포맷이 팬 신뢰 회복에 유리)"),
        bullet("부상 회복 과정 브이로그 — 감정 기복에 대한 직접 코멘트 포함"),
        bullet("<b>부정적 클립을 단독 Shorts로 올리는 것은 비권장</b> — "
               "복기·분석 맥락 없이 실수 장면만 부각하면 이미지 악화"),
        vspace(4),
    ]))

    # 안예인
    story.append(KeepTogether([
        P("안예인  ·  언급량 1위 + 이중 시청자층", STYLES["h3"]),
        rule(BLUE, 0.8),
        P(
            "안예인은 이번 경기에서 <b>언급량 최다(16회)</b>를 기록했지만, "
            "댓글은 두 개의 완전히 다른 시청자층에서 나왔습니다. "
            "첫째, <b>외모·패션 관심층</b>: '살 빠지니까 겁나 이쁘네', "
            "'가디건 브랜드는요?', '미모는 안예인이 우승'. "
            "둘째, <b>경기력 책임론</b>: '결정적으로 안예인이 오비 내면서 시작된 것' "
            "(답글 반박 포함), '안예인이 17번홀에서 왼쪽으로 자신있게 던졌나요?'. "
            "두 층 모두 콘텐츠 반응성은 높지만 성격이 전혀 다릅니다.",
            STYLES["body"]),
        vspace(2),
        P("콘텐츠 기회:", STYLES["h3"]),
        bullet("외모·패션 시청자층: 의상 협찬 노출, 비하인드 콘텐츠, 뷰티 관련 브랜드 협업"),
        bullet("경기력 시청자층: 17번홀 OB 상황 본인 해설 — 인정과 분석의 혼합"),
        bullet("'안예인 vs 공태현 — 누구 책임인가?' 논쟁 포맷은 조회는 나오지만 "
               "팬층 분열 가능성이 있어 <b>채널 톤 확인 후 판단 권장</b>"),
        vspace(4),
    ]))

    # 고수진
    story.append(KeepTogether([
        P("고수진  ·  신규 발견 + 성장 서사", STYLES["h3"]),
        rule(GREY, 0.8),
        P(
            "고수진은 처음 보는 시청자가 많았고 ('처음 보는데 이쁜데?', "
            "'고수진 귀여워' 9 likes), 긴장으로 인한 경기력 부진을 지적하는 댓글도 있었습니다. "
            "('애기네요', '긴장 너무 하셔서 실력이 안나오네'). "
            "이용희 본인이 '다음 경기는 수진이랑 더 좋은 팀워크 보여드릴게요'라고 "
            "직접 언급한 것은 <b>팀 서사 콘텐츠의 씨앗</b>입니다.",
            STYLES["body"]),
        bullet("고수진 소개/성장 콘텐츠는 타이밍이 좋습니다 — 이번 경기로 인지도가 생겼습니다"),
        vspace(2),
    ]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 4 — Emotional Patterns
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("3.  감정 패턴 분석")

    story.append(P(
        "자동 분류는 규칙 기반 어휘 매칭으로 감정을 5개 버킷으로 나눴습니다. "
        "아래는 원댓글 맥락을 추가로 검토해 보정한 실제 감정 구조입니다.",
        STYLES["body"]))
    story.append(vspace(3))

    emo_tbl = info_table(
        ["감정 유형", "주요 표현", "댓글 수\n(추정)", "마케팅 해석"],
        [
            ["극적 반전·경이",
             "이걸 뒤집네 / 기적이야 / 드라마네 / 끝까지 짜릿하네요",
             "~25개",
             "가장 강력한 감정 훅. 경기 전체를 '드라마'로 포장 가능"],
            ["비판·실망",
             "프로답지 못한 마무리 / 감정 기복이 너무 심해 / 이제 안되겠다",
             "~20개",
             "높은 좋아요. 논쟁성 콘텐츠로 조회 유입에 효과적이나 브랜드 리스크 존재"],
            ["응원·위로",
             "화이팅 / 수고하셨습니다 / 다음에 잘하면 된다",
             "~25개",
             "빈도 높으나 반응 강도 낮음. 커뮤니티 유지 기능으로 이해"],
            ["웃음·희화화",
             "ㅋㅋㅋㅋ오비에 뒷땅에 웃기다 / 레전드네 / 이걸 역전패",
             "~20개",
             "가벼운 소비 성격. Shorts 유입엔 유리하나 팬 이탈 촉진 가능"],
            ["전문적 분석·토론",
             "17번홀 오른쪽 OB 없는데 왜 / 격자 한 칸이 한 클럽 / 선수 선발 기준",
             "~10개",
             "소수지만 댓글 쓰레드를 이끄는 고관여층. 심층 분석 포맷 반응 가능성 ↑"],
        ],
        col_widths=[0.16, 0.30, 0.12, 0.42],
    )
    story.append(emo_tbl)
    story.append(vspace(4))

    story.append(callout(
        "<b>주요 수정 사항 (자동 분석 보정):</b> "
        "자동 요약은 지배적 감정을 '화이팅/응원'으로 분류했습니다. "
        "이는 ㅋㅋ·화이팅 같은 단어의 출현 빈도가 높기 때문입니다. "
        "그러나 좋아요 기준으로 보면 상위 5개 댓글(23, 19, 18, 15, 15 likes)은 "
        "모두 비판·실망·극적반전 계열입니다. "
        "<b>빈도와 감정 강도는 다릅니다.</b> "
        "콘텐츠 기획 시 '가장 많이 말해진 것'보다 '가장 강하게 반응된 것'을 우선하십시오."
    ))
    story.append(vspace(5))

    # 17번홀 callout
    story.append(P("전환점 분석: 17번홀이 경기를 바꿨다", STYLES["h3"]))
    story.append(rule(ORANGE, 0.8))
    story.append(P(
        "복수의 댓글이 <b>17번홀</b>을 구체적으로 지목했습니다. "
        "'오른쪽은 OB 없고 개넓은데, 굳이 왼쪽으로 가겠다고 고집부리다가 "
        "OB나고 뒷땅내고' — 이 묘사가 두 개 이상의 쓰레드에 반복 등장했습니다. "
        "한 댓글은 '최대 더블보기로 끝낼 것을 트리플까지 가네'라고 경기 운영을 분석했습니다. "
        "이는 시청자들이 <b>단순한 감정이 아니라 전술적 판단 실수</b>까지 짚어냈음을 의미합니다.",
        STYLES["body"]))
    story.append(vspace(2))
    story.append(note_box(
        "⚠ 주의: 댓글에는 영상 타임스탬프가 없습니다. '17번홀'이 몇 분대에 해당하는지는 "
        "영상과 수동 대조가 필요합니다. 타임스탬프 기반 반응 폭증 분석은 라이브채팅 로그가 있어야 정확합니다."
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 5 — Content Strategy
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("4.  콘텐츠 전략 시사점")

    story.append(callout(
        "<b>핵심 원칙:</b> 이번 경기에서 먹히는 포맷은 "
        "<b>하이라이트 단순 나열</b>이 아닙니다. "
        "시청자들은 결과를 넘어 <b>왜 그 선택이었나, 어디서 멘탈이 깨졌나, "
        "누가 팀을 이끌었나</b>를 알고 싶어 했습니다. "
        "'전환점 설명 + 감정선 + 선수 캐릭터'가 결합된 콘텐츠가 기회입니다."
    ))
    story.append(vspace(4))

    cs_tbl = info_table(
        ["우선순위", "추천 포맷", "근거 (댓글 시그널)", "실행 예시"],
        [
            ["1", "전환점 해설형 하이라이트",
             "'17번홀 이후 왜 흐름이 바뀌었나'를 묻는 댓글 다수. 결과보다 '왜'에 반응",
             "17번홀 OB — 왜 왼쪽을 선택했나? 3분 클립 + 해설"],
            ["2", "선수 캐릭터/서사 클립",
             "이용희=하드캐리·침착, 공태현=멘탈·논란으로 인식이 갈림",
             "'이용희 혼자 버텼나?' 편집 / '공태현 그날의 감정선' 복기"],
            ["3", "포맷·규정 토크 콘텐츠",
             "선수 선발 기준, 시간 지연 비매너, 인터벌 제한 제안 댓글 10 likes",
             "'선발 기준 바꿔야 하나?' / '경기 시간 제한 규정 필요한가?'"],
            ["4", "숏폼 감정선 컷",
             "OB·뒷땅·표정 변화 희화화 댓글이 18~23 likes 범위",
             "OB 장면 + 표정 변화 15~30초 / '장갑 벗기 전까지 모른다' 시리즈"],
            ["5", "이용희 팬 직접 소통",
             "@이용희프로 본인이 댓글에 직접 참여한 사실이 확인됨",
             "커뮤니티 포스트 Q&A / 팬댓글 선정 반응 영상"],
        ],
        col_widths=[0.08, 0.18, 0.38, 0.36],
    )
    story.append(KeepTogether([cs_tbl]))
    story.append(vspace(5))

    story += [P("피해야 할 것", STYLES["h3"]), rule(RED, 0.8)]
    avoid = [
        "실수 클립 단독 Shorts — 맥락 없이 실수만 부각하면 이미지 악화, "
        "특히 공태현 관련 부정 콘텐츠는 팬층 분열 가속",
        "ㅋㅋ·화이팅 키워드를 콘텐츠 주제로 직접 사용 — 자동 분석 아티팩트, "
        "전략적 가치 없음",
        "'안예인 vs 공태현 누구 책임?' 논쟁 포맷 — "
        "조회는 나오나 팀 분위기 및 선수 관계 훼손 가능성 있음",
        "라이브채팅 데이터 없이 '시점별 반응 폭증' 주장 — "
        "일반 댓글만으로는 어느 순간에 반응이 폭발했는지 정확히 말할 수 없음",
    ]
    for a in avoid:
        story.append(bullet(a))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 6 — Recommended Content + Titles
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("5.  즉시 테스트할 콘텐츠 아이디어")

    content_ideas = [
        ("1", "전체 영상",
         "왜 이 경기는 뒤집혔나 — 3개의 결정 장면으로 복기",
         "17번홀 OB / 뒷땅 / 퍼터 미스를 전술 해설과 함께 묶음"),
        ("2", "전체 영상",
         "이용희 혼자 버텼나? — 댓글로 본 하드캐리 서사",
         "팬 반응 + 경기 장면 + 본인 인터뷰 (있는 경우)"),
        ("3", "Shorts",
         "3타 차이를 한 홀에 날린 그 장면",
         "OB+뒷땅 장면 15~30초. 후킹용. '끝까지 모른다' 자막"),
        ("4", "전체 영상",
         "공태현 경기 운영, 왜 비판받았나 — 댓글이 지적한 3가지",
         "비판을 회피하지 않고 분석하는 포맷 → 팬 신뢰 회복 가능"),
        ("5", "토크/토론",
         "선수 선발 기준, 지금 방식이 맞나? 시청자 반응으로 본 개선안",
         "팬 참여 유도형. 포맷 논쟁 댓글 10+ likes 확인"),
        ("6", "커뮤니티",
         "이용희 프로가 직접 답한 댓글 모음",
         "@이용희프로 댓글 참여를 콘텐츠화. 팬 직접 소통 강화"),
        ("7", "Shorts",
         "골프는 장갑 벗기 전까지 모른다 — 멘탈이 갈린 순간 시리즈",
         "반전 경기 시리즈 포맷. 반복 사용 가능한 포맷 훅"),
        ("8", "Shorts / 시리즈",
         "댓글이 말하는 경기 — 시청자 반응 하이라이트 리캡",
         "게임 장면 + 댓글 오버레이 + 반응 편집 포맷. 하단 상세 기획안 참조 ↓"),
    ]

    for num, fmt, title, note in content_ideas:
        fmt_color = BLUE if "영상" in fmt else (ORANGE if "Shorts" in fmt else GREEN)
        fmt_p = Paragraph(fmt, ParagraphStyle(
            "fmtt", fontName="KR-Bold", fontSize=7.5, textColor=WHITE,
            alignment=TA_CENTER))
        num_p = Paragraph(num, ParagraphStyle(
            "idxn", fontName="KR-Bold", fontSize=11, textColor=BLUE,
            alignment=TA_CENTER, leading=16))
        title_p = Paragraph(title, ParagraphStyle(
            "itt", fontName="KR-Bold", fontSize=9, leading=14, textColor=BLACK,
            wordWrap="CJK"))
        note_p = Paragraph(note, ParagraphStyle(
            "itn", fontName="KR", fontSize=8.5, leading=13, textColor=GREY,
            wordWrap="CJK"))
        fw_ = PW - 2 * M
        row = Table(
            [[num_p,
              Table([[fmt_p]], colWidths=[14 * mm]),
              Table([[title_p], [note_p]], colWidths=[fw_ - 14 * mm - 12 * mm - 6 * mm])]],
            colWidths=[12 * mm, 17 * mm, fw_ - 12 * mm - 17 * mm],
        )
        row.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (1, 0), fmt_color),
            ("BACKGROUND", (0, 0), (0, 0), BLUE_LIGHT),
            ("BACKGROUND", (2, 0), (2, 0), WHITE),
            ("VALIGN",   (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",    (0, 0), (1, 0),   "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("GRID",     (0, 0), (-1, -1), 0.4, SLATE_MID),
        ]))
        story.append(row)
        story.append(vspace(1.5))

    story.append(vspace(4))
    story += section_heading("6.  제목·썸네일·카피 방향")
    title_tips = [
        "<b>제목:</b> 단순 결과보다 <b>역전, 붕괴, 멘탈, 하드캐리</b> 같은 전환 키워드 우선 사용.",
        "<b>썸네일:</b> 선수 얼굴 1~2명 + 감정선이 바로 보이는 문구. "
        "예: '이걸 뒤집네', '한 홀에 무너졌다', '혼자 버텼다'",
        "<b>커뮤니티 포스트·Shorts 소개:</b> 댓글 언어를 직접 차용해 참여 유도. "
        "예: '프로답지 못한 마무리였나?', '이용희 혼자 하드캐리?'",
        "<b>스폰서/브랜드 메시지:</b> 논란 클립보다 복기·분석형 콘텐츠에 붙이는 편이 안전.",
    ]
    for t in title_tips:
        story.append(bullet(t))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 7 — Marketing Angles + Top Comments
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("7.  마케팅·스폰서 각도")

    ma_tbl = info_table(
        ["각도", "근거", "적용 예시"],
        [
            ["역전 드라마 = 브랜드 연결고리",
             "시청자 다수가 '끝까지 모른다', '드라마', '기적'으로 반응",
             "'포기하지 않는 순간 — (브랜드명)처럼' 형식의 네이티브 광고"],
            ["이용희 침착함 이미지",
             "차분한 경기 운영이 신규 팬층 획득으로 이어짐",
             "클래식·침착함 이미지의 클럽·웨어 브랜드와 적합"],
            ["안예인 패션·뷰티 수요",
             "'가디건 브랜드는요?', 외모 관련 댓글 다수",
             "경기 중 착용 의상 정보 공개, 골프웨어·뷰티 협찬 노출"],
            ["포맷 논쟁 활용",
             "시간 지연, 선발 기준 댓글이 10 likes 이상",
             "대회 운영 개선 영상에 스폰서 연결 — 공정성 이미지 브랜드 적합"],
            ["고수진 신규 팬층",
             "처음 보는 시청자층의 호기심 댓글 다수",
             "신인·성장 스토리 형태의 협찬 콘텐츠 적합"],
        ],
        col_widths=[0.22, 0.40, 0.38],
    )
    story.append(KeepTogether([ma_tbl]))
    story.append(vspace(6))

    # Top comments
    story += section_heading("부록: 반응이 강했던 원댓글")
    story.append(P(
        "상위 좋아요 댓글은 '무엇이 논점이었는지'를 직접 보여줍니다. "
        "클립 셀렉션과 썸네일 문구의 출발점으로 활용하십시오.",
        STYLES["body"]))
    story.append(vspace(3))

    top_comments = [
        ("23", "@jkyo3054",
         "굿샷 나오면 텐션 올라가고 운동이라는 게 기세를 몰아가는거니까 화이팅 하는 건 좋은데, "
         "너무 다 이긴거처럼 나대는 감이 없지 않았음; 부담스러울 정도로 웃으면서 쌍따봉 계속 "
         "날리고 과하게 발랄하더니 오비 한 방에 얼굴 확 굳어서는.. 감정 기복이 너무 심해서;;"),
        ("19", "@화이팅-k1g",
         "ㅠㅠ 너무 프로답지못한 마무리네요"),
        ("18", "@jojomamarunline",
         "ㅋㅋㅋㅋㅋ오비에 뒷땅에ㅋㅋㅋ 웃기다"),
        ("15", "@상큼-q6i",
         "공태현은 이제 진짜 안되겠다"),
        ("15", "@Strawberrybro-79",
         "채팅창에서 공프로팀 시간 겁나 끈다고 했던게 다시보기하니 확실히 알겠네ㅎㅎ"),
        ("11", "@wownow22",
         "공태현은 왠만한 아마한테도 질듯.."),
        ("11", "@양수리전도단",
         "이용희 공태현 누굴 응원해야하나요 마음이 아파 못봅니다. "
         "고수진선수는 작년에는 그렇다치고 올해도 애기네요. 덕소에 최종환프로 찾아가서 "
         "볼스60까지 올리시고 송한백프로 찾아가서 스크린의 전체 기본 개념을 배우시길바랍니다."),
        ("10", "@락커래퍼",
         "선수 선발..팀조합을 평균 성적 조합으로 하는게 좋을듯"),
        ("9", "@yungjoonjo4913",
         "이용희 프로 혼자 하드캐리 눈물겹다. 거의 2:1로 싸우는 느낌."),
        ("9", "@jisungbba",
         "고수진 귀여워"),
    ]

    for likes, author, text in top_comments:
        for flowable in quote_card(likes, author, text):
            story.append(flowable)

    story.append(vspace(5))
    story += section_heading("분석 한계 및 주의사항")
    limits = [
        "<b>일반 댓글 전용:</b> 종료된 라이브채팅 리플레이는 공식 API만으로 안정적으로 수집하기 어렵습니다. "
        "시청 중 실시간 반응 폭증 패턴은 이번 분석에 포함되지 않았습니다.",
        "<b>타임스탬프 기반 분석 불가:</b> 일반 댓글에는 영상 타임스탬프가 없습니다. "
        "'17번홀'과 같은 장면 지목은 시청자 언급에서 나온 것으로, "
        "실제 영상 시점은 수동 대조가 필요합니다.",
        "<b>감정 분류의 한계:</b> 규칙 기반 어휘 매칭은 맥락, 반어, 복합 감정을 잡지 못합니다. "
        "이번 리포트는 원댓글을 추가로 수동 검토해 자동 분류 결과를 보정했습니다.",
        "<b>표본 규모:</b> 155개 댓글은 통계적으로 강한 결론을 내리기에는 소규모입니다. "
        "방향성과 트렌드 파악에는 유효하나, 수치를 절대치로 해석하지 마십시오.",
        "<b>한국어 형태소 분석:</b> 공백 기반 토큰화는 조사 결합어를 별도 토큰으로 처리합니다. "
        "정밀 한국어 분석이 필요한 경우 형태소 분석기(KoNLPy 등) 적용을 권장합니다.",
    ]
    for lim in limits:
        story.append(bullet(lim))

    return story


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    out = str(OUTPUT_DIR / "marketing_insight_report.pdf")
    print(f"Generating: {out}")
    doc = make_doc(out)
    story = build_story()
    doc.build(story)
    import os
    size_kb = os.path.getsize(out) / 1024
    print(f"Done: {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
