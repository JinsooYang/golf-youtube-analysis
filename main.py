"""
YouTube Comment Analyzer — CLI entry point.

Usage:
    python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python main.py "https://youtu.be/VIDEO_ID" --max-comments 1000
    python main.py "https://www.youtube.com/live/VIDEO_ID" --no-replies
"""

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-comment-analyzer",
        description=(
            "Fetch YouTube comments via the Data API v3, "
            "save them to CSV, and generate content strategy insights."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  python main.py "https://youtu.be/dQw4w9WgXcQ" --max-comments 1000
  python main.py "https://www.youtube.com/live/Ef5fYM-WiPA" --no-replies
  python main.py "https://youtu.be/dQw4w9WgXcQ" --output-dir my_output
        """,
    )
    parser.add_argument(
        "url",
        help="YouTube video URL (watch, youtu.be, live, shorts)",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=500,
        metavar="N",
        help="Max top-level comments to fetch (default: 500, max API allows: 10000+)",
    )
    parser.add_argument(
        "--no-replies",
        action="store_true",
        default=False,
        help="Skip fetching reply comments (faster, lower quota usage)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        metavar="DIR",
        help="Directory to write output files (default: output/)",
    )
    return parser


def print_banner() -> None:
    print("\n" + "=" * 62)
    print("  YouTube Comment Analyzer")
    print("  Content strategy insights from audience comments")
    print("=" * 62)


def print_summary(
    analysis: dict,
    insights: dict,
    output_dir: Path,
) -> None:
    stats = analysis["stats"]

    print("\n" + "=" * 62)
    print("  RESULTS SUMMARY")
    print("=" * 62)
    print(f"  Total top-level comments : {stats['total_comments']:>6,}")
    print(f"  Total replies            : {stats['total_replies']:>6,}")
    print(f"  Unique authors           : {stats['unique_authors']:>6,}")
    print(f"  Avg comment length       : {stats['avg_length']:>8.1f} chars")
    print(f"  Avg likes per comment    : {stats['avg_likes']:>8.2f}")
    print(f"  Total likes collected    : {stats['total_likes']:>6,}")

    # Top keywords
    print("\n  Top 10 Keywords")
    print("  " + "-" * 40)
    for i, (word, count) in enumerate(list(analysis["keywords"].items())[:10], 1):
        bar = "█" * min(count, 30)
        print(f"  {i:>2}. {word:<18} {count:>4}  {bar}")

    # Sentiment
    if analysis["sentiment_counts"]:
        total = stats["total_all"] or 1
        print("\n  Sentiment Breakdown")
        print("  " + "-" * 40)
        for cat, count in sorted(
            analysis["sentiment_counts"].items(), key=lambda x: -x[1]
        ):
            pct = count / total * 100
            label = cat.replace("_", " ").title()
            bar = "█" * int(pct / 2)
            print(f"  {label:<26} {count:>4} ({pct:4.1f}%)  {bar}")

    # Notable entities
    if insights["notable_entities"]:
        print("\n  Notable Names / Entities")
        print("  " + "-" * 40)
        names = ", ".join(insights["notable_entities"][:8])
        print(f"  {names}")

    # Top liked comments
    print("\n  Top 3 Most Liked Comments")
    print("  " + "-" * 40)
    for i, row in enumerate(analysis["top_liked"][:3], 1):
        preview = row["text"][:72].replace("\n", " ")
        if len(row["text"]) > 72:
            preview += "…"
        print(f"  {i}. [{row['like_count']:>5} likes] {preview}")

    # Content recommendations
    print("\n  Content Recommendations")
    print("  " + "-" * 40)
    for i, rec in enumerate(insights["recommendations"][:4], 1):
        # Word-wrap at 55 chars
        words = rec.split()
        lines: list[str] = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 > 55:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
        print(f"  {i}. {lines[0]}")
        for line in lines[1:]:
            print(f"     {line}")
        print()

    # Output files
    print("  Output Files")
    print("  " + "-" * 40)
    for fname in [
        "comments_raw.csv",
        "comments_cleaned.csv",
        "top_keywords.csv",
        "top_authors.csv",
        "analysis_summary.md",
    ]:
        print(f"  {output_dir}/{fname}")

    print("=" * 62 + "\n")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    include_replies = not args.no_replies
    output_dir = Path(args.output_dir)

    print_banner()
    print(f"\n  URL           : {args.url}")
    print(f"  Max comments  : {args.max_comments}")
    print(f"  Include replies: {include_replies}")
    print(f"  Output dir    : {output_dir}/")

    # Late imports so startup errors (missing key etc.) surface clearly
    try:
        from src.youtube_client import YouTubeClient
    except EnvironmentError as exc:
        print(f"\n[Error] {exc}")
        return 1

    # ── Step 1: Extract video ID ──────────────────────────────────
    client = YouTubeClient()
    try:
        video_id = client.extract_video_id(args.url)
    except ValueError as exc:
        print(f"\n[Error] {exc}")
        return 1

    print(f"\n  Video ID      : {video_id}")

    # ── Step 2: Fetch comments ────────────────────────────────────
    print("\n[1/4] Fetching comments from YouTube API…")
    raw_comments = client.fetch_comments(
        video_id=video_id,
        max_results=args.max_comments,
        include_replies=include_replies,
    )

    if not raw_comments:
        print(
            "\n  No comments were retrieved. Possible reasons:\n"
            "  - API key is invalid or still set to the placeholder in .env\n"
            "  - Comments are disabled for this video\n"
            "  - Invalid video ID\n"
            "  - API quota exhausted\n"
        )
        return 1

    top_level = sum(1 for c in raw_comments if not c["is_reply"])
    replies = len(raw_comments) - top_level
    print(f"  Fetched {top_level} top-level comments + {replies} replies = {len(raw_comments)} total")

    # ── Step 3: Process ───────────────────────────────────────────
    print("\n[2/4] Processing and cleaning comments…")
    from src.data_processor import DataProcessor
    processor = DataProcessor()
    df_raw, df_cleaned = processor.process(raw_comments, video_id, args.url)
    print(f"  Raw rows: {len(df_raw)}  |  After cleaning: {len(df_cleaned)}")

    # ── Step 4: Analyze ───────────────────────────────────────────
    print("\n[3/4] Analyzing comments…")
    from src.analyzer import CommentAnalyzer
    analyzer = CommentAnalyzer()
    analysis = analyzer.analyze(df_cleaned)
    kw_count = len(analysis["keywords"])
    bg_count = len(analysis["bigrams"])
    print(f"  Keywords: {kw_count}  |  Bigrams: {bg_count}  |  Unique authors: {analysis['stats']['unique_authors']}")

    # ── Step 5: Generate insights & save ─────────────────────────
    print("\n[4/4] Generating insights and saving output…")
    from src.insight_generator import InsightGenerator
    from src.reporter import Reporter

    insight_gen = InsightGenerator()
    insights = insight_gen.generate(df_cleaned, analysis)

    reporter = Reporter(output_dir)
    reporter.save_all(df_raw, df_cleaned, analysis, insights, video_id)

    # ── Terminal summary ──────────────────────────────────────────
    print_summary(analysis, insights, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
