"""
packager.py — Assembles the final highlight data structures.

Orchestrates classifier → matcher → scorer for every comment/chat row,
then groups results into:
  - highlight_comments  — per-comment candidate records
  - highlight_moments   — segment-level aggregates (which segments attracted
                          the most / strongest comments)
  - shorts_sequences    — 3-5 ready-to-use Shorts concepts with clip+overlay plans

All heavy NLP is in classifier.py and matcher.py; this module is
deliberately thin — just wiring and aggregation.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

import pandas as pd

from src.highlight.classifier import CategoryClassifier, CommentClassification
from src.highlight.matcher import SegmentMatcher, MatchResult, DEFAULT_PRE_ROLL, DEFAULT_POST_ROLL
from src.highlight.scorer import compute_priority_score
from src.highlight.narrative import build_master_plan
from src.highlight.spike_detector import detect_spikes

logger = logging.getLogger(__name__)

# ── Minimum likes to be included as a highlight candidate ─────────────────────
MIN_LIKES_THRESHOLD = 1   # include everything with ≥1 like (editor filters further)
# ── Top N comments per concept-based Shorts sequence ─────────────────────────
SHORTS_TOP_N = 5
# ── Spike-driven Shorts defaults ──────────────────────────────────────────────
SPIKE_SHORTS_COUNT      = 5     # top N spikes → N Shorts
SPIKE_SHORTS_PRE_ROLL   = 10.0  # seconds before spike anchor → clip start
SPIKE_SHORTS_POST_ROLL  = 5.0   # seconds after spike anchor → clip end
SPIKE_MAX_CHAT_MESSAGES = 50    # max rolling chat messages per spike Short


def build_package(
    comments_df: pd.DataFrame,
    segments: list[dict],
    player_names: list[str] | None = None,
    live_chat_df: Optional[pd.DataFrame] = None,
    video_id: str = "",
    video_title: str = "",
    pre_roll: float = DEFAULT_PRE_ROLL,
    post_roll: float = DEFAULT_POST_ROLL,
    shorts_pre_roll: float = SPIKE_SHORTS_PRE_ROLL,
    shorts_post_roll: float = SPIKE_SHORTS_POST_ROLL,
    max_window_messages: int = SPIKE_MAX_CHAT_MESSAGES,
) -> dict:
    """
    Build the complete highlight package from loaded data.

    Parameters
    ----------
    comments_df:   DataFrame from loaders.load_comments
    segments:      list of segment dicts from loaders.load_segments
                   (may be empty — live chat timestamps still work without segments)
    player_names:  known player names (detected entities)
    live_chat_df:  optional live-chat DataFrame from loaders.load_live_chat
    video_id:      YouTube video ID (for metadata)
    video_title:   video title (for metadata)
    pre_roll:        seconds before reaction timestamp for direct-mode clip window
                     (used by matcher — baked into matched_start/end for all clips)
    post_roll:       seconds after reaction timestamp for direct-mode clip window
    shorts_pre_roll: seconds before spike anchor for Shorts clip window
                     (used only in spike-driven Shorts mode)
    shorts_post_roll:    seconds after spike anchor for Shorts clip window
    max_window_messages: max chat messages to include in each spike Short's
                         rolling_chat_messages list (default 20)

    Returns
    -------
    dict with keys: meta, highlight_comments, highlight_moments,
                    spike_moments, shorts_sequences, master_plan
    """
    players = list(player_names or [])
    classifier = CategoryClassifier(player_names=players)
    matcher    = SegmentMatcher(
        segments     = segments,
        player_names = players,
        pre_roll     = pre_roll,
        post_roll    = post_roll,
    )

    # Combine regular comments + live chat into a single processing list
    all_rows = _combine_sources(comments_df, live_chat_df)
    if all_rows.empty:
        logger.warning("no comments or live-chat rows to process")
        return _empty_package(video_id, video_title)

    max_likes = int(all_rows["like_count"].max()) or 1

    # ── Per-comment processing ─────────────────────────────────────────────────
    records: list[dict] = []
    for _, row in all_rows.iterrows():
        text       = str(row["text"])
        likes      = int(row.get("like_count", 0))
        source     = str(row.get("source_type", "comment"))
        comment_id = str(row.get("comment_id", ""))
        author     = str(row.get("author", ""))

        # Classifier
        cls: CommentClassification = classifier.classify(text, likes)

        # Matcher
        if source == "live_chat":
            ts = float(row.get("timestamp_seconds", -1))
            match: MatchResult = (
                matcher.match_live_chat(ts) if ts >= 0 else matcher.match_comment(text)
            )
        else:
            match: MatchResult = matcher.match_comment(text)

        # Scorer
        priority = compute_priority_score(
            likes=likes,
            emotion_strength=cls.emotion_strength,
            category=cls.category,
            matching_confidence=match.matching_confidence,
            max_likes=max_likes,
        )

        records.append({
            "comment_id":                   comment_id,
            "source_type":                  source,
            "text":                         text,
            "likes":                        likes,
            "author":                       author,
            "category":                     cls.category,
            "all_categories":               "|".join(cls.all_categories),
            "emotion_strength":             cls.emotion_strength,
            "priority_score":               priority,
            "related_player_names":         "|".join(cls.related_players),
            "suggested_caption":            cls.suggested_caption,
            "recommended_usage":            cls.recommended_usage,
            "matched_segment_id":           match.matched_segment_id or "",
            "matched_start":                match.matched_start if match.matched_start is not None else "",
            "matched_end":                  match.matched_end   if match.matched_end   is not None else "",
            "matching_confidence":          match.matching_confidence,
            "needs_manual_timestamp_mapping": match.needs_manual_timestamp_mapping,
            "match_signals":                "|".join(match.match_signals),
            "editor_notes":                 cls.editor_notes,
        })

    # Sort by priority_score descending
    records.sort(key=lambda r: r["priority_score"], reverse=True)

    # ── Determine whether live chat timestamp mode is active ──────────────────
    lc_records = [r for r in records if r["source_type"] == "live_chat"]
    live_chat_timing_mode = any(
        "live_chat_timestamp_direct" in r.get("match_signals", "")
        for r in lc_records
    )

    # ── Moment candidates (segment-level aggregation) ──────────────────────────
    moment_records = _build_moments(records, segments)

    # ── Spike moments (live chat density peaks) ────────────────────────────────
    spike_moments = detect_spikes(live_chat_df) if live_chat_df is not None else []

    # ── Shorts sequences — spike-driven when live chat available, else concept ──
    if live_chat_timing_mode and spike_moments and live_chat_df is not None:
        shorts_sequences = _build_spike_shorts_sequences(
            spike_moments      = spike_moments,
            live_chat_df       = live_chat_df,
            pre_roll           = shorts_pre_roll,
            post_roll          = shorts_post_roll,
            max_chat_messages  = max_window_messages,
        )
    else:
        shorts_sequences = _build_shorts_sequences(records, players, pre_roll, post_roll)

    # ── Master highlight plan ──────────────────────────────────────────────────
    master_plan = build_master_plan(
        comment_records=records,
        player_names=players,
        video_id=video_id,
        video_title=video_title,
    )

    return {
        "meta": {
            "video_id":    video_id,
            "video_title": video_title,
            "total_comments_processed":  len([r for r in records if r["source_type"] == "comment"]),
            "total_live_chat_processed": len(lc_records),
            "segments_loaded":           len(segments),
            "player_names":              players,
            "has_live_chat":             live_chat_df is not None,
            "live_chat_timing_mode":     live_chat_timing_mode,
            "spike_moments_detected":    len(spike_moments),
            "pre_roll":                  pre_roll,
            "post_roll":                 post_roll,
            "shorts_pre_roll":           shorts_pre_roll,
            "shorts_post_roll":          shorts_post_roll,
        },
        "highlight_comments": records,
        "highlight_moments":  moment_records,
        "spike_moments":      spike_moments,
        "shorts_sequences":   shorts_sequences,
        "master_plan":        master_plan,
    }


# ── Moment aggregation ─────────────────────────────────────────────────────────

def _build_moments(
    comment_records: list[dict],
    segments: list[dict],
) -> list[dict]:
    """
    Aggregate comment candidates by matched segment to create moment candidates.
    """
    if not segments:
        return []

    # Index segments for fast lookup
    seg_index: dict[str, dict] = {s["id"]: s for s in segments}

    # Group comments by matched_segment_id
    seg_comments: dict[str, list[dict]] = defaultdict(list)
    for rec in comment_records:
        sid = rec.get("matched_segment_id")
        if sid and sid in seg_index:
            seg_comments[sid].append(rec)

    moments: list[dict] = []
    for seg_id, matched in seg_comments.items():
        seg = seg_index[seg_id]

        # Aggregate metrics
        total_likes = sum(r["likes"] for r in matched)
        max_priority = max(r["priority_score"] for r in matched)
        categories = [r["category"] for r in matched]
        dominant_category = _most_common(categories)

        # All player names mentioned across matched comments
        players_set: set[str] = set()
        for r in matched:
            players_set.update(p for p in r["related_player_names"].split("|") if p)

        # Event signals detected across matched comments
        signals_set: set[str] = set()
        for r in matched:
            signals_set.update(s for s in r["match_signals"].split("|") if s)
        event_kws = [s.split(":", 1)[1] for s in signals_set if s.startswith("event:")]

        # Reaction intensity = mean emotion_strength of matched comments
        reaction_intensity = round(
            sum(r["emotion_strength"] for r in matched) / len(matched), 2
        )

        # Recommended clip usage based on dominant category
        from src.highlight.classifier import USAGE_MAP
        clip_usage = USAGE_MAP.get(dominant_category, "summary_overlay")

        # Confidence summary
        confidences = [r["matching_confidence"] for r in matched]
        best_confidence = _best_confidence(confidences)

        # Top comment for this moment
        top_comment = matched[0] if matched else {}

        notes_parts: list[str] = []
        if best_confidence in ("high", "medium"):
            notes_parts.append(f"추정 구간: {_fmt_time(seg['start'])}–{_fmt_time(seg['end'])}.")
        else:
            notes_parts.append("매칭 신뢰도 낮음 — 수동 구간 확인 필요.")
        if players_set:
            notes_parts.append(f"등장 선수: {', '.join(sorted(players_set))}.")
        notes_parts.append(f"댓글 {len(matched)}개 매칭됨.")

        moments.append({
            "moment_id":            f"moment_{seg_id}",
            "segment_id":           seg_id,
            "start":                seg["start"],
            "end":                  seg["end"],
            "segment_text":         seg["text"],
            "matched_comment_count":len(matched),
            "matched_comment_ids":  "|".join(r["comment_id"] for r in matched),
            "total_likes":          total_likes,
            "max_priority_score":   max_priority,
            "dominant_category":    dominant_category,
            "player_names":         "|".join(sorted(players_set)),
            "event_keywords":       "|".join(sorted(set(event_kws))),
            "reaction_intensity":   reaction_intensity,
            "best_matching_confidence": best_confidence,
            "recommended_clip_usage":   clip_usage,
            "top_comment_text":     top_comment.get("text", ""),
            "top_comment_likes":    top_comment.get("likes", 0),
            "needs_manual_verification": best_confidence in ("low", "none"),
            "editor_notes":         " ".join(notes_parts),
        })

    # Sort by max_priority_score descending
    moments.sort(key=lambda m: m["max_priority_score"], reverse=True)
    return moments


# ── Shorts sequence generation ─────────────────────────────────────────────────

# ── Spike-driven Shorts builder ────────────────────────────────────────────────

def _build_spike_shorts_sequences(
    spike_moments: list[dict],
    live_chat_df: pd.DataFrame,
    pre_roll: float = SPIKE_SHORTS_PRE_ROLL,
    post_roll: float = SPIKE_SHORTS_POST_ROLL,
    top_n: int = SPIKE_SHORTS_COUNT,
    max_chat_messages: int = SPIKE_MAX_CHAT_MESSAGES,
) -> list[dict]:
    """
    Build Shorts sequences from the top N live-chat spike moments.

    Each spike produces one Short:
        hook card  → clip [anchor - pre_roll, anchor + post_roll]
                     with rolling live-chat overlay → CTA card

    The rolling chat messages are all live-chat messages from the spike's
    detection window, sorted by timestamp — the renderer uses them to
    build a phased overlay that "rolls in" during playback.
    """
    sequences: list[dict] = []

    for i, spike in enumerate(spike_moments[:top_n], 1):
        anchor   = float(spike["anchor_time"])
        w_start  = float(spike["window_start"])
        w_end    = float(spike["window_end"])
        count    = int(spike["message_count"])
        score    = float(spike["weighted_score"])

        clip_start  = max(0.0, anchor - pre_roll)
        clip_end    = anchor + post_roll
        concept_id  = f"spike_{i:03d}"

        # All messages in the spike detection window, sorted by time
        mask = (
            (live_chat_df["timestamp_seconds"] >= w_start)
            & (live_chat_df["timestamp_seconds"] <= w_end)
        )
        win_msgs = (
            live_chat_df[mask]
            .sort_values("timestamp_seconds")
            .head(max_chat_messages)
        )
        rolling_messages = [
            {
                "timestamp_seconds": float(row["timestamp_seconds"]),
                "text":   str(row.get("text",   ""))[:120],
                "author": str(row.get("author", ""))[:32],
                "likes":  int(row.get("likes",  0)),
            }
            for _, row in win_msgs.iterrows()
        ]

        # Hook = highest-weight message from spike top_messages (already ranked)
        top_msgs  = spike.get("top_messages", [])
        hook_data = top_msgs[0] if top_msgs else {
            "text": "🔥 라이브 반응 급상승!", "author": "", "likes": 0
        }

        anchor_min = int(anchor) // 60
        anchor_sec = int(anchor) % 60
        time_label = f"{anchor_min}:{anchor_sec:02d}"

        clip_dur   = round(clip_end - clip_start, 1)
        est_dur    = int(3.5 + clip_dur + 3.5)  # hook + clip + cta

        sequences.append({
            "concept_id":     concept_id,
            "sequence_type":  "spike",
            "title":          f"라이브 반응 피크 #{i} — {time_label}",
            "description":    (
                f"스파이크: {count}개 메시지 · 가중 점수 {score:.0f} · "
                f"클립 {time_label} ({clip_dur}s)"
            ),
            # Spike metadata (used by renderer + writer)
            "spike_anchor_time":    anchor,
            "spike_window_start":   w_start,
            "spike_window_end":     w_end,
            "spike_weighted_score": score,
            "spike_message_count":  count,
            # Clip timing (baked in at planning time)
            "clip_start":           clip_start,
            "clip_end":             clip_end,
            # Messages for rolling chat overlay
            "rolling_chat_messages": rolling_messages,
            # Hook card
            "hook_comment": {
                "text":              str(hook_data.get("text", ""))[:200],
                "author":            str(hook_data.get("author", "")),
                "likes":             int(hook_data.get("likes", 0)),
                "suggested_caption": str(hook_data.get("text", ""))[:45],
            },
            "cta": "여러분의 생각은? 댓글로 남겨주세요 \U0001f447",
            # Backward-compat fields so existing renderer path still works
            # (shorts_renderer checks sequence_type first; these are fallback)
            "clip_sequence": [{
                "segment_id":   concept_id,
                "start":        clip_start,
                "end":          clip_end,
                "needs_manual_timestamp_mapping": False,
                "note":         f"스파이크 직접 클립 — 타임스탬프 확정 (high)",
            }],
            "overlays": [{
                "order":   1,
                "comment_id":        f"{concept_id}_hook",
                "text":              str(hook_data.get("text", ""))[:200],
                "suggested_caption": str(hook_data.get("text", ""))[:45],
                "author":            str(hook_data.get("author", "")),
                "likes":             int(hook_data.get("likes", 0)),
                "category":          "clutch_hype",
                "matched_segment_id":  concept_id,
                "matched_start":       clip_start,
                "matched_end":         clip_end,
                "matching_confidence": "high",
                "needs_manual_timestamp_mapping": False,
            }],
            "estimated_duration_sec": est_dur,
        })

    return sequences


# ── Concept-based Shorts (used when no live chat / no spikes) ─────────────────

_SHORTS_CONCEPTS: list[dict] = [
    {
        "concept_id": "top_reactions",
        "title_template": "댓글이 말했다 — 이 경기의 진짜 주인공",
        "description": "좋아요 상위 댓글 중심 종합 리캡 Shorts",
        "filter_key": None,
        "filter_value": None,
    },
    {
        "concept_id": "funniest",
        "title_template": "ㅋㅋ 모음 — 오늘의 웃음 포인트",
        "description": "funny 카테고리 상위 댓글 중심 웃음 리캡",
        "filter_key": "category",
        "filter_value": "funny",
    },
    {
        "concept_id": "dramatic",
        "title_template": "끝날 때까지 끝난 게 아니다 — 극적 반전 순간",
        "description": "dramatic 카테고리 — 역전/붕괴 순간 중심",
        "filter_key": "category",
        "filter_value": "dramatic",
    },
    {
        "concept_id": "controversial",
        "title_template": "시청자 판결 — 이 장면, 어떻게 생각하세요?",
        "description": "controversial 카테고리 — 논쟁 포인트 중심 토론형 Shorts",
        "filter_key": "category",
        "filter_value": "controversial",
    },
    {
        "concept_id": "analytical",
        "title_template": "시청자가 본 [선수명] — 분석 관전 모음",
        "description": "analytical 카테고리 — 상세 행동/전술 분석 댓글 중심. 클립 앞 자막 카드로 활용.",
        "filter_key": "category",
        "filter_value": "analytical",
    },
    {
        "concept_id": "clutch",
        "title_template": "역시 [선수명] — 클러치 순간 모음",
        "description": "clutch_hype 카테고리 — 좋은 플레이에 대한 하이프 댓글 중심",
        "filter_key": "category",
        "filter_value": "clutch_hype",
    },
]


def _build_shorts_sequences(
    comment_records: list[dict],
    player_names: list[str],
    pre_roll: float = DEFAULT_PRE_ROLL,
    post_roll: float = DEFAULT_POST_ROLL,
) -> list[dict]:
    sequences: list[dict] = []

    for concept in _SHORTS_CONCEPTS:
        # Filter candidates
        if concept["filter_key"] is None:
            candidates = comment_records
        else:
            k, v = concept["filter_key"], concept["filter_value"]
            candidates = [r for r in comment_records if r.get(k) == v]

        if not candidates:
            continue

        top = candidates[:SHORTS_TOP_N]

        # Hook = highest priority candidate
        hook = top[0]

        # Overlay cards in sequence order
        overlays = [
            {
                "order":             i + 1,
                "comment_id":        r["comment_id"],
                "text":              r["text"],
                "suggested_caption": r["suggested_caption"],
                "author":            r["author"],
                "likes":             r["likes"],
                "category":          r["category"],
                "matched_segment_id":r["matched_segment_id"] or None,
                "matched_start":     r["matched_start"]      or None,
                "matched_end":       r["matched_end"]        or None,
                "matching_confidence": r["matching_confidence"],
                "needs_manual_timestamp_mapping": r["needs_manual_timestamp_mapping"],
            }
            for i, r in enumerate(top)
        ]

        # Suggested title — replace [선수명] with most-mentioned player
        title = concept["title_template"]
        if "[선수명]" in title:
            # For analytical concept, prefer the most-mentioned player in that concept's candidates
            mentioned: list[str] = []
            for r in top:
                mentioned.extend(p for p in r["related_player_names"].split("|") if p)
            from collections import Counter
            top_player = Counter(mentioned).most_common(1)
            placeholder = top_player[0][0] if top_player else (player_names[0] if player_names else "선수")
            title = title.replace("[선수명]", placeholder)

        sequences.append({
            "concept_id":    concept["concept_id"],
            "title":         title,
            "description":   concept["description"],
            "hook_comment":  {
                "text":              hook["text"],
                "suggested_caption": hook["suggested_caption"],
                "author":            hook["author"],
                "likes":             hook["likes"],
            },
            "clip_sequence": _build_clip_sequence(top, pre_roll + post_roll),
            "overlays":      overlays,
            "cta":           "여러분의 생각은? 댓글로 남겨주세요 👇",
            "estimated_duration_sec": _estimate_duration(len(top)),
        })

    return sequences


def _build_clip_sequence(
    top_comments: list[dict],
    max_clip_sec: float = 30.0,
) -> list[dict]:
    """
    Build an editing clip sequence from matched comments.

    Includes any comment that has a matched_segment_id (including synthetic
    lc_ts_* IDs produced by live-chat direct mode).  Skips clips that
    overlap heavily with an already-selected clip to avoid near-duplicate
    footage in the Shorts.

    Overlap threshold: 50 % of the shorter clip.
    """
    seen_ids: set[str] = set()
    selected: list[tuple[float, float, dict]] = []   # (start, end, clip)

    for r in top_comments:
        sid = r.get("matched_segment_id")
        if not sid:
            continue
        if sid in seen_ids:
            continue

        start = _to_float_or_none(r.get("matched_start"))
        end   = _to_float_or_none(r.get("matched_end"))

        # Skip if this clip overlaps > 50% with any already-selected clip
        if start is not None and end is not None:
            if any(_clip_overlap_ratio(start, end, s, e) > 0.5 for s, e, _ in selected):
                continue

        seen_ids.add(sid)
        clip = {
            "segment_id": sid,
            "start":      start,
            "end":        end,
            "needs_manual_timestamp_mapping": r["needs_manual_timestamp_mapping"],
            "note": (
                f"추정 구간 (confidence: {r['matching_confidence']}) — 수동 확인 권장."
                if r["needs_manual_timestamp_mapping"]
                else f"타임스탬프 확정 (confidence: {r['matching_confidence']})."
            ),
        }
        selected.append((start or 0.0, end or 0.0, clip))

    return [c for _, _, c in selected]


def _to_float_or_none(val) -> Optional[float]:
    """Convert a value to float, returning None for empty / un-parseable values."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _clip_overlap_ratio(
    a_start: float, a_end: float,
    b_start: float, b_end: float,
) -> float:
    """Overlap as a fraction of the shorter clip (0.0–1.0)."""
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    if shorter <= 0:
        return 0.0
    return overlap / shorter


