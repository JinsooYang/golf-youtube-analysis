# YouTube Comment Analyzer + Highlight Pipeline

A local Python toolkit that:
1. Fetches YouTube video comments via the Data API v3 and generates content strategy insights.
2. Combines comment data with subtitle segments (from `youtube_extractor.sh`) to produce **editing-ready highlight data** for comment-driven Shorts and highlight videos.
3. **Renders draft `.mp4` videos** — Shorts drafts and one master highlight — directly from the structured data.

---

## What it does

### Layer 0 — Video + subtitle extraction (`youtube_extractor.sh`)
Downloads video and, when subtitles are available, generates sentence-level segments with word timings.
**Video download is always the primary goal** — missing or disabled subtitles do not abort the script.
Output: `lesson_{VIDEO_ID}/video.mp4` (always) and `lesson_{VIDEO_ID}/segments.json` (when subtitles available).

### Layer 1 — Comment analysis (`main.py`)
1. **Fetches** all regular video comments (top-level + replies) via pagination
2. **Saves** raw and cleaned data to CSV
3. **Analyzes** keyword frequency, sentiment/reaction patterns, and author activity
4. **Generates** content strategy recommendations
5. **Reports** everything in a readable Markdown file and a terminal summary

### Layer 2 — Highlight pipeline (`highlight_pipeline.py`)
1. **Loads** comment CSV + optional `segments.json` + optional live-chat CSV
2. **Classifies** each comment/message into one of 8 highlight categories
3. **Matches** to clip windows — three modes (in priority order):
   - **Live chat + segments**: timestamp looked up against subtitle windows
   - **Live chat, no segments**: timestamp used directly as clip anchor (`ts ± pre/post_roll`) — `needs_manual=False`, `confidence=high`
   - **Comment only**: two-pass semantic matching; always `needs_manual=True`
4. **Detects reaction spikes**: sliding-window density analysis on live chat to find "crowd went wild" moments
5. **Scores** candidates by a composite priority score
6. **Outputs** structured files: per-comment candidates, moment candidates, spike moments, a full package JSON, Shorts editing brief, and a **master highlight plan**

### Layer 3 — Video rendering (`render_pipeline.py`)
1. **Reads** `highlight_package.json` and `master_highlight_plan.json`
2. **Renders Shorts** — two modes depending on what the pipeline produced:
   - **Spike mode** (live chat available): top 5 reaction-spike Shorts, each 15 s, with rolling live chat panel overlay showing real-time viewer reactions
   - **Concept mode** (comment-only): one Short per highlight category (funny, dramatic, clutch, etc.)
3. **Renders** one draft master highlight video following the 5-act narrative plan
4. **Inserts placeholder cards** wherever timestamps are missing or confidence is too low

### Layer 2.5 — Live chat replay extraction (`extract_live_chat.py`)

Extracts live chat replay from an ended YouTube livestream using **yt-dlp** and
normalises it into a clean CSV/JSON table.  The output feeds directly into the
highlight pipeline via `--live-chat`, enabling timestamp-based clip matching
and automatic rendering.

```bash
# Extract live chat replay
python extract_live_chat.py "https://www.youtube.com/watch?v=VIDEO_ID"
# → output/live_chat_normalized.csv  ← pass to --live-chat
# → output/live_chat_normalized.json
# → output/live_chat_raw.json
# → output/live_chat_extract.log
```

### About Live chat and timestamps

Regular YouTube comments (from the main API) have **no video timestamp** — all
comment-to-segment matches are semantic best-effort and marked
`needs_manual_timestamp_mapping: true`.

Live chat messages (from a livestream replay) carry `videoOffsetTimeMsec` — the
exact video position when the message was sent.  When live chat is available:
- matching_confidence = `high`
- `needs_manual_timestamp_mapping = False`
- automatic clip rendering works in `render_pipeline.py`

Without live chat, draft videos consist of cards only (placeholders for manual editing).

---

## Project structure

