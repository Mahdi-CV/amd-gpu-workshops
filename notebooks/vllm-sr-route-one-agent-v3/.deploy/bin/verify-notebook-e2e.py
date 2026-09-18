#!/usr/bin/env python3
"""Execute the complete workshop notebook against a running image.

This acceptance test mutates the active Router configuration during Stage 5
and the custom-route challenge. It always attempts to restore the baseline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time

import nbformat
from nbclient import NotebookClient
import requests
import yaml


if os.getenv("WORKSHOP_E2E_CONFIRM_MUTATION") != "1":
    raise SystemExit(
        "Set WORKSHOP_E2E_CONFIRM_MUTATION=1 to acknowledge temporary "
        "Router configuration changes."
    )

SOURCE_ROOT = Path(os.getenv("WORKSHOP_SOURCE_ROOT", "/workspace"))
notebook_override = os.getenv("WORKSHOP_NOTEBOOK")
if notebook_override:
    SOURCE_NOTEBOOK = Path(notebook_override)
else:
    SOURCE_NOTEBOOK = next(
        (
            candidate
            for candidate in (
                SOURCE_ROOT / "route-one-agent-across-two-models-v3.ipynb",
                SOURCE_ROOT / "route-one-agent-across-two-models.ipynb",
            )
            if candidate.is_file()
        ),
        SOURCE_ROOT / "route-one-agent-across-two-models-v3.ipynb",
    )


def tcp_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


service_host = os.getenv("VLLM_SR_SERVICE_HOST")
if not service_host:
    service_host = (
        "127.0.0.1"
        if tcp_ready("127.0.0.1", 8898) or tcp_ready("127.0.0.1", 8001)
        else "172.17.0.1"
    )

MANAGEMENT = os.getenv(
    "WORKSHOP_E2E_MANAGEMENT",
    os.getenv("ROUTER_MANAGEMENT_API", f"http://{service_host}:8080"),
)
ROUTER = os.getenv(
    "WORKSHOP_E2E_ROUTER",
    os.getenv("ROUTER_API", f"http://{service_host}:8898"),
)
EVIDENCE_DIR = Path(
    os.getenv("WORKSHOP_E2E_EVIDENCE_DIR", "/workspace/state/acceptance")
)


def current_config() -> tuple[dict, str]:
    response = requests.get(f"{MANAGEMENT}/api/v1/config", timeout=30)
    response.raise_for_status()
    etag = response.headers.get("ETag")
    if not etag:
        raise RuntimeError("Active config response did not include an ETag")
    return response.json(), etag


def mutate_config(method: str, document: dict) -> dict:
    _, etag = current_config()
    response = requests.request(
        method,
        f"{MANAGEMENT}/api/v1/config",
        headers={"If-Match": etag},
        json={"yaml": yaml.safe_dump(document, sort_keys=False)},
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(
            f"{method} config failed with HTTP {response.status_code}:\n"
            f"{response.text[:4000]}"
        )
    return response.json()


def wait_for_decision(name: str, present: bool = True) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        config, _ = current_config()
        decisions = {
            item.get("name")
            for item in config.get("routing", {}).get("decisions", [])
        }
        if (name in decisions) == present:
            return
        time.sleep(1)
    raise RuntimeError(
        f"Timed out waiting for active decision {name!r} present={present}"
    )


def wait_for_decision_set(expected: set[str]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        config, _ = current_config()
        actual = {
            item.get("name")
            for item in config.get("routing", {}).get("decisions", [])
            if item.get("name")
        }
        if actual == expected:
            return
        time.sleep(1)
    raise RuntimeError(
        "Timed out waiting for baseline decisions to be restored: "
        f"expected={sorted(expected)}"
    )


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise RuntimeError(f"Expected notebook text not found: {old}")
    return source.replace(old, new, 1)


def assert_no_error(cell, index: int) -> None:
    for output in cell.get("outputs", []):
        if output.get("output_type") == "error":
            raise RuntimeError(
                f"Cell {index} failed: {output.get('ename')}: "
                f"{output.get('evalue')}"
            )


def output_text(cell) -> str:
    parts: list[str] = []
    for output in cell.get("outputs", []):
        if output.get("output_type") == "stream":
            value = output.get("text", "")
            parts.append("".join(value) if isinstance(value, list) else value)
        elif output.get("output_type") in {"execute_result", "display_data"}:
            value = output.get("data", {}).get("text/plain", "")
            parts.append("".join(value) if isinstance(value, list) else value)
    return "\n".join(parts)


def prepare_workspace() -> tuple[Path, Path]:
    required = (
        SOURCE_NOTEBOOK,
        SOURCE_ROOT / "workshop_lab.py",
        SOURCE_ROOT / "agent-demo",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing workshop assets: {missing}")

    root = Path(tempfile.mkdtemp(prefix="vllm-sr-workshop-e2e-"))
    shutil.copy2(SOURCE_NOTEBOOK, root / SOURCE_NOTEBOOK.name)
    shutil.copy2(SOURCE_ROOT / "workshop_lab.py", root / "workshop_lab.py")
    shutil.copytree(SOURCE_ROOT / "agent-demo", root / "agent-demo")
    return root, root / SOURCE_NOTEBOOK.name


def main() -> None:
    root, notebook_path = prepare_workspace()
    os.environ["VLLM_SR_WORKSHOP_DIR"] = str(root / "generated-config")
    os.environ.pop("VLLM_SR_BIN", None)

    notebook = nbformat.read(notebook_path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=900,
        kernel_name="python3",
        allow_errors=False,
        resources={"metadata": {"path": str(root)}},
    )

    baseline: dict | None = None
    baseline_decisions: set[str] | None = None
    stage5_activated = False
    challenge_activated = False

    try:
        with client.setup_kernel():
            for index, cell in enumerate(notebook.cells):
                if cell.cell_type != "code":
                    continue

                source = cell.source
                if "routing_experiment = [" in source:
                    source = source.replace(
                        '"prompt": "YOUR ROUTINE PROMPT HERE"',
                        '"prompt": "Rewrite this sentence clearly: retries can run a job twice."',
                    )
                    source = source.replace(
                        '"prompt": "YOUR HARD PROMPT HERE"',
                        (
                            '"prompt": "Diagnose cascading failures in a distributed '
                            'queue, compare multiple remediation strategies and their '
                            'tradeoffs, and justify a safe rollout plan."'
                        ),
                    )
                    source = source.replace(
                        '"prompt": "YOUR AMBIGUOUS PROMPT HERE"',
                        (
                            '"prompt": "A Python API became slower after deployment. '
                            'Suggest what I should check first."'
                        ),
                    )
                    cell.source = source

                if "MY_KEYWORDS = [\"CUSTOMIZE-ME\"]" in source:
                    source = source.replace(
                        'MY_KEYWORDS = ["CUSTOMIZE-ME"]',
                        'MY_KEYWORDS = ["CONFIDENTIAL"]',
                    )
                    source = source.replace(
                        '"positive": "REPLACE WITH A PROMPT THAT SHOULD MATCH"',
                        (
                            '"positive": "CONFIDENTIAL: summarize this internal '
                            'deployment note."'
                        ),
                    )
                    source = source.replace(
                        '"negative": "REPLACE WITH A PROMPT THAT SHOULD NOT MATCH"',
                        '"negative": "Define idempotency in one sentence."',
                    )
                    source = source.replace(
                        '"collision": "REPLACE WITH A PROMPT THAT MATCHES TWO ROUTES"',
                        (
                            '"collision": "CONFIDENTIAL: compare multiple rollout '
                            'strategies and justify the safest plan."'
                        ),
                    )
                    cell.source = source

                client.execute_cell(cell, index)
                assert_no_error(cell, index)
                print(f"PASS cell {index}")

                if "services = lab.start_platform()" in cell.source:
                    baseline, _ = current_config()
                    baseline_decisions = {
                        item.get("name")
                        for item in baseline.get("routing", {}).get(
                            "decisions", []
                        )
                        if item.get("name")
                    }
                    print("PASS baseline Router configuration captured")

                if "incident_signal = {" in cell.source:
                    stage5_path = root / "generated-config/05-incident-policy.yaml"
                    stage5_import_path = (
                        root / "generated-config/05-incident-routing.yaml"
                    )
                    stage5 = yaml.safe_load(stage5_path.read_text())
                    stage5_import = yaml.safe_load(stage5_import_path.read_text())
                    if set(stage5_import) != {"routing"}:
                        raise RuntimeError(
                            "Stage 5 Dashboard import must contain only routing"
                        )
                    if stage5_import["routing"] != stage5["routing"]:
                        raise RuntimeError(
                            "Stage 5 Dashboard routing does not match full policy"
                        )
                    mutate_config("PATCH", {"routing": stage5["routing"]})
                    wait_for_decision("incident-fast-lane")
                    stage5_activated = True
                    print("PASS Stage 5 activated")

                if "MY_KEYWORDS = [\"CONFIDENTIAL\"]" in cell.source:
                    challenge_path = root / "generated-config/06-my-policy.yaml"
                    challenge = yaml.safe_load(challenge_path.read_text())
                    mutate_config("PATCH", {"routing": challenge["routing"]})
                    wait_for_decision("my-route")
                    challenge_activated = True
                    cell.source = replace_once(
                        cell.source,
                        "POLICY_IS_PUBLISHED = False",
                        "POLICY_IS_PUBLISHED = True",
                    )
                    client.execute_cell(cell, index)
                    assert_no_error(cell, index)
                    print("PASS challenge activated and verified")

        hermes_cell = next(
            cell
            for cell in notebook.cells
            if "agent_run = lab.run_agent" in cell.source
        )
        if "3 passed" not in output_text(hermes_cell):
            raise RuntimeError("Hermes cell did not report 3 passed")

        route_cell = next(
            cell for cell in notebook.cells if "turn_results = []" in cell.source
        )
        route_output = output_text(route_cell)
        for expected in (
            "'selected_model': 'routine-model'",
            "'selected_model': 'reasoning-model'",
            "'replay_id':",
        ):
            if expected not in route_output:
                raise RuntimeError(f"Route cell missing {expected}")

        collision_cell = next(
            cell
            for cell in notebook.cells
            if "COLLISION_PROMPT = (" in cell.source
        )
        if "Collision resolved by priority" not in output_text(collision_cell):
            raise RuntimeError("Collision verification did not pass")

        if not stage5_activated or not challenge_activated:
            raise RuntimeError("Not every activation phase executed")

        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EVIDENCE_DIR / "route-one-agent-e2e.executed.ipynb"
        nbformat.write(notebook, output_path)
        print(f"PASS executed notebook saved to {output_path}")
    finally:
        if baseline is not None:
            mutate_config("PUT", baseline)
            if baseline_decisions is not None:
                wait_for_decision_set(baseline_decisions)
            response = requests.get(f"{ROUTER}/v1/models", timeout=30)
            response.raise_for_status()
            print("PASS original Router configuration restored")


if __name__ == "__main__":
    main()
