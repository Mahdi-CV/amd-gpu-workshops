"""Small participant-facing helpers for the vLLM-SR agent workshop.

The workshop image owns environment discovery and process wiring. Notebook
cells call this module so learners can focus on routing behavior.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from pprint import pformat
import shutil
import socket
import subprocess
import sys
import time

import requests


def _tcp_ready(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _service_host() -> str:
    configured = os.getenv("VLLM_SR_SERVICE_HOST")
    if configured:
        return configured
    if _tcp_ready("127.0.0.1", 8898) or _tcp_ready("127.0.0.1", 8899):
        return "127.0.0.1"
    if _tcp_ready("172.17.0.1", 8898):
        return "172.17.0.1"
    return "127.0.0.1"


def _router_port(host: str) -> int:
    configured = os.getenv("VLLM_SR_ROUTER_PORT")
    if configured:
        return int(configured)
    return 8898 if _tcp_ready(host, 8898) else 8899


class WorkshopLab:
    def __init__(self) -> None:
        host = _service_host()
        router_port = _router_port(host)

        self.service_host = host
        self.router_api = os.getenv(
            "ROUTER_API", f"http://{host}:{router_port}"
        )
        self.management_api = os.getenv(
            "ROUTER_MANAGEMENT_API", f"http://{host}:8080"
        )
        self.dashboard_url = os.getenv("DASHBOARD_URL", f"http://{host}:8700")
        self.dashboard_browser_url = os.getenv(
            "DASHBOARD_BROWSER_URL", "http://localhost:8700"
        )
        self.routine_endpoint = os.getenv(
            "ROUTINE_ENDPOINT", f"http://{host}:8002"
        )
        self.reasoning_endpoint = os.getenv(
            "REASONING_ENDPOINT", f"http://{host}:8001"
        )
        self.routine_provider_model = os.getenv(
            "ROUTINE_PROVIDER_MODEL", "gemma-4-12b"
        )
        self.reasoning_provider_model = os.getenv(
            "REASONING_PROVIDER_MODEL", "qwen3.8-27b"
        )
        self.virtual_model = "vllm-sr/auto"

        default_workspace = Path("/tmp/route-one-agent-workshop")
        self.workspace = Path(
            os.getenv("VLLM_SR_WORKSHOP_DIR", str(default_workspace))
        )
        self.workspace.mkdir(parents=True, exist_ok=True)

        bundled_cli = Path(__file__).resolve().parent / "vllm-sr-current"
        self.vllm_sr_bin = (
            os.getenv("VLLM_SR_BIN")
            or shutil.which("vllm-sr")
            or (str(bundled_cli) if bundled_cli.exists() else None)
        )

    def welcome(self) -> None:
        print("Route One Agent Across Two Models")
        print("One agent. One endpoint. Two model paths.")
        print()
        print("We will experience routing first, then rebuild how it works.")

    @staticmethod
    def _probe(url: str, timeout: float = 2.0) -> tuple[bool, str]:
        try:
            response = requests.get(url, timeout=timeout)
            return response.ok, f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def status(self) -> dict[str, bool]:
        services = {
            "routine model": f"{self.routine_endpoint}/v1/models",
            "reasoning model": f"{self.reasoning_endpoint}/v1/models",
            "semantic router": f"{self.router_api}/v1/models",
            "router management": f"{self.management_api}/health",
            "dashboard": self.dashboard_url,
        }
        result: dict[str, bool] = {}
        for name, url in services.items():
            ready, detail = self._probe(url)
            result[name] = ready
            marker = "✓" if ready else "○"
            state = "ready" if ready else "not running"
            print(f"{marker} {name:18} {state:12} {detail}")
        print()
        print(
            "Hermes:",
            "ready" if shutil.which("hermes") else "not installed in this image yet",
        )
        return result

    def start_platform(self) -> dict[str, bool]:
        router_ready = self._probe(f"{self.router_api}/v1/models")[0]
        dashboard_ready = self._probe(self.dashboard_url)[0]
        if router_ready and dashboard_ready:
            print("The routing platform is already running.")
            return self.status()

        script = Path(
            os.getenv(
                "VLLM_SR_START_PLATFORM_SCRIPT",
                "/opt/workshop/bin/start-platform.sh",
            )
        )
        if not script.is_file():
            print("The routing platform is not ready.")
            print(f"The workshop image must provide: {script}")
            return self.status()

        print("Starting Router, Envoy, Dashboard, and Insights support...")
        result = subprocess.run(
            [str(script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode:
            raise RuntimeError(
                f"Platform setup failed with status {result.returncode}"
            )

        services = self.status()
        if not services["semantic router"] or not services["dashboard"]:
            raise RuntimeError(
                "Platform setup returned successfully, but required services "
                "are not ready."
            )
        return services

    def browser_links(self) -> None:
        try:
            from IPython.display import HTML, display

            display(
                HTML(
                    f"""
                    <div style="display:flex;gap:12px;margin:8px 0 16px">
                      <a href="{self.dashboard_browser_url}" target="_blank"
                         style="padding:8px 14px;border:1px solid #888;border-radius:6px">
                        Open vLLM-SR Dashboard
                      </a>
                    </div>
                    """
                )
            )
        except ImportError:
            print("Dashboard:", self.dashboard_browser_url)

    @staticmethod
    def _models(endpoint: str) -> list[str]:
        response = requests.get(f"{endpoint.rstrip('/')}/v1/models", timeout=15)
        response.raise_for_status()
        return [item["id"] for item in response.json().get("data", [])]

    def show_models(self) -> dict[str, list[str]]:
        discovered: dict[str, list[str]] = {}
        for lane, endpoint in (
            ("routine", self.routine_endpoint),
            ("reasoning", self.reasoning_endpoint),
            ("routed", self.router_api),
        ):
            ready, detail = self._probe(f"{endpoint}/v1/models")
            if ready:
                discovered[lane] = self._models(endpoint)
                print(f"{lane:10} {discovered[lane]}")
            else:
                discovered[lane] = []
                print(f"{lane:10} unavailable ({detail})")
        return discovered

    @staticmethod
    def _chat(
        endpoint: str,
        model: str,
        prompt: str,
        max_tokens: int,
        debug: bool = False,
    ) -> dict:
        headers = {"content-type": "application/json"}
        if debug:
            headers["x-vsr-debug"] = "true"
        started = time.perf_counter()
        response = requests.post(
            f"{endpoint.rstrip('/')}/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=650,
        )
        elapsed = time.perf_counter() - started
        response.raise_for_status()
        body = response.json()
        return {
            "requested_model": model,
            "response_model": body.get("model"),
            "decision": response.headers.get("x-vsr-selected-decision"),
            "selected_model": response.headers.get("x-vsr-selected-model"),
            "algorithm": response.headers.get("x-vsr-selected-algorithm"),
            "matched_complexity": response.headers.get(
                "x-vsr-matched-complexity"
            ),
            "replay_id": response.headers.get("x-vsr-replay-id"),
            "latency_seconds": round(elapsed, 3),
            "answer": body.get("choices", [{}])[0]
            .get("message", {})
            .get("content"),
        }

    def direct_model_check(self, lane: str) -> dict:
        if lane == "routine":
            endpoint = self.routine_endpoint
            model = self.routine_provider_model
            prompt = "Reply with exactly: routine model ready"
        elif lane == "reasoning":
            endpoint = self.reasoning_endpoint
            model = self.reasoning_provider_model
            prompt = "Reply with exactly: reasoning model ready"
        else:
            raise ValueError("lane must be 'routine' or 'reasoning'")
        result = self._chat(endpoint, model, prompt, max_tokens=32)
        print(pformat(result))
        return result

    def routed_chat(self, prompt: str, max_tokens: int = 300) -> dict:
        result = self._chat(
            self.router_api,
            self.virtual_model,
            prompt,
            max_tokens=max_tokens,
            debug=True,
        )
        print(pformat(result))
        return result

    def agent_command(self, task: str) -> str:
        command = f'hermes -z {json.dumps(task)} --yolo'
        print(command)
        if not shutil.which("hermes"):
            print()
            print("Hermes is not installed in this development image yet.")
            print("The production workshop image must preinstall and configure it.")
        return command

    def prepare_agent_demo(self) -> Path:
        target = self.workspace / "agent-demo-working"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)

        files = {
            "README.md": """# Pricing report demo

