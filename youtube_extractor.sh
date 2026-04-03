#!/bin/bash

# ============================================
# youtube_extractor.sh
# YouTube 영상 다운로드 + (선택) 자막 추출 + 문장 세그먼트 생성
# ============================================
#
# 필수 설치:
#   brew install yt-dlp python3  (Mac)
#   sudo apt install yt-dlp python3  (Linux)
#
# 사용법:
#   ./youtube_extractor.sh "YouTube_URL"
#
# 예시:
#   ./youtube_extractor.sh "https://www.youtube.com/watch?v=Ef5fYM-WiPA"
#
# 출력 폴더: lesson_VIDEO_ID/
#   video.mp4           — 원본 영상 (720p)   [항상 생성]
#   video_meta.json     — 영상 메타데이터     [항상 생성]
#   subtitles.vtt       — 원본 VTT 자막       [자막 있을 때만]
#   subtitles.srt       — 정제된 SRT 자막     [자막 있을 때만]
#   segments.json       — 문장 세그먼트 +     [자막 있을 때만]
#                         단어 타이밍
#   video_guide.md      — 구간별 타임스탬프   [자막 있을 때만]
#                         가이드
#
# 자막이 없어도 영상 다운로드 + 메타데이터 생성은 항상 완료됩니다.
# segments.json 없이 highlight_pipeline.py를 실행하면 semantic 매칭으로
# 동작합니다 (--segments 생략).
#
# highlight_pipeline.py 연동:
#   # 자막/세그먼트 있는 경우:
#   python highlight_pipeline.py \
#     --segments lesson_VIDEO_ID/segments.json \
#     --comments output/comments_cleaned.csv \
#     --video-id VIDEO_ID
#
#   # 자막 없는 경우:
#   python highlight_pipeline.py \
#     --comments output/comments_cleaned.csv \
#     --video-id VIDEO_ID
# ============================================

# Do NOT use set -e — subtitle absence must not abort the workflow.
# Each step uses explicit error checks instead.

# ── 색상 정의 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── 인자 확인 ──────────────────────────────────────────────────────────────────
if [ -z "$1" ]; then
    echo -e "${RED}❌ 사용법: $0 \"YouTube_URL\"${NC}"
    echo ""
    echo "예시:"
    echo "  $0 \"https://www.youtube.com/watch?v=Ef5fYM-WiPA\""
    exit 1
fi

URL="$1"

VIDEO_ID=$(echo "$URL" | grep -oE '[a-zA-Z0-9_-]{11}' | head -1)
if [ -z "$VIDEO_ID" ]; then
    echo -e "${RED}❌ 올바른 YouTube URL이 아닙니다${NC}"
    exit 1
