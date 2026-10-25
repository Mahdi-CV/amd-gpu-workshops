"""Notebook-facing runtime API for the OpenClaw vLLM-SR workshop."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


OLD_ACCURACY_LINE = (
    "    return round((correct // (total_typed + 1)) * 100, 1)"
)
NEW_ACCURACY_LINE = "    return round((correct / total_typed) * 100, 1)"
EQUIVALENT_ACCURACY_LINE = (
    "    return round(correct / total_typed * 100, 1)"
)
ACCEPTED_ACCURACY_LINES = (
    NEW_ACCURACY_LINE,
    EQUIVALENT_ACCURACY_LINE,
)
MODEL_LABELS = {
    "qwen/qwen3.8-flash-next": "Qwen3.8-Flash-Next",
    "qwen/qwen3.8-27b": "Qwen3.8-27B",
    "zai/glm-5.3-flash": "GLM-5.3-Flash",
}
GLM_PROMPT_RATE = 0.44
GLM_COMPLETION_RATE = 4.35


class WorkshopLab:
    def __init__(self) -> None:
        self.root = Path(os.getenv("WORKSHOP_ROOT", "/opt/workshop"))
        self.workspace = Path(os.getenv("WORKSHOP_WORKSPACE", "/workspace"))
        self.runtime = Path(
            os.getenv("WORKSHOP_RUNTIME_DIR", self.workspace / "runtime")
        )
        self.state = Path(
            os.getenv("OPENCLAW_STATE_DIR", self.workspace / "state/openclaw")
        )
        self.agents = Path(
            os.getenv(
                "OPENCLAW_WORKSHOP_WORKSPACES",
                self.workspace / "agents",
            )
        )
        self.demo_root = Path(
            os.getenv(
                "OPENCLAW_WORKSHOP_DEMO_ROOT",
                self.workspace / "demo",
            )
        )
        self.demo_repo = self.demo_root / "open_type_faster"
        self.fixture = self.root / ".deploy/fixture/open_type_faster"
        self.routes = self.runtime / "routes.jsonl"
        self.phase_file = self.runtime / "current-phase.json"
        self.gateway_pid = self.runtime / "gateway.pid"
        self.gateway_log = self.runtime / "gateway.log"
        self.verification_file = self.runtime / "verification.json"
        self.rehearsal_file = (
            self.root / ".deploy/artifacts/simple-route-results.json"
        )
        self.policy_analysis_file = (
            self.root / ".deploy/artifacts/policy-analysis.json"
        )
        self.openclaw = shutil.which("openclaw") or "openclaw"
        self.auto_model = os.getenv("AUTO_MODEL", "vllm-sr/auto")
        self.provider_id = os.getenv("OPENCLAW_PROVIDER_ID", "vllm-sr")
        for path in (
            self.workspace,
            self.runtime,
            self.state.parent,
            self.agents,
            self.demo_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "OPENCLAW_STATE_DIR": str(self.state),
            "HOME": os.getenv("HOME", "/home/workshop"),
        }

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 300,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        print("$", " ".join(map(str, command)))
        result = subprocess.run(
            list(map(str, command)),
            cwd=str(cwd) if cwd else None,
            env=self.env,
            text=True,
            capture_output=capture,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode:
            detail = (result.stderr or result.stdout)[-2000:]
            raise RuntimeError(
                f"Command failed ({result.returncode}): {detail}"
            )
        return result

    def openclaw_command(
        self,
        *args: str,
        timeout: int = 300,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [self.openclaw, *args],
            timeout=timeout,
            capture=capture,
        )

    def _proxy_ready(self) -> bool:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:19090/readyz",
                timeout=3,
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    @staticmethod
    def _port_ready(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def _fixture_manifest_ok(self) -> bool:
        manifest = self.root / ".deploy/fixture/MANIFEST.sha256"
        if not self.fixture.is_dir() or not manifest.is_file():
            return False
        result = subprocess.run(
            ["sha256sum", "-c", str(manifest)],
            cwd=str(manifest.parent),
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def status(self) -> dict[str, Any]:
        openclaw_version = self._run(
            [self.openclaw, "--version"],
            check=False,
        )
        fixture_ok = self._fixture_manifest_ok()
        gpu_devices = Path("/dev/kfd").exists() or any(
            Path("/dev/dri").glob("renderD*")
        )
        result = {
            "openclaw": (
                openclaw_version.stdout.strip()
                if openclaw_version.returncode == 0
                else "unavailable"
            ),
            "proxy_ready": self._proxy_ready(),
            "state_configured": (self.state / "openclaw.json").is_file(),
            "fixture_ready": fixture_ok,
            "workspace_writable": os.access(self.workspace, os.W_OK),
            "gateway_ready": self._port_ready(18789),
            "gpu_devices_present": gpu_devices,
        }
        result["ready"] = all(
            (
                result["proxy_ready"],
                result["state_configured"],
                result["fixture_ready"],
                result["workspace_writable"],
                not result["gpu_devices_present"],
            )
        )
        return result

    def check_ready(self) -> dict[str, Any]:
        result = self.status()
        labels = {
            "openclaw": "OpenClaw",
            "proxy_ready": "vLLM-SR proxy",
            "state_configured": "OpenClaw base state",
            "fixture_ready": "debugging fixture",
            "workspace_writable": "writable workspace",
            "gateway_ready": "Gateway",
            "gpu_devices_present": "GPU devices hidden",
        }
        for key, label in labels.items():
            value = result[key]
            if key == "openclaw":
                print(f"✓ {label}: {value}")
            elif key == "gpu_devices_present":
                print(("✗" if value else "✓"), label)
            elif key == "gateway_ready":
                print(("✓" if value else "○"), f"{label}: {'running' if value else 'stopped'}")
            else:
                print(("✓" if value else "✗"), label)
        if not result["ready"]:
            raise RuntimeError(
                "Workshop runtime is not ready. Run workshop-status."
            )
        return result

    def reset_demo(self) -> Path:
        if self.demo_root.exists():
            shutil.rmtree(self.demo_root)
        self.demo_root.mkdir(parents=True)
        shutil.copytree(self.fixture, self.demo_repo)
        return self.demo_repo

    def baseline_demo(self) -> dict[str, Any]:
        self.reset_demo()
        result = self._run(
            [
                os.getenv("PYTHON", "python3"),
                "-m",
                "pytest",
                "tests",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            cwd=self.demo_repo,
            check=False,
            timeout=180,
        )
        value = {
            "returncode": result.returncode,
            "contains_5_failed_102_passed": (
                "5 failed" in result.stdout and "102 passed" in result.stdout
            ),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        value["ready"] = (
            value["returncode"] == 1
            and value["contains_5_failed_102_passed"]
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if not value["ready"]:
            raise RuntimeError("Fixture baseline is not 5 failed, 102 passed.")
        return value

    def _configured_agents(self) -> set[str]:
        result = self.openclaw_command("agents", "list", "--json")
        body = json.loads(result.stdout)
        rows = body.get("agents", body) if isinstance(body, dict) else body
        return {str(item.get("id")) for item in rows}

    def _role_files(self) -> dict[str, str]:
        source = (self.fixture / "stats.py").read_text(encoding="utf-8")
        start = source.index("def _accuracy")
        end = source.index("\ndef _count_correct", start)
        accuracy_source = source[start:end].strip()
        tests = (self.fixture / "tests/test_stats.py").read_text(
            encoding="utf-8"
        )
        test_start = tests.index("class TestAccuracy")
        test_end = tests.index("# ── _count_correct", test_start)
        accuracy_tests = tests[test_start:test_end].strip()
        return {
            "main": """# Team Reporter

