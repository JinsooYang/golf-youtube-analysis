"""
Marketing Insight PDF — Demo (Condensed) Version
2026 샤브20 GTOUR 슈퍼매치

Run:
    python generate_report_demo.py
Output:
    output/marketing_insight_report_demo.pdf

Changes vs. full report
-----------------------
  Section 1  : 유지
  Section 2  : 선수별 핵심만 — 임팩트 카드 1장/인물
  Section 3  : 테이블 유지, 본문 축약
  Section 4  : 유지 (임팩트 강화)
  Section 5  : 5개만
  Section 6  : 유지
  Section 7  : 삭제
  부록       : 상위 5개만
  분석 한계  : 삭제
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

FONT_DIR  = Path("fonts")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

pdfmetrics.registerFont(TTFont("KR",      str(FONT_DIR / "NanumGothic-Regular.ttf")))
pdfmetrics.registerFont(TTFont("KR-Bold", str(FONT_DIR / "NanumGothic-Bold.ttf")))
pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR-Bold")

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


# ── Style helpers ──────────────────────────────────────────────────────────────

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
    "footer":    S("ft",  fontSize=7.5, textColor=GREY, alignment=TA_LEFT),
    "footer_r":  S("ftr", fontSize=7.5, textColor=GREY, alignment=TA_RIGHT),
    "tag":       S("tag", fontName="KR-Bold", fontSize=8, textColor=BLUE),
    "num_big":   S("nb",  fontName="KR-Bold", fontSize=28, leading=34,
                   textColor=BLUE, alignment=TA_CENTER),
    "num_label": S("nl",  fontSize=8, textColor=GREY, alignment=TA_CENTER),
    "bullet":    S("blt", fontSize=9, leading=15, leftIndent=12, spaceAfter=3),
}


# ── Page template ──────────────────────────────────────────────────────────────

def make_doc(path: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M + 8 * mm, bottomMargin=M + 8 * mm,
        title="유튜브 댓글 기반 마케팅 인사이트 리포트 (데모)",
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
        canvas.drawString(M, PH - M - 1.5 * mm, "YouTube 댓글 기반 마케팅 인사이트")
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawRightString(PW - M, PH - M - 1.5 * mm, "2026 샤브20 GTOUR 슈퍼매치")
        canvas.setStrokeColor(SLATE_MID)
        canvas.line(M, M + 5 * mm, PW - M, M + 5 * mm)
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


# ── Utility flowables ──────────────────────────────────────────────────────────

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

def stat_table(items: list) -> Table:
    n = len(items)
    w = (PW - 2 * M) / n
    data = [
        [Paragraph(str(v), STYLES["num_big"]) for _, v in items],
        [Paragraph(lbl,    STYLES["num_label"]) for lbl, _ in items],
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

def info_table(headers, rows, col_widths=None) -> Table:
    fw = PW - 2 * M
    if col_widths is None:
        col_widths = [fw / len(headers)] * len(headers)
    else:
        col_widths = [fw * r for r in col_widths]

    header_cells = [Paragraph(h, ParagraphStyle(
        "th", fontName="KR-Bold", fontSize=8.5, leading=13,
        textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK")) for h in headers]

    body_rows = [[
        Paragraph(str(c), ParagraphStyle(
            "td", fontName="KR", fontSize=8.5, leading=14,
            textColor=BLACK, wordWrap="CJK"))
        for c in row
    ] for row in rows]

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
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LINEBELOW",     (0, 0), (-1, 0),  1,   BLUE),
    ]))
    return t

def quote_card(likes: str, author: str, text: str, accent=BLUE):
    fw = PW - 2 * M
    likes_style = ParagraphStyle(
        "lk", fontName="KR-Bold", fontSize=11, textColor=accent,
        alignment=TA_CENTER, leading=16)
    likes_label = ParagraphStyle(
        "lkl", fontName="KR", fontSize=7.5, textColor=GREY, alignment=TA_CENTER)
    author_style = ParagraphStyle(
        "auth", fontName="KR-Bold", fontSize=8, textColor=GREY, leading=12)
    text_style = ParagraphStyle(
        "qt2", fontName="KR", fontSize=9, leading=15, textColor=SLATE,
        wordWrap="CJK", alignment=TA_JUSTIFY)

    left  = [[Paragraph(likes, likes_style), Paragraph("likes", likes_label)]]
    right = [[Paragraph(author, author_style)], [Paragraph(text, text_style)]]

    lw = 18 * mm
    rw = fw - lw - 3 * mm

    lt = Table(left, colWidths=[lw])
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
        ("VALIGN",          (0, 0), (-1, -1), "TOP"),
        ("GRID",            (0, 0), (-1, -1), 0.4, SLATE_MID),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 0),
        ("TOPPADDING",      (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 0),
    ]))
    return [outer, vspace(2)]

def callout(text: str, accent=BLUE) -> Table:
    data = [[Paragraph(text, ParagraphStyle(
        "cal", fontName="KR", fontSize=9, leading=15,
        textColor=BLACK, wordWrap="CJK", alignment=TA_JUSTIFY))]]
    t = Table(data, colWidths=[PW - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), BLUE_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0, 0), (-1, -1), 10),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0,0), (-1, -1), 8),
        ("LINEBEFORE",  (0, 0), (-1, -1), 3, accent),
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


# ── Section 2 helper: compact player card ─────────────────────────────────────

def player_card(
    name: str,
    tag: str,
    tag_color,
    signal: str,
    opportunities: list[str],
) -> Table:
    """
    One-row card per player:
        left  — name + tag label (accent bar)
        right — signal sentence + content bullet(s)
    """
    fw = PW - 2 * M
    lw = 44 * mm
    rw = fw - lw

    name_p = Paragraph(name, ParagraphStyle(
        "pn", fontName="KR-Bold", fontSize=11, leading=16,
        textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK"))
    tag_p = Paragraph(tag, ParagraphStyle(
        "pt", fontName="KR-Bold", fontSize=7.5, leading=11,
        textColor=WHITE, alignment=TA_CENTER, wordWrap="CJK"))

    left_inner = Table([[name_p], [tag_p]], colWidths=[lw])
    left_inner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), tag_color),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))

    signal_p = Paragraph(signal, ParagraphStyle(
        "ps", fontName="KR", fontSize=8.5, leading=14,
        textColor=SLATE, wordWrap="CJK"))

    opp_items = []
    for opp in opportunities:
        opp_items.append(Paragraph(
            f"→ {opp}",
            ParagraphStyle("po", fontName="KR", fontSize=8, leading=13,
                           textColor=BLACK, wordWrap="CJK", leftIndent=4)))

    right_content = [[signal_p]] + [[o] for o in opp_items]
    right_inner = Table(right_content, colWidths=[rw - 6 * mm])
    right_inner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("TOPPADDING",    (0, 0), (0, 0),   6),
        ("BOTTOMPADDING", (0, -1),(-1,-1),  6),
        ("TOPPADDING",    (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("LINEABOVE",     (0, 1), (-1, 1),  0.4, SLATE_MID),
    ]))

    card = Table([[left_inner, right_inner]], colWidths=[lw, rw])
    card.setStyle(TableStyle([
        ("VALIGN",          (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 0),
        ("TOPPADDING",      (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 0),
        ("GRID",            (0, 0), (-1, -1), 0.5, SLATE_MID),
    ]))
    return card


# ── Report content ─────────────────────────────────────────────────────────────

def build_story() -> list:
    story = []
    P = Paragraph

    # ═══════════════════════════════════════════════════════════
    # PAGE 1 — Cover / Executive Summary  (항목1 유지)
    # ═══════════════════════════════════════════════════════════
    story.append(P("유튜브 댓글 기반<br/>마케팅 인사이트 리포트", STYLES["h1"]))
    story.append(P(
        "2026 샤브20 GTOUR 슈퍼매치 &nbsp;·&nbsp; 시청자 반응에서 다음 콘텐츠 기회를 도출",
        STYLES["subtitle"]))
    story.append(rule(BLUE, 1.2))
    story.append(vspace(2))

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

    story.append(stat_table([
        ("전체 댓글 수", "155"), ("고유 작성자", "131"),
        ("총 좋아요", "367"), ("최대 좋아요", "23"),
    ]))
    story.append(vspace(6))

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

    for b in [
        "언급량 1위는 <b>안예인</b>이지만, 고좋아요 반응은 <b>공태현의 멘탈·태도 논란</b>과 "
        "<b>이용희의 하드캐리 서사</b>에 집중됐습니다.",
        "<b>17번홀 OB + 뒷땅</b>이 경기의 결정적 전환점. 이 장면은 클립 1순위입니다.",
        "<b>이용희 본인 계정(@이용희프로)</b>이 댓글 쓰레드에 직접 참여 — 팬 소통 콘텐츠 확장 시그널.",
        "다음 콘텐츠는 '누가 잘했나' 결과보다 "
        "<b>'왜 무너졌는가·어떻게 뒤집혔는가·누가 버텼는가'</b> 서사가 반응을 끌어낼 가능성이 큽니다.",
        "클립 선정 시 <b>브랜드 톤 관리</b> 필요 — 논란 클립보다 복기·분석형 포맷이 안전합니다.",
    ]:
        story.append(bullet(b))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 2 — Reaction Structure  (항목1 원본 유지)
    # ═══════════════════════════════════════════════════════════
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

    story.append(P("선수별 언급량 (댓글 기준)  vs  반응 유형별 좋아요 합계 추정",
                   STYLES["h3"]))
    story.append(vspace(2))

    half = (fw - 6 * mm) / 2

    mention_items = [("안예인", 16), ("이용희", 10), ("공태현", 9), ("고수진", 6)]
    like_items = [
        ("극적 반전·불신", 62), ("실수·멘탈 붕괴", 78),
        ("태도·운영 비판", 80), ("응원·격려", 35), ("웃음·희화화", 42),
    ]

    lbl_left  = P("선수별 언급량", ParagraphStyle(
        "cl", fontName="KR-Bold", fontSize=8, textColor=BLUE, alignment=TA_CENTER))
    lbl_right = P("반응 유형별 좋아요 합계 (추정)", ParagraphStyle(
        "cr", fontName="KR-Bold", fontSize=8, textColor=ORANGE, alignment=TA_CENTER))

    def mini_bar(items, max_val, color, label_w_mm=28):
        lw = label_w_mm * mm
        bw = half - lw - 12 * mm
        vw = 12 * mm
        rows = []
        for lbl, val in items:
            fill  = int(bw * val / max_val)
            empty = bw - fill
            bar = Table([[" ", " "]], colWidths=[fill or 1, empty or 1], rowHeights=[8])
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), color),
                ("BACKGROUND", (1, 0), (1, 0), SLATE_MID),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))
            rows.append([
                Paragraph(lbl, ParagraphStyle(
                    "mb", fontName="KR", fontSize=8, leading=11,
                    textColor=BLACK, wordWrap="CJK")),
                bar,
                Paragraph(str(val), ParagraphStyle(
                    "mv", fontName="KR-Bold", fontSize=7.5, textColor=GREY,
                    alignment=TA_RIGHT)),
            ])
        t = Table(rows, colWidths=[lw, bw, vw])
        t.setStyle(TableStyle([
            ("VALIGN",           (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",       (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",    (0, 0), (-1, -1), 3),
            ("LEFTPADDING",      (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",     (0, 0), (-1, -1), 0),
            ("ROWBACKGROUNDS",   (0, 0), (-1, -1), [WHITE, SLATE_LIGHT]),
        ]))
        return t

    left_block = Table([[lbl_left], [mini_bar(mention_items, 20, BLUE)]], colWidths=[half])
    left_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    right_block = Table([[lbl_right], [mini_bar(like_items, 90, ORANGE, 34)]], colWidths=[half])
    right_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FFF7ED")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    charts = Table([[left_block, "", right_block]], colWidths=[half, 6 * mm, half])
    charts.setStyle(TableStyle([
        ("VALIGN",          (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 0),
        ("TOPPADDING",      (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 0),
    ]))
    story.append(charts)
    story.append(vspace(3))
    story.append(note_box(
        "읽는 법: 언급량은 안예인이 가장 높지만, 반응 강도(좋아요 합산)는 "
        "'태도·운영 비판'과 '실수·멘탈 붕괴' 테마가 더 높습니다. "
        "'많이 말한 것'과 '강하게 반응한 것'은 다릅니다."
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 3 — Player Insight  (항목2: 선수별 임팩트 카드)
    # ═══════════════════════════════════════════════════════════
    story += section_heading("2.  선수·인물별 시청자 인식")
    story.append(vspace(2))

    players = [
        dict(
            name  = "이용희",
            tag   = "하드캐리 · 침착함의 아이콘",
            color = GREEN,
            signal = (
                "혼자 2:1로 싸우는 느낌 (9 likes) · 오늘 경기로 팬됐어요 · "
                "@이용희프로 본인이 댓글 쓰레드에 직접 답글 — 신규 팬 유입 시그널."
            ),
            opps = [
                "'이용희 혼자 버틴 경기였나?' 복기 영상",
                "본인이 팬 댓글에 반응하는 직접 소통 포맷",
                "'역전 당사자가 말하는 그날의 심리' 인터뷰",
            ],
        ),
        dict(
            name  = "공태현",
            tag   = "논란 + 팬 이탈 위기",
            color = RED,
            signal = (
                "최고 좋아요(23) 댓글이 감정 기복·OB 후 표정 급변을 지적. "
                "'이제 진짜 안되겠다'(15) · '왠만한 아마한테도 질 듯'(11). "
                "부상 동정 댓글도 공존 — 이탈과 잔류가 동시 진행."
            ),
            opps = [
                "'왜 비판받았나 — 3가지 장면 복기' (논란 정면 인정 포맷)",
                "부상 회복 브이로그 + 감정 기복 직접 코멘트",
                "⚠ 단독 실수 Shorts는 비권장 — 이미지 악화",
            ],
        ),
        dict(
            name  = "안예인",
            tag   = "언급량 1위 · 이중 시청자층",
            color = BLUE,
            signal = (
                "언급 16회로 최다. 외모·패션 관심층과 경기력 책임론이 완전히 분리. "
                "'가디건 브랜드는요?' vs '결정적으로 안예인이 OB 내면서 시작된 것'."
            ),
            opps = [
                "패션 시청자층: 의상 협찬·뷰티 브랜드 협업",
                "경기력 시청자층: 17번홀 OB 본인 해설 (인정+분석)",
                "⚠ vs 공태현 논쟁 포맷 — 팬층 분열 가능성, 채널 톤 확인 후 판단",
            ],
        ),
        dict(
            name  = "고수진",
            tag   = "신규 발견 · 성장 서사",
            color = GREY,
            signal = (
                "'처음 보는데 이쁜데?' · '고수진 귀여워'(9 likes). "
                "이용희 본인이 '다음 경기는 수진이랑 더 좋은 팀워크'라고 직접 언급 — "
                "팀 서사 콘텐츠의 씨앗."
            ),
            opps = [
                "소개/성장 콘텐츠 — 이번 경기로 인지도 생김, 타이밍 최적",
                "이용희-고수진 팀 서사 콘텐츠로 확장",
            ],
        ),
    ]

    for pd_ in players:
        story.append(KeepTogether([
            player_card(
                name         = pd_["name"],
                tag          = pd_["tag"],
                tag_color    = pd_["color"],
                signal       = pd_["signal"],
                opportunities= pd_["opps"],
            ),
            vspace(3),
        ]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 4 — Emotional Patterns  (항목3: 간결)
    # ═══════════════════════════════════════════════════════════
    story += section_heading("3.  감정 패턴 분석")
    story.append(vspace(2))

    emo_tbl = info_table(
        ["감정 유형", "주요 표현", "댓글 수", "마케팅 해석"],
        [
            ["극적 반전·경이",
             "이걸 뒤집네 / 드라마네 / 끝까지 짜릿하네요",
             "~25개",
             "가장 강력한 훅. 경기 전체를 '드라마'로 포장 가능"],
            ["비판·실망",
             "프로답지 못한 마무리 / 감정 기복 너무 심해 / 이제 안되겠다",
             "~20개",
             "높은 좋아요. 논쟁성 콘텐츠로 조회 유입 효과적, 단 브랜드 리스크"],
            ["응원·위로",
             "화이팅 / 수고하셨습니다 / 다음엔 잘하면 된다",
             "~25개",
             "빈도 높으나 반응 강도 낮음. 커뮤니티 유지 기능"],
            ["웃음·희화화",
             "ㅋㅋㅋㅋ오비에 뒷땅에 웃기다 / 레전드네",
             "~20개",
             "Shorts 유입 창구로 유리. 팬 이탈 촉진 가능성 주의"],
            ["전문 분석·토론",
             "17번홀 OB 없는데 왜 / 선수 선발 기준",
             "~10개",
             "소수지만 고관여층. 심층 분석 포맷 반응 가능성 ↑"],
        ],
        col_widths=[0.16, 0.30, 0.10, 0.44],
    )
    story.append(emo_tbl)
    story.append(vspace(4))

    story.append(callout(
        "<b>핵심 보정:</b> 자동 요약은 '화이팅/응원'을 지배적 감정으로 분류했지만, "
        "좋아요 기준 상위 5개 댓글(23·19·18·15·15 likes)은 <b>모두 비판·실망·극적반전 계열</b>입니다. "
        "<b>빈도 ≠ 감정 강도.</b> 콘텐츠 기획 시 '많이 말해진 것'보다 '강하게 반응된 것'을 우선하십시오."
    ))
    story.append(vspace(4))

    story.append(P("전환점: 17번홀이 경기를 바꿨다", STYLES["h3"]))
    story.append(rule(ORANGE, 0.8))
    for b in [
        "복수 쓰레드가 '오른쪽은 OB 없는데 굳이 왼쪽으로 고집부리다 OB·뒷땅'을 반복 지목.",
        "'최대 더블보기로 끝낼 것을 트리플까지' — 시청자들은 단순 감정이 아닌 <b>전술적 판단 실수</b>까지 짚었습니다.",
        "이 장면이 클립 1순위입니다.",
    ]:
        story.append(bullet(b))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 5 — Content Strategy  (항목4 유지, 임팩트 강화)
    # ═══════════════════════════════════════════════════════════
    story += section_heading("4.  콘텐츠 전략 시사점")

    story.append(callout(
        "<b>핵심 원칙:</b> 먹히는 포맷은 <b>하이라이트 단순 나열이 아닙니다.</b> "
        "시청자들은 결과를 넘어 <b>왜 그 선택이었나, 어디서 멘탈이 깨졌나, 누가 팀을 이끌었나</b>를 "
        "원했습니다. '전환점 설명 + 감정선 + 선수 캐릭터'가 결합된 콘텐츠가 기회입니다."
    ))
    story.append(vspace(4))

    cs_tbl = info_table(
        ["우선순위", "추천 포맷", "근거", "실행 예시"],
        [
            ["1", "전환점 해설형 하이라이트",
             "결과보다 '왜'에 반응 — '17번홀 이후 흐름이 바뀌었나' 댓글 다수",
             "17번홀 OB — 왜 왼쪽을 선택했나? 3분 클립 + 해설"],
            ["2", "선수 캐릭터·서사 클립",
             "이용희=하드캐리·침착 / 공태현=멘탈·논란으로 인식 선명하게 갈림",
             "'이용희 혼자 버텼나?' 편집 / '공태현 그날의 감정선' 복기"],
            ["3", "포맷·규정 토크",
             "선수 선발 기준·시간 지연·인터벌 댓글 10+ likes",
             "'선발 기준 바꿔야 하나?' / '경기 시간 제한 필요한가?'"],
            ["4", "숏폼 감정선 컷",
             "OB·뒷땅·표정 변화 희화화 댓글 18~23 likes",
             "OB + 표정 변화 15~30초 / '장갑 벗기 전까지 모른다' 시리즈"],
            ["5", "이용희 팬 직접 소통",
             "@이용희프로 본인이 댓글에 직접 참여 확인",
             "커뮤니티 포스트 Q&A / 팬댓글 선정 반응 영상"],
        ],
        col_widths=[0.08, 0.18, 0.38, 0.36],
    )
    story.append(KeepTogether([cs_tbl]))
    story.append(vspace(5))

    story += [P("피해야 할 것", STYLES["h3"]), rule(RED, 0.8)]
    for a in [
        "<b>실수 클립 단독 Shorts</b> — 맥락 없이 실수만 부각하면 이미지 악화. 공태현 부정 클립 특히 주의.",
        "<b>ㅋㅋ·화이팅 키워드를 콘텐츠 주제로 직접 사용</b> — 자동 분석 아티팩트, 전략적 가치 없음.",
        "<b>'안예인 vs 공태현 누구 책임?' 논쟁 포맷</b> — 조회는 나오나 선수 관계·팀 분위기 훼손 가능.",
        "<b>라이브채팅 없이 '시점별 반응 폭증' 주장</b> — 일반 댓글만으로는 정확히 말할 수 없음.",
    ]:
        story.append(bullet(a))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 6 — Content Ideas (항목5: 5개만) + Titles (항목6 유지)
    # ═══════════════════════════════════════════════════════════
    story += section_heading("5.  즉시 테스트할 콘텐츠 아이디어")

    content_ideas_5 = [
        ("1", "전체 영상",
         "왜 이 경기는 뒤집혔나 — 3개의 결정 장면으로 복기",
         "17번홀 OB / 뒷땅 / 퍼터 미스를 전술 해설과 함께 묶음"),
        ("2", "전체 영상",
         "이용희 혼자 버텼나? — 댓글로 본 하드캐리 서사",
         "팬 반응 + 경기 장면 + 본인 인터뷰 (있는 경우)"),
        ("3", "Shorts",
         "3타 차이를 한 홀에 날린 그 장면",
         "OB+뒷땅 15~30초. 후킹용. '끝까지 모른다' 자막"),
        ("4", "전체 영상",
         "공태현 경기 운영, 왜 비판받았나 — 댓글이 지적한 3가지",
         "비판 회피 없이 분석하는 포맷 → 팬 신뢰 회복 가능"),
        ("5", "커뮤니티",
         "이용희 프로가 직접 답한 댓글 모음",
         "@이용희프로 댓글 참여를 콘텐츠화. 팬 직접 소통 강화"),
    ]

    for num, fmt, title, note in content_ideas_5:
        fmt_color = BLUE if "영상" in fmt else (ORANGE if "Shorts" in fmt else GREEN)
        fw_ = PW - 2 * M
        row = Table(
            [[Paragraph(num, ParagraphStyle(
                "idxn", fontName="KR-Bold", fontSize=11, textColor=BLUE,
                alignment=TA_CENTER, leading=16)),
              Table([[Paragraph(fmt, ParagraphStyle(
                  "fmtt", fontName="KR-Bold", fontSize=7.5, textColor=WHITE,
                  alignment=TA_CENTER))]], colWidths=[14 * mm]),
              Table([[Paragraph(title, ParagraphStyle(
                  "itt", fontName="KR-Bold", fontSize=9, leading=14,
                  textColor=BLACK, wordWrap="CJK"))],
                     [Paragraph(note, ParagraphStyle(
                  "itn", fontName="KR", fontSize=8.5, leading=13,
                  textColor=GREY, wordWrap="CJK"))]],
                    colWidths=[fw_ - 14 * mm - 12 * mm - 6 * mm])]],
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

    story.append(vspace(5))

    # 항목6: 제목·썸네일·카피 방향 (유지)
    story += section_heading("6.  제목·썸네일·카피 방향")
    for t in [
        "<b>제목:</b> 단순 결과보다 <b>역전, 붕괴, 멘탈, 하드캐리</b> 같은 전환 키워드 우선 사용.",
        "<b>썸네일:</b> 선수 얼굴 1~2명 + 감정선이 바로 보이는 문구. "
        "예: '이걸 뒤집네', '한 홀에 무너졌다', '혼자 버텼다'",
        "<b>커뮤니티 포스트·Shorts 소개:</b> 댓글 언어를 직접 차용해 참여 유도. "
        "예: '프로답지 못한 마무리였나?', '이용희 혼자 하드캐리?'",
        "<b>스폰서/브랜드 메시지:</b> 논란 클립보다 복기·분석형 콘텐츠에 붙이는 편이 안전.",
    ]:
        story.append(bullet(t))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════
    # PAGE 7 — Top 5 Comments  (부록: 5개만, 7·분석한계 삭제)
    # ═══════════════════════════════════════════════════════════
    story += section_heading("부록: 반응이 강했던 원댓글 TOP 5")
    story.append(P(
        "상위 좋아요 댓글은 무엇이 논점이었는지를 직접 보여줍니다. "
        "클립 셀렉션과 썸네일 문구의 출발점으로 활용하십시오.",
        STYLES["body"]))
    story.append(vspace(3))

    top5 = [
        ("23", "@jkyo3054",
         "굿샷 나오면 텐션 올라가고 화이팅 하는 건 좋은데, 너무 다 이긴거처럼 나대는 감이 없지 않았음; "
         "부담스러울 정도로 웃으면서 쌍따봉 계속 날리고 과하게 발랄하더니 "
         "오비 한 방에 얼굴 확 굳어서는.. 감정 기복이 너무 심해서;;"),
        ("19", "@화이팅-k1g",
         "ㅠㅠ 너무 프로답지못한 마무리네요"),
        ("18", "@jojomamarunline",
         "ㅋㅋㅋㅋㅋ오비에 뒷땅에ㅋㅋㅋ 웃기다"),
        ("15", "@상큼-q6i",
         "공태현은 이제 진짜 안되겠다"),
        ("15", "@Strawberrybro-79",
         "채팅창에서 공프로팀 시간 겁나 끈다고 했던게 다시보기하니 확실히 알겠네ㅎㅎ"),
    ]

    for likes, author, text in top5:
        for flowable in quote_card(likes, author, text):
            story.append(flowable)

    return story


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    out = str(OUTPUT_DIR / "marketing_insight_report_demo.pdf")
    print(f"Generating: {out}")
    doc = make_doc(out)
    story = build_story()
    doc.build(story)
    import os
    size_kb = os.path.getsize(out) / 1024
    print(f"Done: {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
