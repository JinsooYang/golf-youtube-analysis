"""
live_chat — live chat replay extraction sub-package.

Pipeline:
    extractor   → yt-dlp subprocess wrapper; downloads .live_chat.json file
    parser      → parse yt-dlp JSONL output into raw event dicts
    normalizer  → convert raw events into flat, schema-stable records
    writer      → write output files (raw JSON, normalized CSV + JSON, log)

Usage:
    python extract_live_chat.py "https://www.youtube.com/watch?v=VIDEO_ID"

Integration with highlight pipeline:
    python highlight_pipeline.py \\
        --comments  output/comments_cleaned.csv \\
        --live-chat output/live_chat_normalized.csv \\
        --video-id  VIDEO_ID

Honesty constraints:
    - timestamp_seconds is always derived from videoOffsetTimeMsec (video offset,
      not epoch time) — this is the correct field for clip matching.
    - If videoOffsetTimeMsec is absent for a message, timestamp_seconds is null.
    - Extraction status is always reported clearly (success / partial / failed).
"""