```
golf-youtube-analysis/
├── main.py                           # Layer 1: Comment fetch + analysis CLI
├── highlight_pipeline.py             # Layer 2: Highlight automation CLI
├── render_pipeline.py                # Layer 3: Draft video rendering CLI  ← NEW
├── youtube_extractor.sh              # Layer 0: Video + subtitle download
├── src/
│   ├── youtube_client.py             # YouTube API v3 client
│   ├── data_processor.py             # Data cleaning, text normalization
│   ├── analyzer.py                   # Stats, keywords, sentiment tagging
│   ├── insight_generator.py          # Content strategy recommendations
│   ├── reporter.py                   # CSV + Markdown report writer
│   ├── highlight/                    # Highlight planning sub-package
│   │   ├── loaders.py                # Load segments.json / comments CSV
│   │   ├── classifier.py             # Category + emotion_strength
│   │   ├── matcher.py                # Comment ↔ segment matching
│   │   ├── scorer.py                 # Priority score
│   │   ├── narrative.py              # Master highlight plan builder
│   │   ├── packager.py               # Pipeline orchestration
│   │   └── writer.py                 # Output file writer
│   ├── live_chat/                    # Live chat extraction sub-package  ← NEW
│   │   ├── extractor.py              # yt-dlp subprocess wrapper + probe
│   │   ├── parser.py                 # JSONL → raw event dicts
│   │   ├── normalizer.py             # raw events → flat schema records
│   │   └── writer.py                 # write CSV / JSON / log outputs
│   └── render/                       # Video rendering sub-package  ← NEW
│       ├── ffmpeg_utils.py           # trim / card-to-video / concat / probe
│       ├── cards.py                  # Pillow card image generation
│       ├── overlay.py                # Pillow transparent overlay images
│       ├── shorts_renderer.py        # Render Shorts drafts
│       └── highlight_renderer.py     # Render master highlight draft
├── extract_live_chat.py              # Layer 2.5: Live chat replay extraction CLI  ← NEW
├── generate_report.py                # Marketing insight PDF
├── generate_highlight_plan.py        # Highlight format plan PDF
├── output/                           # Generated files (created at runtime)
│   ├── shorts_drafts/                # Draft Shorts .mp4 files  ← NEW
│   └── highlight_drafts/             # Draft master highlight .mp4  ← NEW
├── fonts/                            # NanumGothic TTF (required for Korean text)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone / download the project

```bash
cd golf-youtube-analysis
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install ffmpeg (required for video rendering)

ffmpeg must be on your PATH.

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:** Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) and add to PATH.

**Verify:**
```bash
ffmpeg -version
ffprobe -version
```

### 5. Get a YouTube Data API v3 key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Data API v3**
3. Credentials → Create Credentials → API key

### 6. Configure your API key

```bash
cp .env.example .env
# Edit .env and set: YOUTUBE_API_KEY=your_actual_key_here
```

---

## Typical workflow

```bash
# Step 0 — Download video (+ subtitle segments when available)
./youtube_extractor.sh "https://www.youtube.com/watch?v=VIDEO_ID"
# → lesson_VIDEO_ID/video.mp4          (always)
# → lesson_VIDEO_ID/video_meta.json    (always)
# → lesson_VIDEO_ID/segments.json      (only if subtitles available)
# → lesson_VIDEO_ID/subtitles.vtt/.srt (only if subtitles available)

# Step 1 — Fetch and analyze comments
source .venv/bin/activate
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
# → output/comments_cleaned.csv

# Step 2.5 — Extract live chat replay (primary timing source for livestreams)
python extract_live_chat.py "https://www.youtube.com/watch?v=VIDEO_ID"
# → output/live_chat_normalized.csv

# Step 2 — Run highlight pipeline
# PRIMARY: live chat timestamps → real clips, no segments.json needed
python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --live-chat output/live_chat_normalized.csv \
    --video-id  VIDEO_ID \
    --players   이용희 공태현 안예인 고수진
# clip windows: pre=10s before timestamp, post=20s after (configurable)
# → output/highlight_package.json
# → output/master_highlight_plan.json
# → output/shorts_script.md
# → output/master_highlight_script.md
# → output/highlight_comment_candidates.csv
# → output/spike_moments.csv

# OPTIONAL: also pass segments.json when subtitles were available
python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --live-chat output/live_chat_normalized.csv \
    --segments  lesson_VIDEO_ID/segments.json \
    --video-id  VIDEO_ID \
    --players   이용희 공태현 안예인 고수진

# WITHOUT live chat (comments only — all clips are placeholders)
python highlight_pipeline.py \
    --comments  output/comments_cleaned.csv \
    --video-id  VIDEO_ID \
    --players   이용희 공태현 안예인 고수진

# Step 3 — Render draft videos
python render_pipeline.py \
    --video lesson_VIDEO_ID/video.mp4
# → output/shorts_drafts/{concept}.mp4  (one per Shorts concept)
# → output/highlight_drafts/master_highlight.mp4

# Step 3a — Render Shorts only
python render_pipeline.py --video lesson_VIDEO_ID/video.mp4 --shorts-only

# Step 3b — Render master highlight only
python render_pipeline.py --video lesson_VIDEO_ID/video.mp4 --highlight-only

# Step 4 (optional) — Generate PDF reports
python generate_report.py
python generate_highlight_plan.py
```

