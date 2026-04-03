"""
matcher.py — Comment-to-segment matching for the highlight pipeline.

Three matching modes:

1. LIVE CHAT + SEGMENTS mode (both available):
   Direct time-window lookup against subtitle segments.
   Confidence: "high" (in-window) | "medium" (near-window) | "low" (far)
   Falls through to mode 3 when timestamp is far from all segments.

2. COMMENT mode (no timestamp):
   Two-pass semantic matching against subtitle segments.

   Pass A — Signal matching:
     Extract typed signals (player names, hole numbers, golf event keywords)
     from both the comment and each segment.  Weighted overlap score.
     Confidence: "high" (≥ HIGH_THRESHOLD) | "medium" | "low" | "none"

   Pass B — Word-overlap fallback (runs when Pass A produces "none"):
     Extract content words (len ≥ 2, Korean stopwords excluded) from both
     texts and compute Jaccard-like overlap.  Only improves on a "none"
     result; confidence is capped at "low" because lexical overlap between
     a viewer comment and a transcription segment is inherently uncertain.

3. LIVE CHAT DIRECT mode (timestamp available, no segment match):
   When no subtitle segments exist, or when the timestamp falls outside
   LIVE_CHAT_WINDOW of every segment, the timestamp itself is used as
   the clip anchor.  A clip window of [ts - pre_roll, ts + post_roll] is
   returned with confidence "high" and a synthetic segment ID.

   This is the primary path when live chat replay data is available but
   youtube_extractor.sh did not produce segments.json (subtitles absent).

Honesty constraint (preserved)
-------------------------------
Regular YouTube comments (commentThreads.list) carry NO video timestamp.
needs_manual_timestamp_mapping is ALWAYS True for comment-mode matches,
regardless of confidence level.  The matched_start / matched_end fields
reflect the segment's transcript window, not a confirmed reaction time.

Live chat messages carry videoOffsetTimeMsec — a confirmed video offset.
needs_manual_timestamp_mapping is ALWAYS False for live-chat matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ── Thresholds ─────────────────────────────────────────────────────────────────

LIVE_CHAT_WINDOW  = 30.0   # seconds — "near" window for live-chat matching
HIGH_THRESHOLD    = 6      # signal score for "high" confidence
MED_THRESHOLD     = 3      # signal score for "medium" confidence
OVERLAP_MIN       = 0.07   # minimum Jaccard word-overlap for "low" confidence

# Default clip window for live-chat direct mode (used when no segment available)
DEFAULT_PRE_ROLL  = 10.0   # seconds before the reaction timestamp
DEFAULT_POST_ROLL = 20.0   # seconds after the reaction timestamp

# ── Golf event keywords ────────────────────────────────────────────────────────

_EVENT_KW: list[str] = [
    # Mistakes / shot types
    "ob", "OB", "아웃오브바운즈", "뒷땅", "뒤땅", "탑볼", "쏙땅", "생크",
    # Scores
    "버디", "파", "보기", "더블", "이글", "홀인원", "알바트로스",
    "birdie", "eagle", "bogey", "par", "hole in one",
    # Drama
    "역전", "반전", "리드", "따라잡", "동타", "타차",
    "comeback", "lead", "tied", "chip-in", "chip in", "putt",
    # Course
    "벙커", "러프", "페어웨이", "그린", "핀", "워터",
    "bunker", "rough", "fairway", "green", "pin", "water",
]

_EVENT_PATTERNS: list[re.Pattern] = [
    re.compile(re.escape(kw), re.IGNORECASE) for kw in _EVENT_KW
]

# Hole number patterns
_HOLE_RE = re.compile(
    r"(?:(?P<ko>\d{1,2})\s*번\s*홀)"
    r"|(?:hole\s*(?P<en1>\d{1,2}))"
    r"|(?:#(?P<en2>\d{1,2}))"
    r"|(?:(?P<ord>\d{1,2})(?:st|nd|rd|th)\s+hole)",
    re.IGNORECASE,
)

# ── Korean content-word stopwords ──────────────────────────────────────────────
# Common Korean words that carry no matching value and would inflate overlap.

_KO_MATCH_STOPWORDS: frozenset[str] = frozenset({
    # Particles / endings attached after splitting
    "이다", "있다", "없다", "하다", "되다", "같다",
    "있어", "있는", "있습니", "있네요", "있네",
    "하는", "하고", "하니", "해서", "했다", "했어", "했네",
    "이런", "그런", "저런", "어떤",
    "정말", "너무", "진짜", "완전", "그냥", "좀",
    "이번", "오늘", "지금", "아직", "다시", "또",
    "이걸", "저걸", "그걸",
    "합니다", "합니다", "이에요", "인데요", "네요",
    # Common short particles often left after split
    "이고", "이며", "에서", "으로", "에게",
})

_CONTENT_WORD_RE = re.compile(r"[^\w가-힣]+")


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class MatchResult:
    matched_segment_id: Optional[str]
    matched_start: Optional[float]
    matched_end: Optional[float]
    matching_confidence: str          # "high" | "medium" | "low" | "none"
    needs_manual_timestamp_mapping: bool
    match_signals: list[str]


# ── Confidence rank for comparison ────────────────────────────────────────────

_CONF_RANK: dict[str, int] = {"high": 4, "medium": 3, "low": 2, "none": 1}


# ── Main matcher ───────────────────────────────────────────────────────────────

class SegmentMatcher:
    """
    Match comments or live-chat messages to subtitle segments.

    Parameters
    ----------
    segments:
        list of segment dicts (id, start, end, text) from loaders.
        May be empty — live-chat messages are still matched via their
        timestamp (mode 3 / live-chat direct mode).
    player_names:
        Known player names — treated as high-value matching signals.
    pre_roll:
        Seconds to include before the reaction timestamp in direct-mode
        clip windows.  Default: DEFAULT_PRE_ROLL (10 s).
    post_roll:
        Seconds to include after the reaction timestamp in direct-mode
        clip windows.  Default: DEFAULT_POST_ROLL (20 s).
    """

    def __init__(
        self,
        segments: list[dict],
        player_names: list[str] | None = None,
        pre_roll: float = DEFAULT_PRE_ROLL,
        post_roll: float = DEFAULT_POST_ROLL,
    ) -> None:
        self.segments  = segments
        self.pre_roll  = float(pre_roll)
        self.post_roll = float(post_roll)
        self.player_names: list[str] = list(player_names or [])
        self._player_patterns: list[tuple[str, re.Pattern]] = [
            (name, re.compile(re.escape(name), re.IGNORECASE))
            for name in self.player_names
        ]
        # Pre-compute signal sets and content-word sets for all segments
        self._seg_signals: list[set[str]] = [
            _extract_signals(seg["text"], self._player_patterns)
            for seg in segments
        ]
        self._seg_words: list[set[str]] = [
            _extract_content_words(seg["text"])
            for seg in segments
        ]

    # ------------------------------------------------------------------

    def match_live_chat(self, timestamp_seconds: float) -> MatchResult:
        """
        Match a live-chat message using its confirmed video timestamp.

        Priority:
          1. Subtitle segment that contains the timestamp (high, segment-anchored)
          2. Nearest subtitle segment within LIVE_CHAT_WINDOW (medium/low)
          3. Direct clip window from the timestamp itself (high, no segments needed)

        Mode 3 is used when no subtitle segments were loaded OR when the
        timestamp falls outside LIVE_CHAT_WINDOW of every segment.  The clip
        window [ts - pre_roll, ts + post_roll] is renderable without any
        segment data — the live-chat timestamp IS the confirmed video offset.
        """
        if self.segments:
            # 1. Direct in-window hit
            for seg in self.segments:
                if seg["start"] <= timestamp_seconds <= seg["end"]:
                    return MatchResult(
                        matched_segment_id=seg["id"],
                        matched_start=seg["start"],
                        matched_end=seg["end"],
                        matching_confidence="high",
                        needs_manual_timestamp_mapping=False,
                        match_signals=["timestamp_in_window"],
                    )

            # 2. Nearest segment within LIVE_CHAT_WINDOW
            best_seg, best_dist = _nearest_segment(self.segments, timestamp_seconds)
            if best_seg is not None and best_dist <= LIVE_CHAT_WINDOW:
                conf = "medium" if best_dist <= LIVE_CHAT_WINDOW / 2 else "low"
                return MatchResult(
                    matched_segment_id=best_seg["id"],
                    matched_start=best_seg["start"],
                    matched_end=best_seg["end"],
                    matching_confidence=conf,
                    needs_manual_timestamp_mapping=False,
                    match_signals=[f"timestamp_near_{best_dist:.1f}s"],
                )

        # 3. Live-chat direct mode — use timestamp as clip anchor
        #    This is the primary path when segments.json is absent.
        clip_start = max(0.0, timestamp_seconds - self.pre_roll)
        clip_end   = timestamp_seconds + self.post_roll
        return MatchResult(
            matched_segment_id      = f"lc_ts_{int(timestamp_seconds):06d}",
            matched_start           = clip_start,
            matched_end             = clip_end,
            matching_confidence     = "high",
            needs_manual_timestamp_mapping = False,
            match_signals           = ["live_chat_timestamp_direct"],
        )

    # ------------------------------------------------------------------

    def match_comment(self, text: str) -> MatchResult:
        """
        Match a regular comment via two-pass semantic matching.

        Pass A: typed-signal overlap (player names, hole numbers, events).
        Pass B: word-level content overlap (fallback when Pass A finds nothing).

        needs_manual_timestamp_mapping is ALWAYS True — regular comments
        have no video timestamp.
        """
        if not self.segments:
            return _no_match(needs_manual=True)

        # ── Pass A: signal-based ───────────────────────────────────────
        result_a = self._signal_match(text)
        if _CONF_RANK[result_a.matching_confidence] >= _CONF_RANK["medium"]:
            return result_a

        # ── Pass B: word-overlap fallback ──────────────────────────────
        result_b = self._word_overlap_match(text)

        # Return whichever pass produced the stronger result
        if _CONF_RANK[result_b.matching_confidence] > _CONF_RANK[result_a.matching_confidence]:
            return result_b

        return result_a   # may be "low" from Pass A or "none"

    # ------------------------------------------------------------------

    def _signal_match(self, text: str) -> MatchResult:
        comment_signals = _extract_signals(text, self._player_patterns)
        if not comment_signals:
            return _no_match(needs_manual=True)

        best_score  = 0
        best_seg: Optional[dict] = None
        best_overlap: set[str]   = set()

        for seg, seg_sig in zip(self.segments, self._seg_signals):
            overlap = comment_signals & seg_sig
            score   = _signal_score(overlap)
            if score > best_score:
                best_score   = score
                best_seg     = seg
                best_overlap = overlap

        if best_seg is None or best_score == 0:
            return _no_match(needs_manual=True)

        conf = (
            "high"   if best_score >= HIGH_THRESHOLD else
            "medium" if best_score >= MED_THRESHOLD  else
            "low"
        )
        return MatchResult(
            matched_segment_id=best_seg["id"],
            matched_start=best_seg["start"],
            matched_end=best_seg["end"],
            matching_confidence=conf,
            needs_manual_timestamp_mapping=True,
            match_signals=sorted(best_overlap),
        )

    def _word_overlap_match(self, text: str) -> MatchResult:
        """
        Word-overlap fallback.  Returns "low" confidence at best.

        Uses Jaccard similarity on content-word sets.  Confidence is
        deliberately capped at "low" because lexical overlap between a
        viewer comment and a transcription sentence is structurally weak —
        viewers react in colloquial language while transcripts are formal
        commentary.  The match gives the editor a candidate segment to
        check, not a confirmed timestamp.
        """
        comment_words = _extract_content_words(text)
        if not comment_words:
            return _no_match(needs_manual=True)

        best_score = 0.0
        best_seg: Optional[dict] = None
        best_overlap: set[str]   = set()

        for seg, seg_words in zip(self.segments, self._seg_words):
            if not seg_words:
                continue
            overlap = comment_words & seg_words
            if not overlap:
                continue
            # Weighted Jaccard: shared / union
            score = len(overlap) / max(len(comment_words | seg_words), 1)
            # Boost score if the overlap words are player names
            player_bonus = sum(
                0.06 for name in self.player_names
                if name in overlap or any(name in w for w in overlap)
            )
            score += player_bonus
            if score > best_score:
                best_score   = score
                best_seg     = seg
                best_overlap = overlap

        if best_seg is None or best_score < OVERLAP_MIN:
            return _no_match(needs_manual=True)

        return MatchResult(
            matched_segment_id=best_seg["id"],
            matched_start=best_seg["start"],
            matched_end=best_seg["end"],
            matching_confidence="low",      # always low for word-overlap
            needs_manual_timestamp_mapping=True,
            match_signals=["overlap:" + w for w in sorted(best_overlap)[:6]],
        )


# ── Signal extraction ──────────────────────────────────────────────────────────

def _extract_signals(
    text: str,
    player_patterns: list[tuple[str, re.Pattern]],
) -> set[str]:
    """
    Extract typed signals from text.

    player:<name>   weight 3
    hole:<N>        weight 4
    event:<keyword> weight 2
    """
    signals: set[str] = set()

    for name, pattern in player_patterns:
        if pattern.search(text):
            signals.add(f"player:{name}")

    for m in _HOLE_RE.finditer(text):
        num = m.group("ko") or m.group("en1") or m.group("en2") or m.group("ord")
        if num:
            signals.add(f"hole:{num}")

    for kw, pattern in zip(_EVENT_KW, _EVENT_PATTERNS):
        if pattern.search(text):
            signals.add(f"event:{kw.lower()}")

    return signals


def _signal_score(signals: set[str]) -> int:
    score = 0
    for sig in signals:
        if sig.startswith("player:"):
            score += 3
        elif sig.startswith("hole:"):
            score += 4
        elif sig.startswith("event:"):
            score += 2
    return score


# ── Content word extraction ────────────────────────────────────────────────────

def _extract_content_words(text: str) -> set[str]:
    """
    Extract lowercase content words of length ≥ 2 from Korean/English text.

    Skips common Korean filler words that would produce false overlap scores.
    """
    raw = _CONTENT_WORD_RE.split(text.lower())
    return {
        tok for tok in raw
        if len(tok) >= 2
        and not tok.isdigit()
        and tok not in _KO_MATCH_STOPWORDS
    }


# ── Utilities ──────────────────────────────────────────────────────────────────

def _nearest_segment(
    segments: list[dict],
    ts: float,
) -> tuple[Optional[dict], float]:
    best_seg  = None
    best_dist = float("inf")
    for seg in segments:
        mid  = (seg["start"] + seg["end"]) / 2
        dist = abs(mid - ts)
        if dist < best_dist:
            best_dist = dist
            best_seg  = seg
    return best_seg, best_dist


def _no_match(needs_manual: bool = False) -> MatchResult:
    return MatchResult(
        matched_segment_id=None,
        matched_start=None,
        matched_end=None,
        matching_confidence="none",
        needs_manual_timestamp_mapping=needs_manual,
        match_signals=[],
    )
