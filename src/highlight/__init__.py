"""
highlight — comment-driven highlight automation sub-package.

Pipeline:
    loaders   → load segments / comments / live-chat
    classifier → category + emotion_strength
    matcher    → semantic comment ↔ segment matching
    scorer     → priority_score
    packager   → assemble final data structures
    writer     → write output files
"""
