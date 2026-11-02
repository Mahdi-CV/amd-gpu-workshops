#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-${ROOT}/amd-booth-teaser.mp4}"
if [[ "${OUT}" != /* ]]; then
  OUT="${ROOT}/${OUT#./}"
fi
WIDTH="${WIDTH:-1920}"
HEIGHT="${HEIGHT:-1080}"
FPS="${FPS:-30}"
DURATION="60"
QUALITY="${JPEG_QUALITY:-94}"
CHROME_BIN="${CHROME_BIN:-/snap/bin/chromium}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
FFMPEG_BIN="${FFMPEG_BIN:-/usr/bin/ffmpeg}"
FFPROBE_BIN="${FFPROBE_BIN:-/usr/bin/ffprobe}"
WORK="${ROOT}/.render"
FRAMES="${WORK}/frames"
POSTER_FRAME=$((57 * FPS))

case "${OUT}" in
  "${ROOT}"/*) ;;
  *)
    echo "Output must stay under ${ROOT}" >&2
    exit 2
    ;;
esac

for tool in "${PYTHON_BIN}" "${FFMPEG_BIN}" "${FFPROBE_BIN}" "${CHROME_BIN}"; do
  if [[ ! -x "${tool}" ]]; then
    echo "Missing required executable: ${tool}" >&2
    exit 2
  fi
done

if ! "${PYTHON_BIN}" -c "import websockets.sync.client" >/dev/null 2>&1; then
  echo "Python module 'websockets' is required for deterministic Chrome capture." >&2
  exit 2
fi

cleanup() {
  if [[ "${KEEP_FRAMES:-0}" != "1" ]]; then
    rm -rf -- "${WORK}"
  fi
}
trap cleanup EXIT

rm -rf -- "${WORK}"
mkdir -p "${FRAMES}"

echo "Capturing $((FPS * 60)) frames at ${WIDTH}x${HEIGHT}..."
"${PYTHON_BIN}" "${ROOT}/render_frames.py" \
  --html "${ROOT}/teaser.html" \
  --output-dir "${FRAMES}" \
  --chrome "${CHROME_BIN}" \
  --width "${WIDTH}" \
  --height "${HEIGHT}" \
  --fps "${FPS}" \
  --duration "${DURATION}" \
  --quality "${QUALITY}"

poster_source="$(printf "%s/frame_%06d.jpg" "${FRAMES}" "${POSTER_FRAME}")"
if [[ -f "${poster_source}" ]]; then
  cp "${poster_source}" "${ROOT}/poster.jpg"
fi

common_video_args=(
  -map 0:v:0
  -c:v libx264
  -preset slow
  -crf 18
  -profile:v high
  -level:v 4.1
  -pix_fmt yuv420p
  -r "${FPS}"
  -g "$((FPS * 2))"
  -video_track_timescale 90000
  -movflags +faststart
  -metadata "title=AMD Booth Agent — 60-second teaser"
  -metadata "comment=Cloud API/token estimates exclude local hardware, hosting, power, and operations."
)

echo "Encoding ${OUT}..."
if [[ -n "${VOICEOVER_AUDIO:-}" ]]; then
  if [[ ! -f "${VOICEOVER_AUDIO}" ]]; then
    echo "VOICEOVER_AUDIO does not exist: ${VOICEOVER_AUDIO}" >&2
    exit 2
  fi
  "${FFMPEG_BIN}" -hide_banner -loglevel warning -y \
    -framerate "${FPS}" -start_number 0 -i "${FRAMES}/frame_%06d.jpg" \
    -i "${VOICEOVER_AUDIO}" \
    -filter_complex "[1:a]apad=pad_dur=${DURATION},atrim=duration=${DURATION}[audio]" \
    "${common_video_args[@]}" \
    -map "[audio]" -c:a aac -b:a 160k -ar 48000 -ac 2 \
    -t "${DURATION}" \
    "${OUT}"
else
  "${FFMPEG_BIN}" -hide_banner -loglevel warning -y \
    -framerate "${FPS}" -start_number 0 -i "${FRAMES}/frame_%06d.jpg" \
    -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \
    "${common_video_args[@]}" \
    -map 1:a:0 -c:a aac -b:a 128k -ar 48000 -ac 2 \
    -t "${DURATION}" \
    "${OUT}"
fi

FFMPEG_BIN="${FFMPEG_BIN}" FFPROBE_BIN="${FFPROBE_BIN}" \
  "${PYTHON_BIN}" "${ROOT}/validate_video.py" "${OUT}" \
  --width "${WIDTH}" \
  --height "${HEIGHT}" \
  --fps "${FPS}" \
  --duration "${DURATION}" \
  --decode

echo "Rendered: ${OUT}"
echo "Poster:   ${ROOT}/poster.jpg"
