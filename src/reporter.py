"""
Output reporter.

Writes all output files under the configured output directory:
  - comments_raw.csv
  - comments_cleaned.csv
  - top_keywords.csv
  - top_authors.csv
  - analysis_summary.md
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


class Reporter:
    """Write analysis results to files."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_all(
        self,
        df_raw: pd.DataFrame,
        df_cleaned: pd.DataFrame,
        analysis: dict[str, Any],
        insights: dict[str, Any],
        video_id: str,
    ) -> None:
        """Write every output file."""
        self._save_raw_comments(df_raw)
        self._save_cleaned_comments(df_cleaned)
        self._save_top_keywords(analysis)
        self._save_top_authors(analysis)
        self._save_markdown_report(df_raw, analysis, insights, video_id)

    # ------------------------------------------------------------------
    # CSV writers
    # ------------------------------------------------------------------

    def _save_raw_comments(self, df: pd.DataFrame) -> None:
        path = self.output_dir / "comments_raw.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  Saved: {path}  ({len(df)} rows)")

    def _save_cleaned_comments(self, df: pd.DataFrame) -> None:
        path = self.output_dir / "comments_cleaned.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  Saved: {path}  ({len(df)} rows)")

    def _save_top_keywords(self, analysis: dict) -> None:
        rows = []
        for word, count in analysis["keywords"].items():
            rows.append({"phrase": word, "count": count, "type": "unigram"})
        for phrase, count in analysis["bigrams"].items():
            rows.append({"phrase": phrase, "count": count, "type": "bigram"})
        df = pd.DataFrame(rows).sort_values("count", ascending=False)
        path = self.output_dir / "top_keywords.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  Saved: {path}  ({len(df)} rows)")

    def _save_top_authors(self, analysis: dict) -> None:
        df = pd.DataFrame(analysis["top_authors"])
        path = self.output_dir / "top_authors.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  Saved: {path}  ({len(df)} rows)")

    # ------------------------------------------------------------------
    # Markdown report
    # ------------------------------------------------------------------

    def _save_markdown_report(
        self,
        df_raw: pd.DataFrame,
        analysis: dict[str, Any],
        insights: dict[str, Any],
        video_id: str,
    ) -> None:
        md = self._build_markdown(df_raw, analysis, insights, video_id)
        path = self.output_dir / "analysis_summary.md"
        path.write_text(md, encoding="utf-8")
        print(f"  Saved: {path}")

    def _build_markdown(
        self,
        df_raw: pd.DataFrame,
        analysis: dict,
        insights: dict,
        video_id: str,
    ) -> str:
        stats = analysis["stats"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        video_url = (
            df_raw["video_url"].iloc[0]
            if not df_raw.empty and "video_url" in df_raw.columns
            else f"https://www.youtube.com/watch?v={video_id}"
        )

        sections: list[str] = []

        # ── Header ──────────────────────────────────────────────────
        sections.append(f"# YouTube Comment Analysis Report\n")
        sections.append(f"**Video ID:** `{video_id}`  ")
        sections.append(f"**URL:** {video_url}  ")
        sections.append(f"**Generated:** {now}\n")
        sections.append("---\n")

        # ── Basic Stats ─────────────────────────────────────────────
        sections.append("## Basic Statistics\n")
        sections.append(
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Top-level comments | {stats['total_comments']:,} |\n"
            f"| Replies | {stats['total_replies']:,} |\n"
            f"| Total (all) | {stats['total_all']:,} |\n"
            f"| Unique authors | {stats['unique_authors']:,} |\n"
            f"| Avg comment length | {stats['avg_length']:.1f} chars |\n"
            f"| Median comment length | {stats['median_length']:.1f} chars |\n"
            f"| Avg likes per comment | {stats['avg_likes']:.2f} |\n"
            f"| Total likes across all comments | {stats['total_likes']:,} |\n"
            f"| Most liked single comment | {stats['max_likes']:,} likes |\n"
        )

        # ── Top Keywords ────────────────────────────────────────────
        sections.append("\n## Top Keywords & Phrases\n")
        sections.append("### Most Frequent Words\n")
        sections.append("| Word | Count |\n|------|-------|\n")
        for word, count in list(analysis["keywords"].items())[:20]:
            sections.append(f"| {word} | {count} |\n")

        sections.append("\n### Most Frequent Bigrams (2-word phrases)\n")
        sections.append("| Phrase | Count |\n|--------|-------|\n")
        for phrase, count in list(analysis["bigrams"].items())[:15]:
            sections.append(f"| {phrase} | {count} |\n")

        # ── Notable Entities ────────────────────────────────────────
        if insights["notable_entities"]:
            sections.append("\n## Notable Names & Entities\n")
            sections.append(
                "These capitalized words appeared repeatedly — likely player names, "
                "brands, course names, or event names:\n\n"
            )
            sections.append(", ".join(f"`{e}`" for e in insights["notable_entities"]) + "\n")

        # ── Sentiment ───────────────────────────────────────────────
        sections.append("\n## Sentiment & Reaction Analysis\n")
        total = stats["total_all"] or 1
        sc = analysis["sentiment_counts"]
        if sc:
            sections.append("| Category | Comments | % of Total |\n|----------|----------|------------|\n")
            for cat, count in sorted(sc.items(), key=lambda x: -x[1]):
                pct = count / total * 100
                label = cat.replace("_", " ").title()
                sections.append(f"| {label} | {count} | {pct:.1f}% |\n")
        else:
            sections.append("_No sentiment signals detected._\n")

        dominant = insights["audience_profile"].get("_dominant", "")
        if dominant:
            sections.append(
                f"\n**Dominant emotional tone:** `{dominant.replace('_', ' ')}`\n"
            )

        # ── Top Liked Comments ───────────────────────────────────────
        sections.append("\n## Top Liked Comments\n")
        sections.append(
            "_High-like comments often point at the moments that resonated most. "
            "Review these manually to identify highlight-worthy scenes._\n\n"
        )
        for i, row in enumerate(analysis["top_liked"][:10], 1):
            preview = _truncate(row["text"], 200)
            sections.append(
                f"**{i}. [{row['like_count']} likes]** — *{row['author']}*\n\n"
                f"> {preview}\n\n"
            )

        # ── High Engagement Themes ───────────────────────────────────
        if insights["high_engagement_themes"]:
            sections.append("## High-Engagement Themes\n")
            sections.append(
                "These topics appear disproportionately in high-liked comments:\n\n"
            )
            for theme in insights["high_engagement_themes"]:
                sections.append(f"- `{theme}`\n")
            sections.append("\n")

        # ── Content Recommendations ──────────────────────────────────
        sections.append("## Content Strategy Recommendations\n")
        sections.append(
            "> These recommendations are derived from comment volume, keyword "
            "frequency, sentiment patterns, and like-weighted engagement signals.\n\n"
        )
        for i, rec in enumerate(insights["recommendations"], 1):
            wrapped = textwrap.fill(rec, width=90)
            sections.append(f"**{i}.** {wrapped}\n\n")

        # ── Highlight Signals ────────────────────────────────────────
        if insights["highlight_signals"]:
            sections.append("## Potential Highlight Signals\n")
            sections.append(
                "> ⚠️ **Limitation:** These are the most-liked comments. Without "
                "live-chat timestamps or video chapter data, we **cannot determine "
                "when** in the video the moment occurred. Use these as a manual "
                "review checklist — watch the video and match comments to scenes.\n\n"
            )
            for sig in insights["highlight_signals"][:5]:
                sections.append(
                    f"- **{sig['likes']} likes** — *{sig['author']}*: "
                    f"\"{sig['text_preview']}\"\n"
                )
            sections.append("\n")

        # ── Marketing Angles ─────────────────────────────────────────
        sections.append("## Marketing & Monetization Angles\n")
        for angle in insights["marketing_angles"]:
            sections.append(f"- {angle}\n")
        sections.append("\n")

        # ── Limitations ──────────────────────────────────────────────
        sections.append("## Limitations & Scope Notes\n")
        sections.append(
            "- **Live chat is out of scope.** Live chat replay for ended streams "
            "is not reliably accessible via the YouTube Data API v3 alone. "
            "Only regular video comments (below the video) are analyzed here.\n"
            "- **No timestamp-based spike analysis.** Comment-only data has no "
            "inherent video timestamp. True reaction-spike analysis requires live "
            "chat logs (with timestamps) or YouTube video chapter/analytics data.\n"
            "- **Sentiment is rule-based.** The lexicon-based approach is fast and "
            "requires no external models, but it cannot detect sarcasm, context "
            "shifts, or nuanced Korean expressions. For production use, consider "
            "a fine-tuned Korean-English sentiment model.\n"
            "- **Korean tokenization is simplified.** For accurate Korean morpheme "
            "analysis, integrate KoNLPy (requires Java) or use a cloud NLP API.\n"
            "- **Quota:** YouTube Data API v3 has a default quota of 10,000 units/day. "
            "Each `commentThreads.list` page costs ~1 unit. Large videos with many "
            "replies will consume more quota.\n"
        )

        return "".join(sections)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"
