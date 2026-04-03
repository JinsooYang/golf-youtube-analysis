#!/usr/bin/env python3
"""
render_pipeline.py — Draft video rendering CLI.

Reads highlight_package.json and master_highlight_plan.json and produces:

  output/shorts_drafts/   — one .mp4 per Shorts concept
  output/highlight_drafts/ — master_highlight.mp4

Clips are auto-rendered only when matching_confidence ∈ {high, medium}
AND needs_manual_timestamp_mapping = False.  Everything else becomes a
red placeholder card that the editor replaces manually.

This is most useful when live-chat data with confirmed timestamps is
present.  With comment-only data (no live chat), most clip slots will be
placeholders — that is honest and expected behaviour.

Usage examples
--------------
# Auto-detect source video from lesson_VIDEO_ID/ and render both outputs
python render_pipeline.py --video lesson_Ef5fYM-WiPA/video.mp4

# Shorts only
python render_pipeline.py --video lesson_Ef5fYM-WiPA/video.mp4 --shorts-only

# Master highlight only
python render_pipeline.py --video lesson_Ef5fYM-WiPA/video.mp4 --highlight-only

# Full options
python render_pipeline.py \\
  --video       lesson_Ef5fYM-WiPA/video.mp4 \\
  --package     output/highlight_package.json \\
  --master-plan output/master_highlight_plan.json \\
  --output-dir  output \\
  --font        fonts/NanumGothic-Regular.ttf \\
  --width 1280 --height 720 \\
  --min-confidence medium \\
  --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_STEP_NUM = 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render-pipeline",
        description="Render draft Shorts and master highlight videos from highlight data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required
    p.add_argument(
        "--video", "-v",
        metavar="FILE",
        required=True,
        help="Path to source video file (e.g. lesson_VIDEO_ID/video.mp4)",
    )

    # Inputs
    p.add_argument(
        "--package",
        metavar="FILE",
        default="output/highlight_package.json",
        help="highlight_package.json (default: output/highlight_package.json)",
    )
    p.add_argument(
        "--master-plan",
        metavar="FILE",
        default="output/master_highlight_plan.json",
        help="master_highlight_plan.json (default: output/master_highlight_plan.json)",
    )

    # Output
    p.add_argument(
        "--output-dir", "-o",
        metavar="DIR",
        default="output",
        help="Output directory root (default: output/)",
    )
    p.add_argument(
        "--font",
        metavar="FILE",
        default=None,
        help="TTF font for Korean text overlays (auto-detected from fonts/ if omitted)",
    )
    p.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Output video width in pixels (default: 1280)",
    )
    p.add_argument(
        "--height",
        type=int,
        default=720,
        help="Output video height in pixels (default: 720)",
    )
    p.add_argument(
        "--min-confidence",
        choices=["high", "medium", "low"],
        default="medium",
        help=(
            "Minimum matching confidence required to auto-render a clip. "
            "Below this level a placeholder card is inserted instead. "
            "(default: medium)"
        ),
    )

    # Spike Shorts chat overlay
    p.add_argument(
        "--max-chat-lines",
        metavar="N",
        type=int,
        default=8,
        dest="max_chat_lines",
        help=(
            "Max chat messages visible at once in spike Short overlays. "
            "Default: 8."
        ),
    )
    p.add_argument(
        "--chat-update-interval",
        metavar="SEC",
        type=float,
        default=0.5,
        dest="chat_update_interval",
        help=(
            "Chat panel update granularity in seconds for spike Shorts. "
            "Smaller values = more frequent keyframes = smoother chat feed. "
            "Default: 0.5."
        ),
    )

    # Mode
    p.add_argument("--shorts-only",    action="store_true", help="Render Shorts drafts only")
    p.add_argument("--highlight-only", action="store_true", help="Render master highlight only")
    p.add_argument("--verbose",        action="store_true", help="Enable debug-level logging")

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    t0 = time.monotonic()

    # ── Validate source video ──────────────────────────────────────────────────
    video_path = Path(args.video)
    if not video_path.exists():
        logger.error("source video not found: %s", video_path)
        logger.error(
            "Run: ./youtube_extractor.sh 'https://www.youtube.com/watch?v=VIDEO_ID' "
            "to download the video first."
        )
        return 1

    # ── Late imports ───────────────────────────────────────────────────────────
    try:
        from src.render.ffmpeg_utils      import check_ffmpeg
        from src.render.shorts_renderer   import render_all_shorts
        from src.render.highlight_renderer import render_master_highlight
    except ImportError as exc:
        logger.error("import error: %s — run: pip install -r requirements.txt", exc)
        return 1

    # ── Check ffmpeg ───────────────────────────────────────────────────────────
    try:
        check_ffmpeg()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    # ── Load JSON inputs ───────────────────────────────────────────────────────
    package_path = Path(args.package)
    master_path  = Path(args.master_plan)

    package     = _load_json(package_path)
    master_plan = _load_json(master_path)

    if package is None and not args.highlight_only:
        logger.error(
            "could not load %s — run highlight_pipeline.py first", package_path
        )
        return 1

    if master_plan is None and not args.shorts_only:
        logger.error(
            "could not load %s — run highlight_pipeline.py first", master_path
        )
        return 1

    # ── Resolve font ───────────────────────────────────────────────────────────
    font_path = _resolve_font(args.font)
    if font_path:
        logger.info("font: %s", font_path)
    else:
        logger.warning(
            "no Korean font found in fonts/ — overlay text may not render correctly. "
            "Add NanumGothic-Regular.ttf to fonts/ or pass --font PATH."
        )

    output_dir = Path(args.output_dir)

    # ── Render ─────────────────────────────────────────────────────────────────
    shorts_results:  list[dict] = []
    highlight_result: dict | None = None

    if not args.highlight_only and package:
        _step("Rendering Shorts drafts")
        shorts_results = render_all_shorts(
            package              = package,
            source_video         = video_path,
            output_dir           = output_dir / "shorts_drafts",
            font_path            = font_path,
            min_confidence       = args.min_confidence,
            width                = args.width,
            height               = args.height,
            max_chat_lines       = args.max_chat_lines,
            chat_update_interval = args.chat_update_interval,
        )

    if not args.shorts_only and master_plan:
        _step("Rendering master highlight draft")
        highlight_result = render_master_highlight(
            master_plan    = master_plan,
            source_video   = video_path,
            output_dir     = output_dir / "highlight_drafts",
            font_path      = font_path,
            min_confidence = args.min_confidence,
            width          = args.width,
            height         = args.height,
        )

    elapsed = time.monotonic() - t0
    _print_summary(shorts_results, highlight_result, elapsed)
    return 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _step(label: str) -> None:
    global _STEP_NUM
    _STEP_NUM += 1
    print(f"\n[{_STEP_NUM}] {label}…")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        logger.warning("file not found: %s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("failed to parse %s: %s", path, exc)
        return None


def _resolve_font(explicit: str | None) -> Path | None:
    """Return a font path, preferring the explicit arg, then fonts/ auto-detect."""
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for candidate in [
        Path("fonts/NanumGothic-Regular.ttf"),
        Path("fonts/NanumGothic-Bold.ttf"),
        Path("fonts/AppleSDGothicNeo-Regular.ttf"),
    ]:
        if candidate.exists():
            return candidate
    return None


def _print_summary(
    shorts_results: list[dict],
    highlight_result: dict | None,
    elapsed: float,
) -> None:
    print()
    print("=" * 62)
    print("  렌더링 파이프라인 완료")
    print("=" * 62)
    print()

    if shorts_results:
        print(f"  Shorts 드래프트 ({len(shorts_results)}개):")
        for r in shorts_results:
            icon = "✓" if r["status"] == "ok" else ("⚠" if r["status"] == "placeholder_only" else "✗")
            p = Path(r["output_path"]) if r.get("output_path") else None
            size = f"{p.stat().st_size:,} bytes" if p and p.exists() else "생성 실패"
            print(
                f"    {icon} [{r['concept_id']:15s}]  "
                f"clips={r['clips_rendered']}  "
                f"placeholders={r['clips_skipped']}  "
                f"{size}"
            )
            if r.get("note"):
                print(f"       ↳ {r['note'][:90]}")
        print()

    if highlight_result:
        p = Path(highlight_result["output_path"]) if highlight_result.get("output_path") else None
        size = f"{p.stat().st_size:,} bytes" if p and p.exists() else "생성 실패"
        icon = "✓" if highlight_result.get("status") in ("ok", "cards_only") else "✗"
        print("  마스터 하이라이트:")
        print(f"    {icon} {highlight_result.get('output_path', '없음')}")
        print(
            f"       clips={highlight_result.get('clips_rendered', 0)}  "
            f"placeholders={highlight_result.get('clips_skipped', 0)}  "
            f"acts={highlight_result.get('acts_rendered', 0)}  "
            f"{size}"
        )
        if highlight_result.get("note"):
            print(f"       ↳ {highlight_result['note'][:90]}")
        print()

    # Explain placeholder behaviour
    total_ph = (
        sum(r.get("clips_skipped", 0) for r in shorts_results)
        + (highlight_result.get("clips_skipped", 0) if highlight_result else 0)
    )
    if total_ph > 0:
        print(
            f"  ⚠  {total_ph}개 플레이스홀더 — 일반 댓글은 타임스탬프가 없어 자동 클립 렌더링 불가.\n"
            "     편집 소프트웨어에서 빨간 카드 위치를 실제 클립으로 교체하세요."
        )
        print()

    print(f"  소요 시간: {elapsed:.1f}s")
    print()


if __name__ == "__main__":
    sys.exit(main())
