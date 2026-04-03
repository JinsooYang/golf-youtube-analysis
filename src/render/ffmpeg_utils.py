"""
ffmpeg_utils.py — Low-level ffmpeg/ffprobe subprocess wrappers.

All intermediate files are encoded to a common target format so they can be
losslessly concatenated at the end:

  Video: H.264 (libx264), yuv420p, 25 fps, configurable resolution
  Audio: AAC stereo 44100 Hz (silent track added to card segments)

All functions accept Path objects or plain strings.
Failures raise RuntimeError with the relevant ffmpeg stderr excerpt.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Target encoding parameters ─────────────────────────────────────────────────
TARGET_FPS           = 25
TARGET_VCODEC        = "libx264"
TARGET_ACODEC        = "aac"
TARGET_PIX_FMT       = "yuv420p"
TARGET_PRESET        = "fast"
TARGET_CRF           = "23"
TARGET_AUDIO_RATE    = "44100"
TARGET_AUDIO_CHANNELS = "2"


# ── Validation ─────────────────────────────────────────────────────────────────

def check_ffmpeg() -> None:
    """Raise RuntimeError if ffmpeg or ffprobe are not on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        try:
            result = subprocess.run(
                [tool, "-version"], capture_output=True, timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"{tool} returned non-zero on -version")
        except FileNotFoundError:
            raise RuntimeError(
                f"{tool} not found on PATH. "
                "Install ffmpeg: https://ffmpeg.org/download.html  "
                "macOS: brew install ffmpeg"
            )


# ── Probe ──────────────────────────────────────────────────────────────────────

def probe_video(src: Path | str) -> dict:
    """
    Return basic video metadata via ffprobe.

    Returns dict with keys: width, height, duration (seconds), fps.
    Any missing field is None.
    """
    src = Path(src)
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {src}:\n{result.stderr[-500:]}")

    info   = json.loads(result.stdout)
    width  = height = duration = fps = None

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            width  = stream.get("width")
            height = stream.get("height")
            raw_dur = stream.get("duration") or info.get("format", {}).get("duration")
            if raw_dur:
                duration = float(raw_dur)
            r_frame = stream.get("r_frame_rate", "25/1")
            try:
                num, den = r_frame.split("/")
                fps = round(int(num) / max(int(den), 1), 3)
            except Exception:
                fps = 25.0
            break

    return {"width": width, "height": height, "duration": duration, "fps": fps}


# ── Trim ───────────────────────────────────────────────────────────────────────

def trim_clip(
    src: Path | str,
    start: float,
    end: float,
    dst: Path | str,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """
    Trim [start, end] seconds from src and write to dst.

    Re-encodes to the common target format at the given resolution.
    Uses scale+pad to letterbox/pillarbox without distortion.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    duration = end - start
    if duration <= 0:
        raise ValueError(f"trim_clip: end ({end}) must be > start ({start})")

    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(src),
        "-t", str(duration),
        "-vf", scale_filter,
        "-c:v", TARGET_VCODEC,
        "-preset", TARGET_PRESET,
        "-crf", TARGET_CRF,
        "-pix_fmt", TARGET_PIX_FMT,
        "-r", str(TARGET_FPS),
        "-c:a", TARGET_ACODEC,
        "-ar", TARGET_AUDIO_RATE,
        "-ac", TARGET_AUDIO_CHANNELS,
        "-movflags", "+faststart",
        str(dst),
    ]
    _run(cmd, f"trim_clip {start:.1f}–{end:.1f}")
    return dst


# ── Image → video ──────────────────────────────────────────────────────────────

def image_to_video(
    image_path: Path | str,
    duration: float,
    dst: Path | str,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """
    Convert a still image (PNG/JPEG) to a video segment of the given duration.

    Adds a silent AAC audio track so concat always works cleanly.
    """
    image_path, dst = Path(image_path), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-f", "lavfi",
        "-i", f"anullsrc=r={TARGET_AUDIO_RATE}:cl=stereo",
        "-t", str(duration),
        "-vf", scale_filter,
        "-c:v", TARGET_VCODEC,
        "-preset", TARGET_PRESET,
        "-crf", TARGET_CRF,
        "-pix_fmt", TARGET_PIX_FMT,
        "-r", str(TARGET_FPS),
        "-c:a", TARGET_ACODEC,
        "-ar", TARGET_AUDIO_RATE,
        "-ac", TARGET_AUDIO_CHANNELS,
        "-shortest",
        "-movflags", "+faststart",
        str(dst),
    ]
    _run(cmd, f"image_to_video {image_path.name}")
    return dst


# ── Overlay ────────────────────────────────────────────────────────────────────

def add_image_overlay(
    src: Path | str,
    overlay_img: Path | str,
    dst: Path | str,
) -> Path:
    """
    Composite a transparent PNG overlay onto a video clip.

    The overlay image must be the same size as the source video frame.
    Alpha channel in the PNG is used for blending.
    """
    src, overlay_img, dst = Path(src), Path(overlay_img), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Force RGBA on the overlay input so alpha blending is applied correctly
    filter_complex = "[1:v]format=rgba[ov];[0:v][ov]overlay=0:0[out]"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-i", str(overlay_img),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", TARGET_VCODEC,
        "-preset", TARGET_PRESET,
        "-crf", TARGET_CRF,
        "-pix_fmt", TARGET_PIX_FMT,
        "-r", str(TARGET_FPS),
        "-c:a", TARGET_ACODEC,
        "-ar", TARGET_AUDIO_RATE,
        "-ac", TARGET_AUDIO_CHANNELS,
        "-movflags", "+faststart",
        str(dst),
    ]
    _run(cmd, f"add_image_overlay → {dst.name}")
    return dst


# ── Concat ─────────────────────────────────────────────────────────────────────

def concat_clips(
    clip_paths: list[Path | str],
    dst: Path | str,
) -> Path:
    """
    Concatenate clips using the ffmpeg concat demuxer.

    All clips must have been encoded with identical parameters (same codec,
    resolution, fps, audio channels) — use trim_clip / image_to_video which
    both normalise to the common target format.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not clip_paths:
        raise ValueError("concat_clips: clip list is empty")

    if len(clip_paths) == 1:
        shutil.copy(str(clip_paths[0]), str(dst))
        return dst

    # Write absolute paths to a temp concat list file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        list_path = f.name
        for p in clip_paths:
            # Escape single quotes in path
            safe = str(Path(p).resolve()).replace("\\", "\\\\").replace("'", "\\'")
            f.write(f"file '{safe}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        _run(cmd, f"concat {len(clip_paths)} clips → {dst.name}")
    finally:
        Path(list_path).unlink(missing_ok=True)

    return dst


# ── Internal ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], label: str) -> None:
    logger.debug("ffmpeg [%s]: %s", label, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:]
        logger.error("ffmpeg [%s] failed:\n%s", label, stderr_tail)
        raise RuntimeError(
            f"ffmpeg [{label}] exited {result.returncode}.\n"
            f"Stderr (last 1000 chars):\n{result.stderr[-1000:]}"
        )


# ── Helpers for callers ────────────────────────────────────────────────────────

def valid_timestamp(v) -> Optional[float]:
    """
    Return float if v is a usable timestamp, else None.
    Handles None, empty string, and non-numeric values safely.
    """
    if v is None or v == "" or v is False:
        return None
    try:
        f = float(v)
        return f if f >= 0 else None
    except (TypeError, ValueError):
        return None
