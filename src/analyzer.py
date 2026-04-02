"""
Core analysis engine.

Produces:
  - Basic statistics
  - Keyword / bigram frequency tables
  - Rule-based sentiment / reaction tagging
  - Top liked comments and top active authors

All heavy lifting is done with stdlib + pandas; no NLTK or spaCy required.
Korean-English mixed comments are handled correctly because we rely on
unicode character properties rather than ASCII-only word boundaries.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

from src.data_processor import extract_text_tokens


# ------------------------------------------------------------------
# Stopwords
# ------------------------------------------------------------------

EN_STOPWORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "it", "its", "this", "that", "these", "those", "i", "me", "my", "we",
    "our", "you", "your", "he", "him", "his", "she", "her", "they", "them",
    "their", "what", "which", "who", "whom", "how", "when", "where", "why",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "same", "so", "than", "too", "very",
    "just", "also", "about", "up", "out", "then", "there", "here", "now",
    "like", "know", "think", "see", "get", "got", "go", "going", "come",
    "one", "two", "time", "year", "make", "way", "even", "well", "back",
    "still", "good", "new", "first", "last", "long", "great", "little",
    "own", "right", "old", "big", "high", "great",
    # common YouTube-comment filler
    "lol", "lmao", "haha", "hahaha", "im", "ive", "its", "dont", "cant",
    "thats", "youre", "theyre", "wont", "wasnt", "didnt", "doesnt",
}

KO_STOPWORDS: set[str] = {
    # particles / auxiliary
    "이", "가", "을", "를", "은", "는", "에", "에서", "도", "의", "와", "과",
    "로", "으로", "이다", "이고", "에게", "한테", "께", "보다", "처럼",
    # common verbs/adjectives as stop-tokens after simple splitting
    "있다", "없다", "하다", "이다", "되다", "같다", "그", "저", "이것",
    "그것", "저것", "거", "것", "수", "좀", "더", "제", "그냥", "진짜",
    "너무", "정말", "또", "다", "잘", "못", "안", "왜", "어",
}

ALL_STOPWORDS = EN_STOPWORDS | KO_STOPWORDS


# ------------------------------------------------------------------
# Sentiment / reaction lexicons
# ------------------------------------------------------------------

SENTIMENT_LEXICONS: dict[str, list[str]] = {
    "positive": [
        # English
        "amazing", "awesome", "beautiful", "best", "brilliant", "excellent",
        "fantastic", "good", "great", "incredible", "love", "loved", "lovely",
        "nice", "outstanding", "perfect", "superb", "wonderful", "wow",
        "impressive", "stunning", "unbelievable", "insane", "goat", "legend",
        "legendary", "clutch", "epic",
        # Korean
        "좋아", "최고", "대박", "짱", "완벽", "훌륭", "멋지", "최강", "굿",
        "레전드", "갓", "미쳤다", "미쳐", "대단", "역시",
    ],
    "negative": [
        # English
        "awful", "bad", "boring", "disappointing", "disgusting", "dull",
        "frustrating", "horrible", "mediocre", "poor", "terrible", "trash",
        "waste", "worst", "wrong", "disappointed", "sucks", "rip",
        # Korean
        "별로", "실망", "최악", "형편없", "아쉽", "못해", "진짜별로",
        "노재미", "노잼",
    ],
    "surprise_excitement": [
        # English
        "omg", "whoa", "no way", "unreal", "crazy", "insane", "wild",
        "mind blown", "mindblown", "shocked", "stunning",
        # Korean
        "헐", "와", "대박", "미쳤", "실화", "진심", "어머",
    ],
    "cheering_support": [
        # English
        "go", "lets go", "let's go", "come on", "you can do it", "fighting",
        "support", "cheer", "rooting", "believe", "keep going", "keep it up",
        # Korean
        "화이팅", "파이팅", "응원", "힘내", "기대", "잘해",
    ],
    "criticism": [
        # English
        "should have", "could have", "would have", "missed", "wasted",
        "overrated", "overhyped", "inconsistent", "mistake", "error",
        "blunder", "why didnt", "why didn't", "poor shot", "dropped",
        # Korean
        "아쉽다", "왜저래", "실수", "왜이래", "별로다",
    ],
}

# Pre-compile lowercase versions for fast matching
_COMPILED_LEXICONS: dict[str, list[str]] = {
    cat: [kw.lower() for kw in kws]
    for cat, kws in SENTIMENT_LEXICONS.items()
}


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------

class CommentAnalyzer:
    """Analyze a cleaned comment DataFrame and return an analysis dict."""

    def analyze(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Run the full analysis pipeline.

        Returns a nested dict consumed by InsightGenerator and Reporter.
        """
        if df.empty:
            return _empty_analysis()

        stats = self._compute_stats(df)
        keywords, bigrams = self._extract_keywords(df)
        sentiment_map, sentiment_counts = self._tag_sentiment(df)
        top_liked = self._top_liked(df, n=20)
        top_authors = self._top_authors(df, n=30)
        entity_candidates = self._extract_entity_candidates(df)

        return {
            "stats": stats,
            "keywords": keywords,
            "bigrams": bigrams,
            "sentiment_map": sentiment_map,
            "sentiment_counts": sentiment_counts,
            "top_liked": top_liked,
            "top_authors": top_authors,
            "entity_candidates": entity_candidates,
        }

    # ------------------------------------------------------------------

    def _compute_stats(self, df: pd.DataFrame) -> dict:
        top_level = df[~df["is_reply"]]
        replies = df[df["is_reply"]]
        df["text_len"] = df["text"].str.len()

        return {
            "total_comments": len(top_level),
            "total_replies": len(replies),
            "total_all": len(df),
            "unique_authors": df["author"].nunique(),
            "avg_length": df["text_len"].mean(),
            "median_length": df["text_len"].median(),
            "avg_likes": df["like_count"].mean(),
            "total_likes": int(df["like_count"].sum()),
            "max_likes": int(df["like_count"].max()),
        }

    def _extract_keywords(
        self,
        df: pd.DataFrame,
        top_n: int = 100,
    ) -> tuple[dict[str, int], dict[str, int]]:
        unigram_counter: Counter = Counter()
        bigram_counter: Counter = Counter()

        for text in df["text"]:
            tokens = [
                t for t in extract_text_tokens(text)
                if t not in ALL_STOPWORDS and not t.isdigit()
            ]
            unigram_counter.update(tokens)
            # bigrams
            for a, b in zip(tokens, tokens[1:]):
                bigram_counter[f"{a} {b}"] += 1

        keywords = dict(unigram_counter.most_common(top_n))
        bigrams = dict(bigram_counter.most_common(top_n))
        return keywords, bigrams

    def _tag_sentiment(
        self,
        df: pd.DataFrame,
    ) -> tuple[dict[str, list[str]], dict[str, int]]:
        """
        Assign one or more sentiment/reaction categories to each comment.

        Returns
        -------
        sentiment_map:    comment_id -> list of category strings
        sentiment_counts: category -> total count across all comments
        """
        sentiment_map: dict[str, list[str]] = {}
        totals: Counter = Counter()

        for _, row in df.iterrows():
            text_lower = row["text"].lower()
            tags = []
            for category, keywords in _COMPILED_LEXICONS.items():
                if any(kw in text_lower for kw in keywords):
                    tags.append(category)
            sentiment_map[row["comment_id"]] = tags
            totals.update(tags)

        return sentiment_map, dict(totals)

    def _top_liked(self, df: pd.DataFrame, n: int = 20) -> list[dict]:
        top = (
            df[df["like_count"] > 0]
            .nlargest(n, "like_count")[
                ["comment_id", "author", "text", "like_count", "is_reply"]
            ]
        )
        return top.to_dict("records")

    def _top_authors(self, df: pd.DataFrame, n: int = 30) -> list[dict]:
        agg = (
            df.groupby("author")
            .agg(
                comment_count=("comment_id", "count"),
                total_likes=("like_count", "sum"),
                avg_length=("text", lambda s: s.str.len().mean()),
            )
            .reset_index()
            .sort_values("comment_count", ascending=False)
            .head(n)
        )
        agg["avg_length"] = agg["avg_length"].round(1)
        return agg.to_dict("records")

    def _extract_entity_candidates(self, df: pd.DataFrame) -> list[str]:
        """
        Heuristically identify potential named entities (proper nouns).

        Strategy: collect tokens that start with a capital letter in the
        original (uncased) text, appear >= 3 times, and are not stop words.
        These are strong candidates for player names, brands, and locations.
        """
        counter: Counter = Counter()
        cap_word_re = re.compile(r"\b([A-Z][a-z]{1,})\b")

        for text in df["text"]:
            for match in cap_word_re.finditer(text):
                word = match.group(1)
                if word.lower() not in ALL_STOPWORDS:
                    counter[word] += 1

        return [word for word, count in counter.most_common(50) if count >= 3]


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _empty_analysis() -> dict:
    return {
        "stats": {
            "total_comments": 0, "total_replies": 0, "total_all": 0,
            "unique_authors": 0, "avg_length": 0.0, "median_length": 0.0,
            "avg_likes": 0.0, "total_likes": 0, "max_likes": 0,
        },
        "keywords": {},
        "bigrams": {},
        "sentiment_map": {},
        "sentiment_counts": {},
        "top_liked": [],
        "top_authors": [],
        "entity_candidates": [],
    }
