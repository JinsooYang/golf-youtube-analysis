"""
extractor.py — yt-dlp subprocess wrapper for live chat replay extraction.

Two-stage approach:
  1. probe_video_info(url)       — run yt-dlp --dump-json to get video metadata
                                   and check whether live_chat subtitle exists.
  2. download_live_chat(url, …)  — run yt-dlp --write-subs --sub-langs live_chat
                                   to download the raw JSONL file.

Both stages surface clear status codes and messages so the CLI can report
exactly what happened without guessing.

Status codes
------------
  "ok"               — extraction succeeded, chat file written
  "no_replay"        — video has no live chat replay (not a live archive,
                        or chat replay was disabled by the creator)
  "partial"          — yt-dlp ran but the output file is suspiciously small;
                        replay may be incomplete
  "probe_failed"     — yt-dlp could not fetch video metadata
  "download_failed"  — yt-dlp ran but did not produce a chat file
  "ytdlp_missing"    — yt-dlp not installed or not on PATH
  "error"            — unexpected exception
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum file size to be considered a real chat download (bytes).
# A single-line header from a failed attempt is ~200 bytes.
MIN_CHAT_FILE_BYTES = 500


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    status: str                         # see module docstring
    chat_file: Optional[Path] = None    # path to raw .live_chat.json file
    video_id: str = ""
    video_title: str = ""
    video_url: str = ""
    was_live: Optional[bool] = None     # True if video is/was a live stream
    has_live_chat_subtitle: Optional[bool] = None  # True if yt-dlp lists live_chat
    message: str = ""                   # human-readable status detail
    stderr: str = ""                    # last 500 chars of yt-dlp stderr (for debug)
    elapsed_seconds: float = 0.0


# ── Public API ─────────────────────────────────────────────────────────────────

def check_ytdlp() -> None:
    """Raise RuntimeError if yt-dlp is not on PATH."""
    try:
        r = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            raise RuntimeError(f"yt-dlp --version returned {r.returncode}")
        logger.debug("yt-dlp version: %s", r.stdout.strip())
    except FileNotFoundError:
        raise RuntimeError(
            "yt-dlp not found on PATH.\n"
            "Install: pip install yt-dlp  (or: brew install yt-dlp)"
        )


def probe_video_info(url: str) -> dict:
    """
    Fetch video metadata via yt-dlp --dump-json.

    Returns the parsed JSON dict on success.
    Raises RuntimeError if yt-dlp fails or output is not parseable JSON.

    Useful fields in the result:
      id, title, was_live, is_live, duration,
      subtitles          — dict of lang → list of format dicts
      automatic_captions — same; live_chat may appear here instead
    """
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        url,
    ]
    logger.debug("probe: %s", " ".join(cmd))
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp probe failed (exit {result.returncode}).\n"
            f"stderr: {result.stderr[-500:]}"
        )

    # yt-dlp --dump-json may output multiple JSON objects (for playlists).
    # We only want the first one.
    first_line = result.stdout.strip().split("\n")[0]
    try:
        info = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"yt-dlp output is not valid JSON: {exc}")

    logger.debug("probe OK in %.1fs — id=%s was_live=%s", elapsed, info.get("id"), info.get("was_live"))
    return info


def download_live_chat(
    url: str,
    work_dir: Path,
    video_id: str = "",
) -> ExtractionResult:
    """
    Attempt to download the live chat replay for a YouTube video.

    Writes the raw JSONL file to work_dir and returns an ExtractionResult.
    The caller is responsible for copying the file to the final output location
    if desired.

    Parameters
    ----------
    url       : YouTube video URL
    work_dir  : directory to write the raw chat file (should be a temp or output dir)
    video_id  : optional hint; used only for logging
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()

    # ── Stage 1: probe metadata ────────────────────────────────────────────────
    logger.info("probing video metadata…")
    try:
        info = probe_video_info(url)
    except RuntimeError as exc:
        return ExtractionResult(
            status="probe_failed",
            message=str(exc),
            elapsed_seconds=time.monotonic() - t0,
        )

    vid_id    = info.get("id", video_id)
    vid_title = info.get("title", "")
    was_live  = info.get("was_live", None)
    is_live   = info.get("is_live", False)

    # Check for live_chat in subtitles or automatic_captions
    subs      = info.get("subtitles", {}) or {}
    auto_caps = info.get("automatic_captions", {}) or {}
    has_lc    = "live_chat" in subs or "live_chat" in auto_caps

    logger.info(
        "video: %s | was_live=%s | is_live=%s | has_live_chat_subtitle=%s",
        vid_id, was_live, is_live, has_lc,
    )

    if not has_lc:
        msg = (
            "No live chat replay found in video metadata. "
        )
        if was_live is False:
            msg += "This video does not appear to be a live stream archive."
        elif was_live is True:
            msg += (
                "This was a live stream but live chat replay appears to be "
                "disabled or unavailable (common for older streams or when "
                "the creator has turned it off)."
            )
        else:
            msg += (
                "yt-dlp reports no live_chat subtitle track. "
                "The video may not be a live stream, or replay chat may be unavailable."
            )
        return ExtractionResult(
            status         = "no_replay",
            video_id       = vid_id,
            video_title    = vid_title,
            video_url      = url,
            was_live       = was_live,
            has_live_chat_subtitle = False,
            message        = msg,
            elapsed_seconds = time.monotonic() - t0,
        )

    # ── Stage 2: download live chat ────────────────────────────────────────────
    # Use %(id)s so the output filename is predictable: VIDEO_ID.live_chat.json
    output_template = str(work_dir / "%(id)s")

    cmd = [
        "yt-dlp",
        "--write-subs",
        "--sub-langs", "live_chat",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "-o", output_template,
        url,
    ]
    logger.info("downloading live chat (this may take a while for long streams)…")
    logger.debug("command: %s", " ".join(cmd))

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600  # 10 min for large streams
    )
    elapsed = time.monotonic() - t0
    stderr_tail = result.stderr[-500:] if result.stderr else ""

    if result.returncode != 0:
        return ExtractionResult(
            status         = "download_failed",
            video_id       = vid_id,
            video_title    = vid_title,
            video_url      = url,
            was_live       = was_live,
            has_live_chat_subtitle = True,
            message        = (
                f"yt-dlp exited with code {result.returncode}. "
                "Live chat download failed. Check stderr for details."
            ),
            stderr         = stderr_tail,
            elapsed_seconds = elapsed,
        )

    # ── Find the output file ───────────────────────────────────────────────────
    chat_file = _find_chat_file(work_dir, vid_id)

    if chat_file is None:
        return ExtractionResult(
            status         = "download_failed",
            video_id       = vid_id,
            video_title    = vid_title,
            video_url      = url,
            was_live       = was_live,
            has_live_chat_subtitle = True,
            message        = (
                "yt-dlp completed but no live_chat file was created. "
                "The replay may be empty or yt-dlp may have silently skipped it."
            ),
            stderr         = stderr_tail,
            elapsed_seconds = elapsed,
        )

    file_size = chat_file.stat().st_size
    if file_size < MIN_CHAT_FILE_BYTES:
        return ExtractionResult(
            status         = "partial",
            chat_file      = chat_file,
            video_id       = vid_id,
            video_title    = vid_title,
            video_url      = url,
            was_live       = was_live,
            has_live_chat_subtitle = True,
            message        = (
                f"Chat file is very small ({file_size} bytes) — "
                "replay may be unavailable or empty."
            ),
            stderr         = stderr_tail,
            elapsed_seconds = elapsed,
        )

    logger.info(
        "live chat downloaded: %s (%.1f KB) in %.1fs",
        chat_file.name, file_size / 1024, elapsed,
    )
    return ExtractionResult(
        status         = "ok",
        chat_file      = chat_file,
        video_id       = vid_id,
        video_title    = vid_title,
        video_url      = url,
        was_live       = was_live,
        has_live_chat_subtitle = True,
        message        = f"Live chat downloaded: {file_size:,} bytes.",
        elapsed_seconds = elapsed,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_chat_file(directory: Path, video_id: str) -> Optional[Path]:
    """
    Locate the yt-dlp live chat output file.

    yt-dlp names the file <base>.live_chat.json (or .json3 in some versions).
    We search broadly to handle version differences.
    """
    # Try exact patterns first (predictable with -o %(id)s template)
    for pattern in [
        f"{video_id}.live_chat.json",
        f"{video_id}.live_chat.json3",
    ]:
        p = directory / pattern
        if p.exists() and p.stat().st_size > 0:
            return p

    # Broad fallback: any .live_chat.* file in the directory
    for p in sorted(directory.glob("*.live_chat.*")):
        if p.stat().st_size > 0:
            logger.debug("found chat file via glob: %s", p)
            return p

    # Last resort: any file with 'live_chat' in the name
    for p in sorted(directory.glob("*live_chat*")):
        if p.stat().st_size > 0:
            logger.debug("found chat file via loose glob: %s", p)
            return p

    return None
