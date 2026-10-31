const state = {
  config: null,
  selectedTask: null,
  runId: null,
  eventSource: null,
  startedAt: null,
  timer: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  if (!Number.isFinite(Number(value))) return "$0.0000";
  const number = Number(value);
  return number >= 0.01 ? `$${number.toFixed(3)}` : `$${number.toFixed(5)}`;
}

function modelInfo(model) {
  return state.config?.models?.[model] ?? {
    label: model || "Unknown model",
    location: "Unknown",
    color: "#777d86",
  };
}

function splitSignals(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function loadConfig() {
  const response = await fetch("/api/config");
  state.config = await response.json();
  renderSuggestions();
  renderModelPool();
  $("task-input").maxLength = state.config.limits.max_prompt_chars;
  updateCharacterCount();
}

async function refreshSystem() {
  try {
    const response = await fetch("/api/system");
    const body = await response.json();
    const ready = body.router === "ready";
    $("system-dot").className = `status-dot ${ready ? "ready" : "error"}`;
    $("system-label").textContent = ready
      ? "Router and model pool ready"
      : "Model pool starting";
  } catch {
    $("system-dot").className = "status-dot error";
    $("system-label").textContent = "Connection unavailable";
  }
}

function renderSuggestions() {
  $("suggestions").innerHTML = state.config.suggested_tasks
    .map(
      (task) => `
      <button class="suggestion" data-task="${escapeHtml(task.id)}">
        <span class="suggestion-icon">${escapeHtml(task.icon)}</span>
        <span>
          <strong>${escapeHtml(task.title)}</strong>
          <small>${escapeHtml(task.subtitle)}</small>
        </span>
      </button>
    `,
    )
    .join("");

  document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      const task = state.config.suggested_tasks.find(
        (row) => row.id === button.dataset.task,
      );
      state.selectedTask = task;
      $("task-input").value = task.prompt;
      document
        .querySelectorAll(".suggestion")
        .forEach((node) => node.classList.remove("selected"));
      button.classList.add("selected");
      updateCharacterCount();
    });
  });
}

function renderModelPool() {
  $("model-pool").innerHTML = Object.entries(state.config.models)
    .map(([id, model]) => {
      const rate =
        model.tier === "local"
          ? "$0 API"
          : `$${model.input_rate}/$${model.output_rate}`;
      return `
        <div class="model-row">
          <span class="model-color" style="background:${model.color}"></span>
          <span>
            <strong>${escapeHtml(model.label)}</strong>
            <small>${escapeHtml(model.location)}</small>
          </span>
          <span class="model-price">${rate}</span>
        </div>
      `;
    })
    .join("");
}

function updateCharacterCount() {
  const length = $("task-input").value.length;
  const max = $("task-input").maxLength;
  $("char-count").textContent = `${length} / ${max}`;
}

function resetDisplay() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = null;
  state.runId = null;
  state.startedAt = null;
  if (state.timer) clearInterval(state.timer);
  $("run-clock").textContent = "00:00";
  $("timeline").className = "timeline empty";
  $("timeline").innerHTML = `
    <div class="empty-state">
      <div class="pulse-logo">⚡</div>
      <h3>Ready for a live task</h3>
      <p>OpenClaw will call one endpoint. The Router will explain every model decision.</p>
    </div>`;
  $("result-panel").classList.add("hidden");
  updateMetrics({});
  updateAgents(null);
  $("route-detail").className = "route-placeholder";
  $("route-detail").textContent =
    "Select a task to see the router explain its decision.";
  $("run-button").disabled = false;
}

function startClock() {
  state.startedAt = Date.now();
  if (state.timer) clearInterval(state.timer);
  state.timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
    const remainder = String(seconds % 60).padStart(2, "0");
    $("run-clock").textContent = `${minutes}:${remainder}`;
  }, 1000);
}

