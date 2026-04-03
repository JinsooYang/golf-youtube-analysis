"""
writer.py — Write live chat extraction outputs to disk.

Output files
------------
  live_chat_raw.json            — normalized records as a pretty-printed JSON array
                                  (the raw yt-dlp JSONL is not kept; this is the
                                  parsed+cleaned version of the raw events)
  live_chat_normalized.csv      — flat CSV, directly usable by load_live_chat()
  live_chat_normalized.json     — same data as JSON array
  live_chat_extract.log         — extraction metadata / status report

CSV column order is chosen to put the most useful columns first for quick
inspection in a spreadsheet editor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.live_chat.extractor import ExtractionResult
from src.live_chat.parser import ParseStats

logger = logging.getLogger(__name__)

# CSV column order — most useful columns first
_CSV_COLS = [
    "timestamp_seconds",
    "timestamp_text",
    "author",
    "text",
    "message_type",
    "likes",
    "superchat_amount",
    "message_id",
    "author_channel_id",
    "timestamp_usecs",
    "video_id",
    "video_url",
    "source",
    "source_type",
]


def write_outputs(
    records: list[dict],
    raw_events: list[dict],
    extraction_result: ExtractionResult,
    parse_stats: Optional[ParseStats],
    output_dir: Path | str,
) -> dict[str, Path]:
    """
    Write all output files for a live chat extraction run.

    Parameters
    ----------
    records            : normalized records (from normalizer.normalize_events)
    raw_events         : raw parsed events (from parser.parse_live_chat_file)
    extraction_result  : ExtractionResult from extractor.download_live_chat
    parse_stats        : ParseStats from parser.parse_live_chat_file (or None)
    output_dir         : directory to write all files

    Returns dict mapping role → Path of written file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    if records:
        written["raw_json"]        = _write_raw_json(raw_events, out)
        written["normalized_csv"]  = _write_normalized_csv(records, out)
        written["normalized_json"] = _write_normalized_json(records, out)

    written["log"] = _write_log(
        extraction_result = extraction_result,
        parse_stats       = parse_stats,
        record_count      = len(records),
        out               = out,
    )

    return written


# ── Individual writers ─────────────────────────────────────────────────────────

def _write_raw_json(raw_events: list[dict], out: Path) -> Path:
    """
    Write raw parser events as a pretty-printed JSON array.

    The 'raw' field (original renderer dict) is excluded from this output
    to keep file size manageable.
    """
    path = out / "live_chat_raw.json"

    cleaned = []
    for ev in raw_events:
        record = {k: v for k, v in ev.items() if k != "raw"}
        cleaned.append(record)

    path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("wrote live_chat_raw.json (%d events) → %s", len(cleaned), path)
    return path


def _write_normalized_csv(records: list[dict], out: Path) -> Path:
    path = out / "live_chat_normalized.csv"

    df = pd.DataFrame(records)
    for col in _CSV_COLS:
        if col not in df.columns:
            df[col] = ""

    # Ensure numeric types for CSV
    df["timestamp_seconds"] = pd.to_numeric(df["timestamp_seconds"], errors="coerce")
    df["likes"]             = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)

    df[_CSV_COLS].to_csv(path, index=False, encoding="utf-8")
    logger.info("wrote live_chat_normalized.csv (%d rows) → %s", len(df), path)
    return path


def _write_normalized_json(records: list[dict], out: Path) -> Path:
    path = out / "live_chat_normalized.json"

    # Exclude alias columns (keep primary names only for clean JSON)
    _EXCLUDE = {"author_name", "message_text", "like_count"}
    cleaned = [
        {k: v for k, v in r.items() if k not in _EXCLUDE}
        for r in records
    ]

    path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("wrote live_chat_normalized.json (%d records) → %s", len(cleaned), path)
    return path


def _write_log(
    extraction_result: ExtractionResult,
    parse_stats: Optional[ParseStats],
    record_count: int,
    out: Path,
) -> Path:
    path = out / "live_chat_extract.log"

    now = datetime.now(timezone.utc).isoformat()
    er  = extraction_result

    lines = [
        f"live_chat extraction log — {now}",
        "=" * 60,
        "",
        f"status:          {er.status}",
        f"video_id:        {er.video_id}",
        f"video_title:     {er.video_title}",
        f"video_url:       {er.video_url}",
        f"was_live:        {er.was_live}",
        f"has_live_chat:   {er.has_live_chat_subtitle}",
        f"elapsed_seconds: {er.elapsed_seconds:.1f}",
        "",
        f"message: {er.message}",
    ]

    if er.stderr:
        lines += ["", "yt-dlp stderr (last 500 chars):", er.stderr]

    if parse_stats:
        lines += [
            "",
            "parse statistics:",
            f"  lines_read:       {parse_stats.lines_read}",
            f"  lines_skipped:    {parse_stats.lines_skipped}",
            f"  lines_error:      {parse_stats.lines_error}",
            f"  events_extracted: {parse_stats.events_extracted}",
            f"  events_by_type:   {parse_stats.events_by_type}",
        ]

    lines += [
        "",
        f"normalized records: {record_count}",
    ]

    if record_count > 0:
        lines += [
            "",
            "next step — feed into highlight pipeline:",
            f"  python highlight_pipeline.py \\",
            f"    --comments  output/comments_cleaned.csv \\",
            f"    --live-chat output/live_chat_normalized.csv \\",
            f"    --video-id  {er.video_id}",
        ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("wrote live_chat_extract.log → %s", path)
    return path


def write_failure_log(
    extraction_result: ExtractionResult,
    output_dir: Path | str,
) -> Path:
    """Write a log-only file when extraction fails with no records."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    return _write_log(
        extraction_result = extraction_result,
        parse_stats       = None,
        record_count      = 0,
        out               = out,
    )