Summarize only the verified result supplied by the user. Keep the answer to
the requested length. No filesystem or execution work is required.
""",
            "bug_reviewer": f"""# Bug Reviewer

Review the supplied implementation and observed failures. All evidence is
below. Identify the root cause and smallest source-only fix.

```python
{accuracy_source}
```

Observed failures:
- perfect: expected 100.0, got 0
- half correct: expected 50.0, got 0
- two of three: expected 66.7, got 0
""",
            "test_reviewer": f"""# Test Reviewer

Define the behavioral contract and regression matrix from the complete
evidence below.

Implementation:
```python
{accuracy_source}
```

Existing contract:
```python
{accuracy_tests}
```
""",
            "fixer": f"""# Fixer

Work only in:

{self.demo_repo}

Use filesystem and execution tools. Preserve every test file. Apply the
reviewer handoff, make the smallest source-only correction, run the complete
pytest suite, and report the result.
""",
        }

    def add_team(self) -> dict[str, str]:
        self.stop_gateway()
        self.reset_demo()
        model_ref = f"{self.provider_id}/{self.auto_model}"
        existing = self._configured_agents()
        for agent in ("bug_reviewer", "test_reviewer", "fixer"):
            if agent not in existing:
                self.openclaw_command(
                    "agents",
                    "add",
                    agent,
                    "--non-interactive",
                    "--workspace",
                    str(self.agents / agent),
                    "--model",
                    model_ref,
                )
        for agent in ("main", "bug_reviewer", "test_reviewer", "fixer"):
            self.openclaw_command(
                "config",
                "set",
                f"agents.entries.{agent}.model",
                model_ref,
            )
            self.openclaw_command(
                "config",
                "set",
                f"agents.entries.{agent}.skills",
                "[]",
                "--strict-json",
            )
            self.openclaw_command(
                "config",
                "set",
                f"agents.entries.{agent}.tools.profile",
                "coding" if agent == "fixer" else "minimal",
            )
        roles = self._role_files()
        for agent, instructions in roles.items():
            workspace = self.agents / agent
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "AGENTS.md").write_text(
                instructions,
                encoding="utf-8",
            )
            (workspace / "SOUL.md").write_text(
                "# Soul\n\nBe precise, calm, and evidence-driven.\n",
                encoding="utf-8",
            )
            (workspace / "IDENTITY.md").write_text(
                f"# Identity\n\nName: {agent}\n",
                encoding="utf-8",
            )
            (workspace / "USER.md").write_text(
                "# User\n\nPrefer minimal changes and verified results.\n",
                encoding="utf-8",
            )
            (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)
        return roles

    def _pid(self) -> int | None:
        if not self.gateway_pid.is_file():
            return None
        try:
            return int(self.gateway_pid.read_text())
        except ValueError:
            return None

    @staticmethod
    def _pid_matches(pid: int, text: str) -> bool:
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return False
        return text.encode() in raw

    def stop_gateway(self) -> None:
        pid = self._pid()
        if not pid:
            self.gateway_pid.unlink(missing_ok=True)
            return
        if not self._pid_matches(pid, "openclaw"):
            raise RuntimeError("Gateway PID file does not identify OpenClaw.")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self.gateway_pid.unlink(missing_ok=True)
            return
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.2)
        else:
            os.kill(pid, signal.SIGKILL)
        self.gateway_pid.unlink(missing_ok=True)

    def start_gateway(self) -> int:
        if self._port_ready(18789):
            pid = self._pid()
            return pid or 0
        log_handle = self.gateway_log.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [self.openclaw, "gateway"],
            env=self.env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.gateway_pid.write_text(str(process.pid), encoding="utf-8")
        for _ in range(120):
            if self._port_ready(18789):
                return process.pid
            if process.poll() is not None:
                raise RuntimeError(
                    f"Gateway exited. Inspect {self.gateway_log}."
                )
            time.sleep(1)
        raise TimeoutError("Gateway did not become ready.")

    def clear_routes(self) -> None:
        self.routes.parent.mkdir(parents=True, exist_ok=True)
        self.routes.write_text("", encoding="utf-8")
        self.mark_phase("unmarked")

    def mark_phase(self, phase: str) -> dict[str, Any]:
        value = {
            "phase": phase,
            "timestamp": time.time(),
        }
        self.phase_file.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Phase:", phase)
        return value

    @staticmethod
    def build_fixer_prompt(bug_review: str, test_review: str) -> str:
        if not bug_review.strip() or not test_review.strip():
            raise ValueError("Paste both reviewer outputs before the handoff.")
        return (
            "Use this debugging-team handoff as guidance.\n\n"
            "BUG REVIEW:\n"
            f"{bug_review.strip()}\n\n"
            "TEST REVIEW:\n"
            f"{test_review.strip()}\n\n"
            "Fix the prepared open_type_faster accuracy bug, run the complete "
            "pytest suite, and report the verified result."
        )

    @staticmethod
    def build_main_prompt(verification: dict[str, Any]) -> str:
        return (
            "In one sentence, summarize this independently verified result:\n"
            f"{json.dumps(verification, sort_keys=True)}"
        )

    @staticmethod
    def _tree_hashes(root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            hashes[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        return hashes

    def verify_demo(self) -> dict[str, Any]:
        tests = self._run(
            [
                os.getenv("PYTHON", "python3"),
                "-m",
                "pytest",
                "tests",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            cwd=self.demo_repo,
            check=False,
            timeout=180,
        )
        fixture_hashes = self._tree_hashes(self.fixture)
        demo_hashes = self._tree_hashes(self.demo_repo)
        test_keys = [
            key for key in fixture_hashes if key.startswith("tests/")
        ]
        tests_unchanged = all(
            demo_hashes.get(key) == fixture_hashes[key] for key in test_keys
        )
        changed = sorted(
            key
            for key in set(fixture_hashes) | set(demo_hashes)
            if fixture_hashes.get(key) != demo_hashes.get(key)
        )
        stats_text = (self.demo_repo / "stats.py").read_text(encoding="utf-8")
        fixture_stats = (self.fixture / "stats.py").read_text(
            encoding="utf-8"
        )
        replacement = next(
            (
                line
                for line in ACCEPTED_ACCURACY_LINES
                if stats_text
                == fixture_stats.replace(OLD_ACCURACY_LINE, line, 1)
            ),
            None,
        )
        source_fix_valid = (
            fixture_stats.count(OLD_ACCURACY_LINE) == 1
            and replacement is not None
            and changed == ["stats.py"]
        )
        exact_patch = (
            source_fix_valid and replacement == NEW_ACCURACY_LINE
        )
        value = {
            "pytest_returncode": tests.returncode,
            "pytest_summary": next(
                (
                    line
                    for line in reversed(tests.stdout.splitlines())
                    if "passed" in line or "failed" in line
                ),
                "",
            ),
            "contains_107_passed": "107 passed" in tests.stdout,
            "tests_unchanged": tests_unchanged,
            "changed_files": changed,
            "source_fix_valid": source_fix_valid,
            "source_fix_variant": (
                "canonical"
                if replacement == NEW_ACCURACY_LINE
                else "equivalent"
                if replacement == EQUIVALENT_ACCURACY_LINE
                else None
            ),
            "exact_source_patch": exact_patch,
        }
        value["passed"] = all(
            (
                value["pytest_returncode"] == 0,
                value["contains_107_passed"],
                value["tests_unchanged"],
                value["source_fix_valid"],
            )
        )
        self.verification_file.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(value, indent=2))
        return value

    def _load_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def route_report(self, *, source: str = "live") -> list[dict[str, Any]]:
        if source == "rehearsal":
            return self.rehearsal_report()
        if source != "live":
            raise ValueError("source must be 'live' or 'rehearsal'")
        rows = self._load_jsonl(self.routes)
        if not rows:
            print("No live route records. Run the TUI turns first.")
            return []
        report = []
        for row in rows:
            headers = row.get("routing_headers") or {}
            usage = row.get("usage") or {}
            projections = str(
                headers.get("x-vsr-matched-projections") or ""
            )
            effort = next(
                (
                    item.strip().removeprefix("effort_")
                    for item in projections.split(",")
                    if item.strip().startswith("effort_")
                ),
                None,
            )
            report.append(
                {
                    "call": row.get("request_id"),
                    "phase": row.get("phase"),
                    "decision": headers.get("x-vsr-selected-decision"),
                    "model": (
                        headers.get("x-vsr-selected-model")
                        or row.get("selected_cost_model")
                        or row.get("response_model")
                    ),
                    "reasoning": headers.get("x-vsr-selected-reasoning"),
                    "effort": effort,
                    "tools": row.get("tool_count"),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": usage.get("reasoning_tokens"),
                    "latency_s": row.get("latency_seconds"),
                    "first_byte_s": row.get("first_byte_seconds"),
                    "cost_xxx": row.get("estimated_relative_cost_xxx"),
                }
            )
        return report

    def rehearsal_report(self) -> list[dict[str, Any]]:
        if not self.rehearsal_file.is_file():
            print("No verified rehearsal artifact is installed.")
            return []
        body = json.loads(self.rehearsal_file.read_text(encoding="utf-8"))
        report = []
        call = 0
        for phase, rows in body.get("routes", {}).items():
            for row in rows:
                call += 1
                report.append({"call": call, "phase": phase, **row})
        print("Showing VERIFIED REHEARSAL data, not the live session.")
        return report

    @staticmethod
    def _routed_model_calls(
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if row.get("model")
            and (
                row.get("prompt_tokens") is not None
                or row.get("completion_tokens") is not None
            )
        ]

    def routing_summary(self, *, source: str = "live") -> dict[str, Any]:
        rows = self._routed_model_calls(self.route_report(source=source))
        if not rows:
            return {"source": source, "status": "no route data"}

        by_model: dict[str, dict[str, Any]] = {}
        effort_counts: dict[str, int] = {}
        for row in rows:
            model = str(row["model"])
            item = by_model.setdefault(
                model,
                {
                    "model": model,
                    "label": MODEL_LABELS.get(model, model),
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "reasoning_tokens": 0,
                    "relative_compute_xxx": 0.0,
                    "efforts": {},
                },
            )
            item["calls"] += 1
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
            ):
                item[key] += int(row.get(key) or 0)
            item["relative_compute_xxx"] += float(
                row.get("cost_xxx") or 0
            )

            effort = str(
                row.get("effort")
                or ("off" if row.get("reasoning") == "off" else "on")
            )
            item["efforts"][effort] = item["efforts"].get(effort, 0) + 1
            effort_counts[effort] = effort_counts.get(effort, 0) + 1

        total_calls = len(rows)
        model_rows = []
        for item in by_model.values():
            item["call_share_percent"] = round(
                item["calls"] / total_calls * 100,
                1,
            )
            item["relative_compute_xxx"] = round(
                item["relative_compute_xxx"],
                8,
            )
            item["efforts"] = dict(sorted(item["efforts"].items()))
            model_rows.append(item)
        model_rows.sort(key=lambda item: (-item["calls"], item["label"]))

        missing = [
            row["call"] for row in rows if row.get("cost_xxx") is None
        ]
        routed = sum(float(row.get("cost_xxx") or 0) for row in rows)
        all_glm = sum(
            (
                int(row.get("prompt_tokens") or 0) * GLM_PROMPT_RATE
                + int(row.get("completion_tokens") or 0)
                * GLM_COMPLETION_RATE
            )
            / 1_000_000
            for row in rows
        )
        reduction = (
            round((1 - routed / all_glm) * 100, 2)
            if all_glm and not missing
            else None
        )
        return {
            "source": source,
            "total_calls": total_calls,
            "models": model_rows,
            "reasoning_efforts": dict(sorted(effort_counts.items())),
            "relative_compute": {
                "vllm_sr_auto_xxx": round(routed, 8),
                "all_glm_flash_max_same_tokens_xxx": round(all_glm, 8),
                "reduction_percent": reduction,
                "routed_share_of_glm_baseline_percent": (
                    round(routed / all_glm * 100, 2)
                    if all_glm and not missing
                    else None
                ),
                "incomplete_cost_calls": missing,
                "baseline": (
                    "The same observed prompt and completion tokens priced "
                    "at the Decision Balance GLM-5.3-Flash relative-compute "
                    "rate. This conservative baseline does not add extra "
                    "tokens that max reasoning might generate."
                ),
            },
        }

    def show_routing_summary(
        self,
        *,
        source: str = "live",
        title: str = "OpenClaw routing summary",
    ) -> dict[str, Any]:
        summary = self.routing_summary(source=source)
        if summary.get("status") == "no route data":
            print("No routed model calls yet. Run the TUI turns first.")
            return summary

        print("=" * 78)
        print(title)
        print("=" * 78)
        print(f"Total routed LLM calls: {summary['total_calls']}")
        print()
        print(
            f"{'Selected model':<28}"
            f"{'Calls':>8}"
            f"{'Share':>10}"
            f"{'Reasoning effort':>24}"
        )
        print("-" * 78)
        for row in summary["models"]:
            efforts = ", ".join(
                f"{name}={count}"
                for name, count in row["efforts"].items()
            )
            print(
                f"{row['label']:<28}"
                f"{row['calls']:>8}"
                f"{row['call_share_percent']:>9.1f}%"
                f"{efforts:>24}"
            )

        compute = summary["relative_compute"]
        print()
        print("Relative compute (XXX; lower is better)")
        print("-" * 78)
        print(
            f"{'vLLM-SR auto':<48}"
            f"{compute['vllm_sr_auto_xxx']:>18.8f} XXX"
        )
        print(
            f"{'All GLM-5.3-Flash @ max (same tokens)':<48}"
            f"{compute['all_glm_flash_max_same_tokens_xxx']:>18.8f} XXX"
        )
        if compute["reduction_percent"] is not None:
            print(
                f"{'Relative compute avoided':<48}"
                f"{compute['reduction_percent']:>17.2f}%"
            )
            print(
                f"{'Auto used this share of the GLM baseline':<48}"
                f"{compute['routed_share_of_glm_baseline_percent']:>17.2f}%"
            )
        else:
            print(
                "Compute reduction unavailable because one or more routed "
                "calls had no token-cost record."
            )
        print()
        print(
            "* Conservative same-token comparison: it does not assume the "
            "additional reasoning tokens an all-GLM/max run may generate."
        )
        print("* XXX is relative compute, not dollars.")
        return summary

    def cost_summary(self, *, source: str = "live") -> dict[str, Any]:
        summary = self.routing_summary(source=source)
        if summary.get("status") == "no route data":
            return {"source": source, "status": "no route data"}
        compute = summary["relative_compute"]
        result = {
            "source": source,
            "calls": summary["total_calls"],
            "routed_estimated_xxx": compute["vllm_sr_auto_xxx"],
            "glm_repricing_of_same_tokens_xxx": compute[
                "all_glm_flash_max_same_tokens_xxx"
            ],
            "estimated_reduction_percent": compute["reduction_percent"],
            "incomplete_cost_calls": compute["incomplete_cost_calls"],
            "qualification": compute["baseline"],
        }
        return result

    def policy_comparison(self) -> dict[str, Any]:
        if not self.policy_analysis_file.is_file():
            raise FileNotFoundError(
                "The precomputed policy-analysis artifact is not installed."
            )
        body = json.loads(
            self.policy_analysis_file.read_text(encoding="utf-8")
        )
        auto = body["arms"]["auto"]
        direct = body["arms"]["direct_glm"]
        matched = body["matched_successful_pairs"]
        routing = body["same_auto_token_backend_mix"]
        result = {
            "quality_gate": body["quality_definition"],
            "reliability": {
                "vllm_sr_auto": (
                    f"{auto['functional_successes']}/{auto['attempts']}"
                ),
                "direct_glm": (
                    f"{direct['functional_successes']}/{direct['attempts']}"
                ),
            },
            "empirical_matched_successes": {
                "pairs": matched["count"],
                "auto_cost_xxx": matched["auto_cost_xxx"],
                "direct_glm_cost_xxx": matched[
                    "direct_glm_cost_xxx"
                ],
                "auto_savings_percent": matched[
                    "pooled_auto_savings_percent"
                ],
                "latency_reduction_percent": matched[
                    "pooled_latency_reduction_percent"
                ],
            },
            "same_auto_token_sensitivity": {
                "auto_actual_cost_xxx": routing[
                    "auto_actual_cost_xxx"
                ],
                "same_tokens_at_glm_rates_xxx": routing[
                    "same_tokens_at_glm_rates_xxx"
                ],
                "gross_backend_model_mix_savings_percent": routing[
                    "gross_backend_model_mix_savings_percent"
                ],
            },
            "auto_route_counts": {
                "models": body["auto_routes"]["models"],
                "decisions": body["auto_routes"]["decisions"],
                "phase_routes": body["auto_routes"]["phase_routes"],
            },
            "qualification": {
                "unit": "XXX is relative compute, not money.",
                "same_token": routing["qualification"],
            },
        }
        print(json.dumps(result, indent=2))
        return result


lab = WorkshopLab()