async function startRun() {
  const task = $("task-input").value.trim();
  if (task.length < 2) {
    $("task-input").focus();
    return;
  }

  $("run-button").disabled = true;
  $("result-panel").classList.add("hidden");
  $("timeline").className = "timeline";
  $("timeline").innerHTML = "";
  startClock();

  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      title: state.selectedTask?.title ?? "Custom booth task",
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    appendEvent({
      type: "run.failed",
      timestamp: new Date().toISOString(),
      error: body.detail ?? "Unable to start task.",
    });
    $("run-button").disabled = false;
    return;
  }

  const body = await response.json();
  state.runId = body.id;
  state.eventSource = new EventSource(`/api/runs/${body.id}/events`);
  state.eventSource.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    handleEvent(payload);
  };
  state.eventSource.onerror = () => {
    if (state.eventSource?.readyState === EventSource.CLOSED) {
      $("run-button").disabled = false;
    }
  };
}

function handleEvent(event) {
  appendEvent(event);
  if (event.agent) updateAgents(event.agent);
  if (event.type === "route.selected") updateRoute(event);
  if (event.metrics) updateMetrics(event.metrics);
  if (event.type === "metrics.updated") updateMetrics(event.metrics);
  if (event.type === "run.completed") {
    showResult(event);
    finishRun();
  }
  if (event.type === "run.failed" || event.type === "run.cancelled") {
    showFailure(event);
    finishRun();
  }
}

function finishRun() {
  if (state.eventSource) state.eventSource.close();
  if (state.timer) clearInterval(state.timer);
  $("run-button").disabled = false;
  updateAgents(null);
}

function eventDescription(event) {
  switch (event.type) {
    case "run.started":
      return {
        title: "OpenClaw accepted the mission",
        copy: event.task,
        color: "#ed1c24",
      };
    case "llm.request":
      return {
        title: `${event.agent} requested intelligence`,
        copy: event.prompt || "Continuing an agent tool loop",
        color: "#777d86",
      };
    case "route.selected": {
      const info = modelInfo(event.model);
      return {
        title: `${event.agent} → ${info.label}`,
        copy: `${event.decision || "default"} route · ${event.effort || "unknown"} effort`,
        color: info.color,
      };
    }
    case "tool.call":
      return {
        title: `${event.agent} called ${event.name}`,
        copy: event.arguments || "Tool call",
        color: "#00c2de",
      };
    case "run.completed":
      return {
        title: "Mission complete",
        copy: "OpenClaw returned a verified result.",
        color: "#56d890",
      };
    case "run.failed":
      return {
        title: "Task failed",
        copy: event.error,
        color: "#ed1c24",
      };
    case "run.cancelled":
      return {
        title: "Task cancelled",
        copy: event.message,
        color: "#777d86",
      };
    default:
      return null;
  }
}

