#!/usr/bin/env python3
"""
highlight_pipeline.py — Comment-driven highlight automation pipeline.

Takes the outputs of youtube_extractor.sh (segments.json) and main.py
(comments_cleaned.csv), and optionally a live-chat CSV, then produces
structured highlight data for Shorts / highlight video production.

Usage examples
--------------
# Minimal — comments only, no segment file
python highlight_pipeline.py \\
    --comments output/comments_cleaned.csv \\
    --video-id Ef5fYM-WiPA

# With subtitle segments from youtube_extractor.sh
python highlight_pipeline.py \\
    --comments  output/comments_cleaned.csv \\
    --segments  lesson_Ef5fYM-WiPA/segments.json \\
    --video-id  Ef5fYM-WiPA \\
    --players   이용희 공태현 안예인 고수진

# With live chat (when available)
python highlight_pipeline.py \\
    --comments   output/comments_cleaned.csv \\
    --segments   lesson_Ef5fYM-WiPA/segments.json \\
    --live-chat  live_chat_Ef5fYM-WiPA.csv \\
    --video-id   Ef5fYM-WiPA \\
    --players    이용희 공태현 안예인 고수진

Output files (all in --output-dir, default: output/)
-----------------------------------------------------
  highlight_comment_candidates.csv
  highlight_comment_candidates.json
  highlight_moment_candidates.csv
  highlight_package.json
  shorts_script.md
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="highlight-pipeline",
        description=(
            "Comment-driven highlight automation pipeline. "
            "Reads comment CSV + optional segments.json and live-chat CSV, "
            "outputs structured editing data."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Inputs
    p.add_argument(
        "--comments", "-c",
        metavar="FILE",
        default="output/comments_cleaned.csv",
        help="Path to comments CSV (default: output/comments_cleaned.csv)",
    )
    p.add_argument(
        "--segments", "-s",
        metavar="FILE",
        default=None,
        help=(
            "Path to segments.json produced by youtube_extractor.sh "
            "(e.g. lesson_VIDEO_ID/segments.json). "
            "Optional — if omitted, matching is skipped."
        ),
    )
    p.add_argument(
        "--live-chat", "-l",
        metavar="FILE",
        default="output/live_chat_normalized.csv",
        dest="live_chat",
        help=(
            "Path to live-chat CSV with timestamps "
            "(default: output/live_chat_normalized.csv). "
            "Optional — enables timestamp-based matching when present. "
            "If the file does not exist the pipeline falls back to comment-only mode. "
            "Expected columns: timestamp_seconds (or time_seconds), text, author."
        ),
    )

    # Metadata
    p.add_argument(
        "--video-id",
        metavar="ID",
        default="",
        help="YouTube video ID (for metadata and URL generation in outputs).",
    )
    p.add_argument(
        "--video-title",
        metavar="TITLE",
        default="",
        help="Video title for report headers.",
    )
    p.add_argument(
        "--players",
        metavar="NAME",
        nargs="+",
        default=None,
        help=(
            "Known player names to detect in comments. "
            "Separate by spaces. "
            "Example: --players 이용희 공태현 안예인 고수진"
        ),
    )

    # Output
    p.add_argument(
        "--output-dir", "-o",
        metavar="DIR",
        default="output",
        help="Output directory (default: output/)",
    )
    p.add_argument(
        "--min-likes",
        metavar="N",
        type=int,
        default=0,
        help="Filter out comments with fewer than N likes before processing (default: 0).",
    )
    # Clip windows (live chat direct mode — used by matcher for all comment→clip matching)
    p.add_argument(
        "--pre-roll",
        metavar="SEC",
        type=float,
        default=10.0,
        help=(
            "Seconds before a live-chat reaction timestamp to start the clip window "
            "when no subtitle segment is available. Default: 10."
        ),
    )
    p.add_argument(
        "--post-roll",
        metavar="SEC",
        type=float,
        default=20.0,
        help=(
            "Seconds after a live-chat reaction timestamp to end the clip window "
            "when no subtitle segment is available. Default: 20."
        ),
    )

    # Spike-driven Shorts clip window (independent of --pre-roll / --post-roll)
    p.add_argument(
        "--shorts-pre-roll",
        metavar="SEC",
        type=float,
        default=10.0,
        dest="shorts_pre_roll",
        help=(
            "Seconds before spike anchor to start each Shorts clip. "
            "Default: 10.  (spike-driven Shorts mode only)"
        ),
    )
    p.add_argument(
        "--shorts-post-roll",
        metavar="SEC",
        type=float,
        default=5.0,
        dest="shorts_post_roll",
        help=(
            "Seconds after spike anchor to end each Shorts clip. "
            "Default: 5.  Total default Shorts clip = 15 s. "
            "(spike-driven Shorts mode only)"
        ),
    )

    p.add_argument(
        "--max-window-messages",
        metavar="N",
        type=int,
        default=50,
        dest="max_window_messages",
        help=(
            "Max live chat messages to include per spike Short's rolling chat "
            "overlay. These are the messages from the spike detection window "
            "that appear in the final clip. Default: 50."
        ),
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging.",
    )

    return p


# ── Main ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    t0 = time.monotonic()

    # Late imports — keep startup fast and surface missing-package errors cleanly
    try:
        from src.highlight.loaders   import load_segments, load_comments, load_live_chat
        from src.highlight.packager  import build_package
        from src.highlight.writer    import write_outputs
    except ImportError as exc:
        logger.error("import error: %s — run: pip install -r requirements.txt", exc)
        return 1

    # ── Step 1: Load inputs ────────────────────────────────────────────────────
    _step("Loading inputs")

    # Auto-detect segments.json from youtube_extractor.sh output when
    # --segments is not given explicitly but --video-id is known.
    if args.segments is None and args.video_id:
        candidate = Path(f"lesson_{args.video_id}") / "segments.json"
        if candidate.exists():
            args.segments = str(candidate)
            logger.info("auto-detected segments file: %s", candidate)
        else:
            logger.info(
                "no segments file found at %s — "
                "run youtube_extractor.sh first to enable segment matching, "
                "or pass --segments explicitly.",
                candidate,
            )

    segments = load_segments(args.segments) if args.segments else []
    if not segments and args.segments:
        logger.warning(
            "segments file '%s' could not be loaded — matching will be skipped.",
            args.segments,
        )

    comments_df = load_comments(args.comments)
    if comments_df.empty:
        logger.error(
            "no comments loaded from '%s'. "
            "Run main.py first to fetch and save comments.",
            args.comments,
        )
        return 1

    live_chat_df = load_live_chat(args.live_chat)

    # Apply --min-likes filter
    if args.min_likes > 0:
        before = len(comments_df)
        comments_df = comments_df[comments_df["like_count"] >= args.min_likes].reset_index(drop=True)
        logger.info("--min-likes %d: kept %d / %d comments", args.min_likes, len(comments_df), before)

    _print_load_summary(args, comments_df, live_chat_df, segments)

    # ── Step 2: Build package ──────────────────────────────────────────────────
    _step("Running highlight pipeline")

    package = build_package(
        comments_df         = comments_df,
        segments            = segments,
        player_names        = args.players,
        live_chat_df        = live_chat_df,
        video_id            = args.video_id,
        video_title         = args.video_title,
        pre_roll            = args.pre_roll,
        post_roll           = args.post_roll,
        shorts_pre_roll     = args.shorts_pre_roll,
        shorts_post_roll    = args.shorts_post_roll,
        max_window_messages = args.max_window_messages,
    )

    n_comments = len(package["highlight_comments"])
    n_moments  = len(package["highlight_moments"])
    n_spikes   = len(package.get("spike_moments", []))
    n_seqs     = len(package["shorts_sequences"])
    master_plan = package.get("master_plan") or {}
    n_acts     = len(master_plan.get("acts", []))
    n_turning  = len(master_plan.get("turning_points", []))

    logger.info(
        "pipeline complete: %d comment candidates, %d moment candidates, "
        "%d spike moments, %d Shorts sequences, %d master-plan acts, %d turning points",
        n_comments, n_moments, n_spikes, n_seqs, n_acts, n_turning,
    )

    # ── Step 3: Write outputs ──────────────────────────────────────────────────
    _step("Writing output files")

    written = write_outputs(package, args.output_dir)

    elapsed = time.monotonic() - t0

    # ── Terminal summary ───────────────────────────────────────────────────────
    _print_summary(package, written, elapsed)

    return 0


# ── Printing helpers ───────────────────────────────────────────────────────────

_STEP_NUM = 0

def _step(label: str) -> None:
    global _STEP_NUM
    _STEP_NUM += 1
    print(f"\n[{_STEP_NUM}] {label}…")


def _print_load_summary(
    args: argparse.Namespace,
    comments_df,
    live_chat_df,
    segments: list,
) -> None:
    print(f"    댓글:       {len(comments_df)} rows  ({args.comments})")
    if live_chat_df is not None:
        print(f"    라이브채팅: {len(live_chat_df)} rows  ({args.live_chat})")
        if not segments:
            print(f"    매칭 모드:  라이브 채팅 타임스탬프 직접 (±{args.pre_roll}s/{args.post_roll}s)")
        print(f"    Shorts 클립: spike_time −{args.shorts_pre_roll}s / +{args.shorts_post_roll}s "
              f"= {args.shorts_pre_roll + args.shorts_post_roll}s")
    else:
        print(f"    라이브채팅: 없음 — 댓글 전용 모드 (타임스탬프 매칭 불가)")
    print(f"    세그먼트:   {len(segments)} segments  ({args.segments or '없음'})")
    if args.players:
        print(f"    선수 목록:  {', '.join(args.players)}")


def _print_summary(package: dict, written: dict, elapsed: float) -> None:
    meta        = package.get("meta", {})
    comments    = package.get("highlight_comments", [])
    moments     = package.get("highlight_moments", [])
    sequences   = package.get("shorts_sequences", [])
    master_plan = package.get("master_plan") or {}

    has_segments     = meta.get("segments_loaded", 0) > 0
    has_chat         = meta.get("has_live_chat", False)
    lc_timing_mode   = meta.get("live_chat_timing_mode", False)
    spike_count      = meta.get("spike_moments_detected", 0)
    pre_roll         = meta.get("pre_roll", 10.0)
    post_roll        = meta.get("post_roll", 20.0)

    print()
    print("=" * 60)
    print("  하이라이트 파이프라인 완료")
    print("=" * 60)
    print()

    # Category breakdown
    from collections import Counter
    cats = Counter(r["category"] for r in comments)
    print("  카테고리별 후보 댓글:")
    for cat, cnt in cats.most_common():
        bar = "█" * min(cnt, 20)
        print(f"    {cat:<15} {bar:20s} {cnt}")
    print()

    # Top 5 by priority_score
    print("  우선순위 상위 5개 댓글:")
    for i, r in enumerate(comments[:5], 1):
        preview = r["text"][:55].replace("\n", " ")
        print(f"    {i}. [{r['likes']:>3} likes] [{r['category']:>13}]"
              f" score={r['priority_score']:>5.1f}  {preview}")
    print()

    # Matching stats
    if lc_timing_mode:
        lc_recs   = [r for r in comments if r["source_type"] == "live_chat"]
        renderable = sum(
            1 for r in lc_recs
            if r["matching_confidence"] in ("high", "medium")
            and not r["needs_manual_timestamp_mapping"]
        )
        print(f"  라이브 채팅 타임스탬프 모드:")
        print(f"    클립 앵커:      pre={pre_roll}s / post={post_roll}s")
        print(f"    라이브 채팅:    {len(lc_recs)} 메시지 처리됨")
        print(f"    렌더 가능 클립: {renderable} (high/medium confidence)")
        if spike_count:
            print(f"    스파이크 순간:  {spike_count}개 감지됨")
    elif has_segments:
        matched   = sum(1 for r in comments if r["matched_segment_id"])
        unmatched = len(comments) - matched
        high_conf = sum(1 for r in comments if r["matching_confidence"] == "high")
        med_conf  = sum(1 for r in comments if r["matching_confidence"] == "medium")
        print(f"  세그먼트 매칭:  {matched}/{len(comments)} 댓글 매칭됨")
        print(f"                  high={high_conf}  medium={med_conf}  기타={unmatched}")
        if not has_chat:
            print("  ⚠  일반 댓글은 타임스탬프 없음 — 모든 매칭은 수동 확인 필요")
    else:
        print("  ⚠  세그먼트 없음 — 구간 매칭 건너뜀")
    print()

    # Output files
    print("  생성된 파일:")
    for role, path in written.items():
        size = Path(path).stat().st_size if Path(path).exists() else 0
        print(f"    {str(path):<55} {size:>7,} bytes")
    print()
    print(f"  소요 시간: {elapsed:.2f}s")
    print()

    # Shorts concepts
    if sequences:
        seq_type = sequences[0].get("sequence_type", "concept")
        type_label = "스파이크 기반" if seq_type == "spike" else "카테고리 기반"
        print(f"  Shorts 시퀀스 ({len(sequences)}개 · {type_label}):")
        for seq in sequences:
            if seq.get("sequence_type") == "spike":
                anchor  = seq.get("spike_anchor_time", "?")
                dur     = seq.get("estimated_duration_sec", "?")
                n_msgs  = len(seq.get("rolling_chat_messages", []))
                print(f"    • [{seq['concept_id']}] {seq['title'][:50]}")
                print(f"      → 앵커 {anchor}s · 롤링 채팅 {n_msgs}개 · ~{dur}초")
            else:
                n_clips = len(seq.get("clip_sequence", []))
                n_ov    = len(seq.get("overlays", []))
                print(f"    • [{seq['concept_id']}] {seq['title'][:50]}")
                print(f"      → 클립 {n_clips}개, 오버레이 {n_ov}개, ~{seq.get('estimated_duration_sec')}초")
        print()

    # Master highlight plan
    acts         = master_plan.get("acts", [])
    turning_pts  = master_plan.get("turning_points", [])
    player_arcs  = master_plan.get("player_arcs", [])
    title_suggs  = master_plan.get("title_suggestions", [])
    if acts:
        print(f"  마스터 하이라이트 플랜:")
        print(f"    서사 막 수:     {len(acts)}막")
        print(f"    전환점:        {len(turning_pts)}개")
        print(f"    선수 아크:     {len(player_arcs)}명")
        if title_suggs:
            print(f"    제목 후보 1:   {title_suggs[0]}")
        opening = master_plan.get("opening_hook")
        if opening:
            preview = opening["text"][:55].replace("\n", " ")
            print(f"    오프닝 훅:     [{opening['category']}] {preview}…")
        print()


if __name__ == "__main__":
    sys.exit(main())
