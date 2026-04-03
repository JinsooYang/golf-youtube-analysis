"""
writer.py — Write all highlight pipeline outputs to disk.

Output files:
  highlight_comment_candidates.csv   — per-comment flat table
  highlight_comment_candidates.json  — same data as JSON array
  highlight_moment_candidates.csv    — segment-level aggregation
  highlight_package.json             — full nested package (all data)
  shorts_script.md                   — human-readable Shorts editing brief
  master_highlight_plan.json         — full master highlight plan (JSON)
  master_highlight_script.md         — human-readable master highlight brief

All paths are relative to output_dir.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# CSV column order for comment candidates
_COMMENT_CSV_COLS = [
    "comment_id", "source_type", "text", "likes", "author",
    "category", "emotion_strength", "priority_score",
    "related_player_names", "suggested_caption", "recommended_usage",
    "matched_segment_id", "matched_start", "matched_end",
    "matching_confidence", "needs_manual_timestamp_mapping",
    "match_signals", "editor_notes",
]

# CSV column order for moment candidates
_MOMENT_CSV_COLS = [
    "moment_id", "segment_id", "start", "end", "segment_text",
    "matched_comment_count", "total_likes", "max_priority_score",
    "dominant_category", "player_names", "event_keywords",
    "reaction_intensity", "best_matching_confidence",
    "recommended_clip_usage", "top_comment_text", "top_comment_likes",
    "needs_manual_verification", "editor_notes",
]

# CSV column order for spike moments
_SPIKE_CSV_COLS = [
    "anchor_time", "window_start", "window_end",
    "message_count", "weighted_score",
]


def write_outputs(package: dict, output_dir: str | Path) -> dict[str, Path]:
    """
    Write all output files from a highlight package.

    Returns a dict mapping file role → absolute Path of written file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    written["comment_csv"]      = _write_comment_csv(package, out)
    written["comment_json"]     = _write_comment_json(package, out)
    written["moment_csv"]       = _write_moment_csv(package, out)
    written["spike_csv"]        = _write_spike_moments_csv(package, out)
    written["package_json"]     = _write_package_json(package, out)
    written["shorts_script"]    = _write_shorts_script(package, out)
    written["master_plan_json"] = _write_master_plan_json(package, out)
    written["master_script"]    = _write_master_script(package, out)

    return written


# ── Individual writers ─────────────────────────────────────────────────────────

def _write_comment_csv(package: dict, out: Path) -> Path:
    path = out / "highlight_comment_candidates.csv"
    rows = package.get("highlight_comments", [])
    if not rows:
        _write_empty(path)
        return path

    df = pd.DataFrame(rows)
    # Keep only defined columns (add missing as empty)
    for col in _COMMENT_CSV_COLS:
        if col not in df.columns:
            df[col] = ""
    df[_COMMENT_CSV_COLS].to_csv(path, index=False, encoding="utf-8")
    logger.info("wrote %d comment candidates → %s", len(df), path)
    return path


def _write_comment_json(package: dict, out: Path) -> Path:
    path = out / "highlight_comment_candidates.json"
    rows = package.get("highlight_comments", [])
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("wrote %d comment candidates → %s", len(rows), path)
    return path


def _write_moment_csv(package: dict, out: Path) -> Path:
    path = out / "highlight_moment_candidates.csv"
    rows = package.get("highlight_moments", [])
    if not rows:
        _write_empty(path)
        return path

    df = pd.DataFrame(rows)
    for col in _MOMENT_CSV_COLS:
        if col not in df.columns:
            df[col] = ""
    df[_MOMENT_CSV_COLS].to_csv(path, index=False, encoding="utf-8")
    logger.info("wrote %d moment candidates → %s", len(df), path)
    return path


