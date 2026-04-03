"""
narrative.py — Master highlight plan builder.

Produces a structured full-video plan (master_plan) from ranked comment data.

Structure:
  opening_hook      — single highest-impact comment to open the video
  acts              — 5 narrative acts inferred from comment signals
  player_arcs       — per-player sentiment / category arc
  turning_points    — top dramatic/controversial/analytical pivots
  closing_note      — best supportive/emotional comment for the ending
  title_suggestions — 5 Korean title templates

Honesty constraint (same as matcher.py):
  All act assignments are inferred from comment LANGUAGE, not confirmed
  video positions.  Every act/turning-point record carries:
    inferred_from_comments: True
    needs_manual_sequence_review: True
  The editor must verify narrative order against the actual video.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Optional


# ── Act definitions ────────────────────────────────────────────────────────────
# Each act is characterised by a set of signal keywords.
# Comments are assigned to the FIRST act whose keywords match (in order).
# If no act matches, the comment goes to the generic "전개" act.

_ACT_DEFS: list[dict] = [
    {
        "act_id":    "act_1_opening",
        "act_name":  "개막",
        "emoji":     "🏌️",
        "desc":      "경기 시작 — 선수 소개, 초반 분위기",
        "keywords":  [
            "시작", "첫", "1번홀", "첫홀", "오프닝", "개막", "출전",
            "나왔", "등장", "처음", "시작하",
        ],
    },
    {
        "act_id":    "act_2_buildup",
        "act_name":  "전개",
        "emoji":     "📈",
        "desc":      "흐름 형성 — 일진일퇴, 상황 설명",
        "keywords":  [
            "리드", "따라잡", "동타", "타차", "점수", "스코어",
            "버디", "파", "보기", "이글",
        ],
    },
    {
        "act_id":    "act_3_turning",
        "act_name":  "전환점",
        "emoji":     "⭐",
        "desc":      "반전 / 전환점 — 분위기를 바꾼 결정적 순간",
        "keywords":  [
            "역전", "반전", "무너지", "한홀에", "뒤집", "흔들",
            "OB", "ob", "아웃오브", "뒷땅", "생크",
            "comeback", "turning", "pivotal",
        ],
    },
    {
        "act_id":    "act_4_climax",
        "act_name":  "클라이맥스",
        "emoji":     "🔥",
        "desc":      "최고조 — 승부처, 압박, 하이라이트 샷",
        "keywords":  [
            "홀인원", "이글", "하드캐리", "대박", "미쳤", "신", "완벽",
            "클러치", "결정적", "최고", "hole in one",
            "amazing", "incredible", "insane",
        ],
    },
    {
        "act_id":    "act_5_closing",
        "act_name":  "결말",
        "emoji":     "🏆",
        "desc":      "마무리 — 결과, 소감, 팬 반응",
        "keywords":  [
            "우승", "최종", "결과", "끝", "수고", "고생", "화이팅",
            "응원", "다음", "다음번", "기대", "잘했",
        ],
    },
]

# ── Category roles in the master narrative ────────────────────────────────────

# Categories that provide narrative weight (in descending value)
_NARRATIVE_CATEGORIES = [
    "dramatic", "controversial", "analytical",
    "critical", "funny", "clutch_hype", "emotional",
]

# Categories best suited to bridge/narrate between clips
_BRIDGE_CATEGORIES = {"analytical", "representative", "dramatic"}

# ── Title templates ────────────────────────────────────────────────────────────

_TITLE_TEMPLATES: list[str] = [
    "{player1} vs {player2} — 시청자가 기억하는 진짜 승부",
    "이 경기의 진짜 주인공은? — 댓글이 말하는 풀매치 리뷰",
    "전반의 흐름, 후반의 반전 — {player1} 하이라이트 편집본",
    "댓글 {total_comments}개가 선택한 {event_word} 순간 BEST 모음",
    "보는 내내 이랬음 ㅋㅋ — {player1} 풀게임 시청자 반응 총정리",
]

# ── Player sentiment classification ───────────────────────────────────────────

def _classify_player_sentiment(categories: list[str]) -> str:
    """
    Infer overall sentiment arc for a player from their comment categories.
    Returns: "positive" | "contested" | "mixed" | "negative"
    """
    cat_counts = Counter(categories)
    positive = cat_counts.get("clutch_hype", 0) + cat_counts.get("emotional", 0) + cat_counts.get("supportive", 0)
    negative = cat_counts.get("critical", 0) + cat_counts.get("controversial", 0)
    dramatic = cat_counts.get("dramatic", 0)
    analytical = cat_counts.get("analytical", 0)
    total = max(sum(cat_counts.values()), 1)

    if negative / total >= 0.4:
        return "contested"
    if (negative + dramatic) / total >= 0.5:
        return "mixed"
    if positive / total >= 0.5:
        return "positive"
    if analytical / total >= 0.4:
        return "analytical_focus"
    return "mixed"


# ── Act assignment ─────────────────────────────────────────────────────────────

def _assign_act(text: str, category: str) -> str:
    """
    Assign a comment to one of the 5 narrative acts.
    Match order: category shortcuts first, then keyword scan.
    """
    text_lower = text.lower()

    for act in _ACT_DEFS:
        for kw in act["keywords"]:
            if kw.lower() in text_lower:
                return act["act_id"]

    # Category-based fallback assignment
    _CAT_ACT_FALLBACK = {
        "dramatic":      "act_3_turning",
        "controversial": "act_3_turning",
        "clutch_hype":   "act_4_climax",
        "emotional":     "act_5_closing",
        "supportive":    "act_5_closing",
        "funny":         "act_2_buildup",
        "critical":      "act_2_buildup",
        "analytical":    "act_2_buildup",
    }
    return _CAT_ACT_FALLBACK.get(category, "act_2_buildup")


# ── Main builder ───────────────────────────────────────────────────────────────

def build_master_plan(
    comment_records: list[dict],
    player_names: list[str],
    video_id: str = "",
    video_title: str = "",
) -> dict:
    """
    Build the master highlight plan from ranked comment records.

    Parameters
    ----------
    comment_records:  sorted highlight_comments list (priority_score desc)
    player_names:     known player names
    video_id:         YouTube video ID
    video_title:      video title

    Returns
    -------
    dict — master_plan structure (see module docstring)
    """
    if not comment_records:
        return _empty_master_plan(video_id, video_title)

    # ── Opening hook ──────────────────────────────────────────────────────────
    opening_hook = _pick_opening_hook(comment_records)

    # ── Acts ──────────────────────────────────────────────────────────────────
    acts = _build_acts(comment_records)

    # ── Player arcs ───────────────────────────────────────────────────────────
    player_arcs = _build_player_arcs(comment_records, player_names)

    # ── Turning points ────────────────────────────────────────────────────────
    turning_points = _pick_turning_points(comment_records)

    # ── Closing note ──────────────────────────────────────────────────────────
    closing_note = _pick_closing_note(comment_records)

    # ── Title suggestions ─────────────────────────────────────────────────────
    title_suggestions = _build_titles(comment_records, player_names)

    # ── Key event keywords across all comments ────────────────────────────────
    all_signals: list[str] = []
    for r in comment_records:
        all_signals.extend(s for s in r.get("match_signals", "").split("|") if s)
    event_kws = sorted({s.split(":", 1)[1] for s in all_signals if s.startswith("event:")})

    return {
        "meta": {
            "video_id":   video_id,
            "video_title": video_title,
            "total_comments_used": len(comment_records),
            "player_names": player_names,
            "inferred_from_comments":      True,
            "needs_manual_sequence_review": True,
            "note": (
                "이 플랜은 댓글 언어 패턴으로 추론된 것입니다. "
                "서사 순서는 실제 영상 확인 후 편집자가 조정해야 합니다."
            ),
        },
        "opening_hook":    opening_hook,
        "acts":            acts,
        "player_arcs":     player_arcs,
        "turning_points":  turning_points,
        "closing_note":    closing_note,
        "key_event_keywords": event_kws,
        "title_suggestions": title_suggestions,
    }


# ── Section builders ───────────────────────────────────────────────────────────

def _pick_opening_hook(records: list[dict]) -> Optional[dict]:
    """Pick the single best comment to open the master highlight video."""
    preferred_cats = ("dramatic", "analytical", "controversial", "funny", "clutch_hype")
    for cat in preferred_cats:
        for r in records[:30]:   # search top 30 only
            if r["category"] == cat:
                return _comment_card(r, role="opening_hook")
    # Fallback: highest priority overall
    if records:
        return _comment_card(records[0], role="opening_hook")
    return None


def _build_acts(records: list[dict]) -> list[dict]:
    """
    Assign all comments to acts and build the 5-act structure.
    Each act gets: anchor_comment (best), bridge_comments (top 3), stats.
    """
    act_buckets: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        act_id = _assign_act(r["text"], r["category"])
        act_buckets[act_id].append(r)

    acts = []
    for act_def in _ACT_DEFS:
        act_id   = act_def["act_id"]
        bucket   = act_buckets.get(act_id, [])
        # Sort bucket by priority_score (already sorted, but keep explicit)
        bucket.sort(key=lambda x: x["priority_score"], reverse=True)

        anchor = _comment_card(bucket[0], role="anchor") if bucket else None

        # Bridge comments: prefer analytical/dramatic, exclude anchor
        bridge_pool = [
            r for r in bucket[1:]
            if r["category"] in _BRIDGE_CATEGORIES
        ] or bucket[1:4]
        bridge_comments = [_comment_card(r, role="bridge") for r in bridge_pool[:3]]

        cat_dist = dict(Counter(r["category"] for r in bucket).most_common())

        acts.append({
            "act_id":    act_id,
            "act_name":  act_def["act_name"],
            "emoji":     act_def["emoji"],
            "description": act_def["desc"],
            "comment_count":  len(bucket),
            "anchor_comment": anchor,
            "bridge_comments": bridge_comments,
            "category_distribution": cat_dist,
            "inferred_from_comments":      True,
            "needs_manual_sequence_review": True,
        })

    return acts


def _build_player_arcs(
    records: list[dict],
    player_names: list[str],
) -> list[dict]:
    """Build a narrative arc summary for each player."""
    arcs = []
    for player in player_names:
        player_records = [
            r for r in records
            if player in r.get("related_player_names", "")
        ]
        if not player_records:
            continue

        categories = [r["category"] for r in player_records]
        sentiment  = _classify_player_sentiment(categories)
        cat_dist   = dict(Counter(categories).most_common())
        top_comments = [_comment_card(r, role="player_arc") for r in player_records[:3]]

        # Peak moment = highest priority comment mentioning this player
        peak = player_records[0] if player_records else None

        arcs.append({
            "player":          player,
            "comment_count":   len(player_records),
            "sentiment_arc":   sentiment,
            "category_distribution": cat_dist,
            "top_comments":    top_comments,
            "peak_moment":     _comment_card(peak, role="peak") if peak else None,
        })

    return arcs


def _pick_turning_points(records: list[dict], n: int = 5) -> list[dict]:
    """
    Select the top N comments that mark narrative turning points.
    Priority: dramatic > controversial > analytical > critical
    """
    pivot_cats = ("dramatic", "controversial", "analytical", "critical")
    seen_ids: set[str] = set()
    turning: list[dict] = []

    for cat in pivot_cats:
        if len(turning) >= n:
            break
        for r in records:
            if len(turning) >= n:
                break
            cid = r.get("comment_id", "")
            if r["category"] == cat and cid not in seen_ids:
                seen_ids.add(cid)
                turning.append({
                    **_comment_card(r, role="turning_point"),
                    "narrative_weight": _narrative_weight(r),
                })

    return turning


def _pick_closing_note(records: list[dict]) -> Optional[dict]:
    """Pick the best comment to close the master highlight video."""
    preferred_cats = ("supportive", "emotional", "representative")
    for cat in preferred_cats:
        for r in records:
            if r["category"] == cat and r["likes"] >= 1:
                return _comment_card(r, role="closing_note")
    # Fallback: last in the sorted list that isn't dramatic/controversial
    for r in reversed(records[:50]):
        if r["category"] not in ("dramatic", "controversial", "critical"):
            return _comment_card(r, role="closing_note")
    return None


def _build_titles(
    records: list[dict],
    player_names: list[str],
) -> list[str]:
    """Generate 5 title suggestions using player names and event keywords."""
    player1 = player_names[0] if len(player_names) > 0 else "선수"
    player2 = player_names[1] if len(player_names) > 1 else "상대방"

    # Most frequent event keyword across all comments
    all_signals: list[str] = []
    for r in records:
        all_signals.extend(s for s in r.get("match_signals", "").split("|") if s)
    event_counts = Counter(
        s.split(":", 1)[1] for s in all_signals if s.startswith("event:")
    )
    event_word = event_counts.most_common(1)[0][0] if event_counts else "명장면"

    total = len(records)

    return [
        t.format(
            player1=player1,
            player2=player2,
            event_word=event_word,
            total_comments=total,
        )
        for t in _TITLE_TEMPLATES
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _comment_card(r: dict, role: str) -> dict:
    """Extract the essential fields for display in the master plan."""
    return {
        "role":                          role,
        "comment_id":                    r.get("comment_id", ""),
        "text":                          r.get("text", ""),
        "author":                        r.get("author", ""),
        "likes":                         r.get("likes", 0),
        "category":                      r.get("category", ""),
        "emotion_strength":              r.get("emotion_strength", 0),
        "priority_score":                r.get("priority_score", 0),
        "related_player_names":          r.get("related_player_names", ""),
        "suggested_caption":             r.get("suggested_caption", ""),
        "recommended_usage":             r.get("recommended_usage", ""),
        "matched_segment_id":            r.get("matched_segment_id") or None,
        "matched_start":                 r.get("matched_start") or None,
        "matched_end":                   r.get("matched_end") or None,
        "matching_confidence":           r.get("matching_confidence", "none"),
        "needs_manual_timestamp_mapping": r.get("needs_manual_timestamp_mapping", True),
    }


def _narrative_weight(r: dict) -> str:
    """Assign a narrative weight label for turning points."""
    score = r.get("priority_score", 0)
    if score >= 70:
        return "critical"    # must-use
    if score >= 50:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _empty_master_plan(video_id: str, video_title: str) -> dict:
    return {
        "meta": {
            "video_id":   video_id,
            "video_title": video_title,
            "total_comments_used": 0,
            "player_names": [],
            "inferred_from_comments": True,
            "needs_manual_sequence_review": True,
            "note": "댓글 데이터 없음 — 마스터 플랜을 생성할 수 없습니다.",
        },
        "opening_hook":      None,
        "acts":              [],
        "player_arcs":       [],
        "turning_points":    [],
        "closing_note":      None,
        "key_event_keywords": [],
        "title_suggestions": [],
    }
