#!/usr/bin/env bash
# Builds vllm_sr_lab_install.sh from installer-template.sh with the current setup.sh embedded.
# Run after changing either file:  bash make-installer.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 - "$HERE" <<'PY'
import hashlib, pathlib, sys
here = pathlib.Path(sys.argv[1])
setup = (here / "setup.sh").read_text(encoding="utf-8")
assert "VLLM_SR_SETUP_SH" not in setup, "setup.sh must not contain the heredoc delimiter"
sha = hashlib.sha256(setup.encode()).hexdigest()[:12]
out = (here / "installer-template.sh").read_text(encoding="utf-8")
out = out.replace("@@SETUP_SH@@\n", setup).replace("@@SETUP_SHA@@", sha)
target = here / "vllm_sr_lab_install.sh"
target.write_text(out, encoding="utf-8")
target.chmod(0o755)
print(f"wrote {target.name} (setup.sh sha {sha})")
PY
