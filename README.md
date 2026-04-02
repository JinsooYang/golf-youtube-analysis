# YouTube Comment Analyzer

A local Python CLI that fetches YouTube video comments via the Data API v3,
saves them to CSV, and generates actionable **content strategy insights**.

Designed for YouTube creators who want to understand what their audience
is reacting to — and what to make next.

---

## What it does

1. **Fetches** all regular video comments (top-level + replies) via pagination
2. **Saves** raw and cleaned data to CSV
3. **Analyzes** keyword frequency, sentiment/reaction patterns, and author activity
4. **Generates** specific content recommendations based on what the audience is saying
5. **Reports** everything in a readable Markdown file and a terminal summary

### Out of scope: Live chat

YouTube live chat replay is **not reliably accessible** via the YouTube Data API v3 alone for ended streams. This tool focuses on regular video comments (the comment section below the video).

True time-based reaction analysis (e.g. spike detection at specific video timestamps) requires live chat logs with timestamps or YouTube Analytics event data — see the Limitations section of the generated report.

---

## Project structure

```
golf-youtube-analysis/
├── main.py                  # CLI entry point
├── src/
│   ├── youtube_client.py    # YouTube API v3 client + URL parsing
│   ├── data_processor.py    # Data cleaning, text normalization
│   ├── analyzer.py          # Stats, keywords, sentiment tagging
│   ├── insight_generator.py # Content strategy recommendations
│   └── reporter.py          # CSV + Markdown report writer
├── output/                  # Generated files (created at runtime)
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

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a YouTube Data API v3 key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select an existing one)
3. Enable **YouTube Data API v3**
4. Go to **Credentials → Create Credentials → API key**
5. Copy the key

### 5. Configure your API key

```bash
cp .env.example .env
```

Edit `.env`:

```
YOUTUBE_API_KEY=your_actual_key_here
```

---

## Usage

```bash
# Basic — fetch up to 500 top-level comments + replies
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Short URL format
python main.py "https://youtu.be/VIDEO_ID"

# YouTube Live URL
python main.py "https://www.youtube.com/live/VIDEO_ID"

# Fetch more comments
python main.py "https://youtu.be/VIDEO_ID" --max-comments 2000

# Skip replies (faster, lower quota)
python main.py "https://youtu.be/VIDEO_ID" --no-replies

# Custom output directory
python main.py "https://youtu.be/VIDEO_ID" --output-dir results/my_video
```

### All options

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

---

## Output files

All files are written to `output/` (or your chosen `--output-dir`).

| File | Description |
|------|-------------|
| `comments_raw.csv` | Every comment exactly as returned by the API |
| `comments_cleaned.csv` | Text normalized, HTML entities decoded, whitespace collapsed |
| `top_keywords.csv` | Unigram and bigram frequency table |
| `top_authors.csv` | Most active commenters with like totals |
| `analysis_summary.md` | Full report: stats, keywords, sentiment, recommendations |

### CSV columns

| Column | Description |
|--------|-------------|
| `comment_id` | Unique YouTube comment ID |
| `parent_comment_id` | Thread ID for replies; `None` for top-level |
| `author` | Display name of commenter |
| `text` | Comment text |
| `published_at` | ISO 8601 timestamp |
| `updated_at` | ISO 8601 timestamp (same as published if not edited) |
| `like_count` | Number of likes on the comment |
| `is_reply` | `True` / `False` |
| `reply_count` | Number of replies (top-level only; 0 for replies) |
| `video_id` | YouTube video ID |
| `video_url` | Original URL passed to the CLI |

---

## Extending the analyzer

### Add custom entities (player names, brands)

In `src/analyzer.py`, the `entity_candidates` list uses a heuristic (capitalized words). For a golf channel, you can supplement this by adding a known-names dictionary:

```python
KNOWN_GOLF_ENTITIES = [
    "Rory", "Scottie", "Scheffler", "McIlroy", "Tiger", "Woods",
    "Spieth", "Rahm", "Cantlay", "Hovland", "LIV", "PGA", "Masters",
    "Augusta", "Torrey", "Pines",
]
```

Then filter `keywords` against this list for entity-specific frequency counts.

### Add custom stopwords

In `src/analyzer.py`, extend `EN_STOPWORDS` or `KO_STOPWORDS`:

```python
EN_STOPWORDS.update({"video", "channel", "subscribe", "watch"})
```

### Korean morpheme analysis (advanced)

Replace `extract_text_tokens()` in `data_processor.py` with a
[KoNLPy](https://konlpy.org/) tokenizer for accurate Korean NLP:

```python
from konlpy.tag import Okt
okt = Okt()
tokens = okt.nouns(text)  # extract nouns only
```

Requires Java and the KoNLPy package. Not included by default to keep
setup simple.

---

## API quota

YouTube Data API v3 has a default **10,000 units/day** quota.

| Operation | Cost |
|-----------|------|
| `commentThreads.list` (1 page, up to 100 comments) | ~1 unit |
| `comments.list` for replies | ~1 unit per page |

Fetching 500 top-level comments uses roughly 5–10 units. A 2000-comment
run with many replies might use 50–100 units. You are unlikely to hit the
daily quota under normal use.

---

## Limitations

- **No timestamp analysis** — comment data has no video timestamp. Reaction spikes by video minute require live chat logs or YouTube Analytics.
- **Rule-based sentiment** — the lexicon approach cannot detect sarcasm or context. For production use, a fine-tuned multilingual model is recommended.
- **Korean tokenization** — spaces-based splitting is a simplification. KoNLPy gives accurate morpheme-level analysis.
- **Comments disabled** — if the video has comments disabled, the API returns a 403 and no data is collected.
- **API quota** — the default 10,000 units/day is generous for most use cases but can be exhausted on very large batch runs.
