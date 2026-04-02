"""
Content strategy insight generator.

Turns comment patterns (keywords, sentiment, engagement signals) into
concrete, actionable recommendations for the creator.

All recommendations are grounded in measurable comment data.
Claims that would require live-chat timestamps or video analytics are
explicitly flagged as out of scope.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# ------------------------------------------------------------------
# Thresholds (tune as needed)
# ------------------------------------------------------------------

# A keyword must appear at least this many times to be "prominent"
_KW_PROMINENCE_THRESHOLD = 3

# A comment is "high engagement" if its likes are above this percentile
_HIGH_ENGAGEMENT_PERCENTILE = 90

# Minimum appearances to call an entity candidate "notable"
_ENTITY_MIN_COUNT = 3


class InsightGenerator:
    """Generate content strategy insights from comment analysis results."""

    def generate(
        self,
        df: pd.DataFrame,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Parameters
        ----------
        df:       Cleaned comment DataFrame.
        analysis: Output of CommentAnalyzer.analyze().

        Returns
        -------
        insights dict consumed by Reporter.
        """
        if df.empty:
            return _empty_insights()

        stats = analysis["stats"]
        keywords = analysis["keywords"]
        bigrams = analysis["bigrams"]
        sentiment_counts = analysis["sentiment_counts"]
        top_liked = analysis["top_liked"]
        entity_candidates = analysis["entity_candidates"]

        audience_profile = self._audience_emotional_profile(sentiment_counts, stats)
        top_topics = self._identify_top_topics(keywords, bigrams)
        notable_entities = self._notable_entities(entity_candidates)
        high_engagement_themes = self._high_engagement_themes(df, top_liked, keywords)
        recommendations = self._generate_recommendations(
            top_topics, notable_entities, audience_profile,
            high_engagement_themes, sentiment_counts, stats,
        )
        highlight_signals = self._highlight_signals(df, top_liked)
        marketing_angles = self._marketing_angles(
            top_topics, audience_profile, notable_entities
        )

        return {
            "audience_profile": audience_profile,
            "top_topics": top_topics,
            "notable_entities": notable_entities,
            "high_engagement_themes": high_engagement_themes,
            "recommendations": recommendations,
            "highlight_signals": highlight_signals,
            "marketing_angles": marketing_angles,
        }

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _audience_emotional_profile(
        self,
        sentiment_counts: dict[str, int],
        stats: dict,
    ) -> dict:
        total = stats["total_all"] or 1
        profile = {}
        for category, count in sentiment_counts.items():
            profile[category] = {
                "count": count,
                "pct": round(count / total * 100, 1),
            }
        # Dominant emotion
        if profile:
            dominant = max(profile, key=lambda k: profile[k]["count"])
            profile["_dominant"] = dominant
        return profile

    def _identify_top_topics(
        self,
        keywords: dict[str, int],
        bigrams: dict[str, int],
    ) -> list[dict]:
        """
        Return the most prominent topics as a ranked list.

        Combines unigrams and bigrams, deduplicating overlapping entries
        (e.g. "tiger" and "tiger woods" → keep "tiger woods" only if it
        scores high enough).
        """
        topics: list[dict] = []

        # Add bigrams first (more specific)
        for phrase, count in list(bigrams.items())[:20]:
            if count >= _KW_PROMINENCE_THRESHOLD:
                topics.append({"phrase": phrase, "count": count, "type": "phrase"})

        # Add unigrams not already covered by a bigram
        bigram_words: set[str] = set()
        for t in topics:
            bigram_words.update(t["phrase"].split())

        for word, count in list(keywords.items())[:30]:
            if count >= _KW_PROMINENCE_THRESHOLD and word not in bigram_words:
                topics.append({"phrase": word, "count": count, "type": "word"})

        topics.sort(key=lambda x: x["count"], reverse=True)
        return topics[:25]

    def _notable_entities(self, entity_candidates: list[str]) -> list[str]:
        """Return entity candidates that are likely names/brands."""
        return entity_candidates[:20]

    def _high_engagement_themes(
        self,
        df: pd.DataFrame,
        top_liked: list[dict],
        keywords: dict[str, int],
    ) -> list[str]:
        """
        Find themes that appear disproportionately in high-liked comments.

        A theme is "high engagement" if it shows up in the top-liked
        comments significantly more than in the general population.
        """
        if not top_liked or df.empty:
            return []

        # Collect tokens from high-engagement comments
        from src.data_processor import extract_text_tokens
        from src.analyzer import ALL_STOPWORDS

        he_tokens: list[str] = []
        for row in top_liked[:10]:
            he_tokens.extend([
                t for t in extract_text_tokens(row["text"])
                if t not in ALL_STOPWORDS and not t.isdigit() and len(t) > 2
            ])

        from collections import Counter
        he_counter = Counter(he_tokens)
        total_kw = sum(keywords.values()) or 1

        # A word is "high engagement" if its share among liked comments
        # is at least 2× its overall frequency share
        themes = []
        for word, he_count in he_counter.most_common(30):
            overall_share = keywords.get(word, 0) / total_kw
            he_share = he_count / max(len(he_tokens), 1)
            if he_count >= 2 and (overall_share == 0 or he_share / overall_share >= 1.5):
                themes.append(word)
            if len(themes) >= 10:
                break

        return themes

    def _generate_recommendations(
        self,
        top_topics: list[dict],
        notable_entities: list[str],
        audience_profile: dict,
        high_engagement_themes: list[str],
        sentiment_counts: dict[str, int],
        stats: dict,
    ) -> list[str]:
        recs: list[str] = []

        # 1. Most discussed topics → dedicated content
        if top_topics:
            top3 = [t["phrase"] for t in top_topics[:3]]
            recs.append(
                f"Create dedicated content around your most-discussed topics: "
                f"{', '.join(top3)}. These drove the most comment volume."
            )

        # 2. Notable entities (players, people, brands)
        if notable_entities:
            top_e = notable_entities[:4]
            recs.append(
                f"Consider spotlight videos or segments featuring: "
                f"{', '.join(top_e)}. These names appear repeatedly in comments "
                f"and signal strong audience interest."
            )

        # 3. High engagement themes → highlight clips
        if high_engagement_themes:
            recs.append(
                f"Turn moments around [{', '.join(high_engagement_themes[:4])}] "
                f"into short-form clips or highlight reels — these themes appear "
                f"disproportionately in your most-liked comments."
            )

        # 4. Emotional profile → content angle
        dominant = audience_profile.get("_dominant")
        if dominant == "cheering_support":
            recs.append(
                "Your audience skews heavily supportive/celebratory. "
                "Lean into triumphant moments, comeback narratives, and "
                "player-specific fan content to amplify this energy."
            )
        elif dominant == "surprise_excitement":
            recs.append(
                "Surprise and excitement dominate reactions. "
                "Prioritize unexpected moments, shocking shots, and "
                "'I can't believe this happened' style thumbnails and titles."
            )
        elif dominant == "criticism":
            recs.append(
                "A notable portion of comments express criticism or dissatisfaction. "
                "Consider a 'breakdown / reaction' format that acknowledges what "
                "went wrong — transparent analysis tends to convert critics into fans."
            )
        elif dominant == "positive":
            recs.append(
                "Strong positive sentiment overall. "
                "Capitalize on this goodwill with series continuations, "
                "merch tie-ins, or community challenges."
            )

        # 5. Reply-heavy → debate format
        total = stats["total_all"] or 1
        reply_ratio = stats["total_replies"] / total
        if reply_ratio > 0.4:
            recs.append(
                f"High reply ratio ({reply_ratio:.0%}) signals debate or "
                f"discussion. Formats like 'Hot Take', 'Controversial Opinion', "
                f"or 'Would You Rather' could perform well for this audience."
            )

        # 6. Low like average → discoverability problem
        if stats["avg_likes"] < 1.0 and stats["total_all"] > 50:
            recs.append(
                "Average likes per comment is low, suggesting the audience reads "
                "but doesn't interact deeply. Test pinned questions or polls to "
                "drive more active engagement."
            )

        # 7. Recurring format suggestion
        if len(top_topics) >= 5:
            recs.append(
                "The variety of discussed topics suggests strong demand for a "
                "regular recap or roundup format (weekly/monthly highlights, "
                "power rankings, or 'best of' compilations)."
            )

        # 8. Short-form / clip opportunity
        if high_engagement_themes or top_topics:
            clip_topics = (high_engagement_themes or [t["phrase"] for t in top_topics])[:3]
            recs.append(
                f"Short-form clip opportunity: extract standalone moments about "
                f"[{', '.join(clip_topics)}] as YouTube Shorts or Instagram Reels "
                f"to maximize reach with minimal additional production."
            )

        return recs

    def _highlight_signals(
        self,
        df: pd.DataFrame,
        top_liked: list[dict],
    ) -> list[dict]:
        """
        Surface the comments most likely to point at highlight-worthy moments.

        NOTE: Without live-chat timestamps or video chapter markers, we cannot
        pinpoint *when* in the video a moment occurred. These signals indicate
        *what* resonated, not *when*. True time-based analysis requires
        timestamped event data (live chat logs, video chapter metadata, etc.).
        """
        signals = []
        for row in top_liked[:10]:
            signals.append({
                "author": row["author"],
                "text_preview": row["text"][:120],
                "likes": row["like_count"],
                "note": (
                    "High-liked comment — likely references a notable moment. "
                    "Review manually to identify the corresponding scene."
                ),
            })
        return signals

    def _marketing_angles(
        self,
        top_topics: list[dict],
        audience_profile: dict,
        notable_entities: list[str],
    ) -> list[str]:
        angles: list[str] = []

        dominant = audience_profile.get("_dominant", "")

        if top_topics:
            t = top_topics[0]["phrase"]
            angles.append(
                f"'{t.title()}' appears to resonate most — "
                f"use it prominently in video titles, thumbnails, and ad copy."
            )

        if notable_entities:
            angles.append(
                f"Name-drop or feature {notable_entities[0]} in thumbnails/titles. "
                f"Fan loyalty around specific people drives click-through."
            )

        if dominant in ("cheering_support", "positive"):
            angles.append(
                "Audience sentiment is positive — ideal timing to introduce "
                "community features (membership, merch, Patreon) without friction."
            )

        if dominant == "surprise_excitement":
            angles.append(
                "Lead sponsor reads with an 'unbelievable moment' hook — "
                "excitement transfers to branded content when placed near peak moments."
            )

        angles.append(
            "Audience comment language (words, phrases) is a direct source of "
            "copy for video descriptions, end screens, and community posts."
        )

        return angles


def _empty_insights() -> dict:
    return {
        "audience_profile": {},
        "top_topics": [],
        "notable_entities": [],
        "high_engagement_themes": [],
        "recommendations": ["No comments found — nothing to analyze."],
        "highlight_signals": [],
        "marketing_angles": [],
    }