function appendEvent(event) {
  if (event.type === "metrics.updated") return;
  const description = eventDescription(event);
  if (!description) return;
  const time = new Date(event.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const stats =
    event.type === "route.selected"
      ? `<div class="event-stats">
          <span>${Number(event.latency_seconds || 0).toFixed(2)}s</span>
          <span>${event.usage?.prompt_tokens || 0} in</span>
          <span>${event.usage?.completion_tokens || 0} out</span>
          <span>${money(event.estimated_cost)}</span>
        </div>`
      : "";
  const signals =
    event.type === "route.selected"
      ? [
          ...splitSignals(event.decision_signals),
          ...splitSignals(event.conversation_signals),
          ...splitSignals(event.projection_signals),
        ]
          .slice(0, 8)
          .map((signal) => `<span class="chip">${escapeHtml(signal)}</span>`)
          .join("")
      : "";
  const html = `
    <div class="event">
      <div class="event-meta">${time}</div>
      <div class="event-card ${event.type === "route.selected" ? "route" : ""}"
           style="border-left-color:${description.color}">
        <div class="event-title">${escapeHtml(description.title)}</div>
        <div class="event-copy">${escapeHtml(description.copy || "")}</div>
        ${signals ? `<div class="chips">${signals}</div>` : ""}
        ${stats}
      </div>
    </div>`;
  $("timeline").insertAdjacentHTML("beforeend", html);
  $("timeline").scrollTop = $("timeline").scrollHeight;
}

function updateAgents(agent) {
  document.querySelectorAll(".agent-node").forEach((node) => {
    node.classList.toggle(
      "active",
      agent ? node.dataset.agent === agent : node.dataset.agent === "main",
    );
  });
}

function updateRoute(event) {
  const info = modelInfo(event.model);
  const signals = [
    ...splitSignals(event.decision_signals),
    ...splitSignals(event.conversation_signals),
    ...splitSignals(event.projection_signals),
  ];
  $("route-detail").className = "route-placeholder";
  $("route-detail").innerHTML = `
    <div class="route-model" style="color:${info.color}">
      ${escapeHtml(info.label)}
    </div>
    <div class="route-reason">
      <strong>${escapeHtml(event.decision || "default")}</strong>
      · ${escapeHtml(event.effort || "unknown")} effort
      · ${escapeHtml(info.location || "")}
    </div>
    ${
      event.decision_ranking
        ? `<div class="route-reason">${escapeHtml(event.decision_ranking)}</div>`
        : ""
    }
    <div class="chips">
      ${signals
        .slice(0, 10)
        .map((signal) => `<span class="chip">${escapeHtml(signal)}</span>`)
        .join("")}
    </div>`;
}

function updateMetrics(metrics) {
  const actual = Number(metrics.actual_cost || 0);
  const kimi = Number(metrics.all_kimi_cost || 0);
  const savings = Number(metrics.savings_vs_kimi_percent || 0);
  $("metric-calls").textContent = metrics.calls || 0;
  $("metric-cost").textContent = money(actual);
  $("metric-kimi").textContent = money(kimi);
  $("metric-savings").textContent = `${savings.toFixed(1)}%`;
  const ratio = kimi > 0 ? Math.min(100, Math.max(0, (actual / kimi) * 100)) : 0;
  $("cost-fill").style.width = `${ratio}%`;
  $("cost-explainer").textContent =
    kimi > 0
      ? `The routed task used ${ratio.toFixed(1)}% of the all-Kimi token cost.`
      : "Cost updates as model calls complete.";

  const counts = metrics.model_counts || {};
  $("distribution").innerHTML = Object.entries(state.config?.models || {})
    .map(([id, info]) => {
      const count = counts[id] || 0;
      return `
        <div class="distribution-row">
          <span class="model-color" style="background:${info.color}"></span>
          <span>
            <strong>${escapeHtml(info.label)}</strong>
            <small>${escapeHtml(info.location)}</small>
          </span>
          <span class="distribution-count">${count}</span>
        </div>`;
    })
    .join("");
}

function showResult(event) {
  $("result-panel").classList.remove("hidden");
  $("result-title").textContent = state.selectedTask?.title ?? "Task complete";
  $("result-body").textContent = event.result || "Task completed.";
  $("artifact-list").innerHTML = (event.artifacts || [])
    .map(
      (artifact) => `
      <a class="artifact" href="${escapeHtml(artifact.url)}" target="_blank">
        ${escapeHtml(artifact.name)} ↗
      </a>`,
    )
    .join("");
}

function showFailure(event) {
  $("result-panel").classList.remove("hidden");
  $("result-title").textContent = "Task did not complete";
  $("result-body").textContent = event.error || event.message || "Unknown error";
  $("artifact-list").innerHTML = "";
}

$("task-input").addEventListener("input", () => {
  state.selectedTask = null;
  document
    .querySelectorAll(".suggestion")
    .forEach((node) => node.classList.remove("selected"));
  updateCharacterCount();
});
$("run-button").addEventListener("click", startRun);
$("clear-button").addEventListener("click", () => {
  $("task-input").value = "";
  state.selectedTask = null;
  updateCharacterCount();
  resetDisplay();
});

Promise.all([loadConfig(), refreshSystem()]).then(() => {
  resetDisplay();
  setInterval(refreshSystem, 10000);
});