---

## Usage reference

### `main.py`

```
usage: youtube-comment-analyzer [-h] [--max-comments N] [--no-replies]
                                 [--output-dir DIR] url

positional arguments:
  url                  YouTube video URL

options:
  --max-comments N     Max top-level comments to fetch (default: 500)
  --no-replies         Skip reply comments
  --output-dir DIR     Output directory (default: output/)
```

### `extract_live_chat.py`

```
positional arguments:
  URL                   YouTube video URL (ended livestream)

options:
  --output-dir DIR      Output directory (default: output/)
  --highlight-only      Keep only text/superchat messages with valid timestamps
  --keep-raw            Also copy the raw yt-dlp .live_chat.json file
  --verbose             Enable debug-level logging
```

Exit codes: `0` success · `1` no replay or extraction failed · `2` yt-dlp missing

### `highlight_pipeline.py`

```
options:
  --comments FILE       Path to comments CSV (default: output/comments_cleaned.csv)
  --segments FILE       Path to segments.json from youtube_extractor.sh (optional)
  --live-chat FILE      Path to live-chat CSV with timestamps (optional)
                        When present without segments, timestamps are used directly
                        as clip anchors (live chat timestamp mode)
  --video-id ID         YouTube video ID
  --video-title TITLE   Video title for report headers
  --players NAME ...    Known player names for detection and matching
  --output-dir DIR      Output directory (default: output/)
  --min-likes N         Filter out comments with fewer than N likes

  # Matching clip window (used by matcher for all comment→clip mapping)
  --pre-roll SEC        Seconds before reaction timestamp (default: 10)
  --post-roll SEC       Seconds after reaction timestamp (default: 20)

  # Spike-driven Shorts clip window (independent of --pre-roll/--post-roll)
  --shorts-pre-roll SEC  Seconds before spike anchor → Shorts clip start (default: 10)
  --shorts-post-roll SEC Seconds after spike anchor → Shorts clip end (default: 5)
                         Total default Shorts clip = 15 s

  --verbose             Enable debug-level logging
```

**Shorts mode selection** (automatic):

| Inputs | Shorts mode | Clip duration |
|--------|-------------|:-------------:|
| `--live-chat` + spikes detected | **Spike-driven**: top 5 reaction peaks, rolling chat overlay | `--shorts-pre-roll + --shorts-post-roll` |
| `--comments` only or no spikes | **Concept-driven**: one per category (funny, dramatic, etc.) | `--pre-roll + --post-roll` |

**Matching mode selection** (automatic):

| Inputs | Mode | `needs_manual` | Clips render? |
|--------|------|:--------------:|:-------------:|
| `--live-chat` (no `--segments`) | Live chat timestamp direct | False | ✓ |
| `--live-chat` + `--segments` | Live chat + segment window | False | ✓ |
| `--comments` only | Semantic matching | True | ✗ (placeholders) |

### `render_pipeline.py`

```
options:
  --video FILE          Source video file (required)
                        e.g. lesson_VIDEO_ID/video.mp4
  --package FILE        highlight_package.json
                        (default: output/highlight_package.json)
  --master-plan FILE    master_highlight_plan.json
                        (default: output/master_highlight_plan.json)
  --output-dir DIR      Output directory root (default: output/)
  --font FILE           TTF font for Korean text overlays
                        (auto-detected from fonts/ if omitted)
  --width N             Output width in pixels (default: 1280)
  --height N            Output height in pixels (default: 720)
  --min-confidence      Minimum confidence to auto-render clips:
                        high | medium | low  (default: medium)
  --shorts-only         Render Shorts drafts only
  --highlight-only      Render master highlight only
  --verbose             Enable debug-level logging
```