This deliberately small project calculates item totals and renders a text
report. The implementation contains duplicated discount logic for the agent to
identify and refactor.

Run:

```bash
python -m pytest -q
```
""",
            "pricing.py": """def customer_total(subtotal: float, premium: bool) -> float:
    discount = 0.10 if premium else 0.0
    return round(subtotal * (1 - discount), 2)


def invoice_total(subtotal: float, premium: bool) -> float:
    discount = 0.10 if premium else 0.0
    return round(subtotal * (1 - discount), 2)
""",
            "reporting.py": """from pricing import customer_total, invoice_total


def render_report(subtotal: float, premium: bool) -> str:
    customer = customer_total(subtotal, premium)
    invoice = invoice_total(subtotal, premium)
    return f"customer={customer:.2f}\\ninvoice={invoice:.2f}\\n"
""",
            "test_pricing.py": """from pricing import customer_total, invoice_total
from reporting import render_report


def test_regular_customer_totals() -> None:
    assert customer_total(100, False) == 100
    assert invoice_total(100, False) == 100


def test_premium_customer_totals() -> None:
    assert customer_total(100, True) == 90
    assert invoice_total(100, True) == 90


def test_report() -> None:
    assert render_report(100, True) == "customer=90.00\\ninvoice=90.00\\n"
