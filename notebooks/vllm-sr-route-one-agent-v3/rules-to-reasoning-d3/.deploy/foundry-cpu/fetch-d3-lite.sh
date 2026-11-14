#!/usr/bin/env bash
# Puts the pinned d3-lite model into ./models/d3-lite for the image build and verifies every
# file against the model's own MODEL_MANIFEST.json (SHA-256). The folder is git-ignored.
#
#   bash fetch-d3-lite.sh                 # download from Hugging Face
#   D3_LITE_FROM=/path/to/snapshot bash fetch-d3-lite.sh   # copy an existing copy instead
set -euo pipefail

REPO="vllm-sr/d3-lite"
REVISION="a8d25a91ef75552803f7009d25b7bd435991abd9"   # the revision vllm-sr 6b782822 pins
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/models/d3-lite"

mkdir -p "$DEST"
if [ -n "${D3_LITE_FROM:-}" ]; then
  echo "== copying $D3_LITE_FROM"
  cp -a "$D3_LITE_FROM"/. "$DEST"/
else
  echo "== downloading $REPO@$REVISION"
  curl -fsSL "https://huggingface.co/api/models/$REPO/revision/$REVISION" \
    | python3 -c 'import json,sys; [print(s["rfilename"]) for s in json.load(sys.stdin)["siblings"]]' \
    | while read -r f; do
        mkdir -p "$DEST/$(dirname "$f")"
        curl -fsSL --retry 3 -o "$DEST/$f" "https://huggingface.co/$REPO/resolve/$REVISION/$f"
      done
fi

python3 - "$DEST" <<'PY'
import hashlib, json, os, sys
root = sys.argv[1]
files = json.load(open(os.path.join(root, "MODEL_MANIFEST.json")))["files_sha256"]
bad = []
for name, want in files.items():
    path = os.path.join(root, name)
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        bad.append(name + " (missing)")
        continue
    if h.hexdigest() != want:
        bad.append(name)
if bad:
    sys.exit("d3-lite verification FAILED: " + ", ".join(bad))
print(f"d3-lite verified: {len(files)} files match MODEL_MANIFEST.json")
PY