---

## Live chat extraction details

### How it works

1. **Probe** — `yt-dlp --dump-json URL` checks if a `live_chat` subtitle track exists
2. **Download** — `yt-dlp --write-subs --sub-langs live_chat --skip-download URL`
3. **Parse** — reads the JSONL file line by line; each line is a `replayChatItemAction` batch from YouTube's innertube API
4. **Normalize** — flattens nested renderer objects into a flat schema
5. **Write** — CSV, JSON, and a plain-text extraction log

### Message types

| Type | Renderer | Default | `--highlight-only` |
|------|----------|---------|-------------------|
| Regular text | `liveChatTextMessageRenderer` | ✓ | ✓ |
| Super Chat | `liveChatPaidMessageRenderer` | ✓ | ✓ |
| Membership join | `liveChatMembershipItemRenderer` | ✓ | ✗ |
| Paid sticker | `liveChatPaidStickerRenderer` | ✓ | ✗ |
| System messages | `liveChatViewerEngagementMessageRenderer` | ✗ always skipped | ✗ |

### Timestamp field

`timestamp_seconds` is `videoOffsetTimeMsec ÷ 1000` — the **video offset in seconds**, not an epoch timestamp.  Messages without `videoOffsetTimeMsec` get `timestamp_seconds = null` and are excluded by `--highlight-only`.

### Extraction status codes

| Status | Meaning |
|--------|---------|
| `ok` | Downloaded and parsed |
| `partial` | File is very small — may be incomplete |
| `no_replay` | No `live_chat` subtitle track found |
| `probe_failed` | yt-dlp could not fetch metadata |
| `download_failed` | yt-dlp ran but produced no file |
| `ytdlp_missing` | yt-dlp not installed |

### Common failure cases

| Situation | What to do |
|-----------|-----------|
| Regular video (not a livestream) | Use `main.py` for comment extraction |
| Ended livestream, chat replay disabled | Cannot extract; use `main.py` only |
| Chat replay expired (old stream) | Not recoverable |
| yt-dlp not installed | `pip install yt-dlp` |

---

## How rendering works

### Spike-driven Shorts

When live chat is available and reaction spikes are detected, Shorts are generated from the top 5 spike moments (not from comment categories).

Each spike Short:
1. **Hook card** (3.5 s) — highest-liked message from the spike window
2. **Rolling-chat clip** — the actual video clip with a live chat panel overlaid in the bottom-right corner. The panel updates in 3 phases as the clip plays, showing an increasing subset of messages — simulating chat scrolling in real time
3. **CTA card** (3.5 s)

**Rolling chat phases** for a 15 s clip with 9 messages:
- Phase 1 (0–5 s): messages 1–3 visible (reactions just starting)
- Phase 2 (5–10 s): messages 1–6 visible (peak reaction)
- Phase 3 (10–15 s): messages 1–9 visible (aftermath)

The chat panel is positioned in the **bottom-right corner** of the frame to avoid covering center-frame golf action. It shows a "💬 라이브" header, author names in blue, and message text in white on a semi-transparent dark background.

### Confidence gating

Each comment record carries two honesty fields:

| Field | Meaning |
|-------|---------|
| `matching_confidence` | Quality of the comment→segment match: `high` / `medium` / `low` / `none` |
| `needs_manual_timestamp_mapping` | `True` for ALL regular YouTube comments (no real timestamp exists) |

A clip is **auto-rendered** only when:
- `matching_confidence` ∈ `{high, medium}` (configurable via `--min-confidence`)
- `needs_manual_timestamp_mapping = False` (only live-chat messages can satisfy this)

Everything else gets a **red placeholder card** with a clear label explaining why.

### Card types

| Card | When used |
|------|-----------|
| Title card | Video opening — dark background, large title |
| Hook card | Comment display — large text on dark background |
| Section card | Act divider in master highlight — coloured background |
| CTA card | Video ending — call-to-action |
| Placeholder card | Red ⚠ card for missing/low-confidence timestamps |

### Intermediate encoding

All clips and cards are encoded to a common format before concat:

| Parameter | Value |
|-----------|-------|
| Video codec | H.264 (libx264) |
| Audio codec | AAC stereo 44100 Hz |
| Pixel format | yuv420p |
| Frame rate | 25 fps |
| CRF | 23 (good quality / reasonable size) |
| Preset | fast |

Cards get a silent AAC audio track so concat always succeeds without re-encoding.

### Output format note

Output is **1280×720 (16:9)** by default.  True 9:16 vertical Shorts would require footage shot vertically. For tournament footage, 16:9 is used and content is letterboxed/pillarboxed to the output resolution as needed. Override with `--width 1080 --height 1920` for 9:16 if your source footage supports it.

---

## Output files

### `youtube_extractor.sh` outputs (`lesson_{VIDEO_ID}/`)

| File | Always created | Description |
|------|:--------------:|-------------|
| `video.mp4` | ✓ | Downloaded video (720p) |
| `video_meta.json` | ✓ | Video metadata (title, channel, file paths — nullable when missing) |
| `subtitles.vtt` | | VTT auto-captions with word-level timings (skipped if unavailable) |
| `subtitles.srt` | | Cleaned SRT file derived from VTT (skipped if unavailable) |
| `segments.json` | | Sentence-level segments with word timings (skipped if unavailable) |
| `video_guide.md` | | Timestamped segment guide with YouTube links (skipped if unavailable) |

If subtitles are unavailable the script still exits 0. Pass `highlight_pipeline.py` without `--segments` to run in semantic-matching mode.

### `main.py` outputs (`output/`)

| File | Description |
|------|-------------|
| `comments_raw.csv` | Every comment as returned by the API |
| `comments_cleaned.csv` | Normalized text, HTML decoded |
| `top_keywords.csv` | Unigram and bigram frequency table |
| `top_authors.csv` | Most active commenters |
| `analysis_summary.md` | Full analysis report |

### `extract_live_chat.py` outputs (`output/`)

| File | Description |
|------|-------------|
| `live_chat_normalized.csv` | Flat table — pass to `--live-chat` in `highlight_pipeline.py` |
| `live_chat_normalized.json` | Same data as JSON array |
| `live_chat_raw.json` | Parsed raw events (renderer-level detail, no yt-dlp internals) |
| `live_chat_extract.log` | Extraction status, parse stats, suggested next command |

### `highlight_pipeline.py` outputs (`output/`)

| File | Description |
|------|-------------|
| `highlight_comment_candidates.csv` | Per-comment candidates ranked by priority_score |
| `highlight_comment_candidates.json` | Same data as JSON |
| `highlight_moment_candidates.csv` | Segment-level aggregation (empty when no segments) |
| `spike_moments.csv` | Live chat reaction density peaks (empty when no live chat) |
| `highlight_package.json` | Full package: meta + comments + moments + spikes + Shorts sequences + master plan |
| `shorts_script.md` | Human-readable Shorts editing brief (includes spike moments section) |
| `master_highlight_plan.json` | Structured 5-act master highlight plan |
| `master_highlight_script.md` | Human-readable master highlight editing brief |

### `render_pipeline.py` outputs

| Path | Description |
|------|-------------|
| `output/shorts_drafts/top_reactions.mp4` | Shorts draft: top reactions |
| `output/shorts_drafts/funniest.mp4` | Shorts draft: funny moments |
| `output/shorts_drafts/dramatic.mp4` | Shorts draft: dramatic moments |
| `output/shorts_drafts/controversial.mp4` | Shorts draft: controversial moments |
| `output/shorts_drafts/analytical.mp4` | Shorts draft: analytical comments |
| `output/shorts_drafts/clutch.mp4` | Shorts draft: clutch/hype moments |
| `output/highlight_drafts/master_highlight.mp4` | Master highlight draft |

#### Highlight comment candidate fields

