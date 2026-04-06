# Golf YouTube Analysis — Pipeline Guide

## Prerequisites

```bash
pip install -r requirements.txt
pip install -U yt-dlp           # keep updated — required for YouTube JS challenge
brew install ffmpeg             # required for video download and render_pipeline.py
```

Place `NanumGothic-Regular.ttf` and `NanumGothic-Bold.ttf` in the `fonts/` directory.  
Set `YOUTUBE_API_KEY` in `.env`.

---

## Live Chat Flow  ← primary flow

Analyzes real-time chat messages from a livestream replay. Detects spike moments
where viewer reactions surged, identifies players, and produces a marketing insight report.

### One-command workflow (recommended)

Edit `config.json` at the repo root, then run:

```bash
./generate_report config.json
```

**`config.json`** (edit the URL before each run):

```json
{
  "youtube_url":       "https://www.youtube.com/watch?v=VIDEO_ID",
  "download_video":    true,
  "analyze_subtitles": true,
  "analyze_comments":  true,
  "analyze_live_chat": true
}
```

`generate_report` runs five steps in order, extracts the video ID automatically,
and passes `--segments` to the highlight pipeline when subtitle segments are present.
Each step is printed clearly; the script exits non-zero on failure.

| Option | Controls | Fatal if fails? |
|---|---|---|
| `download_video` | `youtube_extractor.sh` | No — continues without video/subtitles |
| `analyze_subtitles` | whether to pass `--segments` to the pipeline | n/a |
| `analyze_comments` | `main.py` comment fetch (requires `YOUTUBE_API_KEY`) | Yes |
| `analyze_live_chat` | `extract_live_chat.py` | Yes |

Set any option to `false` to skip that step and reuse existing output files
(e.g. `"download_video": false` skips re-downloading a video you already have).

### Output files

| File | Description |
|---|---|
| `lesson_VIDEO_ID/video.mp4` | Downloaded video (720p) |
| `lesson_VIDEO_ID/segments.json` | Subtitle-derived sentence segments with word timings |
| `output/live_chat_normalized.csv` | Parsed chat messages with timestamps |
| `output/live_chat_extract.log` | Extraction status and parse statistics |
| `output/spike_moments.csv` | Detected reaction spike windows |
| `output/highlight_package.json` | Spike moments, shorts sequences, title suggestions |
| `output/live_chat_insight_report.pdf` | **Final report (full)** |
| `output/live_chat_summary_report.pdf` | **Final report (summary)** |

> **Note:** Live chat replay must be available. If the stream has ended and chat replay
> is disabled, `extract_live_chat.py` exits with code `1` and `generate_report` stops
> with a clear error.

---

### Step-by-step (for debugging or manual execution)

Run individual steps when you need to inspect intermediate output or re-run a
specific stage without repeating earlier ones.

```bash
# Step 1 — Download video + subtitles (optional)
#   Creates lesson_VIDEO_ID/ with video.mp4 and segments.json
./youtube_extractor.sh "<URL>"

# Step 2 — Fetch YouTube comments (requires YOUTUBE_API_KEY in .env)
python main.py "<URL>"

# Step 3 — Extract live chat replay
python extract_live_chat.py "<URL>"

# Step 4 — Detect spikes, build highlight package
#   Replace VIDEO_ID with the actual ID (e.g. owl8NxtVjfc)
python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --live-chat output/live_chat_normalized.csv \
    --video-id  VIDEO_ID

#   If subtitle segments exist from step 1, add --segments:
python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --live-chat output/live_chat_normalized.csv \
    --segments  lesson_VIDEO_ID/segments.json \
    --video-id  VIDEO_ID

# Step 5 — Generate PDF report
python generate_report_by_live_chat.py
```

---

## Comment Flow

Analyzes regular comments posted under the video.

### Steps

```bash
# 1. Fetch comments from YouTube API
python main.py "<URL>"

# 2. Classify, score, and package highlight candidates
python highlight_pipeline.py \
    --comments output/comments_cleaned.csv \
    --video-id VIDEO_ID

# 3. Generate PDF report
python generate_report_by_comment.py
```

### Output files

| File | Description |
|---|---|
| `output/comments_raw.csv` | Raw comment data from YouTube API |
| `output/comments_cleaned.csv` | Normalized comments used for analysis |
| `output/analysis_summary.md` | Stats, keywords, sentiment, content recommendations |
| `output/top_keywords.csv` | Keyword frequency table |
| `output/top_authors.csv` | Most active commenters |
| `output/highlight_package.json` | Classified highlight candidates, master plan, shorts sequences |
| `output/comment_insight_report.pdf` | **Final report** |

---

## Running Both Flows Together

Both flows share `highlight_pipeline.py` and write to the same `output/` directory.
Run both extractions first, then a single pipeline run incorporates everything.

```bash
python main.py "<URL>"
./youtube_extractor.sh "<URL>"
python extract_live_chat.py "<URL>"

python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --live-chat output/live_chat_normalized.csv \
    --segments  lesson_VIDEO_ID/segments.json \
    --video-id  VIDEO_ID

python generate_report_by_comment.py
python generate_report_by_live_chat.py
```

---

## highlight_pipeline.py — Key Options

```
--comments FILE     Comments CSV (default: output/comments_cleaned.csv)
--live-chat FILE    Live chat CSV (default: output/live_chat_normalized.csv)
--segments FILE     Subtitle segments from youtube_extractor.sh (optional)
--video-id ID       YouTube video ID — used in output metadata and URLs
--players NAME ...  Player names to detect  e.g. --players 이용희 공태현 안예인
--verbose           Show debug logging
```

---

## Script Responsibilities

| Script | Input | Output |
|---|---|---|
| `youtube_extractor.sh` | YouTube URL | `lesson_VIDEO_ID/video.mp4`, `segments.json` |
| `main.py` | YouTube URL | `comments_*.csv`, `analysis_summary.md`, `top_*.csv` |
| `extract_live_chat.py` | YouTube URL | `live_chat_normalized.csv`, `live_chat_extract.log` |
| `highlight_pipeline.py` | comments + live chat + segments | `highlight_package.json`, `spike_moments.csv` |
| `generate_report_by_comment.py` | `output/` files | `comment_insight_report.pdf` |
| `generate_report_by_live_chat.py` | `output/` files | `live_chat_insight_report.pdf` |
| `render_pipeline.py` | `highlight_package.json`, `lesson_*/video.mp4` | `output/shorts_drafts/`, `output/highlight_drafts/` |

---

## Troubleshooting

**Video download fails at step [2/3]**  
Most likely cause: outdated yt-dlp. YouTube periodically changes their JS challenge format.
```bash
pip install -U yt-dlp
```
If it still fails, check `lesson_VIDEO_ID/video_dl.log` for the exact error.

**Live chat extraction returns no data**  
- The video must be an ended livestream with chat replay enabled.
- Some channels disable chat replay. Nothing can be done in that case.

**`generate_report_by_live_chat.py` shows no player data**  
- Player detection requires chat messages containing `name+title` patterns (e.g. `이성훈프로`, `공태현선수`).
- Add new player aliases to `PLAYER_ALIASES` in `generate_report_by_live_chat.py` if they are missing.

**`highlight_pipeline.py` runs in comment-only mode**  
- This happens when `output/live_chat_normalized.csv` does not exist.
- Run `extract_live_chat.py` first, then re-run the pipeline.
