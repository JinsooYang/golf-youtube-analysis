"""
scorer.py — Priority scoring for highlight candidates.

priority_score is a 0–100 composite that reflects:
  - Like weight      (0–40 pts)  — raw audience validation
  - Emotion weight   (8–40 pts)  — intensity of the reaction
  - Category weight  (0–15 pts)  — editorial value for Shorts
  - Confidence bonus (0–5 pts)   — bonus for comments matched to a segment

The score is used to rank candidates before the editor reviews them.
It is NOT a replacement for editorial judgment.
"""

from __future__ import annotations

# ── Category editorial weights ─────────────────────────────────────────────────
# Higher = more interesting for Shorts / hype content

CATEGORY_WEIGHTS: dict[str, float] = {
    "dramatic":      1.5,
    "controversial": 1.4,
    "analytical":    1.35,   # detailed comments — high editorial value
    "funny":         1.3,
    "critical":      1.2,
    "clutch_hype":   1.1,
    "emotional":     1.0,
    "representative":0.9,
    "supportive":    0.8,
}

# ── Matching confidence bonus ──────────────────────────────────────────────────

CONFIDENCE_BONUS: dict[str, float] = {
    "high":   5.0,
    "medium": 3.0,
    "low":    1.0,
    "none":   0.0,
}


def compute_priority_score(
    likes: int,
    emotion_strength: float,
    category: str,
    matching_confidence: str,
    max_likes: int,
) -> float:
    """
    Compute the priority score (0–100) for a single highlight candidate.

    Parameters
    ----------
    likes:               like_count of the comment
    emotion_strength:    1.0–5.0 float from classifier
    category:            one of the 8 category strings
    matching_confidence: "high" | "medium" | "low" | "none"
    max_likes:           maximum like count in the current dataset
                         (used to normalise the likes component)
    """
    like_norm   = likes / max(max_likes, 1)            # 0–1
    like_pts    = like_norm * 40.0                     # 0–40

    emotion_pts = (emotion_strength / 5.0) * 40.0     # 8–40

    cat_weight  = CATEGORY_WEIGHTS.get(category, 0.9)
    cat_pts     = cat_weight * 10.0                    # 8–15

    conf_pts    = CONFIDENCE_BONUS.get(matching_confidence, 0.0)  # 0–5

    raw = like_pts + emotion_pts + cat_pts + conf_pts
    return round(min(raw, 100.0), 2)