| Field | Description |
|-------|-------------|
| `comment_id` | YouTube comment ID |
| `source_type` | `comment` or `live_chat` |
| `text` | Comment text |
| `likes` | Like count |
| `author` | Author display name |
| `category` | `funny` / `dramatic` / `critical` / `emotional` / `supportive` / `controversial` / `clutch_hype` / `representative` |
| `emotion_strength` | 1.0–5.0 float |
| `priority_score` | 0–100 composite score |
| `related_player_names` | Pipe-separated player names |
| `suggested_caption` | Short overlay caption (~45 chars) |
| `recommended_usage` | Editing action (e.g. `open_short_with_hook_card`) |
| `matched_segment_id` | Matched subtitle segment ID (or empty) |
| `matched_start` | Segment start in seconds (or empty) |
| `matched_end` | Segment end in seconds (or empty) |
| `matching_confidence` | `high` / `medium` / `low` / `none` |
| `needs_manual_timestamp_mapping` | `True` for all regular comments |
| `match_signals` | Pipe-separated matching signals |
| `editor_notes` | Auto-generated editor notes |

---

## Limitations

### Rendering limitations

- **Live chat is the primary clip source:** Only `source_type=live_chat` rows get `needs_manual_timestamp_mapping=False`, enabling auto clip rendering. When live chat is provided (even without `segments.json`), real clips are cut from `video.mp4` using `timestamp_seconds ± pre/post_roll`.
- **Comment-only mode:** Without live-chat data, ALL clips will be placeholder cards because regular comments have no video timestamp. The rendered video will consist entirely of cards with embedded comment text. This is correct behaviour — not a bug.
- **`segments.json` is optional:** When live chat replay is available, subtitle segments are not required for clip rendering. Segments improve timestamp matching precision when available but are not the timing source.
- **Aspect ratio:** Output defaults to 1280×720 (16:9). YouTube Shorts prefer 9:16 but that requires vertically-shot source footage.
- **No transitions:** Clips are concatenated directly. Add transitions in your editing software.
- **No audio mixing:** Music/voiceover must be added in post.
- **Font:** Korean text requires `fonts/NanumGothic-Regular.ttf`. Text falls back to Pillow's default font if missing (Latin characters only).
- **Temp disk usage:** Intermediate files are written to a system temp dir and cleaned up after each render. Ensure sufficient disk space (~2× the final output size per video).

### Extraction limitations

- **Subtitles unavailable** — many videos have auto-captions disabled or are in languages without auto-caption support. `youtube_extractor.sh` will still download the video and write `video_meta.json`; `segments.json` simply won't be produced. Run `highlight_pipeline.py` without `--segments` to continue in semantic-matching mode.
- **Subtitle language** — the script tries English auto-captions first, then any available language. The VTT word-timing parser handles all languages the same way; segment quality depends on the quality of the auto-caption track.

### Analysis limitations

- **No timestamp analysis** — regular comments carry no video timestamp.
- **Rule-based sentiment** — cannot detect sarcasm or complex context.
- **Korean tokenization** — space-based splitting is a simplification.
- **Comments disabled** — API returns 403 if comments are disabled on the video.
- **API quota** — default 10,000 units/day (generous for normal use).

---

## Live chat CSV format

If you have live chat data from a third-party tool, pass it with `--live-chat`:

| Column | Description |
|--------|-------------|
| `timestamp_seconds` (or `time_seconds`, `offset_seconds`) | Video position in seconds |
| `text` (or `message`, `content`) | Message text |
| `author` | Author name (optional) |
| `likes` | Like count (optional) |

Live chat messages get `needs_manual_timestamp_mapping: False` and `matching_confidence: high`, enabling automatic clip rendering.

---

## API quota

| Operation | Cost |
|-----------|------|
| `commentThreads.list` (1 page, up to 100 comments) | ~1 unit |
| `comments.list` for replies | ~1 unit per page |

Fetching 500 top-level comments uses roughly 5–10 units. The default 10,000 units/day quota is sufficient for most use cases.

---

## Extending the project

### Add custom player names / entities

Pass `--players NAME [NAME ...]` to `highlight_pipeline.py`.  Player names are used as high-weight matching signals (weight 3 vs event keywords weight 2).

### Add custom stopwords

In `src/highlight/matcher.py`, extend `_KO_MATCH_STOPWORDS`.

### Adjust confidence threshold for rendering

Use `--min-confidence high` to only render clips with the strongest matches, or `--min-confidence low` to attempt rendering more clips (with more potential for wrong timestamps).

### Korean morpheme analysis (advanced)

Replace the space-based tokenizer in `src/data_processor.py` with [KoNLPy](https://konlpy.org/) for accurate Korean NLP (requires Java).