fi

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  YouTube 영상 추출기${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "${YELLOW}📺 Video ID: ${VIDEO_ID}${NC}"
echo ""

WORK_DIR="lesson_${VIDEO_ID}"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo -e "${GREEN}📁 작업 폴더: $(pwd)${NC}"
echo ""

# ── 상태 플래그 ─────────────────────────────────────────────────────────────────
HAS_VIDEO=0
HAS_SUBTITLES=0
VIDEO_FILE="video.mp4"
VTT_FILE="subtitles.vtt"
SRT_FILE="subtitles.srt"

# ── 1. 영상 정보 가져오기 ───────────────────────────────────────────────────────
echo -e "${YELLOW}[1/3] 📋 영상 정보 가져오는 중...${NC}"
TITLE=$(yt-dlp --get-title "$URL" 2>/dev/null | head -1)
CHANNEL=$(yt-dlp --print channel "$URL" 2>/dev/null | head -1)
TITLE="${TITLE:-제목 없음}"
CHANNEL="${CHANNEL:-채널 없음}"
echo -e "      제목: ${TITLE}"
echo -e "      채널: ${CHANNEL}"
echo ""

SAFE_TITLE=$(echo "$TITLE" | tr -cd '[:alnum:] _-' | tr ' ' '_' | cut -c1-50)

# ── 2. 영상 다운로드 (720p) — 주 목표 ──────────────────────────────────────────
echo -e "${YELLOW}[2/3] 🎬 영상 다운로드 중 (720p)...${NC}"

yt-dlp --extractor-args "youtube:player_client=android_creator" -f "best[height<=720]" \
    -o "${VIDEO_FILE}" "$URL" 2>/dev/null
RC=$?

# Fallback: drop player_client hint, allow any container extension
if [ $RC -ne 0 ] || [ ! -f "$VIDEO_FILE" ]; then
    yt-dlp -f "best[height<=720]" -o "video.%(ext)s" "$URL" 2>/dev/null
    FOUND_VID=$(ls video.mp4 video.webm video.mkv 2>/dev/null | head -1)
    if [ -n "$FOUND_VID" ]; then
        VIDEO_FILE="$FOUND_VID"
    fi
fi

if [ -f "$VIDEO_FILE" ]; then
    HAS_VIDEO=1
    echo -e "      ${GREEN}✅ 영상 저장: ${VIDEO_FILE}${NC}"
else
    echo -e "${RED}❌ 영상 다운로드 실패${NC}"
    # Write minimal metadata even on video failure so the folder is useful
    python3 -c "
import json, sys
meta = {
    'videoId': '${VIDEO_ID}',
    'title':   '${TITLE}',
    'channel': '${CHANNEL}',
    'sourceUrl': '${URL}',
    'status': 'video_download_failed',
    'videoFile': None,
    'subtitleFile': None,
    'srtFile': None,
    'segmentsFile': None,
    'guideFile': None,
    'createdAt': __import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
}
with open('video_meta.json', 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
" 2>/dev/null
    exit 1
fi
echo ""

# ── 3. 자막 다운로드 (선택) ────────────────────────────────────────────────────
echo -e "${YELLOW}[3/3] 📝 자막 다운로드 시도 중...${NC}"

# Attempt 1 — English auto-captions
yt-dlp --write-auto-sub --sub-lang en --sub-format vtt --skip-download \
    -o "${SAFE_TITLE}" "$URL" 2>/dev/null || true

FOUND_VTT=$(ls *.vtt 2>/dev/null | head -1)

# Attempt 2 — Any available auto-caption language
if [ -z "$FOUND_VTT" ]; then
    echo -e "      (영어 자막 없음 — 다른 언어 자막 재시도 중...)"
    yt-dlp --write-auto-sub --sub-format vtt --skip-download \
        -o "${SAFE_TITLE}" "$URL" 2>/dev/null || true
    FOUND_VTT=$(ls *.vtt 2>/dev/null | head -1)
fi

if [ -n "$FOUND_VTT" ]; then
    mv "$FOUND_VTT" "$VTT_FILE" 2>/dev/null || true
    HAS_SUBTITLES=1
    echo -e "      ${GREEN}✅ 자막 저장: ${VTT_FILE}${NC}"
else
    echo -e "      ${YELLOW}⚠️  자막 없음 (자막 비활성화 또는 미지원 영상) — 계속 진행${NC}"
fi
echo ""

# ── 4. 자막 파싱 & 문장 세그먼트 생성 (자막 있을 때만) ─────────────────────────
if [ "$HAS_SUBTITLES" -eq 1 ]; then
    echo -e "${YELLOW}[4/4] 🔍 자막 분석 & 문장 세그먼트 생성 중...${NC}"

    python3 << 'PYTHON_SCRIPT'
import re
import json
import glob
import sys

# ── Safety limits ──────────────────────────────────────────────────────────
MAX_DURATION  = 9.0    # seconds — flush segment if exceeded
MAX_CHARS     = 140    # characters — flush segment if exceeded
SIM_THRESHOLD = 0.80   # Jaccard word-overlap — skip near-duplicate cues

# ── VTT time helpers ───────────────────────────────────────────────────────

def parse_vtt_time(ts):
    """'HH:MM:SS.mmm' → float seconds"""
    h, m, s = ts.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def fmt_srt_time(s):
    """float seconds → 'HH:MM:SS,mmm' (SRT format)"""
    ms  = int(round(s * 1000))
    h   = ms // 3_600_000; ms %= 3_600_000
    m   = ms // 60_000;    ms %= 60_000
    sec = ms // 1_000;     ms %= 1_000
    return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

# ── VTT parser ─────────────────────────────────────────────────────────────

def parse_vtt(filepath):
    """
    Parse a YouTube VTT auto-caption file.

    YouTube VTT uses a rolling-window format:
      - Each cue block has 1–2 body lines.
      - Line 1 (when present) is the PREVIOUS phrase repeated — discard it.
      - Line 2 is the NEW content, with <HH:MM:SS.mmm><c>word</c> timing tags.
      - ~10 ms flash cues (transition artifacts) carry no new content — skip them.

    Returns:
      entries   — list of {start, end, text} dicts (one per kept cue)
      all_words — flat list of {word, time} dicts (deduplicated, sorted by time)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    tc_re   = re.compile(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})')
    word_re = re.compile(r'<(\d{2}:\d{2}:\d{2}\.\d{3})><c>(.*?)</c>')

    entries   = []
    raw_words = []

    for block in re.split(r'\n\n+', content.strip()):
        lines = block.strip().split('\n')

        tc_line_idx = None
        tc_match    = None
        for i, ln in enumerate(lines):
            m = tc_re.match(ln.strip())
            if m:
                tc_line_idx = i
                tc_match    = m
                break
        if tc_match is None:
            continue

        start = parse_vtt_time(tc_match.group(1))
        end   = parse_vtt_time(tc_match.group(2))

        if end - start < 0.05:
            continue

        body_lines  = [ln.strip() for ln in lines[tc_line_idx + 1:]]
        active_line = None
        for ln in reversed(body_lines):
            if ln:
                active_line = ln
                break
        if not active_line:
            continue

        import html as _html
        clean = _html.unescape(re.sub(r'<[^>]+>', '', active_line)).strip()
        if not clean:
            continue

        entries.append({'start': start, 'end': end, 'text': clean})

        bare = re.match(r'^([^<\s][^<]*?)(?=<|$)', active_line)
        if bare:
            w = bare.group(1).strip()
            if w:
                raw_words.append((start, w))
        for wm in word_re.finditer(active_line):
            t = parse_vtt_time(wm.group(1))
            w = wm.group(2).strip()
            if w:
                raw_words.append((t, w))

    deduped_words = []
    last_t = -1.0
    for (t, w) in sorted(raw_words, key=lambda x: x[0]):
        if t > last_t + 0.001:
            deduped_words.append({'word': w, 'time': round(t, 3)})
            last_t = t

    return entries, deduped_words

# ── Rolling-window collapse ─────────────────────────────────────────────────

def collapse_overlapping(entries):
    if not entries:
        return entries
    collapsed = [entries[0]]
    for cur in entries[1:]:
        prev = collapsed[-1]
        if cur['start'] < prev['end'] - 0.02:
            if len(cur['text']) > len(prev['text']):
                collapsed[-1] = cur
        else:
            collapsed.append(cur)
    return collapsed

# ── SRT writer ─────────────────────────────────────────────────────────────

def write_srt(entries, filepath):
    blocks = []
    for i, e in enumerate(entries, 1):
        blocks.append(
            f"{i}\n{fmt_srt_time(e['start'])} --> {fmt_srt_time(e['end'])}\n{e['text']}"
        )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(blocks) + '\n')

# ── Sentence segment builder ───────────────────────────────────────────────

def word_jaccard(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

def build_sentence_segments(entries):
    segments  = []
    seg_texts = []
    seg_start = None
    seg_end   = None
    prev_text = None

    for entry in entries:
        text = entry['text']

        if prev_text is not None and word_jaccard(text, prev_text) >= SIM_THRESHOLD:
            continue
        prev_text = text

        if seg_start is None:
            seg_start = entry['start']
            seg_end   = entry['end']
            seg_texts = [text]
        else:
            proposed     = ' '.join(seg_texts + [text])
            proposed_dur = entry['end'] - seg_start

            if proposed_dur > MAX_DURATION or len(proposed) > MAX_CHARS:
                segments.append({
                    'id':    f'seg_{len(segments)+1:04d}',
                    'start': round(seg_start, 3),
                    'end':   round(seg_end, 3),
                    'text':  ' '.join(seg_texts),
                })
                seg_start = entry['start']
                seg_end   = entry['end']
                seg_texts = [text]
            else:
                seg_texts.append(text)
                seg_end = entry['end']

        last_char = seg_texts[-1].rstrip()[-1:] if seg_texts else ''
        if last_char in '.?!':
            segments.append({
                'id':    f'seg_{len(segments)+1:04d}',
                'start': round(seg_start, 3),
                'end':   round(seg_end, 3),
                'text':  ' '.join(seg_texts),
            })
            seg_texts = []
            seg_start = None
            seg_end   = None
            prev_text = None

    if seg_texts:
        segments.append({
            'id':    f'seg_{len(segments)+1:04d}',
            'start': round(seg_start, 3),
            'end':   round(seg_end, 3),
            'text':  ' '.join(seg_texts),
        })

    return segments

# ── Word-timing assignment ─────────────────────────────────────────────────

def assign_words(segments, all_words):
    for seg in segments:
        ws = [w for w in all_words if seg['start'] <= w['time'] < seg['end']]
        if ws:
            seg['words'] = ws

# ── Main ───────────────────────────────────────────────────────────────────

vtt_files = glob.glob('*.vtt')
if not vtt_files:
    print('      ⚠️  VTT 파일 없음 — 세그먼트 생성 건너뜀')
    sys.exit(0)

entries, all_words = parse_vtt(vtt_files[0])

before_collapse = len(entries)
entries = collapse_overlapping(entries)
collapsed_count = before_collapse - len(entries)
if collapsed_count:
    print(f'      ℹ️  롤링 윈도우 중복 {collapsed_count}개 제거')

write_srt(entries, 'subtitles.srt')

segments = build_sentence_segments(entries)
assign_words(segments, all_words)

with open('segments.json', 'w', encoding='utf-8') as f:
    json.dump(segments, f, ensure_ascii=False, indent=2)

segs_with_words = sum(1 for s in segments if 'words' in s)
total_words     = sum(len(s.get('words', [])) for s in segments)
print(f'      ✅ {len(entries)}개 VTT 큐 → {len(segments)}개 문장 세그먼트')
print(f'      ✅ {segs_with_words}/{len(segments)}개 세그먼트에 단어 타이밍 포함 (총 {total_words}개)')
PYTHON_SCRIPT

    echo ""
fi

# ── video_meta.json (항상 생성) ─────────────────────────────────────────────────
CREATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
python3 -c "
import json, os
has_sub  = os.path.exists('subtitles.vtt')
has_srt  = os.path.exists('subtitles.srt')
has_segs = os.path.exists('segments.json')
meta = {
    'videoId':      '${VIDEO_ID}',
    'title':        '${TITLE}',
    'channel':      '${CHANNEL}',
    'sourceUrl':    '${URL}',
    'videoFile':    '${VIDEO_FILE}',
    'subtitleFile': 'subtitles.vtt'  if has_sub  else None,
    'srtFile':      'subtitles.srt'  if has_srt  else None,
    'segmentsFile': 'segments.json'  if has_segs else None,
    'guideFile':    'video_guide.md' if has_segs else None,
    'createdAt':    '${CREATED_AT}'
}
with open('video_meta.json', 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print('      ✅ video_meta.json 생성 완료')
"

# ── 구간별 가이드 생성 (세그먼트 있을 때만) ────────────────────────────────────────
if [ -f "segments.json" ]; then
    echo ""
    echo -e "${YELLOW}📝 구간별 가이드 생성 중...${NC}"

    python3 << PYTHON_GUIDE
import json

def fmt(s):
    m, sec = divmod(int(s), 60)
    return f'{m:02d}:{sec:02d}'

with open('segments.json', 'r', encoding='utf-8') as f:
    segs = json.load(f)

vid = "${VIDEO_ID}"

md = [
    "# 구간별 타임스탬프 가이드",
    "",
    f"📺 **영상:** [YouTube에서 보기](https://www.youtube.com/watch?v={vid})",
    "",
    "---",
    "",
    "## 요약",
    "",
    f"| 항목 | 값 |",
    f"|------|------|",
    f"| 문장 세그먼트 | **{len(segs)}개** |",
    "",
    "---",
    "",
    "## 문장 세그먼트",
    "",
]

for seg in segs:
    t = int(seg['start'])
    link = f"https://www.youtube.com/watch?v={vid}&t={t}s"
    md.append(f"**[{fmt(seg['start'])}]({link})** ~ {fmt(seg['end'])}")
    md.append("")
    md.append(f"> {seg['text']}")
    md.append("")

with open('video_guide.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(md))

print("      ✅ video_guide.md 생성 완료")
PYTHON_GUIDE
fi

# ── 완료 ────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}✅ 완료!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "📁 생성된 파일 (${WORK_DIR}/):"

# List only files that actually exist
[ -f "${VIDEO_FILE}" ]    && echo -e "   ├── ${VIDEO_FILE}            (원본 영상 720p)"
[ -f "video_meta.json" ]  && echo -e "   ├── video_meta.json         (영상 메타데이터)"
[ -f "subtitles.vtt" ]    && echo -e "   ├── subtitles.vtt           (원본 VTT 자막 — 단어 타이밍 포함)"
[ -f "subtitles.srt" ]    && echo -e "   ├── subtitles.srt           (정제된 SRT 자막)"
[ -f "segments.json" ]    && echo -e "   ├── segments.json           (문장 세그먼트 + 단어 타이밍)"
[ -f "video_guide.md" ]   && echo -e "   └── video_guide.md          (구간별 타임스탬프 가이드)"

if [ "$HAS_SUBTITLES" -eq 0 ]; then
    echo ""
    echo -e "${YELLOW}  ⚠️  자막을 가져오지 못했습니다. segments.json 없이도 highlight_pipeline.py를${NC}"
    echo -e "${YELLOW}     실행할 수 있습니다 (--segments 생략, semantic 매칭 모드).${NC}"
fi

echo ""
echo -e "${YELLOW}💡 다음 단계 — 하이라이트 파이프라인:${NC}"

if [ -f "segments.json" ]; then
    echo -e "   python highlight_pipeline.py \\"
    echo -e "     --segments ${WORK_DIR}/segments.json \\"
    echo -e "     --comments output/comments_cleaned.csv \\"
    echo -e "     --video-id ${VIDEO_ID}"
else
    echo -e "   python highlight_pipeline.py \\"
    echo -e "     --comments output/comments_cleaned.csv \\"
    echo -e "     --video-id ${VIDEO_ID}"
    echo -e "   (자막 없으므로 --segments 생략 — semantic 매칭 모드로 동작)"
fi
echo ""