def _estimate_duration(n_comments: int) -> int:
    """Rough Shorts duration estimate: hook 4s + 15s per clip + 3s CTA."""
    return 4 + n_comments * 15 + 3


# ── Utility ────────────────────────────────────────────────────────────────────

def _most_common(items: list[str]) -> str:
    if not items:
        return "representative"
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return max(counts, key=counts.__getitem__)


_CONFIDENCE_RANK = {"high": 4, "medium": 3, "low": 2, "none": 1}


def _best_confidence(items: list[str]) -> str:
    if not items:
        return "none"
    return max(items, key=lambda c: _CONFIDENCE_RANK.get(c, 0))


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _combine_sources(
    comments_df: pd.DataFrame,
    live_chat_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    if not comments_df.empty:
        df = comments_df.copy()
        if "source_type" not in df.columns:
            df["source_type"] = "comment"
        frames.append(df)

    if live_chat_df is not None and not live_chat_df.empty:
        frames.append(live_chat_df.copy())

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["like_count"] = pd.to_numeric(
        combined["like_count"], errors="coerce"
    ).fillna(0).astype(int)
    return combined


def _empty_package(video_id: str, video_title: str) -> dict:
    return {
        "meta": {
            "video_id": video_id, "video_title": video_title,
            "total_comments_processed":  0,
            "total_live_chat_processed": 0,
            "segments_loaded":           0,
            "player_names":              [],
            "has_live_chat":             False,
            "live_chat_timing_mode":     False,
            "spike_moments_detected":    0,
            "pre_roll":                  DEFAULT_PRE_ROLL,
            "post_roll":                 DEFAULT_POST_ROLL,
            "shorts_pre_roll":           SPIKE_SHORTS_PRE_ROLL,
            "shorts_post_roll":          SPIKE_SHORTS_POST_ROLL,
        },
        "highlight_comments":  [],
        "highlight_moments":   [],
        "spike_moments":       [],
        "shorts_sequences":    [],
        "master_plan":         None,
    }