""",
        }
        for relative_path, content in files.items():
            (target / relative_path).write_text(content, encoding="utf-8")

        print("Created a disposable exercise copy:")
        print(target)
        print()
        print("The helper can recreate this clean fixture whenever needed.")
        return target

    @staticmethod
    def _request_count(endpoint: str) -> int | None:
        try:
            response = requests.get(f"{endpoint.rstrip('/')}/metrics", timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            return None

        total = 0.0
        found = False
        for line in response.text.splitlines():
            if not line.startswith("vllm:request_success_total{"):
                continue
            if 'finished_reason="error"' in line or 'finished_reason="abort"' in line:
                continue
            try:
                total += float(line.rsplit(" ", 1)[1])
                found = True
            except (IndexError, ValueError):
                continue
        return int(total) if found else None

    def route_counts(self, *, show: bool = True) -> dict[str, int | None]:
        counts = {
            "routine-model": self._request_count(self.routine_endpoint),
            "reasoning-model": self._request_count(self.reasoning_endpoint),
        }
        if show:
            for model, count in counts.items():
                print(f"{model:16} {count if count is not None else 'unavailable'}")
        return counts

    def run_agent(self, task: str, exercise_dir: Path) -> dict:
        hermes = shutil.which("hermes")
        if not hermes:
            print("Hermes is not installed in this development image yet.")
            print("The production workshop image must preinstall and configure it.")
            return {
                "completed": False,
                "skipped": True,
                "reason": "hermes is unavailable",
            }

        try:
            configured_model = subprocess.run(
                [hermes, "config", "get", "model.default"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            configured_base_url = subprocess.run(
                [hermes, "config", "get", "model.base_url"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Hermes configuration check failed: {exc}")
            return {
                "completed": False,
                "skipped": True,
                "reason": "hermes configuration is unavailable",
            }

        if (
            configured_model.returncode
            or configured_base_url.returncode
            or configured_model.stdout.strip() != self.virtual_model
            or not configured_base_url.stdout.strip()
        ):
            print("Hermes is installed but is not configured for this workshop.")
            print("Expected model:", self.virtual_model)
            print("Run the workshop image's Hermes configuration step first.")
            return {
                "completed": False,
                "skipped": True,
                "reason": "hermes is not configured for vllm-sr",
            }

        before = self.route_counts()
        stdout_path = exercise_dir / ".hermes-stdout.log"
        stderr_path = exercise_dir / ".hermes-stderr.log"

        print()
        print("Starting Hermes with one task:")
        print(task)
        print()
        print("Hermes is working. This normally takes a few minutes.")
        print("The counters below update while its internal model/tool loop runs.")
        print(flush=True)

        started = time.monotonic()
        with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_file:
            process = subprocess.Popen(
                [hermes, "-z", task, "--yolo"],
                cwd=exercise_dir,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )
            try:
                while process.poll() is None:
                    elapsed = int(time.monotonic() - started)
                    current = self.route_counts(show=False)
                    deltas = {
                        model: (
                            current[model] - before[model]
                            if before[model] is not None
                            and current[model] is not None
                            else None
                        )
                        for model in before
                    }
                    routine_delta = deltas["routine-model"]
                    reasoning_delta = deltas["reasoning-model"]
                    print(
                        f"[{elapsed // 60:02d}:{elapsed % 60:02d}] "
                        f"agent still working | "
                        f"routine +{routine_delta if routine_delta is not None else '?'} | "
                        f"reasoning +{reasoning_delta if reasoning_delta is not None else '?'}",
                        flush=True,
                    )
                    if elapsed >= 900:
                        process.terminate()
                        raise TimeoutError("Hermes exceeded the 15-minute workshop timeout.")
                    time.sleep(10)
            except KeyboardInterrupt:
                process.terminate()
                process.wait(timeout=10)
                raise

        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
        if stdout:
            print()
            print("Hermes final response:")
            print(stdout)
        if stderr:
            print()
            print("Hermes diagnostic output:")
            print(stderr)
        if process.returncode:
            raise RuntimeError(f"Hermes exited with status {process.returncode}")

        print("Verifying the modified exercise:")
        tests = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=exercise_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(tests.stdout)
        if tests.stderr:
            print(tests.stderr)
        if tests.returncode:
            raise RuntimeError("The exercise tests failed after the Hermes run.")

        after = self.route_counts()
        delta = {
            model: (
                after[model] - before[model]
                if before[model] is not None and after[model] is not None
                else None
            )
            for model in before
        }
        print()
        print("Requests added during the agent task:")
        for model, count in delta.items():
            print(f"{model:16} {count if count is not None else 'unavailable'}")

        return {
            "completed": True,
            "working_directory": str(exercise_dir),
            "before": before,
            "after": after,
            "delta": delta,
            "final_response": stdout.strip(),
        }

    def incident_challenge_template(self) -> dict:
        return {
            "requirement": "",
            "signal": "",
            "decision": "",
            "priority": None,
            "model": "",
            "positive_test": "",
            "negative_test": "",
            "collision_test": "",
            "observed_result": "",
            "explanation": "",
        }


lab = WorkshopLab()
