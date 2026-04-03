"""
classifier.py — Comment classification for highlight pipeline.

Assigns each comment:
  - category         one of 9 highlight types (analytical is new)
  - emotion_strength float 1.0–5.0
  - related_players  list of player names detected in the text
  - suggested_caption short display text for video overlay
  - recommended_usage editing-action name
  - editor_notes     auto-generated guidance for the editor

Category priority (checked top to bottom; first match wins as primary):
  dramatic > controversial > analytical > funny > critical > clutch_hype >
  emotional > supportive > representative

Deconfounding:
  clutch_hype signals that appear inside long critical/analytical comments
  (e.g. "굿샷 나오면 텐션 올라가고... 감정기복이;;") are demoted so the
  primary category reflects editorial intent, not incidental word hits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

# ── Category signal tables ─────────────────────────────────────────────────────
#
# Each list entry is a substring that is matched case-insensitively against
# the full comment text.  Order within each list does not matter.
# Order of CATEGORY_PRIORITY DOES matter.

CATEGORY_PRIORITY: list[str] = [
    "dramatic",       # clear reversal / collapse / comeback signal
    "controversial",  # format / selection / rule / delay debate
    "analytical",     # detailed behavioral or tactical observation (;; key signal)
    "funny",          # ㅋㅋ / haha reactions
    "critical",       # direct negative verdict on a player's performance
    "clutch_hype",    # genuine hype for a good play — only when uncontested
    "emotional",      # ㅠㅠ / 눈물 / 마음이 reactions
    "supportive",     # 화이팅 / 응원
    "representative", # catch-all — only assigned when nothing else matches
]

_SIGNALS: dict[str, list[str]] = {
    "dramatic": [
        # Korean
        "역전", "반전", "한방에", "무너지", "무너졌", "끝날때까지", "끝난게아니",
        "드라마", "극적", "역전패", "역전승", "역대급", "뒤집", "뒤집었",
        "멘탈나", "멘탈붕괴", "한홀에", "한 홀에", "한방에",
        "3타차를", "타차를", "끝날때까지끝난게",
        # English
        "comeback", "reversal", "dramatic", "unbelievable", "choke", "collapse",
    ],
    "controversial": [
        # Time delay / unsportsmanlike conduct
        "비매너", "시간 끈", "시간끈", "끈다고", "인터벌",
        "시간 제한", "시간제한", "시간 끌",
        # Player selection / format critique
        "팀조합", "팀 구성", "팀구성", "선발 기준", "선발기준",
        "나오지말아야", "못나오고", "예선광탈", "탑10에도못",
        "성적 조합", "평균 성적 조합",
        # Rules / fairness
        "규정", "논란", "문제있", "공정", "반칙",
        # English
        "unsportsmanlike", "slow play", "controversy", "unfair",
    ],
    "analytical": [
        # Frustration / irony marker — strongest signal for analytical category
        ";;",
        # Behavioral critique vocabulary
        "감정기복", "감정 기복",
        "나대는", "나댄다", "나대고",
        "과하게", "과한 것", "과한것",
        "발랄하더니",
        "분위기 이상", "분위기이상",
        "개정색빨면서",
        # Tactical / coaching advice language
        "찾아가서", "배우시길", "개선하",
        "볼스", "스크린의",
        # Team / strategic analysis
        "선발기준", "팀조합",          # also controversial; analytical takes priority
        "경기 운영", "경기운영",
        "멘탈 관리", "멘탈관리",
        # Observer language
        "봐주기에는", "봐주기엔",
    ],
    "funny": [
        "ㅋㅋ", "ㅎㅎ", "ㅋㄱ",
        "lol", "lmao", "haha", "hilarious", "funny", "cringe", "😂", "🤣",
    ],
    "critical": [
        # General negative verdict
        "실망", "왜저래", "왜이래", "별로", "형편없",
        "프로가맞나", "프로답지", "수준이", "기대이하", "기대 이하",
        # Performance collapse
        "안되겠", "안되겠다", "이제진짜", "진짜안되",
        "아마추어", "아마한테도", "아마보다", "아마도질",
        "프로대아마", "아마로 나가", "아마로나가",
        "나가야될", "나가야 될",
        "못해", "못하는",
        # English
        "disappointing", "terrible", "awful", "poor", "bad shot",
    ],
    "clutch_hype": [
        "대박", "굿샷", "짱", "하드캐리", "클러치", "레전드", "갓",
        "미쳤다", "미쳐", "최고", "완벽", "멋지",
        "awesome", "clutch", "legendary", "goat", "amazing", "insane",
        "incredible", "🔥",
        # Must appear alone / without analytical modifiers — deconfounded below
    ],
    "emotional": [
        "ㅠㅠ", "ㅜㅜ", "눈물", "감동", "마음이", "가슴이",
        "울었", "안타깝", "슬프", "애잔", "가슴아프", "눈물겹",
        "귀여워", "귀여운", "귀엽", "부럽", "부러워",
        "😢", "😭", "heartbreaking", "touching",
    ],
    "supportive": [
        "화이팅", "파이팅", "응원", "힘내", "기대해", "수고", "고생하셨",
        "잘했", "잘하", "잘해", "응원합니다",
        "fighting", "support", "well done", "good job", "keep going",
    ],
}

# Signals that indicate the word before it is used in a negative/analytical
# context even if the word itself looks positive (e.g. "굿샷 나오면 ... 나대는")
_CONTRAST_MARKERS: tuple[str, ...] = (
    "좋은데,", "좋은데 ", "하지만", "근데 ", "그런데 ",
    "않았음", "않았나", "않았어", "감이 없지", "감이없지",
    "나대는", "과하게", "발랄하더니",
)

# ── Recommended usage (editing-action names) ──────────────────────────────────

USAGE_MAP: dict[str, str] = {
    "dramatic":      "open_short_with_hook_card",
    "controversial": "standalone_debate_short",
    "analytical":    "context_card_before_clip",
    "funny":         "overlay_on_funny_clip",
    "critical":      "pair_with_mistake_clip",
    "clutch_hype":   "overlay_on_highlight_clip",
    "emotional":     "cut_to_player_reaction",
    "supportive":    "close_short_with_fan_voice",
    "representative":"mid_roll_summary_card",
}

# ── Korean informal text normalisation ────────────────────────────────────────
#
# Korean informal/mobile typing substitutes some syllable blocks with adjacent
# Unicode codepoints.  The most common case: 겟 (U+AC9F) used where standard
# Korean requires 겠 (U+ACA0, future-tense auxiliary).  We normalise before
# signal matching so signal tables only need the standard form.

_KO_INFORMAL_MAP: dict[str, str] = {
    "겟": "겠",   # 안되겟다 → 안되겠다
    "됬": "됐",   # 됬어 → 됐어
    "않됬": "안됐",
}

_KO_INFORMAL_RE = re.compile("|".join(re.escape(k) for k in _KO_INFORMAL_MAP))


def _normalize_ko_informal(text: str) -> str:
    """Replace known informal Korean typing variants with standard forms."""
    return _KO_INFORMAL_RE.sub(lambda m: _KO_INFORMAL_MAP[m.group(0)], text)


# ── Intensity regex helpers ────────────────────────────────────────────────────

_KK_RE = re.compile(r"[ㅋ]")
_TT_RE = re.compile(r"[ㅠㅜ]")
_EX_RE = re.compile(r"!")
_SC_RE = re.compile(r";;")


# ── Dataclass for classifier output ───────────────────────────────────────────

@dataclass
class CommentClassification:
    category: str
    all_categories: list[str]
    emotion_strength: float
    related_players: list[str]
    suggested_caption: str
    recommended_usage: str
    editor_notes: str


# ── Main classifier ────────────────────────────────────────────────────────────

class CategoryClassifier:
    """
    Classify a comment into highlight categories.

    Parameters
    ----------
    player_names:
        Known player names to detect in comment text.
    """

    def __init__(self, player_names: Sequence[str] | None = None) -> None:
        self.player_names: list[str] = list(player_names or [])
        self._player_patterns: list[re.Pattern] = [
            re.compile(re.escape(p), re.IGNORECASE) for p in self.player_names
        ]

    def classify(self, text: str, likes: int = 0) -> CommentClassification:
        """Classify a single comment."""
        # Normalise informal Korean typing variants before signal matching.
        # Korean informal text frequently substitutes 겟 (U+AC9F) for 겠 (U+ACA0)
        # since the two characters are adjacent on the keyboard.
        text_lower = _normalize_ko_informal(text).lower()

        # ── Step 1: collect all matching categories ────────────────────
        matched: list[str] = []
        for cat in CATEGORY_PRIORITY:
            if cat == "representative":
                continue
            signals = _SIGNALS.get(cat, [])
            if any(sig.lower() in text_lower for sig in signals):
                matched.append(cat)

        # ── Step 2: deconfound clutch_hype vs analytical/critical ──────
        matched = _deconfound(matched, text)

        # ── Step 3: representative only when nothing else matched ──────
        if not matched:
            matched = ["representative"]

        primary = matched[0]

        # ── Derived fields ─────────────────────────────────────────────
        emotion_strength  = _compute_emotion_strength(text)
        related_players   = self._detect_players(text)
        suggested_caption = _make_caption(text)
        recommended_usage = USAGE_MAP.get(primary, "mid_roll_summary_card")
        editor_notes      = _build_editor_notes(
            text, primary, likes, related_players, emotion_strength
        )

        return CommentClassification(
            category=primary,
            all_categories=matched,
            emotion_strength=round(emotion_strength, 2),
            related_players=related_players,
            suggested_caption=suggested_caption,
            recommended_usage=recommended_usage,
            editor_notes=editor_notes,
        )

    def _detect_players(self, text: str) -> list[str]:
        return [
            name for name, pattern in zip(self.player_names, self._player_patterns)
            if pattern.search(text)
        ]


# ── Deconfounding ──────────────────────────────────────────────────────────────

def _deconfound(categories: list[str], text: str) -> list[str]:
    """
    Resolve category conflicts caused by incidental word hits.

    Key rule: a comment that contains a clutch_hype word (e.g. "굿샷")
    in a conditional or contrasting structure — combined with ;; frustration
    markers or explicit negative language — should not be primarily tagged
    as clutch_hype.  The editorial intent is analytical or critical.
    """
    if "clutch_hype" not in categories:
        return categories

    has_frustration = ";;" in text or text.count("..") >= 2
    has_contrast    = any(m in text for m in _CONTRAST_MARKERS)
    is_long         = len(text) > 80

    # If the comment is substantively analytical or critical, clutch_hype
    # is almost certainly incidental — demote it.
    if is_long and (has_frustration or has_contrast):
        # Other stronger categories already matched → just drop clutch_hype
        if any(c in categories for c in ("analytical", "critical", "controversial", "dramatic")):
            return [c for c in categories if c != "clutch_hype"]
        # clutch_hype is the only match → promote to analytical
        if categories == ["clutch_hype"]:
            return ["analytical"]
        # clutch_hype is primary with only weak co-matches → demote
        if categories[0] == "clutch_hype":
            rest = [c for c in categories[1:] if c != "clutch_hype"]
            return (rest if rest else ["analytical"])

    return categories


# ── Emotion strength ───────────────────────────────────────────────────────────

def _compute_emotion_strength(text: str) -> float:
    """Score 1.0–5.0 based on textual intensity markers."""
    score = 1.0

    kk  = len(_KK_RE.findall(text))
    tt  = len(_TT_RE.findall(text))
    ex  = len(_EX_RE.findall(text))
    sc  = len(_SC_RE.findall(text))

    score += min((kk - 1) * 0.25, 2.0) if kk > 1 else 0
    score += min(tt * 0.35, 1.5)
    score += min(ex * 0.2,  1.0)
    score += min(sc * 0.5,  1.0)
    if len(text) > 100:
        score += 0.5

    return max(1.0, min(score, 5.0))


# ── Caption generation ─────────────────────────────────────────────────────────

_STRIP_KK = re.compile(r"ㅋ{2,}")
_STRIP_TT = re.compile(r"[ㅠㅜ]{2,}")
_SENT_END  = re.compile(r"[.!?；;;。…]+")
_CAP_MAX   = 45


def _make_caption(text: str) -> str:
    """
    Generate a short display caption for video overlay.

    Strips heavy ㅋ/ㅠ repetitions, takes the first sentence, truncates.
    """
    cleaned = _STRIP_KK.sub("ㅋ", text)
    cleaned = _STRIP_TT.sub("ㅠ", cleaned).strip()

    m = _SENT_END.search(cleaned)
    if m:
        candidate = cleaned[: m.end()].strip()
        if len(candidate) >= 4:
            cleaned = candidate

    if len(cleaned) > _CAP_MAX:
        cleaned = cleaned[:_CAP_MAX].rstrip() + "…"

    return cleaned or text[:_CAP_MAX]


# ── Editor notes ───────────────────────────────────────────────────────────────

_CATEGORY_NOTES: dict[str, str] = {
    "dramatic":      "극적 반전 반응 — 역전/붕괴 장면과 매칭해 Short 오프닝 카드로 사용.",
    "controversial": "논쟁성 댓글 — 단독 토론형 Short 또는 '시청자 판결' 포맷에 적합. 단독 클립보다 논의 맥락 필요.",
    "analytical":    "상세 분석/비판 댓글 — 해당 장면 클립 앞에 자막 카드로 맥락 제공. 브랜드 톤 고려 필요.",
    "funny":         "ㅋㅋ 집중 반응 — 실수·어이없는 순간 클립에 오버레이. 텍스트 크게 표시.",
    "critical":      "선수 비판 댓글 — 실수 클립과 매칭 가능하나 브랜드 이미지 우선 확인. 단독 Short에는 주의.",
    "clutch_hype":   "하이프 반응 — 명장면/굿샷 클립 위에 텍스트 오버레이. 강조 폰트 사용.",
    "emotional":     "감정적 반응 — 선수 표정·반응 컷 뒤에 배치. 조용한 BGM과 조합 권장.",
    "supportive":    "응원 댓글 — Short 마지막 카드로 마무리. 긍정 에너지 강조.",
    "representative":"일반 반응 댓글 — 요약 섹션이나 중간 카드로 활용. 편집자 재량.",
}


def _build_editor_notes(
    text: str,
    category: str,
    likes: int,
    players: list[str],
    strength: float,
) -> str:
    parts: list[str] = []

    if likes >= 10:
        parts.append(f"좋아요 {likes}개 — 공감도 높음.")
    if players:
        parts.append(f"{', '.join(players)} 관련 — 해당 선수 등장 장면 확인.")

    cat_note = _CATEGORY_NOTES.get(category, "")
    if cat_note:
        parts.append(cat_note)

    if strength >= 4.0:
        parts.append("감정 강도 높음 — 임팩트 있는 오버레이로 활용 가능.")

    return " ".join(parts) if parts else "표준 반응 댓글. 편집자 재량으로 활용."
