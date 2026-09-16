"""Participant-facing helpers for the vLLM-SR agent workshop."""

from __future__ import annotations

import json
import os
from pathlib import Path
from pprint import pformat
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import requests
import yaml


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

        print("Starting the Router, Envoy, and Dashboard...")
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
        if not response.ok:
            raise RuntimeError(
                f"Routed request failed with HTTP {response.status_code}:\n"
                f"{response.text[:2000]}"
            )
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

    def routed_turn(
        self,
        history: list[dict[str, str]],
        prompt: str,
        max_tokens: int = 120,
    ) -> tuple[list[dict[str, str]], dict]:
        """Send one user turn while preserving the preceding conversation."""
        messages = [*history, {"role": "user", "content": prompt}]
        headers = {
            "content-type": "application/json",
            "x-vsr-debug": "true",
        }
        response = requests.post(
            f"{self.router_api.rstrip('/')}/v1/chat/completions",
            headers=headers,
            json={
                "model": self.virtual_model,
                "messages": messages,
                "max_tokens": max_tokens,
            },
            timeout=650,
        )
        if not response.ok:
            raise RuntimeError(
                f"Turn failed with HTTP {response.status_code}:\n"
                f"{response.text[:2000]}"
            )
        body = response.json()
        message = body.get("choices", [{}])[0].get("message", {})
        answer = message.get("content") or message.get("reasoning") or ""
        observed = {
            "prompt": prompt,
            "matched_complexity": response.headers.get(
                "x-vsr-matched-complexity"
            ),
            "decision": response.headers.get("x-vsr-selected-decision"),
            "selected_model": response.headers.get("x-vsr-selected-model"),
            "replay_id": response.headers.get("x-vsr-replay-id"),
            "answer": answer,
        }
        print(
            pformat(
                {
                    "prompt": observed["prompt"],
                    "matched_complexity": observed["matched_complexity"],
                    "decision": observed["decision"],
                    "selected_model": observed["selected_model"],
                    "replay_id": observed["replay_id"],
                }
            )
        )
        return [*messages, {"role": "assistant", "content": answer}], observed

    def compare_predictions(self, prompts: list[dict[str, str]]) -> list[dict]:
        """Route learner-authored prompts and compare predictions to evidence."""
        results = []
        for item in prompts:
            label = item["label"]
            prompt = item["prompt"]
            prediction = item["prediction"]
            print(f"\n{label}: {prompt}")
            print(f"Prediction: {prediction}")
            observed = self.routed_chat(prompt, max_tokens=80)
            results.append(
                {
                    **item,
                    "observed_complexity": observed.get("matched_complexity"),
                    "observed_decision": observed.get("decision"),
                    "observed_model": observed.get("selected_model"),
                    "replay_id": observed.get("replay_id"),
                }
            )
        return results

    def replay_signal_values(self, replay_id: str) -> dict[str, float]:
        """Fetch raw signal values for one request from Router Replay."""
        if not replay_id:
            raise ValueError("The response did not include x-vsr-replay-id.")
        paths = (
            f"{self.router_api.rstrip('/')}/v1/router_replay/{replay_id}",
            f"{self.management_api.rstrip('/')}/v1/router_replay/{replay_id}",
        )
        failures = []
        for url in paths:
            try:
                response = requests.get(url, timeout=15)
                if not response.ok:
                    failures.append(f"{url}: HTTP {response.status_code}")
                    continue
                body = response.json()
                record = body.get("data", body)
                values = record.get("signal_values", {})
                if values:
                    return values
                failures.append(f"{url}: response contained no signal_values")
            except (requests.RequestException, ValueError) as exc:
                failures.append(f"{url}: {exc}")
        raise RuntimeError(
            "Router Replay did not return signal values. Confirm the pinned "
            "workshop runtime exposes /v1/router_replay and that "
            "global.services.router_replay.enabled is true.\n"
            + "\n".join(failures)
        )

    def complexity_evidence(self, routed_result: dict) -> dict[str, float]:
        """Print the easy score, hard score, and margin for one request."""
        values = self.replay_signal_values(routed_result.get("replay_id"))
        prefix = "complexity:request_complexity:"
        evidence = {
            "hard_score": values.get(prefix + "text_hard_score"),
            "easy_score": values.get(prefix + "text_easy_score"),
            "margin": values.get(prefix + "text_margin"),
        }
        print(pformat(evidence))
        return evidence

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
        source = Path(__file__).resolve().parent / "agent-demo"
        if not source.is_dir():
            raise RuntimeError(
                f"The visible workshop exercise is missing: {source}"
            )
        shutil.copytree(source, target)

        print("Created a clean working copy for the Hermes exercise:")
        print(target)
        print("Run this setup cell again whenever you want to reset the project.")
        return target

    def boot_check(
        self,
        config_path: Path,
        timeout_seconds: int = 90,
        required: bool = True,
    ) -> bool:
        """Require the bundled Router binary to reach startup_complete."""
        development_router = Path("/opt/workshop-router/bin/router")
        router = (
            os.getenv("VLLM_SR_ROUTER_BIN")
            or shutil.which("router")
            or (str(development_router) if development_router.is_file() else None)
        )
        if not router:
            allow_skip = os.getenv("VLLM_SR_ALLOW_SKIP_BOOT_CHECK") == "1"
            if required and not allow_skip:
                raise RuntimeError(
                    "Router boot check is required, but no Router binary was "
                    "found. Bundle the pinned binary or explicitly set "
                    "VLLM_SR_ALLOW_SKIP_BOOT_CHECK=1 in a development-only "
                    "environment."
                )
            print("! ROUTER BOOT CHECK SKIPPED")
            print("  No Router binary is available in this environment.")
            print("  Do not publish a workshop image with this opt-out enabled.")
            return False

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            grpc_port = sock.getsockname()[1]
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            api_port = sock.getsockname()[1]

        services = config.setdefault("global", {}).setdefault("services", {})
        management = services.setdefault("management_api", {})
        management["bind_address"] = "127.0.0.1"
        management["port"] = api_port
        management["remote_exposure"] = False

        with tempfile.TemporaryDirectory(prefix="vllm-sr-boot-check-") as tmp:
            smoke_config = Path(tmp) / "config.yaml"
            smoke_config.write_text(
                yaml.safe_dump(config, sort_keys=False),
                encoding="utf-8",
            )
            process = subprocess.Popen(
                [
                    router,
                    f"-config={smoke_config}",
                    f"-port={grpc_port}",
                    "-enable-api=true",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={
                    **os.environ,
                    "LD_LIBRARY_PATH": ":".join(
                        part
                        for part in (
                            "/opt/workshop-router/lib",
                            os.getenv("LD_LIBRARY_PATH", ""),
                        )
                        if part
                    ),
                },
            )
            lines: list[str] = []
            deadline = time.monotonic() + timeout_seconds
            selector = selectors.DefaultSelector()
            assert process.stdout is not None
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    events = selector.select(timeout=0.25)
                    if not events:
                        continue
                    for key, _ in events:
                        line = key.fileobj.readline()
                        if not line:
                            continue
                        lines.append(line)
                        if "startup_complete" in line:
                            print(
                                f"✓ Router booted {config_path.name} "
                                f"with the bundled runtime"
                            )
                            return True
            finally:
                selector.close()
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

            tail = "".join(lines[-30:])
            raise RuntimeError(
                f"Router did not boot {config_path.name}.\n"
                f"Last Router output:\n{tail}"
            )

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

        stdout_path = exercise_dir / ".hermes-stdout.log"
        stderr_path = exercise_dir / ".hermes-stderr.log"

        print()
        print("Starting Hermes with one task:")
        print(task)
        print()
        print("Hermes is working. Its model and tool loop may take a few minutes.")
        print("Success means Hermes finishes the edit and the tests pass.")
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
                    print(
                        f"[{elapsed // 60:02d}:{elapsed % 60:02d}] "
                        "agent still working",
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

        return {
            "completed": True,
            "working_directory": str(exercise_dir),
            "final_response": stdout.strip(),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }


lab = WorkshopLab()
