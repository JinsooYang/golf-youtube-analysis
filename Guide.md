# Golf YouTube Analysis — Pipeline Guide

## Prerequisites

```bash
pip install -r requirements.txt
brew install ffmpeg          # for render_pipeline.py only
```

Place `NanumGothic-Regular.ttf` and `NanumGothic-Bold.ttf` in the `fonts/` directory.  
Set `YOUTUBE_API_KEY` in `.env`.

---

## Comment-based Flow

Analyzes regular comments posted under the video.

### Steps

```bash
# 1. Fetch comments from YouTube API
python main.py <URL>

# 2. Classify, score, and package highlight candidates
python highlight_pipeline.py

# 3. Generate the PDF report
python generate_report_by_comment.py
```

### Output files

| File | Description |
|---|---|
| `output/comments_raw.csv` | Raw comment data from YouTube API |
| `output/comments_cleaned.csv` | Normalized comments used for analysis |
| `output/analysis_summary.md` | Auto-generated summary: stats, keywords, sentiment, recommendations |
| `output/top_keywords.csv` | Keyword frequency table |
| `output/top_authors.csv` | Most active commenters |
| `output/highlight_package.json` | Classified highlight candidates, master plan, shorts sequences |
| `output/comment_insight_report.pdf` | **Final report** |

---

## Live Chat Flow

Analyzes real-time chat messages from a livestream replay. Detects spike moments where viewer reactions surged.

### Steps

```bash
# 1. Download and parse live chat replay
python extract_live_chat.py <URL>

# 2. Detect spikes and build highlight package
python highlight_pipeline.py

# 3. Generate the PDF report
python generate_report_by_live_chat.py
```

### Output files

| File | Description |
|---|---|
| `output/live_chat_normalized.csv` | Parsed chat messages with timestamps |
| `output/live_chat_normalized.json` | Same data in JSON format |
| `output/live_chat_extract.log` | Extraction status and parse statistics |
| `output/spike_moments.csv` | Detected reaction spike windows |
| `output/highlight_package.json` | Spike moments, shorts sequences, title suggestions |
| `output/live_chat_insight_report.pdf` | **Final report** |

> **Note:** Live chat replay must be available on the video. If the stream has ended and chat replay is disabled, `extract_live_chat.py` will exit with status `no_replay`.

---

## Running Both Flows Together

Both flows share `highlight_pipeline.py`. Run it after whichever extraction step you completed. If you run both `main.py` and `extract_live_chat.py` first, a single `highlight_pipeline.py` run will incorporate both comment and live chat data.

```bash
python main.py <URL>
python extract_live_chat.py <URL>
python highlight_pipeline.py
python generate_report_by_comment.py
python generate_report_by_live_chat.py
```

---

## File Responsibilities

| Script | Input | Output |
|---|---|---|
| `main.py` | YouTube URL | `comments_*.csv`, `analysis_summary.md`, `top_*.csv` |
| `extract_live_chat.py` | YouTube URL | `live_chat_normalized.csv`, `live_chat_extract.log` |
| `highlight_pipeline.py` | `comments_cleaned.csv`, `live_chat_normalized.csv` | `highlight_package.json`, `spike_moments.csv` |
| `generate_report_by_comment.py` | `output/` files | `comment_insight_report.pdf` |
| `generate_report_by_live_chat.py` | `output/` files | `live_chat_insight_report.pdf` |
| `render_pipeline.py` | `highlight_package.json`, `lesson_*/video.mp4` | `output/shorts_drafts/`, `output/highlight_drafts/` |