def _write_spike_moments_csv(package: dict, out: Path) -> Path:
    path = out / "spike_moments.csv"
    rows = package.get("spike_moments", [])
    if not rows:
        _write_empty(path)
        return path

    # Flatten: drop top_messages list (too complex for CSV), keep scalar fields
    flat = [
        {k: v for k, v in row.items() if k != "top_messages"}
        for row in rows
    ]
    df = pd.DataFrame(flat)
    for col in _SPIKE_CSV_COLS:
        if col not in df.columns:
            df[col] = ""
    # Include any extra scalar columns beyond the fixed set
    all_cols = _SPIKE_CSV_COLS + [c for c in df.columns if c not in _SPIKE_CSV_COLS]
    df[all_cols].to_csv(path, index=False, encoding="utf-8")
    logger.info("wrote %d spike moments → %s", len(df), path)
    return path


def _write_package_json(package: dict, out: Path) -> Path:
    path = out / "highlight_package.json"
    path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("wrote highlight_package.json → %s", path)
    return path


def _write_shorts_script(package: dict, out: Path) -> Path:
    path = out / "shorts_script.md"
    md = _build_shorts_script_md(package)
    path.write_text(md, encoding="utf-8")
    logger.info("wrote shorts_script.md → %s", path)
    return path


def _write_master_plan_json(package: dict, out: Path) -> Path:
    path = out / "master_highlight_plan.json"
    plan = package.get("master_plan") or {}
    path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("wrote master_highlight_plan.json → %s", path)
    return path


def _write_master_script(package: dict, out: Path) -> Path:
    path = out / "master_highlight_script.md"
    md = _build_master_script_md(package)
    path.write_text(md, encoding="utf-8")
    logger.info("wrote master_highlight_script.md → %s", path)
    return path


# ── Markdown script builder ────────────────────────────────────────────────────

