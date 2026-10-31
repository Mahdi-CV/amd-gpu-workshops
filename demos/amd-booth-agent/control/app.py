"""Unified AMD booth UI, OpenClaw runner, and vLLM-SR telemetry proxy."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_ROOT = Path(os.getenv("BOOTH_APP_ROOT", "/opt/booth"))
DATA_DIR = Path(os.getenv("BOOTH_DATA_DIR", "/data"))
RUNS_DIR = Path(os.getenv("BOOTH_RUNS_DIR", DATA_DIR / "runs"))
STATE_DIR = Path(os.getenv("OPENCLAW_STATE_DIR", DATA_DIR / "openclaw"))
ROUTER_BASE_URL = os.getenv("ROUTER_BASE_URL", "http://router:8899/v1").rstrip("/")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "vllm-sr/auto")
PUBLIC_ORIGIN = os.getenv("BOOTH_PUBLIC_ORIGIN", "")
MAX_PROMPT_CHARS = 4000
MAX_RUN_SECONDS = 900

MODEL_INFO = {
    "qwen/qwen3.8-27b": {
        "label": "Qwen3.8-27B",
        "location": "Local · AMD MI300X",
        "tier": "local",
        "color": "#00c2de",
        "input_rate": 0.0,
        "cached_rate": 0.0,
        "output_rate": 0.0,
    },
    "zai/glm-5.3-flash": {
        "label": "GLM-5.3-Flash",
        "location": "Fireworks · Serverless",
        "tier": "cloud",
        "color": "#ed1c24",
        "input_rate": 0.15,
        "cached_rate": 0.03,
        "output_rate": 0.50,
    },
    "moonshot/kimi-k3": {
        "label": "Kimi K3",
        "location": "Fireworks · Premium",
        "tier": "premium",
        "color": "#f4bd43",
        "input_rate": 3.00,
        "cached_rate": 0.30,
        "output_rate": 15.00,
    },
}

SUGGESTED_TASKS = [
    {
        "id": "amd-microsite",
        "icon": "◈",
        "title": "Build an AMD accelerator microsite",
        "subtitle": "Research + code + review",
        "prompt": (
            "Research current public AMD Instinct MI300X and MI325X specifications "
            "from primary sources. Then build a polished self-contained HTML "
            "comparison microsite with citations in the shared run directory. "
            "Use the researcher, builder, and reviewer agents."
        ),
        "tags": ["browser", "subagents", "artifact"],
    },
    {
        "id": "debug-benchmark",
        "icon": "⌁",
        "title": "Debug a broken benchmark",
        "subtitle": "Code + tests + verification",
        "prompt": (
            "Inspect the prepared broken Python benchmark in the shared run "
            "directory, reproduce its failures, make the smallest source-only "
            "fix, run the complete tests, and have the reviewer verify it."
        ),
        "tags": ["code", "tools", "reviewer"],
    },
    {
        "id": "routing-visual",
        "icon": "⟲",
        "title": "Create a semantic-routing visual",
        "subtitle": "Research + SVG/HTML",
        "prompt": (
            "Create a dark, booth-ready interactive HTML/SVG visual explaining "
            "how one OpenClaw endpoint routes fast work to local Qwen, agentic "
            "work to GLM-5.3-Flash, and frontier work to Kimi K3. Include a short "
            "plain-language explanation and verify the artifact opens."
        ),
        "tags": ["visual", "code", "artifact"],
    },
    {
        "id": "web-brief",
        "icon": "◎",
        "title": "Live AMD AI news brief",
        "subtitle": "Browse + cite + summarize",
        "prompt": (
            "Find three recent AMD AI or ROCm announcements from primary sources, "
            "verify their dates, and create a concise cited booth briefing with "
            "a small HTML timeline in the shared run directory."
        ),
        "tags": ["browser", "facts", "citations"],
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Any, limit: int = 180) -> str:
    if isinstance(value, str):
        text = " ".join(value.split())
    elif value is None:
        text = ""
    else:
        text = " ".join(json.dumps(value, ensure_ascii=False).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def latest_prompt(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") in {"user", "tool"}:
            return compact_text(message.get("content"), 220)
    return ""


def parse_effort(headers: dict[str, str]) -> str:
    projections = headers.get("x-vsr-matched-projections", "")
    for item in projections.split(","):
        item = item.strip()
        if item.startswith("effort_"):
            return item.removeprefix("effort_")
    return headers.get("x-vsr-selected-reasoning", "unknown")


def usage_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "cached_tokens": int(prompt_details.get("cached_tokens") or 0),
        "reasoning_tokens": int(
            completion_details.get("reasoning_tokens")
            or usage.get("reasoning_tokens")
            or 0
        ),
    }


def parse_upstream_response(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "text/event-stream" not in content_type:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    result: dict[str, Any] = {"choices": [], "usage": {}}
    tool_calls: dict[int, dict[str, Any]] = {}
    finish_reason = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        value = line[5:].strip()
        if not value or value == "[DONE]":
            continue
        try:
            chunk = json.loads(value)
        except json.JSONDecodeError:
            continue
        if chunk.get("model"):
            result["model"] = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            result["usage"] = chunk["usage"]
        choices = chunk.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]
        delta = choice.get("delta") or {}
        for call in delta.get("tool_calls") or []:
            index = int(call.get("index") or 0)
            target = tool_calls.setdefault(
                index,
                {
                    "id": call.get("id"),
                    "type": call.get("type") or "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if call.get("id"):
                target["id"] = call["id"]
            function = call.get("function") or {}
            target["function"]["name"] += function.get("name") or ""
            target["function"]["arguments"] += function.get("arguments") or ""
    if finish_reason:
        result["choices"] = [
            {
                "finish_reason": finish_reason,
                "message": {"tool_calls": list(tool_calls.values())},
            }
        ]
    return result


def cost_for_model(model: str, usage: dict[str, int]) -> float:
    rate = MODEL_INFO.get(model)
    if not rate:
        return 0.0
    cached = min(usage["cached_tokens"], usage["prompt_tokens"])
    uncached = max(0, usage["prompt_tokens"] - cached)
    return (
        uncached * rate["input_rate"]
        + cached * rate["cached_rate"]
        + usage["completion_tokens"] * rate["output_rate"]
    ) / 1_000_000


def counterfactual_cost(model: str, usage: dict[str, int]) -> float:
    return cost_for_model(model, usage)


@dataclass
class RunRecord:
    id: str
    task: str
    title: str
    run_dir: Path
    created_at: str = field(default_factory=utc_now)
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    process: asyncio.subprocess.Process | None = None
    result: str = ""
    error: str = ""
    actual_cost: float = 0.0
    all_kimi_cost: float = 0.0
    all_glm_cost: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    model_counts: dict[str, int] = field(default_factory=dict)

    async def emit(self, event_type: str, **data: Any) -> None:
        event = {
            "seq": len(self.events) + 1,
            "timestamp": utc_now(),
            "type": event_type,
            **data,
        }
        async with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def metrics(self) -> dict[str, Any]:
        kimi_savings = (
            (1 - self.actual_cost / self.all_kimi_cost) * 100
            if self.all_kimi_cost
            else 0.0
        )
        glm_savings = (
            (1 - self.actual_cost / self.all_glm_cost) * 100
            if self.all_glm_cost
            else 0.0
        )
        return {
            "calls": sum(self.model_counts.values()),
            "model_counts": self.model_counts,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "actual_cost": round(self.actual_cost, 6),
            "all_kimi_cost": round(self.all_kimi_cost, 6),
            "all_glm_cost": round(self.all_glm_cost, 6),
            "savings_vs_kimi_percent": round(kimi_savings, 1),
            "savings_vs_glm_percent": round(glm_savings, 1),
        }


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, RunRecord] = {}
        self.active_id: str | None = None
        self.lock = asyncio.Lock()

    def active(self) -> RunRecord | None:
        if not self.active_id:
            return None
        run = self.runs.get(self.active_id)
        if not run or run.status not in {"queued", "running"}:
            return None
        return run


manager = RunManager()
app = FastAPI(title="AMD OpenClaw Booth")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")


class RunRequest(BaseModel):
    task: str = Field(min_length=2, max_length=MAX_PROMPT_CHARS)
    title: str = Field(default="Custom booth task", max_length=100)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "active_run": manager.active_id}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(APP_ROOT / "static/index.html")


@app.get("/api/config")
async def config() -> dict[str, Any]:
    return {
        "suggested_tasks": SUGGESTED_TASKS,
        "models": MODEL_INFO,
        "public_origin": PUBLIC_ORIGIN,
        "limits": {
            "max_prompt_chars": MAX_PROMPT_CHARS,
            "max_run_seconds": MAX_RUN_SECONDS,
            "one_active_run": True,
        },
    }


@app.get("/api/system")
async def system_status() -> dict[str, Any]:
    status: dict[str, Any] = {"router": "unknown", "models": []}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{ROUTER_BASE_URL}/models")
            response.raise_for_status()
            status["router"] = "ready"
            status["models"] = [
                row.get("id") for row in (response.json().get("data") or [])
            ]
    except Exception as exc:  # pragma: no cover - runtime diagnostic
        status["router"] = "unavailable"
        status["error"] = compact_text(str(exc))
    return status


@app.post("/api/runs")
async def create_run(request: RunRequest) -> dict[str, Any]:
    async with manager.lock:
        if manager.active():
            raise HTTPException(
                status_code=409,
                detail="A booth task is already running.",
            )
        run_id = uuid.uuid4().hex[:12]
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        fixture = APP_ROOT / "fixtures" / "broken-benchmark"
        if fixture.is_dir():
            shutil.copytree(fixture, run_dir / "benchmark-demo")
        run = RunRecord(
            id=run_id,
            task=request.task.strip(),
            title=request.title.strip() or "Custom booth task",
            run_dir=run_dir,
        )
        manager.runs[run_id] = run
        manager.active_id = run_id
        asyncio.create_task(execute_run(run))
    return {"id": run_id, "status": run.status}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = manager.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return serialize_run(run)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    run = manager.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    async def stream() -> AsyncIterator[bytes]:
        index = 0
        while True:
            while index < len(run.events):
                event = run.events[index]
                index += 1
                yield (
                    "data: "
                    + json.dumps(event, ensure_ascii=False)
                    + "\n\n"
                ).encode()
            if run.status in {"completed", "failed", "cancelled"}:
                break
            try:
                async with run.condition:
                    await asyncio.wait_for(run.condition.wait(), timeout=15)
            except TimeoutError:
                yield b": keepalive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    run = manager.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.process and run.process.returncode is None:
        run.process.terminate()
    run.status = "cancelled"
    await run.emit("run.cancelled", message="Task cancelled.")
    return serialize_run(run)


@app.get("/artifacts/{run_id}/{artifact_path:path}")
async def artifact(run_id: str, artifact_path: str) -> FileResponse:
    run = manager.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    root = run.run_dir.resolve()
    target = (root / artifact_path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    media_type = mimetypes.guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)


def serialize_run(run: RunRecord) -> dict[str, Any]:
    return {
        "id": run.id,
        "task": run.task,
        "title": run.title,
        "status": run.status,
        "created_at": run.created_at,
        "result": run.result,
        "error": run.error,
        "metrics": run.metrics(),
        "artifacts": list_artifacts(run),
    }


def list_artifacts(run: RunRecord) -> list[dict[str, Any]]:
    artifacts = []
    if not run.run_dir.is_dir():
        return artifacts
    for path in sorted(run.run_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        relative = path.relative_to(run.run_dir).as_posix()
        artifacts.append(
            {
                "name": path.name,
                "path": relative,
                "url": f"/artifacts/{run.id}/{relative}",
                "size": path.stat().st_size,
            }
        )
    return artifacts[:50]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def assistant_text(body: dict[str, Any]) -> str:
    result = body.get("result")
    if isinstance(result, dict):
        visible = result.get("finalAssistantVisibleText")
        if isinstance(visible, str) and visible.strip():
            return visible.strip()
        payloads = result.get("payloads") or []
    else:
        payloads = body.get("payloads") or []
    texts = [
        str(item.get("text") or "").strip()
        for item in payloads
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    return "\n\n".join(texts)


async def execute_run(run: RunRecord) -> None:
    run.status = "running"
    await run.emit(
        "run.started",
        run_id=run.id,
        title=run.title,
        task=run.task,
        run_dir=str(run.run_dir),
    )
    prompt = (
        f"This is AMD booth run {run.id}. The shared run directory is "
        f"{run.run_dir}. Use it for every artifact and tell subagents the "
        f"same absolute path.\n\nVisitor task:\n{run.task}\n\n"
        "Use the researcher, builder, and reviewer agents when helpful. "
        "Return a concise verified result suitable for a live booth demo."
    )
    env = {
        **os.environ,
        "OPENCLAW_STATE_DIR": str(STATE_DIR),
        "HOME": os.getenv("HOME", "/home/booth"),
    }
    command = [
        "openclaw",
        "agent",
        "--agent",
        "main",
        "--session-key",
        f"agent:main:booth-{run.id}",
        "--message",
        prompt,
        "--json",
        "--timeout",
        str(MAX_RUN_SECONDS),
    ]
    try:
        run.process = await asyncio.create_subprocess_exec(
            *command,
            cwd=run.run_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            run.process.communicate(),
            timeout=MAX_RUN_SECONDS + 30,
        )
        if run.process.returncode:
            raise RuntimeError(
                compact_text(stderr.decode(errors="replace"), 2000)
                or f"OpenClaw exited {run.process.returncode}"
            )
        body = extract_json(stdout.decode(errors="replace"))
        run.result = assistant_text(body) or compact_text(
            stdout.decode(errors="replace"),
            4000,
        )
        run.status = "completed"
        await run.emit(
            "run.completed",
            result=run.result,
            artifacts=list_artifacts(run),
            metrics=run.metrics(),
        )
    except asyncio.CancelledError:
        run.status = "cancelled"
        await run.emit("run.cancelled", message="Task cancelled.")
        raise
    except Exception as exc:
        run.status = "failed"
        run.error = compact_text(str(exc), 2000)
        await run.emit("run.failed", error=run.error, metrics=run.metrics())
    finally:
        if manager.active_id == run.id:
            manager.active_id = None


EXCLUDED_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@app.api_route(
    "/proxy/{agent}/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(agent: str, path: str, request: Request) -> Response:
    raw = await request.body()
    request_body: dict[str, Any] = {}
    if raw:
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                request_body = value
        except json.JSONDecodeError:
            pass

    run = manager.active()
    call_id = uuid.uuid4().hex[:10]
    started = time.perf_counter()
    if run:
        await run.emit(
            "llm.request",
            call_id=call_id,
            agent=agent,
            prompt=latest_prompt(request_body.get("messages")),
            tool_count=len(request_body.get("tools") or []),
        )

    upstream_url = f"{ROUTER_BASE_URL}/{path}"
    headers = {
        "Authorization": "Bearer booth-local",
        "Content-Type": request.headers.get(
            "content-type",
            "application/json",
        ),
        "Accept": request.headers.get("accept", "application/json"),
        "User-Agent": "amd-openclaw-booth",
        "x-vsr-debug": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                content=raw or None,
                headers=headers,
            )
        response_raw = upstream.content
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in EXCLUDED_HEADERS
        }
        content_type = upstream.headers.get("content-type", "")
        parsed = parse_upstream_response(response_raw, content_type)
        route_headers = {
            key.lower(): value
            for key, value in upstream.headers.items()
            if key.lower().startswith("x-vsr-")
        }
        usage = usage_from_payload(parsed)
        selected_model = (
            route_headers.get("x-vsr-selected-model")
            or str(parsed.get("model") or "")
        )
        elapsed = time.perf_counter() - started

        if run and selected_model:
            actual = cost_for_model(selected_model, usage)
            kimi = counterfactual_cost("moonshot/kimi-k3", usage)
            glm = counterfactual_cost("zai/glm-5.3-flash", usage)
            run.actual_cost += actual
            run.all_kimi_cost += kimi
            run.all_glm_cost += glm
            run.prompt_tokens += usage["prompt_tokens"]
            run.completion_tokens += usage["completion_tokens"]
            run.reasoning_tokens += usage["reasoning_tokens"]
            run.model_counts[selected_model] = (
                run.model_counts.get(selected_model, 0) + 1
            )
            decision = route_headers.get("x-vsr-selected-decision")
            event = {
                "call_id": call_id,
                "agent": agent,
                "decision": decision,
                "model": selected_model,
                "model_info": MODEL_INFO.get(selected_model, {}),
                "reasoning": route_headers.get("x-vsr-selected-reasoning"),
                "effort": parse_effort(route_headers),
                "confidence": route_headers.get("x-vsr-selected-confidence"),
                "decision_ranking": route_headers.get(
                    "x-vsr-decision-ranking"
                ),
                "decision_signals": route_headers.get(
                    "x-vsr-matched-decision-model"
                ),
                "conversation_signals": route_headers.get(
                    "x-vsr-matched-conversation"
                ),
                "projection_signals": route_headers.get(
                    "x-vsr-matched-projections"
                ),
                "latency_seconds": round(elapsed, 3),
                "usage": usage,
                "estimated_cost": round(actual, 6),
            }
            await run.emit("route.selected", **event)

            choices = parsed.get("choices") or []
            message = choices[0].get("message") if choices else {}
            for tool_call in (message or {}).get("tool_calls") or []:
                function = tool_call.get("function") or {}
                await run.emit(
                    "tool.call",
                    agent=agent,
                    name=function.get("name") or "tool",
                    arguments=compact_text(
                        function.get("arguments"),
                        300,
                    ),
                )
            await run.emit("metrics.updated", metrics=run.metrics())

        return Response(
            content=response_raw,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=None,
        )
    except Exception as exc:
        if run:
            await run.emit(
                "llm.error",
                call_id=call_id,
                agent=agent,
                error=compact_text(str(exc), 800),
            )
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": "Router unavailable",
                    "type": "proxy_error",
                }
            },
        )
