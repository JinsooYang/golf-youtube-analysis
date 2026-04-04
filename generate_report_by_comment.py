"""
Comment-based Marketing Insight PDF Report

Input files (all from output/):
  - comments_cleaned.csv
  - analysis_summary.md
  - top_keywords.csv
  - top_authors.csv
  - highlight_package.json  (optional)

Run: python generate_report_by_comment.py
Output: output/comment_insight_report.pdf
"""

import csv, json, re
from report_utils import *   # imports all shared utilities


# ── Data loader ───────────────────────────────────────────────────────────────

def load_data() -> dict:
    """Load all report inputs from output/ files. No external arguments needed."""
    d: dict = {}

    # 1. comments_cleaned.csv ─────────────────────────────────────────────────
    comments: list = []
    comments_path = OUTPUT_DIR / "comments_cleaned.csv"
    if comments_path.exists():
        with open(comments_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row["like_count"] = int(row.get("like_count") or 0)
                row["is_reply"]   = row.get("is_reply", "False") == "True"
                comments.append(row)

    top_level = [c for c in comments if not c["is_reply"]]
    replies   = [c for c in comments if c["is_reply"]]
    d["comments"]        = comments
    d["top_level_count"] = len(top_level)
    d["reply_count"]     = len(replies)
    d["total_comments"]  = len(comments)
    d["unique_authors"]  = len({c["author"] for c in comments})
    d["total_likes"]     = sum(c["like_count"] for c in comments)
    d["max_likes"]       = max((c["like_count"] for c in comments), default=0)
    d["video_id"]        = comments[0]["video_id"]  if comments else ""
    d["video_url"]       = comments[0]["video_url"] if comments else ""
    d["top_comments"]    = sorted(comments, key=lambda c: c["like_count"], reverse=True)[:10]

    # 2. analysis_summary.md ──────────────────────────────────────────────────
    d["generated_date"]     = ""
    d["dominant_sentiment"] = ""
    d["recommendations"]    = []
    d["themes"]             = []
    d["marketing_angles"]   = []
    d["limitations"]        = []
    d["sentiment_rows"]     = []

    summary_path = OUTPUT_DIR / "analysis_summary.md"
    if summary_path.exists():
        txt = summary_path.read_text(encoding="utf-8")

        m = re.search(r"\*\*Generated:\*\*\s*(.+?)(?:\n|$)", txt)
        if m:
            d["generated_date"] = m.group(1).strip()

        m = re.search(r"\*\*Dominant emotional tone:\*\*\s*`([^`]+)`", txt)
        if m:
            d["dominant_sentiment"] = m.group(1)

        sec = re.search(
            r"## Content Strategy Recommendations\n(.*?)(?=\n## |\Z)", txt, re.DOTALL)
        if sec:
            recs = re.findall(
                r"\*\*\d+\.\*\*\s*(.*?)(?=\n\n\*\*\d+\.\*\*|\n\n##|\Z)",
                sec.group(1), re.DOTALL)
            d["recommendations"] = [r.strip().replace("\n", " ") for r in recs]

        sec = re.search(
            r"## High-Engagement Themes\n.*?\n((?:- `[^`]+`\n?)+)", txt)
        if sec:
            d["themes"] = re.findall(r"`([^`]+)`", sec.group(1))

        sec = re.search(
            r"## Marketing & Monetization Angles\n(.*?)(?=\n## |\Z)", txt, re.DOTALL)
        if sec:
            d["marketing_angles"] = [
                a.strip().replace("\n", " ")
                for a in re.findall(
                    r"^- (.+?)(?=\n-|\Z)", sec.group(1), re.DOTALL | re.MULTILINE)
                if a.strip()
            ]

        sec = re.search(
            r"## Limitations & Scope Notes\n(.*?)(?=\n## |\Z)", txt, re.DOTALL)
        if sec:
            d["limitations"] = [
                l.strip().replace("\n", " ")
                for l in re.findall(
                    r"^- (.+?)(?=\n-|\Z)", sec.group(1), re.DOTALL | re.MULTILINE)
                if l.strip()
            ]

        d["sentiment_rows"] = re.findall(
            r"\| ([^|\-][^|]+?) \| (\d+) \| ([\d.]+%) \|", txt)

    # 3. top_keywords.csv ─────────────────────────────────────────────────────
    d["unigrams"] = []
    d["bigrams"]  = []
    kw_path = OUTPUT_DIR / "top_keywords.csv"
    if kw_path.exists():
        with open(kw_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row["count"] = int(row.get("count") or 0)
                if row.get("type") == "bigram":
                    d["bigrams"].append(row)
                else:
                    d["unigrams"].append(row)

    # 4. top_authors.csv ──────────────────────────────────────────────────────
    d["top_authors"] = []
    auth_path = OUTPUT_DIR / "top_authors.csv"
    if auth_path.exists():
        with open(auth_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row["comment_count"] = int(row.get("comment_count") or 0)
                row["total_likes"]   = int(row.get("total_likes")   or 0)
                d["top_authors"].append(row)

    # 5. highlight_package.json (optional) ────────────────────────────────────
    d["title_suggestions"]  = []
    d["shorts_sequences"]   = []
    d["highlight_comments"] = []
    hp_path = OUTPUT_DIR / "highlight_package.json"
    if hp_path.exists():
        hp = json.loads(hp_path.read_text(encoding="utf-8"))
        mp = hp.get("master_plan") or {}
        if isinstance(mp, dict):
            d["title_suggestions"] = mp.get("title_suggestions", [])
        d["shorts_sequences"] = hp.get("shorts_sequences", [])
        d["highlight_comments"] = sorted(
            hp.get("highlight_comments", []),
            key=lambda c: c.get("likes", 0), reverse=True)

    return d


# ── Report content ────────────────────────────────────────────────────────────

def build_story() -> list:
    story = []
    P = Paragraph
    d = load_data()

    # ═══════════════════════════════════════════════════════════════
    # PAGE 1 — Cover / Executive Summary
    # ═══════════════════════════════════════════════════════════════
    story.append(P("유튜브 댓글 기반<br/>마케팅 인사이트 리포트", STYLES["h1"]))
    story.append(P(
        f"Video: {d['video_id'] or '—'}"
        " &nbsp;·&nbsp; 시청자 반응에서 다음 콘텐츠 기회를 도출",
        STYLES["subtitle"]))
    story.append(rule(BLUE, 1.2))
    story.append(vspace(2))

    # Meta table
    fw = PW - 2 * M
    meta = Table([
        [P("Video ID", STYLES["tag"]),
         P(d["video_id"] or "—", STYLES["body_left"]),
         P("URL", STYLES["tag"]),
         P(d["video_url"] or "—", STYLES["body_left"])],
        [P("데이터 범위", STYLES["tag"]),
         P(f"일반 댓글 {d['top_level_count']}개 + 답글 {d['reply_count']}개",
           STYLES["body_left"]),
         P("생성일", STYLES["tag"]),
         P(d["generated_date"] or "—", STYLES["body_left"])],
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
        ("전체 댓글 수", str(d["total_comments"])),
        ("고유 작성자",  str(d["unique_authors"])),
        ("총 좋아요",    str(d["total_likes"])),
        ("최대 좋아요",  str(d["max_likes"])),
    ]))
    story.append(vspace(6))

    # Executive summary
    story += section_heading("핵심 요약")
    if d["dominant_sentiment"]:
        story.append(callout(
            f"<b>주도적 감정 톤:</b> <b>{d['dominant_sentiment']}</b> — "
            "아래 고좋아요 댓글과 키워드 데이터를 함께 검토해 "
            "실제 감정 강도를 확인하십시오. "
            "<b>빈도(언급 수)와 감정 강도(좋아요 수)는 다를 수 있습니다.</b>"
        ))
        story.append(vspace(3))

    if d["themes"]:
        story.append(P("고관여 테마 (좋아요 비례 상위 등장)", STYLES["h3"]))
        for theme in d["themes"]:
            story.append(bullet(f"<b>{theme}</b>"))
        story.append(vspace(3))

    if d["recommendations"]:
        story.append(P("콘텐츠 전략 핵심", STYLES["h3"]))
        for rec in d["recommendations"][:3]:
            story.append(bullet(rec))
        story.append(vspace(3))

    story.append(note_box(
        "⚠ 이 리포트는 <b>일반 댓글만</b> 분석했습니다. "
        "라이브채팅 리플레이는 공식 API만으로 안정적으로 수집하기 어렵습니다. "
        "시점별 반응 폭증 분석은 라이브채팅 로그 확보 후 별도 진행이 필요합니다."
    ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 2 — Keywords & Author Analysis
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("1.  키워드 분석")

    if d["unigrams"]:
        top_uni = d["unigrams"][:8]
        uni_items = [(row["phrase"], row["count"]) for row in top_uni]
        story.append(P("단어 빈도 상위 8위", STYLES["h3"]))
        story.append(vspace(1))
        story.append(bar_chart(uni_items, top_uni[0]["count"], BLUE))
        story.append(vspace(4))

    if d["bigrams"]:
        story.append(P("구문 빈도 상위 (2단어 구)", STYLES["h3"]))
        story.append(vspace(1))
        story.append(info_table(
            ["구문", "빈도"],
            [(row["phrase"], str(row["count"])) for row in d["bigrams"][:8]],
            col_widths=[0.75, 0.25],
        ))
        story.append(vspace(5))

    # Sentiment breakdown
    if d["sentiment_rows"]:
        story += section_heading("2.  감정 분류 현황")
        story.append(info_table(
            ["감정 유형", "댓글 수", "비율"],
            [(r[0], r[1], r[2]) for r in d["sentiment_rows"]],
            col_widths=[0.50, 0.25, 0.25],
        ))
        story.append(vspace(3))
        if d["dominant_sentiment"]:
            story.append(callout(
                f"<b>지배적 감정:</b> {d['dominant_sentiment']} — "
                "자동 분류는 어휘 빈도 기반입니다. "
                "상위 좋아요 댓글을 직접 확인해 실제 반응 강도를 검증하십시오."
            ))
        story.append(vspace(4))

    # Top authors
    if d["top_authors"]:
        story += section_heading("3.  주요 작성자")
        story.append(info_table(
            ["작성자", "댓글 수", "총 좋아요"],
            [(row["author"], str(row["comment_count"]), str(row["total_likes"]))
             for row in d["top_authors"][:10]],
            col_widths=[0.55, 0.225, 0.225],
        ))

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 3 — Top Comments
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("4.  반응이 강했던 원댓글")
    story.append(P(
        "상위 좋아요 댓글은 '무엇이 논점이었는지'를 직접 보여줍니다. "
        "클립 셀렉션과 썸네일 문구의 출발점으로 활용하십시오.",
        STYLES["body"]))
    story.append(vspace(3))

    for c in d["top_comments"]:
        for flowable in quote_card(str(c["like_count"]), c["author"], c["text"]):
            story.append(flowable)

    story.append(PageBreak())

    # ═══════════════════════════════════════════════════════════════
    # PAGE 4 — Content Strategy + Titles + Shorts + Limitations
    # ═══════════════════════════════════════════════════════════════
    story += section_heading("5.  콘텐츠 전략 시사점")

    if d["recommendations"]:
        for i, rec in enumerate(d["recommendations"], 1):
            story.append(P(f"{i}.&nbsp; {rec}", STYLES["body_left"]))
            story.append(vspace(1))
        story.append(vspace(3))

    if d["title_suggestions"]:
        story += section_heading("6.  추천 영상 제목")
        for ts in d["title_suggestions"]:
            story.append(bullet(ts))
        story.append(vspace(4))

    if d["shorts_sequences"]:
        story += section_heading("7.  Shorts 기획안")
        for s in d["shorts_sequences"]:
            story.append(KeepTogether([
                P(s["title"], STYLES["h3"]),
                P(s.get("description", ""), STYLES["body"]),
                vspace(2),
            ]))
        story.append(vspace(3))

    if d["marketing_angles"]:
        story += section_heading("8.  마케팅·스폰서 각도")
        for angle in d["marketing_angles"]:
            story.append(bullet(angle))
        story.append(vspace(4))

    story += section_heading("분석 한계 및 주의사항")
    if d["limitations"]:
        for lim in d["limitations"]:
            story.append(bullet(lim))
    else:
        for fallback in [
            "<b>일반 댓글 전용:</b> 라이브채팅 리플레이는 이번 분석에 포함되지 않았습니다.",
            "<b>타임스탬프 없음:</b> 일반 댓글에는 영상 타임스탬프가 없습니다.",
            "<b>감정 분류 한계:</b> 규칙 기반 어휘 매칭은 반어, 복합 감정을 잡지 못합니다.",
        ]:
            story.append(bullet(fallback))

    return story


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    out = str(OUTPUT_DIR / "comment_insight_report.pdf")
    print(f"Generating: {out}")
    doc = make_doc(out)
    story = build_story()
    doc.build(story)
    import os
    size_kb = os.path.getsize(out) / 1024
    print(f"Done: {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
