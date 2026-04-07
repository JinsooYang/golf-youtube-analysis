# Golf YouTube Analysis — Pipeline Guide

## Prerequisites

```bash
pip install -r requirements.txt
pip install -U yt-dlp           # keep updated — required for YouTube JS challenge
brew install ffmpeg             # required for video download
```

Place `NanumGothic-Regular.ttf` and `NanumGothic-Bold.ttf` in the `fonts/` directory.  
Set `YOUTUBE_API_KEY` in `.env`.

---

## Primary Flow — Viewer Reaction Analysis Report

Produces one or two PDFs depending on available data:

| Available data | Report mode | Outputs |
|---|---|---|
| Comments + Live chat | **combined** — spike analysis + player detection + audience narrative | `insight_report.pdf` + `insight_report_summary.pdf` |
| Comments only | **comments** — keyword/sentiment/top comments | `insight_report.pdf` |

Mode is **detected automatically** from `output/intermediate/` — no config flag needed.

### One-command workflow (recommended)

Edit `config.json`, then run:

```bash
./generate_report config.json
```

**`config.json`:**

```json
{
  "youtube_url":       "https://www.youtube.com/watch?v=VIDEO_ID",
  "download_video":    true,
  "analyze_subtitles": true,
  "analyze_comments":  true,
  "analyze_live_chat": true
}
```

Set any option to `false` to skip that step and reuse existing files.

| Option | Controls | Notes |
|---|---|---|
| `download_video` | `youtube_extractor.sh` — video file only | Independent of subtitle extraction |
| `analyze_subtitles` | Subtitle fetch + `segments.json` generation | Works even when `download_video: false` |
| `analyze_comments` | `main.py` comment fetch (requires `YOUTUBE_API_KEY`) | Fatal if fails |
| `analyze_live_chat` | `extract_live_chat.py` chat extraction | Fatal if fails |

### Output files

| File | Description |
|---|---|
| `output/insight_report.pdf` | **Final report** (always) |
| `output/insight_report_summary.pdf` | **Summary report** (combined mode only) |
| `lesson_VIDEO_ID/video.mp4` | Downloaded video (720p) |
| `lesson_VIDEO_ID/segments.json` | Subtitle-derived sentence segments with word timings |
| `output/intermediate/comments_cleaned.csv` | Fetched and cleaned YouTube comments |
| `output/intermediate/live_chat_normalized.csv` | Parsed live chat messages with timestamps |
| `output/intermediate/spike_moments.csv` | Detected reaction spike windows |
| `output/intermediate/highlight_package.json` | Spike moments, title suggestions |

All non-PDF artifacts live under `output/intermediate/`.  
Final PDFs are always written directly to `output/`.

---

### Step-by-step (for debugging or manual execution)

```bash
# Step 1a — Download video (optional)
./youtube_extractor.sh "<URL>"

# Step 1b — Subtitle-only extraction (no video download)
./youtube_extractor.sh --subtitles-only "<URL>"

# Step 2 — Fetch YouTube comments
python main.py "<URL>" --output-dir output/intermediate

# Step 3 — Extract live chat replay
python extract_live_chat.py "<URL>" --output-dir output/intermediate

# Step 4 — Build highlight package
python highlight_pipeline.py \
    --comments  output/intermediate/comments_cleaned.csv \
    --live-chat output/intermediate/live_chat_normalized.csv \
    --segments  lesson_VIDEO_ID/segments.json \
    --video-id  VIDEO_ID \
    --output-dir output/intermediate

# Step 5 — Generate unified PDF report (mode auto-detected)
python report.py
```

---

## Subtitle extraction and `download_video`

`download_video` and `analyze_subtitles` are **independent**.

Subtitle extraction uses `yt-dlp --skip-download` internally, so no video file is needed.
When `download_video: false` and `analyze_subtitles: true`, the pipeline automatically
runs a subtitle-only extraction pass (`youtube_extractor.sh --subtitles-only`) to produce
`lesson_VIDEO_ID/segments.json` without downloading the video.

---

## Script Responsibilities

| Script | Input | Output |
|---|---|---|
| `youtube_extractor.sh` | YouTube URL | `lesson_VIDEO_ID/video.mp4`, `segments.json` |
| `main.py` | YouTube URL | `output/intermediate/comments_*.csv`, `analysis_summary.md`, `top_*.csv` |
| `extract_live_chat.py` | YouTube URL | `output/intermediate/live_chat_normalized.csv`, `live_chat_extract.log` |
| `highlight_pipeline.py` | comments + live chat + segments | `output/intermediate/highlight_package.json`, `spike_moments.csv` |
| `report.py` | `output/intermediate/` files (auto-detects mode) | `output/insight_report.pdf`, `output/insight_report_summary.pdf` |
| `render_pipeline.py` | `highlight_package.json`, `lesson_*/video.mp4` | `output/shorts_drafts/`, `output/highlight_drafts/` |

> **Note:** `render_pipeline.py` (shorts/highlight video rendering) is not part of the
> primary report flow. Run it manually when you need draft video clips.

---

## Troubleshooting

**Video download fails**  
Most likely cause: outdated yt-dlp.
```bash
pip install -U yt-dlp
```
Check `lesson_VIDEO_ID/video_dl.log` for the exact error.

**Live chat extraction returns no data**  
- The video must be an ended livestream with chat replay enabled.
- Some channels disable chat replay — nothing can be done in that case.
- `report.py` will automatically fall back to comments-only mode.

**`report.py` shows no player data**  
- Player detection requires chat messages containing `name+title` patterns (e.g. `이성훈프로`, `공태현선수`).
- Add new player aliases to `PLAYER_ALIASES` in `report.py` if they are missing.

**`highlight_pipeline.py` runs in comment-only mode**  
- This happens when `output/intermediate/live_chat_normalized.csv` does not exist.
- Run `extract_live_chat.py` first, then re-run the pipeline.
