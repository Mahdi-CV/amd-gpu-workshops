#!/usr/bin/env bash
# Puts the pinned vela3-fast model into ./models/vela3-fast for the image build and verifies every
# file against the SHA-256 the vLLM-SR runtime pins for this revision. The folder is git-ignored.
#
#   bash fetch-vela3-fast.sh                      # download from Hugging Face
#   VELA3_FAST_FROM=/path/to/copy bash fetch-vela3-fast.sh   # copy an existing copy instead
set -euo pipefail

REPO="vllm-sr/vela3-fast"
REVISION="7cbefd4b92b57234bd0ffb9872451e81abcdac79"   # the revision vllm-sr 6b782822 pins
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/models/vela3-fast"

# The 14 files the runtime loads (src/model-runtime/vllm_srun/registry/tables/vela3.py at 6b782822).
SUMS='a85b358ac11b71d780deb09e8a082efddc67938a2eb4fc16d68d8ae888c69d14  config.json
1aa3f1fdf590a369ba23ebf2b2b5896a0673a007b19597cfc6e7ca3a77cb067c  domain_adapter.safetensors
8aeda02d53ca0f29b1888c567b0e7199dd15ceea0b77faa26448f293840ac774  evidence_adapter.safetensors
fd90e966d466177e4bd2db7701372a98990d34dc9eccc9ec871113c929039b3b  factcheck_adapter.safetensors
c1d7e153fa6be7cd9aa704cd57077596d23949ea0beb9d6650cc3216021cffbb  feedback_df_adapter.safetensors
2294745881d9a01b7d049133b57e5fed2aec6ae1d34ef1ab9fa16f047fc35c8e  model.safetensors
387f409c7f954e696c2d95f6b85829e84e6ea8ad52128f2cf1340f7ee7045f8a  ner_adapter.safetensors
a448606d98c5f0c5e0e3249ac00465c69f58fa6995555b344e6c1d89b99c4d46  relation_adapter.safetensors
30c7f350bcc4060b302b26f57d73c965da8e8b75509c1262ae953942b11adac8  router_adapter.safetensors
5126f841279211df70ab027b6c124187dd444e22dbd10202f4e17de96ad432d5  router_questions.json
15eb0f11e4261bc6f54e4a6a6cc15951575a510dd1d0bd598e6a6d7a15800fd8  span_adapter.safetensors
73c904acf7a765a38fd793b0d5d9d02633f9c5938620c9e063063aa1458cf006  span_sets_adapter.safetensors
38734bb17ef19f84c67b5eb5692bea19801ffd02cb5c5ffc11429e76b0242e08  tokenizer.json
ee5088605aa5151210fbc12e3f6ee0c9a382dddf90d3a43ac606c0df305d9ff2  vela3_config.json'

mkdir -p "$DEST"
printf '%s\n' "$SUMS" > "$DEST/SHA256SUMS"
if [ -n "${VELA3_FAST_FROM:-}" ]; then
  echo "== copying $VELA3_FAST_FROM"
  for f in $(awk '{print $2}' "$DEST/SHA256SUMS"); do cp -a "$VELA3_FAST_FROM/$f" "$DEST/$f"; done
else
  echo "== downloading $REPO@$REVISION"
  for f in $(awk '{print $2}' "$DEST/SHA256SUMS"); do
    curl -fsSL --retry 3 -o "$DEST/$f" "https://huggingface.co/$REPO/resolve/$REVISION/$f"
  done
fi
(cd "$DEST" && sha256sum --quiet -c SHA256SUMS) && echo "vela3-fast verified: 14 files match the pinned SHA-256"