def _build_shorts_script_md(package: dict) -> str:
    meta         = package.get("meta", {})
    comments     = package.get("highlight_comments", [])
    moments      = package.get("highlight_moments", [])
    spike_moments = package.get("spike_moments", [])
    sequences    = package.get("shorts_sequences", [])

    video_id         = meta.get("video_id", "")
    video_title      = meta.get("video_title", "")
    has_chat         = meta.get("has_live_chat", False)
    lc_timing_mode   = meta.get("live_chat_timing_mode", False)
    pre_roll         = meta.get("pre_roll", 10.0)
    post_roll        = meta.get("post_roll", 20.0)
    players          = meta.get("player_names", [])

    if lc_timing_mode:
        mode_note = (
            f"> **라이브 채팅 타임스탬프 모드** — 클립은 라이브 채팅 오프셋 ±{pre_roll}s/{post_roll}s 윈도우로 자동 생성됩니다.  \n"
            f"> segments.json 없이도 실제 영상 클립이 렌더링됩니다."
        )
    else:
        mode_note = (
            "> **주의:** 일반 댓글(영상 하단)에는 영상 내 타임스탬프 정보가 없습니다.  \n"
            "> `needs_manual_timestamp_mapping: True` 표시된 구간은 편집자가 직접 영상에서 찾아야 합니다."
        )

    lines: list[str] = [
        "# 댓글 중심 Shorts 편집 브리프",
        "",
        f"**영상:** {video_title}  ",
        f"**Video ID:** `{video_id}`  ",
        (f"**URL:** https://www.youtube.com/watch?v={video_id}" if video_id else ""),
        f"**라이브 채팅 데이터:** {'있음 (타임스탬프 직접 모드)' if lc_timing_mode else '있음' if has_chat else '없음 (일반 댓글만)'}  ",
        f"**분석 선수:** {', '.join(players) if players else '자동 감지 안 됨'}  ",
        "",
        mode_note,
        "",
        "---",
        "",
    ]

    # ── Summary stats ──────────────────────────────────────────────────────────
    lines += [
        "## 통계 요약",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 분석 댓글 수 | {meta.get('total_comments_processed', 0)} |",
        f"| 분석 라이브 채팅 수 | {meta.get('total_live_chat_processed', 0)} |",
        f"| 로드된 세그먼트 수 | {meta.get('segments_loaded', 0)} |",
        f"| 하이라이트 후보 댓글 수 | {len(comments)} |",
        f"| 하이라이트 후보 순간 수 | {len(moments)} |",
        f"| 생성된 Shorts 시퀀스 수 | {len(sequences)} |",
        "",
        "---",
        "",
    ]

    # ── Category breakdown ─────────────────────────────────────────────────────
    if comments:
        from collections import Counter
        cat_counts = Counter(r["category"] for r in comments)
        lines += [
            "## 카테고리별 분포",
            "",
            "| 카테고리 | 댓글 수 |",
            "|----------|---------|",
        ]
        for cat, cnt in cat_counts.most_common():
            lines.append(f"| {cat} | {cnt} |")
        lines += ["", "---", ""]

    # ── Top comment candidates ─────────────────────────────────────────────────
    top10 = comments[:10]
    if top10:
        lines += [
            "## 상위 10개 하이라이트 후보 댓글",
            "",
            "| 순위 | 좋아요 | 카테고리 | 우선순위 점수 | 선수 | 댓글 (앞 60자) |",
            "|------|--------|----------|--------------|------|----------------|",
        ]
        for i, r in enumerate(top10, 1):
            preview = r["text"][:60].replace("|", "｜")
            players_str = r.get("related_player_names", "").replace("|", ", ")
            lines.append(
                f"| {i} | {r['likes']} | {r['category']} "
                f"| {r['priority_score']} | {players_str} | {preview}… |"
            )
        lines += ["", "---", ""]

    # ── Moment candidates ──────────────────────────────────────────────────────
    top_moments = moments[:8]
    if top_moments:
        lines += [
            "## 상위 구간 (세그먼트) 후보",
            "",
            "| 구간 | 시작 | 종료 | 댓글 수 | 카테고리 | 신뢰도 | 수동 확인 | 자막 (앞 50자) |",
            "|------|------|------|---------|----------|--------|----------|----------------|",
        ]
        for m in top_moments:
            start = _fmt_time(m["start"])
            end   = _fmt_time(m["end"])
            manual = "필요" if m["needs_manual_verification"] else "불필요"
            preview = str(m["segment_text"])[:50].replace("|", "｜")
            lines.append(
                f"| {m['segment_id']} | {start} | {end} "
                f"| {m['matched_comment_count']} | {m['dominant_category']} "
                f"| {m['best_matching_confidence']} | {manual} | {preview}… |"
            )
        lines += ["", "---", ""]

    # ── Spike moments ──────────────────────────────────────────────────────────
    top_spikes = spike_moments[:10]
    if top_spikes:
        lines += [
            "## 반응 스파이크 순간 (라이브 채팅 밀도 피크)",
            "",
            "| 순위 | 앵커 타임 | 윈도우 | 메시지 수 | 가중 점수 | 대표 메시지 (앞 60자) |",
            "|------|-----------|--------|-----------|-----------|----------------------|",
        ]
        for i, sp in enumerate(top_spikes, 1):
            anchor = _fmt_time(sp["anchor_time"])
            w_start = _fmt_time(sp["window_start"])
            w_end   = _fmt_time(sp["window_end"])
            top_msg = sp["top_messages"][0]["text"][:60].replace("|", "｜") if sp["top_messages"] else ""
            lines.append(
                f"| {i} | {anchor} | {w_start}–{w_end} "
                f"| {sp['message_count']} | {sp['weighted_score']:.0f} | {top_msg}… |"
            )
        lines += ["", "---", ""]

    # ── Shorts sequences ───────────────────────────────────────────────────────
    for seq in sequences:
        is_spike = seq.get("sequence_type") == "spike"

        lines += [
            f"## Shorts 시퀀스: {seq['title']}",
            "",
            f"_{seq.get('description', '')}  ",
            f"**유형:** {'🔴 스파이크 기반 (라이브 채팅)' if is_spike else '카테고리 기반'}  ",
            f"**예상 길이:** {seq.get('estimated_duration_sec', '?')}초  ",
            f"**CTA:** {seq.get('cta', '')}",
            "",
        ]

        # Hook
        hook = seq.get("hook_comment", {})
        lines += [
            "### 훅 (Hook)",
            "",
            f"> {hook.get('text', '')[:120]}",
            f"— *{hook.get('author', '')}* ({hook.get('likes', 0)} likes)",
            f"  캡션: **{hook.get('suggested_caption', '')}**",
            "",
        ]

        if is_spike:
            # Spike sequence: show clip window + rolling chat messages
            clip_start  = seq.get("clip_start")
            clip_end    = seq.get("clip_end")
            anchor      = seq.get("spike_anchor_time")
            rolling_msgs = seq.get("rolling_chat_messages", [])
            start_str   = _fmt_time(clip_start) if clip_start is not None else "?"
            end_str     = _fmt_time(clip_end)   if clip_end   is not None else "?"
            anchor_str  = _fmt_time(anchor)     if anchor     is not None else "?"

            lines += [
                "### 클립 윈도우",
                "",
                f"앵커 타임: **{anchor_str}**  |  클립: {start_str} ~ {end_str}  "
                f"(총 {round((clip_end or 0) - (clip_start or 0), 1)}s)",
                "",
                "### 롤링 라이브 채팅 메시지",
                "",
                "| # | 시간 | 작성자 | 메시지 (앞 60자) | 좋아요 |",
                "|---|------|--------|----------------|--------|",
            ]
            for j, msg in enumerate(rolling_msgs[:15], 1):
                ts      = _fmt_time(msg.get("timestamp_seconds", 0))
                preview = str(msg.get("text", ""))[:60].replace("|", "｜")
                lines.append(
                    f"| {j} | {ts} | {msg.get('author', '')} | {preview} | {msg.get('likes', 0)} |"
                )
        else:
            # Concept sequence: existing clip + overlay table
            lines += ["### 클립 시퀀스", ""]
            clips = seq.get("clip_sequence", [])
            if clips:
                for i, clip in enumerate(clips, 1):
                    start = _fmt_time(clip["start"]) if clip["start"] is not None else "?"
                    end   = _fmt_time(clip["end"])   if clip["end"]   is not None else "?"
                    manual_flag = " ⚠ 수동확인필요" if clip.get("needs_manual_timestamp_mapping") else ""
                    lines.append(f"{i}. `{clip['segment_id']}` — {start} ~ {end}{manual_flag}  ")
                    lines.append(f"   _{clip['note']}_")
                    lines.append("")
            else:
                lines += ["_매칭된 클립 없음 — 편집자가 수동으로 구간 찾기 필요._", ""]

            lines += [
                "### 댓글 오버레이 카드",
                "",
                "| 순서 | 캡션 | 작성자 | 좋아요 | 카테고리 | 수동확인 |",
                "|------|------|--------|--------|----------|---------|",
            ]
            for ov in seq.get("overlays", []):
                caption = ov.get("suggested_caption", "")[:40].replace("|", "｜")
                manual  = "⚠" if ov.get("needs_manual_timestamp_mapping") else "✓"
                lines.append(
                    f"| {ov['order']} | {caption} "
                    f"| {ov['author']} | {ov['likes']} "
                    f"| {ov['category']} | {manual} |"
                )

        lines += ["", "---", ""]

    # ── Footer ─────────────────────────────────────────────────────────────────
    lines += [
        "## 주의사항",
        "",
        "- 이 문서는 자동 생성된 편집 브리프입니다. 편집자의 최종 판단이 항상 우선합니다.",
        "- `⚠ 수동확인필요` 표시 구간은 실제 영상에서 장면을 직접 확인 후 타임코드를 확정하십시오.",
        "- 비판/논쟁 댓글 사용 시 선수 및 채널 브랜드 이미지를 고려하십시오.",
        "- 댓글 작성자 닉네임 노출 시 공개 댓글임에도 사전 확인을 권장합니다.",
        "",
        f"_generated by highlight_pipeline.py_",
    ]

    return "\n".join(lines)


