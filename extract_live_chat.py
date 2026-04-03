#!/usr/bin/env python3
"""
extract_live_chat.py — Live chat replay extraction CLI.

Attempts to extract the live chat replay from an ended YouTube livestream
using yt-dlp, then normalises the output into CSV/JSON for downstream use
in the highlight automation pipeline.

Exit codes
----------
  0   — extraction succeeded (some or all records written)
  1   — extraction failed or no replay available (see log for details)
  2   — bad arguments or missing dependency (yt-dlp not installed)

Usage examples
--------------
# Basic — extract and save to output/
python extract_live_chat.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Custom output directory
python extract_live_chat.py "https://youtu.be/VIDEO_ID" --output-dir results/

# Filter to highlight-relevant messages only (text + superchat, timestamped)
python extract_live_chat.py "https://youtu.be/VIDEO_ID" --highlight-only

# Verbose (debug logging)
python extract_live_chat.py "https://youtu.be/VIDEO_ID" --verbose

# Then feed into highlight pipeline
python highlight_pipeline.py \\
    --comments  output/comments_cleaned.csv \\
    --live-chat output/live_chat_normalized.csv \\
    --video-id  VIDEO_ID \\
    --players   이용희 공태현

Output files (all in --output-dir, default: output/)
-----------------------------------------------------
  live_chat_raw.json             parsed raw events (without yt-dlp internals)
  live_chat_normalized.csv       flat table, directly usable as --live-chat input
  live_chat_normalized.json      same data as JSON array
  live_chat_extract.log          extraction report with status, stats, next steps

Notes
-----
- Live chat replay is only available for ended livestreams where the creator
  has not disabled chat replay.
- With comment-only data (no live chat), highlight pipeline uses semantic matching
  and marks all clips as needs_manual_timestamp_mapping=True.
- With live chat, timestamp-based matching is used (confidence=high), enabling
  automatic clip rendering in render_pipeline.py.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="extract-live-chat",
        description=(
            "Extract live chat replay from an ended YouTube livestream. "
            "Outputs normalized CSV/JSON for use with highlight_pipeline.py."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "url",
        metavar="URL",
        help="YouTube video URL (ended livestream with chat replay)",
    )
    p.add_argument(
        "--output-dir", "-o",
        metavar="DIR",
        default="output",
        help="Output directory (default: output/)",
    )
    p.add_argument(
        "--highlight-only",
        action="store_true",
        help=(
            "Only save 'text' and 'superchat' messages with valid timestamps. "
            "Drops membership joins, paid stickers, and messages with no offset. "
            "Produces a smaller CSV better suited for the highlight pipeline."
        ),
    )
    p.add_argument(
        "--keep-raw",
        action="store_true",
        help="Copy the raw yt-dlp .live_chat.json file to output dir as well.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return p


# ── Main ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    t0 = time.monotonic()

    # ── Late imports ───────────────────────────────────────────────────────────
    try:
        from src.live_chat.extractor  import check_ytdlp, download_live_chat
        from src.live_chat.parser     import parse_live_chat_file
        from src.live_chat.normalizer import normalize_events, filter_for_highlight
        from src.live_chat.writer     import write_outputs, write_failure_log
    except ImportError as exc:
        logger.error("import error: %s — run: pip install -r requirements.txt", exc)
        return 2

    # ── Check yt-dlp ──────────────────────────────────────────────────────────
    try:
        check_ytdlp()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    output_dir = Path(args.output_dir)

    # ── Extract ────────────────────────────────────────────────────────────────
    _step("Extracting live chat replay")
    print(f"    URL: {args.url}")

    with tempfile.TemporaryDirectory(prefix="lc_extract_") as tmpdir:
        tmp_path = Path(tmpdir)

        result = download_live_chat(
            url      = args.url,
            work_dir = tmp_path,
        )

        _print_extraction_result(result)

        # ── Handle failure / no-replay ─────────────────────────────────────────
        if result.status in ("no_replay", "probe_failed", "ytdlp_missing"):
            write_failure_log(result, output_dir)
            logger.error(
                "Live chat extraction did not produce data. "
                "See output/live_chat_extract.log for details."
            )
            return 1

        if result.status == "download_failed":
            write_failure_log(result, output_dir)
            logger.error(
                "yt-dlp failed to download live chat. "
                "See output/live_chat_extract.log for details."
            )
            return 1

        # status is "ok" or "partial" — we have a file, try to parse it
        chat_file = result.chat_file
        if chat_file is None:
            logger.error("unexpected: extraction result has no chat_file path")
            write_failure_log(result, output_dir)
            return 1

        # Optionally copy raw file to output dir
        if args.keep_raw:
            raw_dest = output_dir / chat_file.name
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(chat_file), str(raw_dest))
            logger.info("raw chat file copied to %s", raw_dest)

        # ── Parse ──────────────────────────────────────────────────────────────
        _step("Parsing chat events")
        raw_events, parse_stats = parse_live_chat_file(chat_file)

        if not raw_events:
            logger.warning(
                "no events could be parsed from the chat file. "
                "The file may be empty or in an unexpected format."
            )
            write_failure_log(result, output_dir)
            return 1

        # ── Normalize ──────────────────────────────────────────────────────────
        _step("Normalizing events")
        records = normalize_events(
            raw_events = raw_events,
            video_id   = result.video_id,
            video_url  = result.video_url,
        )

        if args.highlight_only:
            from src.live_chat.normalizer import filter_for_highlight
            records = filter_for_highlight(records)
            if not records:
                logger.warning(
                    "no highlight-relevant records after filtering. "
                    "Consider running without --highlight-only to see all messages."
                )
                write_failure_log(result, output_dir)
                return 1

        # ── Write outputs ──────────────────────────────────────────────────────
        _step("Writing output files")
        written = write_outputs(
            records            = records,
            raw_events         = raw_events,
            extraction_result  = result,
            parse_stats        = parse_stats,
            output_dir         = output_dir,
        )

    elapsed = time.monotonic() - t0
    _print_summary(result, parse_stats, records, written, elapsed, args)
    return 0


# ── Printing helpers ───────────────────────────────────────────────────────────

_STEP_NUM = 0


def _step(label: str) -> None:
    global _STEP_NUM
    _STEP_NUM += 1
    print(f"\n[{_STEP_NUM}] {label}…")


def _print_extraction_result(result) -> None:
    status_display = {
        "ok":              "✓ 완료",
        "partial":         "⚠ 부분 성공",
        "no_replay":       "✗ 라이브 채팅 없음",
        "probe_failed":    "✗ 영상 정보 가져오기 실패",
        "download_failed": "✗ 다운로드 실패",
        "ytdlp_missing":   "✗ yt-dlp 없음",
        "error":           "✗ 오류",
    }
    icon = status_display.get(result.status, result.status)
    print(f"    영상:    {result.video_title or '(제목 없음)'}")
    print(f"    ID:      {result.video_id}")
    print(f"    라이브:  {'예' if result.was_live else '아니오' if result.was_live is False else '불명'}")
    print(f"    채팅:    {icon}")
    if result.message:
        print(f"    메시지:  {result.message}")


def _print_summary(result, stats, records, written, elapsed, args) -> None:
    print()
    print("=" * 60)
    print("  라이브 채팅 추출 완료")
    print("=" * 60)
    print()

    if stats:
        print(f"  파싱 통계:")
        print(f"    총 줄:          {stats.lines_read:,}")
        print(f"    이벤트 추출:    {stats.events_extracted:,}")
        if stats.events_by_type:
            for t, n in sorted(stats.events_by_type.items(), key=lambda x: -x[1]):
                print(f"      {t:<15} {n:,}")
        print()

    print(f"  정규화된 레코드: {len(records):,}")
    if args.highlight_only:
        print("  (--highlight-only: 타임스탬프 있는 text/superchat만 포함)")
    print()

    print("  생성된 파일:")
    for role, path in written.items():
        p = Path(path) if not isinstance(path, Path) else path
        size = f"{p.stat().st_size:,} bytes" if p.exists() else "없음"
        print(f"    {str(p):<55} {size}")
    print()

    vid_id = result.video_id
    if records and vid_id:
        print("  다음 단계 — 하이라이트 파이프라인에 연결:")
        print(f"    python highlight_pipeline.py \\")
        print(f"        --comments  output/comments_cleaned.csv \\")
        print(f"        --live-chat output/live_chat_normalized.csv \\")
        print(f"        --video-id  {vid_id}")
        print()

    print(f"  소요 시간: {elapsed:.1f}s")
    print()


if __name__ == "__main__":
    sys.exit(main())
