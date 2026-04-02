"""
댓글 중심 하이라이트 포맷 — 상세 기획안 PDF
2026 샤브20 GTOUR 슈퍼매치 YouTube Comment Analysis

Run:
    python generate_highlight_plan.py
Output:
    output/highlight_format_plan.pdf
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
    BaseDocTemplate, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

# ── Paths ──────────────────────────────────────────────────────────────────────
FONT_DIR = Path("fonts")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Font registration ──────────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont("KR",      str(FONT_DIR / "NanumGothic-Regular.ttf")))
pdfmetrics.registerFont(TTFont("KR-Bold", str(FONT_DIR / "NanumGothic-Bold.ttf")))
pdfmetrics.registerFontFamily("KR", normal="KR", bold="KR-Bold")

# ── Brand colours ──────────────────────────────────────────────────────────────
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
    "bullet":    S("blt", fontSize=9, leading=15, leftIndent=12, spaceAfter=3),
}


# ── Page template ──────────────────────────────────────────────────────────────

def make_doc(path: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        path,
        pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M + 8 * mm, bottomMargin=M + 8 * mm,
        title="댓글 중심 하이라이트 포맷 상세 기획안",
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
        canvas.drawString(M, PH - M - 1.5 * mm, "댓글 중심 하이라이트 포맷 — 상세 기획안")
        canvas.setFont("KR", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawRightString(PW - M, PH - M - 1.5 * mm,
                               "2026 샤브20 GTOUR 슈퍼매치")
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


def callout(text: str, accent=BLUE) -> Table:
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


# ── Document content ───────────────────────────────────────────────────────────

def build_story() -> list:
    P = Paragraph
    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story.append(vspace(6))
    story.append(P("댓글이 말하는 경기", STYLES["h1"]))
    story.append(P(
        "댓글 중심 하이라이트 포맷 — 상세 기획안<br/>"
        "2026 샤브20 GTOUR 슈퍼매치 &nbsp;·&nbsp; YouTube Comment Analysis",
        STYLES["subtitle"]))
    story.append(rule(BLUE_MID, 1.5))
    story.append(vspace(3))

    meta_data = [
        [P("분석 영상", STYLES["tag"]),
         P("2026 샤브20 GTOUR 슈퍼매치", STYLES["body_left"]),
         P("Video ID", STYLES["tag"]),
         P("Ef5fYM-WiPA", STYLES["body_left"])],
        [P("분석 댓글 수", STYLES["tag"]),
         P("155개 (상위 댓글 128 + 답글 27)", STYLES["body_left"]),
         P("생성일", STYLES["tag"]),
         P("2026-04-02", STYLES["body_left"])],
    ]
    fw = PW - 2 * M
    meta_tbl = Table(meta_data, colWidths=[fw * 0.18, fw * 0.32, fw * 0.18, fw * 0.32])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "KR"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("BACKGROUND",    (0, 0), (0, -1),  BLUE_LIGHT),
        ("BACKGROUND",    (2, 0), (2, -1),  BLUE_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_MID),
    ]))
    story.append(meta_tbl)
    story.append(vspace(5))
    story.append(callout(
        "이 문서는 YouTube 댓글 데이터를 기반으로 '댓글이 말하는 경기' Short/하이라이트 포맷의 "
        "전략적 가치, 편집 방법론, 시리즈 기획, 리스크 관리, 자동화 로드맵을 구체적으로 정리한 "
        "실행 기획서입니다. 마케팅 인사이트 리포트의 콘텐츠 아이디어 #8 확장본입니다."
    ))

    story.append(PageBreak())

    # ── PAGE 2: 전략적 가치 ────────────────────────────────────────────────────
    story += section_heading("1.  전략적 가치 — 왜 '댓글이 말하는 경기'인가?")

    story.append(callout(
        "댓글 = 시청자가 이미 편집한 하이라이트 목록\n\n"
        "상위 좋아요 댓글은 채널 운영자가 별도로 '명장면'을 선별할 필요 없이, "
        "시청자 스스로 가장 강렬하게 반응한 순간을 공개 투표 방식으로 정리해 놓은 데이터입니다. "
        "이 포맷은 그 데이터를 편집 자원으로 직접 사용합니다. "
        "시청자는 자신의 반응이 화면에 등장하는 경험을 통해 채널과의 유대감을 느끼며, "
        "댓글 참여율(신규 영상에 댓글을 남기는 비율)이 높아지는 플라이휠 효과가 생깁니다."
    ))
    story.append(vspace(4))

    story.append(KeepTogether([info_table(
        ["효과", "내용"],
        [
            ["시청자 참여 루프",
             "댓글이 콘텐츠에 반영 → 새 시청자가 댓글을 더 많이 작성 → 다음 영상 소재 자동 생성"],
            ["알고리즘 친화성",
             "Shorts 포맷은 노출 확장, 댓글 반응 오버레이는 자막으로 기능해 시청 완주율 상승"],
            ["제작 효율",
             "기존 경기 영상 클립 재사용 + 댓글 캡처 오버레이로 신규 촬영 없이 제작 가능"],
            ["팬 커뮤니티 형성",
             "댓글 작성자 닉네임 노출 → 커뮤니티 구성원 인정 경험 → 멤버십·후원 전환율 상승 기여"],
        ],
        col_widths=[0.25, 0.75],
    )]))

    story.append(PageBreak())

    # ── PAGE 3: 순간 유형 + 댓글 선정 기준 ───────────────────────────────────
    story += section_heading("2.  포착해야 할 순간 유형")

    story.append(KeepTogether([info_table(
        ["유형", "설명", "이번 영상 실제 예시"],
        [
            ["웃음·희화화",
             "실수·어이없는 상황에 ㅋㅋ 반응이 집중된 장면",
             "오비에 뒷땅 연속 — @jojomamarunline 「ㅋㅋㅋㅋㅋ오비에 뒷땅에ㅋㅋㅋ 웃기다」 (18 likes)"],
            ["극적 반전",
             "리드하던 팀·선수가 한 홀 만에 무너지거나 역전 당하는 순간",
             "17번홀 OB 연속 — 「끝날때까지 끝난게 아니다」 계열 댓글 다수"],
            ["감정 기복",
             "선수의 표정·행동 변화에 시청자가 직접 반응한 댓글",
             "「부담스러울 정도로 웃으면서 쌍따봉…오비 한 방에 얼굴 확 굳어서」 (23 likes)"],
            ["논쟁 포인트",
             "시청자 사이에서 의견이 갈리거나 문제 제기가 생긴 순간",
             "시간 지연 문제 — 「공프로팀 시간 겁나 끈다」 (15 likes), 인터벌 시간 제한 제안"],
            ["클러치·인상적 플레이",
             "어려운 상황에서 나온 좋은 샷에 긍정 반응이 모인 순간",
             "이용희 차분한 플레이 — 「혼자 하드캐리」 계열 응원 댓글"],
        ],
        col_widths=[0.18, 0.37, 0.45],
    )]))
    story.append(vspace(5))

    story += section_heading("3.  댓글 선정 기준 (4가지 필터)")

    story.append(KeepTogether([info_table(
        ["기준", "설명", "이번 영상 적용 예"],
        [
            ["좋아요 상위",
             "좋아요 10개 이상 댓글을 1차 후보로 설정 (이번 영상: 10개)",
             "23·19·18·15·15·12·11·11·10·9 likes 댓글"],
            ["감정 밀도",
             "단순 응원보다 구체적 묘사·비교·판단이 담긴 댓글 우선",
             "「감정 기복이 너무 심해서;;」처럼 서술이 긴 댓글"],
            ["대표성",
             "동일 반응을 가장 간결하게 표현한 댓글 (군집 중 1개 선택)",
             "OB 관련 댓글 중 반응을 가장 압축한 단일 표현"],
            ["맥락 독립성",
             "영상 없이 댓글만 봐도 상황이 짐작 가능한 텍스트",
             "「프로답지못한 마무리네요」 — 경기 결말을 압축"],
        ],
        col_widths=[0.18, 0.45, 0.37],
    )]))

    story.append(PageBreak())

    # ── PAGE 4: 편집 구조 + 시리즈 네이밍 ────────────────────────────────────
    story += section_heading("4.  편집 구조 — 5단계 흐름")

    story.append(KeepTogether([info_table(
        ["단계", "내용", "권장 길이"],
        [
            ["① Hook",
             "상위 좋아요 댓글 텍스트를 화면 중앙에 크게 띄움. 소리 없이 0.5초 정지 — 궁금증 유발",
             "3–5초"],
            ["② 경기 클립",
             "해당 댓글이 반응한 실제 게임플레이 장면 재생. 자막 없이 원음 유지",
             "8–15초"],
            ["③ 댓글 오버레이",
             "클립 위에 댓글 말풍선 형태로 등장. 닉네임 + 좋아요 수 포함. 폰트는 채널 브랜드 컬러",
             "3–5초"],
            ["④ 반응 컷",
             "추가 동의 댓글 2–3개 빠르게 순서대로 등장 (리액션 누적 효과)",
             "3–5초"],
            ["⑤ CTA",
             "「여러분의 생각은? 댓글로 남겨주세요」+ 구독/좋아요 버튼 애니메이션",
             "3초"],
        ],
        col_widths=[0.12, 0.65, 0.23],
    )]))
    story.append(vspace(5))

    story += section_heading("5.  Shorts 시리즈 네이밍 아이디어")

    naming_ideas = [
        "「댓글이 말했다」 시리즈 — 댓글 원문을 제목으로 그대로 차용. "
        "예: 「댓글이 말했다 — '프로답지 못한 마무리'」",
        "「시청자 판결」 시리즈 — 논쟁 포인트를 법정 판결처럼 프레이밍. 클릭률 자극.",
        "「N초 요약 + 댓글」 — 경기 핵심 장면 15초 + 상위 댓글 3개. 정보 밀도 극대화.",
        "「리액션 컷」 시리즈 — 감정 기복 장면에 특화. 선수 얼굴 변화와 댓글을 나란히 편집.",
        "에피소드 번호 없이 날짜+선수명으로 구분 — 알고리즘 검색 노출 극대화.",
    ]
    for ni in naming_ideas:
        story.append(bullet(ni))

    story.append(PageBreak())

    # ── PAGE 5: 리스크 + 자동화 워크플로우 ───────────────────────────────────
    story += section_heading("6.  리스크 및 주의사항")

    story.append(note_box(
        "⚠  편집 윤리 체크리스트\n\n"
        "• 희화화 금지: 실수 클립을 비하·조롱 목적으로 편집하지 마십시오. "
        "댓글의 ㅋㅋ 반응은 애정 어린 웃음이지, 공격이 아닙니다. "
        "편집 톤이 '같이 즐기는' 느낌을 유지해야 선수·팬 관계가 유지됩니다.\n\n"
        "• 맥락 절단 금지: 댓글을 오버레이할 때 그 댓글이 반응한 장면을 반드시 함께 보여주십시오. "
        "전후 맥락을 제거하면 오해를 일으키고 댓글 작성자에게도 피해가 됩니다.\n\n"
        "• 부정 댓글 사용 자제: 특정 선수를 겨냥한 비판 댓글(예: '공태현은 이제 진짜 안되겠다')은 "
        "채널 브랜드 이미지 및 선수와의 관계를 해칠 수 있으므로 Short 소재로는 피하십시오.\n\n"
        "• 댓글 작성자 허가: 공개 댓글이지만, 특정 닉네임을 부각하는 경우 사전 DM 확인을 권장합니다."
    ))
    story.append(vspace(5))

    story += section_heading("7.  자동화 가능성 및 워크플로우")

    story.append(note_box(
        "현재 데이터셋의 한계 — 타임스탬프 기반 자동화 불가\n\n"
        "이번 분석에 사용된 데이터는 YouTube Data API v3의 commentThreads.list로 수집한 "
        "일반 댓글(영상 하단 댓글)입니다. 이 데이터에는 '어느 시점에 작성됐는가'에 해당하는 "
        "영상 내 타임스탬프 정보가 포함되어 있지 않습니다.\n\n"
        "따라서 현재 수집 방식으로는 '좋아요 많은 댓글 → 해당 영상 구간 자동 검색 → 클립 자동 추출' "
        "파이프라인을 구현할 수 없습니다. 하이라이트 구간 매핑은 수동 검토가 필요합니다.\n\n"
        "타임스탬프 기반 자동화를 위해서는 실시간 채팅(live chat) 로그가 필요합니다. "
        "실시간 채팅은 발언 시각이 영상 재생 시점과 1:1로 연결되어 있어 반응 스파이크를 "
        "자동으로 감지할 수 있습니다. 다만 종료된 스트림의 라이브 채팅은 "
        "YouTube Data API v3 단독으로는 안정적으로 수집되지 않아 별도 도구가 필요합니다."
    ))
    story.append(vspace(4))

    story.append(KeepTogether([info_table(
        ["단계", "현재 (수동)", "미래 자동화 조건"],
        [
            ["하이라이트 구간 식별",
             "상위 좋아요 댓글을 수동으로 읽고 영상에서 해당 장면을 직접 찾아 타임코드 기록",
             "실시간 채팅 로그 수집 → 반응 스파이크 감지 → 타임코드 자동 추출"],
            ["댓글 후보 선정",
             "좋아요 순 CSV에서 수동 필터링 (맥락·톤 판단)",
             "현재 파이프라인으로 자동화 가능 (likes 임계값 설정)"],
            ["오버레이 제작",
             "영상 편집 툴(Premiere·DaVinci)에서 텍스트 레이어 수동 삽입",
             "After Effects 스크립트 또는 FFmpeg + Python으로 배치 처리 가능"],
            ["Shorts 업로드",
             "수동 업로드 + 제목·태그 직접 작성",
             "YouTube Data API v3 videos.insert로 자동 업로드 가능 (OAuth 인증 필요)"],
        ],
        col_widths=[0.22, 0.39, 0.39],
    )]))

    return story


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    out_path = str(OUTPUT_DIR / "highlight_format_plan.pdf")
    print(f"Generating: {out_path}")
    doc = make_doc(out_path)
    doc.build(build_story())
    size_kb = Path(out_path).stat().st_size // 1024
    print(f"Done: {out_path}  ({size_kb} KB)")