# ── Master highlight markdown builder ─────────────────────────────────────────

def _build_master_script_md(package: dict) -> str:
    plan = package.get("master_plan") or {}
    meta = plan.get("meta", {})

    video_id    = meta.get("video_id", "")
    video_title = meta.get("video_title", "")
    players     = meta.get("player_names", [])
    total_used  = meta.get("total_comments_used", 0)

    lines: list[str] = [
        "# 마스터 하이라이트 편집 브리프",
        "",
        f"**영상:** {video_title}  ",
        f"**Video ID:** `{video_id}`  ",
        (f"**URL:** https://www.youtube.com/watch?v={video_id}" if video_id else ""),
        f"**분석 선수:** {', '.join(players) if players else '자동 감지 안 됨'}  ",
        f"**사용 댓글 수:** {total_used}  ",
        "",
        "> **주의:** 이 플랜은 댓글 언어 패턴으로 추론된 서사 구조입니다.  ",
        "> 모든 섹션의 순서는 실제 영상 확인 후 편집자가 조정해야 합니다.  ",
        "> `needs_manual_timestamp_mapping: True` 표시 댓글은 타임코드를 직접 찾아야 합니다.",
        "",
        "---",
        "",
    ]

    # ── Title suggestions ──────────────────────────────────────────────────────
    titles = plan.get("title_suggestions", [])
    if titles:
        lines += ["## 제목 후보", ""]
        for i, t in enumerate(titles, 1):
            lines.append(f"{i}. {t}")
        lines += ["", "---", ""]

    # ── Opening hook ───────────────────────────────────────────────────────────
    hook = plan.get("opening_hook")
    if hook:
        lines += [
            "## 오프닝 훅",
            "",
            f"> {hook['text'][:150]}",
            f"— *{hook['author']}* ({hook['likes']} likes)  ",
            f"카테고리: **{hook['category']}**  |  "
            f"우선순위 점수: **{hook['priority_score']}**  ",
            f"캡션: _{hook['suggested_caption']}_  ",
            f"편집 활용: `{hook['recommended_usage']}`  ",
            ("⚠ 수동 타임코드 확인 필요" if hook.get("needs_manual_timestamp_mapping") else "✓ 타임코드 확정"),
            "",
            "---",
            "",
        ]

    # ── 5-act structure ────────────────────────────────────────────────────────
    acts = plan.get("acts", [])
    if acts:
        lines += ["## 5막 서사 구조", ""]
        for act in acts:
            emoji       = act.get("emoji", "")
            name        = act.get("act_name", "")
            desc        = act.get("description", "")
            count       = act.get("comment_count", 0)
            cat_dist    = act.get("category_distribution", {})
            anchor      = act.get("anchor_comment")
            bridges     = act.get("bridge_comments", [])

            lines += [
                f"### {emoji} {name}",
                "",
                f"_{desc}_  ",
                f"관련 댓글: **{count}개**",
                "",
            ]

            if cat_dist:
                cat_str = "  |  ".join(f"{c}: {n}" for c, n in cat_dist.items())
                lines += [f"카테고리 분포: {cat_str}", ""]

            if anchor:
                manual_flag = " ⚠" if anchor.get("needs_manual_timestamp_mapping") else " ✓"
                lines += [
                    "**앵커 댓글 (핵심 반응):**",
                    "",
                    f"> {anchor['text'][:120]}",
                    f"— *{anchor['author']}* ({anchor['likes']} likes) · "
                    f"{anchor['category']} · score {anchor['priority_score']}{manual_flag}",
                    f"캡션: _{anchor['suggested_caption']}_",
                    "",
                ]

            if bridges:
                lines += ["**브리지 댓글 (서사 연결):**", ""]
                for b in bridges:
                    manual_flag = " ⚠" if b.get("needs_manual_timestamp_mapping") else " ✓"
                    lines.append(
                        f"- [{b['category']}] {b['text'][:80]}…"
                        f"  _{b['author']}_ ({b['likes']}L){manual_flag}"
                    )
                lines.append("")

            lines += ["---", ""]

    # ── Turning points ─────────────────────────────────────────────────────────
    turning_points = plan.get("turning_points", [])
    if turning_points:
        lines += [
            "## 서사 전환점",
            "",
            "| 중요도 | 카테고리 | 좋아요 | 점수 | 댓글 (앞 70자) | 수동확인 |",
            "|--------|----------|--------|------|----------------|---------|",
        ]
        for tp in turning_points:
            preview  = tp["text"][:70].replace("|", "｜")
            manual   = "⚠" if tp.get("needs_manual_timestamp_mapping") else "✓"
            weight   = tp.get("narrative_weight", "medium")
            lines.append(
                f"| {weight} | {tp['category']} | {tp['likes']} "
                f"| {tp['priority_score']} | {preview}… | {manual} |"
            )
        lines += ["", "---", ""]

    # ── Player arcs ────────────────────────────────────────────────────────────
    player_arcs = plan.get("player_arcs", [])
    if player_arcs:
        lines += ["## 선수별 서사 아크", ""]
        for arc in player_arcs:
            player   = arc["player"]
            sentiment = arc["sentiment_arc"]
            count    = arc["comment_count"]
            cat_dist = arc.get("category_distribution", {})
            peak     = arc.get("peak_moment")

            lines += [
                f"### {player}",
                "",
                f"- 관련 댓글 수: **{count}개**",
                f"- 감정 아크: **{sentiment}**",
            ]

            if cat_dist:
                cat_str = "  |  ".join(f"{c}: {n}" for c, n in cat_dist.items())
                lines.append(f"- 카테고리 분포: {cat_str}")

            if peak:
                manual_flag = " ⚠" if peak.get("needs_manual_timestamp_mapping") else " ✓"
                lines += [
                    "",
                    f"**피크 순간:**  ",
                    f"> {peak['text'][:120]}",
                    f"— *{peak['author']}* ({peak['likes']} likes)"
                    f" · score {peak['priority_score']}{manual_flag}",
                ]

            top_comments = arc.get("top_comments", [])
            if top_comments:
                lines += ["", "**주요 댓글:**", ""]
                for c in top_comments:
                    manual_flag = " ⚠" if c.get("needs_manual_timestamp_mapping") else " ✓"
                    lines.append(
                        f"- [{c['category']}] {c['text'][:70]}…"
                        f"  _{c['author']}_ ({c['likes']}L){manual_flag}"
                    )

            lines += ["", "---", ""]

    # ── Closing note ───────────────────────────────────────────────────────────
    closing = plan.get("closing_note")
    if closing:
        manual_flag = " ⚠ 수동 타임코드 확인 필요" if closing.get("needs_manual_timestamp_mapping") else " ✓ 타임코드 확정"
        lines += [
            "## 클로징 노트",
            "",
            f"> {closing['text'][:150]}",
            f"— *{closing['author']}* ({closing['likes']} likes)  ",
            f"카테고리: **{closing['category']}**  |  "
            f"우선순위 점수: **{closing['priority_score']}**  ",
            f"캡션: _{closing['suggested_caption']}_  ",
            f"편집 활용: `{closing['recommended_usage']}`  ",
            manual_flag,
            "",
            "---",
            "",
        ]

    # ── Key event keywords ─────────────────────────────────────────────────────
    event_kws = plan.get("key_event_keywords", [])
    if event_kws:
        lines += [
            "## 핵심 이벤트 키워드",
            "",
            ", ".join(f"`{kw}`" for kw in event_kws),
            "",
            "---",
            "",
        ]

    # ── Footer ─────────────────────────────────────────────────────────────────
    lines += [
        "## 주의사항",
        "",
        "- 이 문서는 댓글 패턴 분석으로 자동 생성된 편집 브리프입니다.",
        "- **서사 순서(5막 구조)는 추론값입니다.** 실제 영상 확인 후 순서를 조정하세요.",
        "- `⚠ 수동확인필요` 댓글은 실제 영상에서 해당 장면을 찾아 타임코드를 확정하십시오.",
        "- 비판/논쟁 댓글 사용 시 선수 및 채널 브랜드를 고려하십시오.",
        "",
        "_generated by highlight_pipeline.py — master_plan module_",
    ]

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _write_empty(path: Path) -> None:
    path.write_text("", encoding="utf-8")
    logger.info("wrote empty file (no data) → %s", path)
