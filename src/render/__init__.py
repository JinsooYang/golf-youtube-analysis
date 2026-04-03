"""
render — draft video rendering sub-package.

Pipeline:
    ffmpeg_utils       → low-level ffmpeg/ffprobe subprocess wrappers
    cards              → Pillow-based still card image generation
    overlay            → Pillow-based transparent comment overlay images
    shorts_renderer    → render Shorts drafts from shorts_sequences
    highlight_renderer → render master highlight from master_plan

All rendering is driven by highlight_package.json and master_highlight_plan.json
produced by the planning layer (highlight_pipeline.py).

Confidence gating:
    matching_confidence in {high, medium} AND needs_manual_timestamp_mapping=False
    → automatic clip render
    anything else → red placeholder card (editor must fill in)
"""
