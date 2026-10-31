const DEFAULT_CONFIG = {
  suggested_tasks: [],
  limits: {
    max_prompt_chars: 4000,
    max_run_seconds: 900,
  },
  models: {
    "qwen/qwen3.8-27b": {
      label: "Qwen3.8-27B",
      location: "Local · AMD MI300X",
      tier: "local",
      color: "#ed1c24",
      input_rate: 0,
      cached_rate: 0,
      output_rate: 0,
    },
    "zai/glm-5.3-flash": {
      label: "GLM-5.3-Flash",
      location: "Fireworks · Serverless",
      tier: "cloud",
      color: "#ff6a00",
      input_rate: 0.15,
      cached_rate: 0.03,
      output_rate: 0.5,
    },
    "moonshot/kimi-k3": {
      label: "Kimi K3",
      location: "Fireworks · Premium",
      tier: "premium",
      color: "#c1a968",
      input_rate: 3,
      cached_rate: 0.3,
      output_rate: 15,
    },
  },
};

const AGENT_CATALOG = [
  {
    id: "main",
    label: "Coordinator",
    kind: "MAIN",
    idle: "Ready to coordinate",
  },
  {
    id: "researcher",
    label: "Researcher",
    kind: "SUBAGENT",
    idle: "Not used yet",
  },
  {
    id: "builder",
    label: "Builder",
    kind: "SUBAGENT",
    idle: "Not used yet",
  },
  {
    id: "reviewer",
    label: "Reviewer",
    kind: "SUBAGENT",
    idle: "Not used yet",
  },
];

const MODEL_ROLES = {
  "qwen/qwen3.8-27b":
    "Fast/default, everyday reasoning, and visual input on-prem",
  "zai/glm-5.3-flash":
    "Tool loops, code, factual work, and hard reasoning",
  "moonshot/kimi-k3":
    "Premium long context, frontier reasoning, and recovery",
};

const DECISION_EXPLANATIONS = {
  long_context: {
    label: "Long-context handoff",
    explanation:
      "The prompt crossed the local Qwen context safety margin, so the router used the pool’s long-context premium path.",
  },
  vision: {
    label: "Visual input",
    explanation:
      "The conversation includes an image or screenshot. This booth policy keeps visual input on the local MI300X route.",
  },
  recovery: {
    label: "Correction / recovery",
    explanation:
      "The conversation asks to correct a prior answer, so the router switched model families and assigned the maximum reasoning budget.",
  },
  code_agentic: {
    label: "Tool-using code",
    explanation:
      "The request combines code with tools or an active tool loop, favoring the pool’s agentic cloud route.",
  },
  agentic: {
    label: "Tool orchestration",
    explanation:
      "The request needs web, browser, or tool orchestration, so it was routed to the model tuned for agentic work.",
  },
  facts: {
    label: "Precision work",
    explanation:
      "The router detected exact factual, analytical, or writing work and selected the pool’s precision cloud route.",
  },
  frontier: {
    label: "Frontier reasoning",
    explanation:
      "The effort classifier marked this as research-level work, triggering the premium model at maximum effort.",
  },
  code: {
    label: "Code reasoning",
    explanation:
      "The request is code generation or debugging with meaningful reasoning, so the router selected the coding cloud route.",
  },
  hard: {
    label: "Hard reasoning",
    explanation:
      "The router detected a difficult multi-step or STEM problem and assigned a deeper reasoning budget.",
  },
  standard: {
    label: "Everyday reasoning",
    explanation:
      "The request needs balanced multi-step reasoning but fits the local model, avoiding a cloud API call.",
  },
  fast: {
    label: "Fast local",
    explanation:
      "The request matched the simple-response path, so it stayed local with model reasoning disabled.",
  },
  guard: {
    label: "Safety guard",
    explanation:
      "The request matched the safety policy before normal generation routing.",
  },
};

const DECISION_EFFORTS = {
  long_context: "high",
  vision: "medium",
  recovery: "max",
  code_agentic: "low",
  agentic: "high",
  facts: "low",
  frontier: "max",
  code: "low",
  hard: "high",
  standard: "medium",
  fast: "off",
};

const SIGNAL_LABELS = {
  beyond_qwen_window: "Beyond local Qwen context window",
  has_image: "Image or screenshot present",
  has_prior_answer: "Prior answer present",
  has_tools: "Tools available",
  tool_loop: "Active tool loop",
  precise_facts: "Exact facts requested",
  effort_off: "Effort score: off",
  effort_low: "Effort score: low",
  effort_medium: "Effort score: medium",
  effort_high: "Effort score: high",
  effort_max: "Effort score: maximum",
  agentic: "Agentic task",
  analysis: "Analysis task",
  code: "Code task",
  facts: "Factual task",
  stem: "STEM task",
  writing: "Writing task",
  tools: "Tools needed",
  correction: "Correction requested",
  difficulty: "High difficulty",
};

const EFFORT_LEVELS = {
  off: {
    label: "Off",
    index: 0,
    explanation: "Thinking is disabled for the fastest response path.",
  },
  low: {
    label: "Low",
    index: 1,
    explanation: "A light reasoning budget is requested for direct work.",
  },
  medium: {
    label: "Medium",
    index: 2,
    explanation: "A balanced reasoning budget is requested for multi-step work.",
  },
  high: {
    label: "High",
    index: 3,
    explanation: "A deeper reasoning budget is requested for complex work.",
  },
  max: {
    label: "Maximum",
    index: 4,
    explanation:
      "The largest reasoning budget is requested for frontier or recovery work.",
  },
  unknown: {
    label: "Not reported",
    index: -1,
    explanation: "The router did not report a reasoning-effort setting.",
  },
};

const state = {
  config: DEFAULT_CONFIG,
  selectedTask: null,
  runTitle: "Custom booth task",
  runId: null,
  runPhase: "idle",
  eventSource: null,
  startedAt: null,
  timer: null,
  seenEvents: new Set(),
  agents: new Map(),
  recoveryInFlight: false,
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

function safeColor(value) {
  const color = String(value || "");
  return /^#[0-9a-f]{3,8}$/i.test(color) ? color : "#777d86";
}

function numeric(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function count(value) {
  return Math.max(0, Math.round(numeric(value))).toLocaleString();
}

function money(value) {
  const number = Math.max(0, numeric(value));
  if (number >= 1) return `$${number.toFixed(2)}`;
  if (number >= 0.01) return `$${number.toFixed(3)}`;
  return `$${number.toFixed(5)}`;
}

function rate(value) {
  return `$${Math.max(0, numeric(value)).toFixed(2)}`;
}

function compactText(value, limit = 600) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function titleCase(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function normalizeConfig(body) {
  const models =
    body?.models &&
    typeof body.models === "object" &&
    Object.keys(body.models).length
      ? body.models
      : DEFAULT_CONFIG.models;
  return {
    ...DEFAULT_CONFIG,
    ...body,
    models,
    suggested_tasks: Array.isArray(body?.suggested_tasks)
      ? body.suggested_tasks
      : [],
    limits: {
      ...DEFAULT_CONFIG.limits,
      ...(body?.limits || {}),
    },
  };
}

function modelInfo(model, inlineInfo = {}) {
  const configured = state.config?.models?.[model] || {};
  const fallbackLabel = titleCase(String(model || "Unknown model").split("/").at(-1));
  return {
    label: inlineInfo.label || configured.label || fallbackLabel,
    location: inlineInfo.location || configured.location || "Location not reported",
    tier: inlineInfo.tier || configured.tier || "unknown",
    color: safeColor(inlineInfo.color || configured.color),
    input_rate: numeric(inlineInfo.input_rate ?? configured.input_rate),
    cached_rate: numeric(inlineInfo.cached_rate ?? configured.cached_rate),
    output_rate: numeric(inlineInfo.output_rate ?? configured.output_rate),
  };
}

function modelRole(model, info) {
  if (MODEL_ROLES[model]) return MODEL_ROLES[model];
  if (info.tier === "local") return "Local acceleration path";
  if (info.tier === "premium") return "Premium cloud reasoning path";
  return "Cloud model route";
}

function splitSignals(value) {
  if (Array.isArray(value)) {
    return value.flatMap((item) => splitSignals(item));
  }
  const text = String(value || "").trim();
  if (!text) return [];
  if (text.startsWith("[") && text.endsWith("]")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) return splitSignals(parsed);
    } catch {
      // Fall through to the header's comma-separated representation.
    }
  }
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueSignals(values) {
  return [...new Set(values.filter(Boolean))];
}

function humanizeSignal(value) {
  const raw = String(value || "").trim();
  const normalized = raw.toLowerCase();
  if (SIGNAL_LABELS[normalized]) return SIGNAL_LABELS[normalized];
  return raw
    .replace(/[_-]+/g, " ")
    .replace(/\s*([:=])\s*/g, " $1 ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function routeNarrative(event) {
  const decision = String(event.decision || "").trim().toLowerCase();
  if (DECISION_EXPLANATIONS[decision]) {
    return DECISION_EXPLANATIONS[decision];
  }
  return {
    label: decision ? titleCase(decision) : "Default policy",
    explanation:
      "The semantic router selected this model from the three-model pool using the matched task, conversation, and effort signals shown below.",
  };
}

function effortInfo(event) {
  const value = event.effort ?? event.reasoning ?? "unknown";
  if (value === false) return { key: "off", ...EFFORT_LEVELS.off };
  const normalized = String(value).trim().toLowerCase();
  const aliases = {
    disabled: "off",
    none: "off",
    false: "off",
    minimal: "low",
    med: "medium",
    xhigh: "max",
    maximum: "max",
  };
  let key = aliases[normalized] || normalized;
  const decision = String(event.decision || "").trim().toLowerCase();
  if (!EFFORT_LEVELS[key] && DECISION_EFFORTS[decision]) {
    key = DECISION_EFFORTS[decision];
  }
  return {
    key: EFFORT_LEVELS[key] ? key : "unknown",
    ...(EFFORT_LEVELS[key] || EFFORT_LEVELS.unknown),
  };
}

function renderEffortMeter(effort) {
  const keys = ["off", "low", "medium", "high", "max"];
  const segments = keys
    .map((key, index) => {
      const active = effort.index >= 0 && index <= effort.index;
      const current = effort.key === key;
      return `<span class="${active ? "filled" : ""} ${
        current ? "current" : ""
      }" title="${escapeHtml(EFFORT_LEVELS[key].label)}"></span>`;
    })
    .join("");
  return `
    <div class="effort-meter" role="img"
         aria-label="Router-requested reasoning effort: ${escapeHtml(effort.label)}">
      ${segments}
    </div>`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      body.detail || body.error?.message || `Request failed (${response.status})`,
    );
  }
  return body;
}

async function loadConfig() {
  try {
    state.config = normalizeConfig(await fetchJson("/api/config"));
    renderSuggestions();
    renderModelPool();
    const maximum = Math.max(
      2,
      numeric(
        state.config.limits?.max_prompt_chars,
        DEFAULT_CONFIG.limits.max_prompt_chars,
      ),
    );
    $("task-input").maxLength = maximum;
    updateCharacterCount();
    updateMetrics({});
    return true;
  } catch (error) {
    state.config = DEFAULT_CONFIG;
    renderSuggestions();
    renderModelPool();
    updateCharacterCount();
    updateMetrics({});
    console.error("Unable to load booth configuration", error);
    return false;
  }
}

async function refreshSystem() {
  try {
    const body = await fetchJson("/api/system");
    const ready = body.router === "ready";
    $("system-dot").className = `status-dot ${ready ? "ready" : "error"}`;
    $("system-label").textContent = ready
      ? "Semantic router ready"
      : "Semantic router starting";
  } catch {
    $("system-dot").className = "status-dot error";
    $("system-label").textContent = "Router connection unavailable";
  }
}

function renderSuggestions() {
  const tasks = state.config?.suggested_tasks || [];
  if (!tasks.length) {
    $("suggestions").innerHTML = `
      <p class="suggestion-empty">Suggested missions are temporarily unavailable.</p>`;
    return;
  }

  $("suggestions").innerHTML = tasks
    .map(
      (task) => `
      <button class="suggestion" type="button"
              data-task="${escapeHtml(task.id)}" aria-pressed="false">
        <span class="suggestion-icon" aria-hidden="true">${escapeHtml(task.icon)}</span>
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
      const task = tasks.find((row) => String(row.id) === button.dataset.task);
      if (!task) return;
      state.selectedTask = task;
      $("task-input").value = task.prompt || "";
      syncSuggestionSelection();
      updateCharacterCount();
      setFormMessage("");
      $("task-input").focus();
    });
  });
}

function syncSuggestionSelection() {
  document.querySelectorAll(".suggestion").forEach((button) => {
    const selected =
      state.selectedTask &&
      String(state.selectedTask.id) === String(button.dataset.task);
    button.classList.toggle("selected", Boolean(selected));
    button.setAttribute("aria-pressed", String(Boolean(selected)));
  });
}

function renderModelPool() {
  const models = Object.entries(state.config?.models || {});
  $("model-pool").innerHTML = models
    .map(([id, model]) => {
      const info = modelInfo(id, model);
      const pricing =
        info.tier === "local"
          ? `
            <span class="model-price">
              <strong>No cloud API charge*</strong>
              <small>MI300X costs excluded</small>
            </span>`
          : `
            <span class="model-price">
              <strong>${rate(info.input_rate)} in / ${rate(info.output_rate)} out</strong>
              <small>per 1M tokens</small>
            </span>`;
      return `
        <div class="model-row">
          <span class="model-color" style="background:${info.color}" aria-hidden="true"></span>
          <span class="model-identity">
            <strong>${escapeHtml(info.label)}</strong>
            <small>${escapeHtml(info.location)}</small>
            <small class="model-role">${escapeHtml(modelRole(id, info))}</small>
          </span>
          ${pricing}
        </div>
      `;
    })
    .join("");
}

function setFormMessage(message, tone = "") {
  const target = $("form-message");
  target.textContent = message;
  target.className = tone ? `form-message ${tone}` : "";
}

function updateCharacterCount() {
  const input = $("task-input");
  const length = input.value.length;
  const maximum = input.maxLength;
  const counter = $("char-count");
  counter.textContent = `${length} / ${maximum}`;
  counter.classList.toggle("warning", maximum > 0 && length / maximum >= 0.9);
}

function agentCatalogEntry(id) {
  return AGENT_CATALOG.find((agent) => agent.id === id);
}

function ensureAgent(id) {
  const key = String(id || "main");
  if (state.agents.has(key)) return state.agents.get(key);
  const catalog = agentCatalogEntry(key);
  const agent = {
    id: key,
    label: catalog?.label || titleCase(key) || "Agent",
    kind: catalog?.kind || (key === "main" ? "MAIN" : "SUBAGENT"),
    idle: catalog?.idle || "Not used yet",
    seen: false,
    active: false,
    calls: 0,
    tools: 0,
    latestModel: null,
    status: catalog?.idle || "Not used yet",
  };
  state.agents.set(key, agent);
  return agent;
}

function resetAgents() {
  state.agents = new Map();
  AGENT_CATALOG.forEach((agent) => ensureAgent(agent.id));
  renderAgentMap();
}

function agentDisplay(id) {
  return ensureAgent(id).label;
}

function recordAgentEvent(event) {
  if (event.type === "run.started") {
    const main = ensureAgent("main");
    main.seen = true;
    main.active = true;
    main.status = "Coordinating task…";
    renderAgentMap();
    return;
  }

  if (
    event.type === "run.completed" ||
    event.type === "run.failed" ||
    event.type === "run.cancelled"
  ) {
    finishAgentActivity();
    return;
  }

  if (!event.agent) return;
  state.agents.forEach((agent) => {
    agent.active = false;
  });
  const agent = ensureAgent(event.agent);
  agent.seen = true;
  agent.active = true;

  if (event.type === "llm.request") {
    agent.status = "Requesting a route…";
  } else if (event.type === "route.selected") {
    agent.calls += 1;
    agent.latestModel = event.model || null;
    agent.status = `${agent.calls} model ${agent.calls === 1 ? "call" : "calls"}`;
  } else if (event.type === "tool.call") {
    agent.tools += 1;
    agent.status = `Using ${event.name || "a tool"}…`;
  } else if (event.type === "llm.error") {
    agent.status = "Model call failed";
  }
  renderAgentMap();
}

function finishAgentActivity() {
  state.agents.forEach((agent) => {
    agent.active = false;
    if (!agent.seen) {
      agent.status = agent.id === "main" ? "No model calls" : "Not used";
    } else if (agent.calls || agent.tools) {
      const parts = [];
      if (agent.calls) parts.push(`${agent.calls} model ${agent.calls === 1 ? "call" : "calls"}`);
      if (agent.tools) parts.push(`${agent.tools} ${agent.tools === 1 ? "tool" : "tools"}`);
      agent.status = parts.join(" · ");
    } else {
      agent.status = "Participated";
    }
  });
  renderAgentMap();
}

function agentCard(agent) {
  const model = agent.latestModel
    ? modelInfo(agent.latestModel)
    : null;
  const classes = [
    "agent-node",
    agent.active ? "active" : "",
    agent.seen ? "seen" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `
    <div class="${classes}" data-agent="${escapeHtml(agent.id)}"
         aria-label="${escapeHtml(`${agent.label}: ${agent.status}`)}">
      <div class="agent-node-top">
        <span>${escapeHtml(agent.kind)}</span>
        <i class="agent-live-dot" aria-hidden="true"></i>
      </div>
      <strong>${escapeHtml(agent.label)}</strong>
      <small class="agent-activity">${escapeHtml(agent.status)}</small>
      ${
        model
          ? `<span class="agent-model">
               <i style="background:${model.color}" aria-hidden="true"></i>
               ${escapeHtml(model.label)}
             </span>`
          : `<span class="agent-model waiting">Awaiting first route</span>`
      }
    </div>`;
}

function renderAgentMap() {
  const ordered = [
    ...AGENT_CATALOG.map((entry) => ensureAgent(entry.id)),
    ...[...state.agents.values()].filter(
      (agent) => !agentCatalogEntry(agent.id),
    ),
  ];
  const main = ordered.find((agent) => agent.id === "main") || ordered[0];
  const subagents = ordered.filter((agent) => agent !== main);
  $("agent-map").innerHTML = `
    ${agentCard(main)}
    <div class="agent-connector" aria-hidden="true"><span>→</span></div>
    ${subagents.map(agentCard).join("")}
  `;

  const usedSubagents = subagents.filter((agent) => agent.seen);
  const active = ordered.find((agent) => agent.active);
  let summary =
    "Subagent cards light up when they make a model or tool call; dim cards were not used.";
  if (active && active.id !== "main") {
    summary = `${active.label} is active. ${usedSubagents.length} ${
      usedSubagents.length === 1 ? "subagent has" : "subagents have"
    } participated so far.`;
  } else if (usedSubagents.length) {
    summary = `${usedSubagents.length} ${
      usedSubagents.length === 1 ? "subagent" : "subagents"
    } participated: ${usedSubagents.map((agent) => agent.label).join(", ")}.`;
  } else if (main?.seen) {
    summary = "The coordinator is working; no subagent has made a call yet.";
  }
  $("agent-summary").textContent = summary;
}

function setRunControls(phase) {
  state.runPhase = phase;
  const busy = phase !== "idle";
  $("run-button").disabled = busy;
  $("run-button").setAttribute("aria-busy", String(busy));
  $("task-input").readOnly = busy;
  document.querySelectorAll(".suggestion").forEach((button) => {
    button.disabled = busy;
  });

  const runLabels = {
    idle: "Run agent",
    starting: "Starting…",
    running: "Agent running",
    cancelling: "Cancelling…",
  };
  $("run-button-label").textContent = runLabels[phase] || "Run agent";
  $("clear-button").textContent = busy ? "Cancel run" : "Clear";
  $("clear-button").disabled = phase === "starting" || phase === "cancelling";
}

function setRunState(label, tone = "") {
  const target = $("run-state");
  target.textContent = label;
  target.className = tone ? `run-state ${tone}` : "run-state";
}

function emptyTimelineMarkup() {
  return `
    <div class="empty-state">
      <div class="pulse-logo" aria-hidden="true">⚡</div>
      <h3>Ready for a live task</h3>
      <p>
        OpenClaw calls one endpoint. The semantic router chooses local Qwen,
        Fireworks GLM, or premium Kimi—and reports why.
      </p>
    </div>`;
}

function resetDisplay({ clearMessage = true } = {}) {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = null;
  state.runId = null;
  state.startedAt = null;
  state.seenEvents = new Set();
  state.recoveryInFlight = false;
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  $("run-clock").textContent = "00:00";
  $("timeline").className = "timeline empty";
  $("timeline").innerHTML = emptyTimelineMarkup();
  $("result-panel").className = "result hidden";
  $("result-body").textContent = "";
  $("artifact-list").innerHTML = "";
  updateMetrics({});
  resetAgents();
  $("route-detail").className = "route-placeholder";
  $("route-detail").textContent =
    "Run a task to see the selected model, matched signals, and router-requested reasoning effort.";
  setRunControls("idle");
  setRunState("Idle");
  if (clearMessage) setFormMessage("");
}

function startClock() {
  state.startedAt = Date.now();
  if (state.timer) clearInterval(state.timer);
  const tick = () => {
    const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
    const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
    const remainder = String(seconds % 60).padStart(2, "0");
    $("run-clock").textContent = `${minutes}:${remainder}`;
  };
  tick();
  state.timer = setInterval(tick, 1000);
}

function finishRun() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = null;
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  state.runId = null;
  state.recoveryInFlight = false;
  setRunControls("idle");
  finishAgentActivity();
}

async function startRun() {
  if (state.runPhase !== "idle") return;
  const input = $("task-input");
  const task = input.value.trim();
  if (task.length < 2) {
    input.setAttribute("aria-invalid", "true");
    setFormMessage("Enter a task before starting the agent.", "error");
    input.focus();
    return;
  }

  input.removeAttribute("aria-invalid");
  setFormMessage("");
  state.runTitle = state.selectedTask?.title || "Custom booth task";
  state.seenEvents = new Set();
  resetAgents();
  updateMetrics({});
  $("route-detail").className = "route-placeholder";
  $("route-detail").textContent = "Waiting for the first routing decision…";
  $("result-panel").className = "result hidden";
  $("timeline").className = "timeline";
  $("timeline").innerHTML = "";
  setRunControls("starting");
  setRunState("Starting", "working");
  startClock();

  try {
    const body = await fetchJson("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task,
        title: state.runTitle,
      }),
    });
    if (!body.id) throw new Error("The run started without an ID.");
    state.runId = body.id;
    setRunControls("running");
    setRunState("Connecting live feed", "working");
    connectEventStream();
  } catch (error) {
    const event = {
      type: "run.failed",
      timestamp: new Date().toISOString(),
      error: error.message || "Unable to start task.",
    };
    appendEvent(event);
    showFailure(event);
    setRunState("Could not start", "error");
    setFormMessage(event.error, "error");
    finishRun();
  }
}

function connectEventStream() {
  if (!state.runId || state.runPhase !== "running") return;
  if (state.eventSource) state.eventSource.close();
  const runId = state.runId;
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  state.eventSource = source;

  source.onopen = () => {
    if (state.runPhase === "running") setRunState("Live", "success");
  };

  source.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      console.warn("Ignored malformed booth event", message.data);
      return;
    }
    const sequence = numeric(event.seq, -1);
    if (sequence >= 0) {
      if (state.seenEvents.has(sequence)) return;
      state.seenEvents.add(sequence);
    }
    handleEvent(event);
  };

  source.onerror = () => {
    if (state.runPhase !== "running") return;
    if (source.readyState === EventSource.CONNECTING) {
      setRunState("Reconnecting…", "warning");
      return;
    }
    setRunState("Live feed interrupted", "warning");
    void recoverRun(runId);
  };
}

async function recoverRun(runId) {
  if (state.recoveryInFlight || state.runPhase !== "running") return;
  state.recoveryInFlight = true;
  try {
    const body = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
    if (body.metrics) updateMetrics(body.metrics);
    if (body.status === "completed") {
      handleEvent({
        type: "run.completed",
        timestamp: new Date().toISOString(),
        result: body.result,
        artifacts: body.artifacts,
        metrics: body.metrics,
      });
    } else if (body.status === "failed" || body.status === "cancelled") {
      handleEvent({
        type: `run.${body.status}`,
        timestamp: new Date().toISOString(),
        error: body.error,
        message: body.status === "cancelled" ? "Task cancelled." : undefined,
        metrics: body.metrics,
      });
    } else {
      setRunState("Reconnecting…", "warning");
      window.setTimeout(() => {
        if (state.runPhase === "running" && state.runId === runId) {
          connectEventStream();
        }
      }, 1200);
    }
  } catch {
    setRunState("Live feed unavailable", "error");
  } finally {
    state.recoveryInFlight = false;
  }
}

function handleEvent(event) {
  recordAgentEvent(event);
  appendEvent(event);
  if (event.type === "route.selected") updateRoute(event);
  if (event.metrics) updateMetrics(event.metrics);
  if (event.type === "run.waiting") {
    setRunState("Waiting for subagents…", "warning");
  }

  if (event.type === "run.completed") {
    showResult(event);
    setRunState("Completed", "success");
    finishRun();
  } else if (event.type === "run.failed") {
    showFailure(event);
    setRunState("Failed", "error");
    finishRun();
  } else if (event.type === "run.cancelled") {
    showFailure(event);
    setRunState("Cancelled", "warning");
    finishRun();
  }
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
        title: `${agentDisplay(event.agent)} requested a model`,
        copy: event.prompt || "Continuing an agent tool loop",
        color: "#777d86",
      };
    case "route.selected": {
      const info = modelInfo(event.model, event.model_info);
      const narrative = routeNarrative(event);
      return {
        title: `${agentDisplay(event.agent)} routed to ${info.label}`,
        copy: narrative.explanation,
        color: info.color,
      };
    }
    case "tool.call":
      return {
        title: `${agentDisplay(event.agent)} called ${event.name || "a tool"}`,
        copy: event.arguments || "Tool call",
        color: "#00c2de",
      };
    case "run.waiting":
      return {
        title: "OpenClaw is waiting for delegated work",
        copy:
          event.message ||
          "Subagents are still working and will report back automatically.",
        color: "#f4bd43",
      };
    case "llm.error":
      return {
        title: `${agentDisplay(event.agent)} model call failed`,
        copy: event.error || "The routed model call did not complete.",
        color: "#ed1c24",
      };
    case "run.completed":
      return {
        title: "Mission complete",
        copy: "OpenClaw returned a result and collected the run artifacts.",
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
        copy: event.message || "The booth run was stopped.",
        color: "#777d86",
      };
    default:
      return null;
  }
}

function eventTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function appendEvent(event) {
  if (event.type === "metrics.updated") return;
  const description = eventDescription(event);
  if (!description) return;
  const timeline = $("timeline");
  const shouldFollow =
    timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 90;
  const route = event.type === "route.selected";
  const effort = route ? effortInfo(event) : null;
  const usage = event.usage || {};
  const cloudCost = Math.max(0, numeric(event.estimated_cost));
  const stats = route
    ? `<div class="event-stats">
        <span>${numeric(event.latency_seconds).toFixed(2)}s latency</span>
        <span>${count(usage.prompt_tokens)} prompt</span>
        <span>${count(usage.completion_tokens)} output</span>
        <span>${count(usage.reasoning_tokens)} reasoning</span>
        <span>${cloudCost ? money(cloudCost) : "$0"} cloud API*</span>
      </div>`
    : "";
  const signals = route
    ? uniqueSignals([
        ...splitSignals(event.decision_signals),
        ...splitSignals(event.conversation_signals),
        ...splitSignals(event.projection_signals),
      ])
        .slice(0, 7)
        .map(
          (signal) =>
            `<span class="chip">${escapeHtml(humanizeSignal(signal))}</span>`,
        )
        .join("")
    : "";
  const agent = event.agent
    ? `<span class="event-agent ${
        event.agent === "main" ? "main" : "subagent"
      }">${escapeHtml(
        event.agent === "main"
          ? "MAIN"
          : `SUBAGENT · ${agentDisplay(event.agent)}`,
      )}</span>`
    : "";
  const effortBadge = effort
    ? `<span class="effort-badge effort-${escapeHtml(effort.key)}">
         REASONING · ${escapeHtml(effort.label)}
       </span>`
    : "";
  const html = `
    <div class="event">
      <div class="event-meta">${eventTime(event.timestamp)}</div>
      <div class="event-card ${route ? "route" : ""}"
           style="border-left-color:${safeColor(description.color)}">
        <div class="event-badges">${agent}${effortBadge}</div>
        <div class="event-title">${escapeHtml(description.title)}</div>
        <div class="event-copy">${escapeHtml(description.copy || "")}</div>
        ${signals ? `<div class="chips">${signals}</div>` : ""}
        ${stats}
      </div>
    </div>`;
  timeline.insertAdjacentHTML("beforeend", html);
  if (shouldFollow) timeline.scrollTop = timeline.scrollHeight;
}

function renderSignalGroup(label, values) {
  const signals = uniqueSignals(splitSignals(values));
  if (!signals.length) return "";
  return `
    <div class="signal-group">
      <span>${escapeHtml(label)}</span>
      <div class="chips">
        ${signals
          .map(
            (signal) =>
              `<span class="chip">${escapeHtml(humanizeSignal(signal))}</span>`,
          )
          .join("")}
      </div>
    </div>`;
}

function confidenceLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const percent = number <= 1 ? number * 100 : number;
  if (percent < 0 || percent > 100) return "";
  return `${percent.toFixed(0)}% confidence`;
}

function updateRoute(event) {
  const info = modelInfo(event.model, event.model_info);
  const narrative = routeNarrative(event);
  const effort = effortInfo(event);
  const confidence = confidenceLabel(event.confidence);
  const cloudCost = Math.max(0, numeric(event.estimated_cost));
  const ranking = compactText(event.decision_ranking);
  const signalGroups = [
    renderSignalGroup("Task signals", event.decision_signals),
    renderSignalGroup("Conversation signals", event.conversation_signals),
    renderSignalGroup("Effort signals", event.projection_signals),
  ].join("");
  $("route-detail").className = "route-card";
  $("route-detail").innerHTML = `
    <div class="route-header">
      <div>
        <span class="route-kicker">SELECTED MODEL</span>
        <div class="route-model" style="color:${info.color}">
          ${escapeHtml(info.label)}
        </div>
        <div class="route-location">${escapeHtml(info.location)}</div>
      </div>
      <span class="route-decision">${escapeHtml(narrative.label)}</span>
    </div>

    <div class="route-explanation">
      <strong>Why this route</strong>
      <p>${escapeHtml(narrative.explanation)}</p>
    </div>

    <div class="effort-panel">
      <div class="effort-heading">
        <span>ROUTER-REQUESTED REASONING</span>
        <strong>${escapeHtml(effort.label)}</strong>
      </div>
      ${renderEffortMeter(effort)}
      <p>
        ${escapeHtml(effort.explanation)}
        This is a budget setting, not a display of private chain-of-thought.
      </p>
    </div>

    <div class="route-facts">
      <span><small>LATENCY</small><strong>${numeric(
        event.latency_seconds,
      ).toFixed(2)}s</strong></span>
      <span><small>CLOUD API*</small><strong>${
        cloudCost ? money(cloudCost) : "$0"
      }</strong></span>
      ${
        confidence
          ? `<span><small>ROUTER</small><strong>${escapeHtml(confidence)}</strong></span>`
          : ""
      }
    </div>

    ${signalGroups ? `<div class="route-signals">${signalGroups}</div>` : ""}

    ${
      ranking
        ? `<details class="route-ranking">
             <summary>Router candidate ranking</summary>
             <code>${escapeHtml(ranking)}</code>
           </details>`
        : ""
    }
  `;
}

function updateMetrics(metrics) {
  const actual = Math.max(0, numeric(metrics.actual_cost));
  const kimi = Math.max(0, numeric(metrics.all_kimi_cost));
  const calls = Math.max(0, Math.round(numeric(metrics.calls)));
  const reportedSavings = Number(metrics.savings_vs_kimi_percent);
  const savings = Number.isFinite(reportedSavings)
    ? reportedSavings
    : kimi > 0
      ? (1 - actual / kimi) * 100
      : 0;
  $("metric-calls").textContent = count(calls);
  $("metric-cost").textContent = money(actual);
  $("metric-kimi").textContent = money(kimi);
  $("metric-savings").textContent = kimi > 0 ? `${savings.toFixed(1)}%` : "—";
  $("metric-savings").classList.toggle("negative", kimi > 0 && savings < 0);
  $("metric-prompt-tokens").textContent = count(metrics.prompt_tokens);
  $("metric-output-tokens").textContent = count(metrics.completion_tokens);
  $("metric-reasoning-tokens").textContent = count(metrics.reasoning_tokens);

  const ratio = kimi > 0 ? Math.max(0, (actual / kimi) * 100) : 0;
  $("cost-fill").style.width = `${Math.min(100, ratio)}%`;
  $("cost-fill").classList.toggle("over", ratio > 100);
  if (kimi > 0 && actual === 0) {
    $("cost-explainer").textContent =
      "Observed calls show $0 cloud API token cost; the local MI300X cost is outside this estimate.";
  } else if (kimi > 0 && savings >= 0) {
    $("cost-explainer").textContent =
      `Routed cloud API cost is ${ratio.toFixed(1)}% of the all-Kimi estimate ` +
      `(${savings.toFixed(1)}% estimated savings).`;
  } else if (kimi > 0) {
    $("cost-explainer").textContent =
      `Routed cloud API cost is ${Math.abs(savings).toFixed(1)}% above the ` +
      "same-token all-Kimi estimate.";
  } else if (calls > 0) {
    $("cost-explainer").textContent =
      "Calls are visible, but no billable token usage has been reported yet.";
  } else {
    $("cost-explainer").textContent =
      "Cloud token/API estimates update as model calls complete.";
  }

  const counts = metrics.model_counts || {};
  $("distribution").innerHTML = Object.entries(state.config?.models || {})
    .map(([id, model]) => {
      const info = modelInfo(id, model);
      const modelCalls = Math.max(0, Math.round(numeric(counts[id])));
      return `
        <div class="distribution-row">
          <span class="model-color" style="background:${info.color}" aria-hidden="true"></span>
          <span>
            <strong>${escapeHtml(info.label)}</strong>
            <small>${escapeHtml(info.location)}</small>
          </span>
          <span class="distribution-count">${count(modelCalls)}</span>
        </div>`;
    })
    .join("");
}

function safeArtifactUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    if (
      url.origin !== window.location.origin ||
      !url.pathname.startsWith("/artifacts/")
    ) {
      return "";
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "";
  }
}

function showResult(event) {
  const panel = $("result-panel");
  panel.className = "result";
  $("result-title").textContent = state.runTitle || "Task complete";
  $("result-status").textContent = "COMPLETED";
  $("result-body").textContent = event.result || "Task completed.";
  $("artifact-list").innerHTML = (event.artifacts || [])
    .map((artifact) => {
      const url = safeArtifactUrl(artifact.url);
      if (!url) return "";
      return `
        <a class="artifact" href="${escapeHtml(url)}" target="_blank"
           rel="noopener noreferrer">
          ${escapeHtml(artifact.name || "Artifact")} ↗
        </a>`;
    })
    .join("");
}

function showFailure(event) {
  const cancelled = event.type === "run.cancelled";
  const panel = $("result-panel");
  panel.className = "result failure";
  $("result-title").textContent = cancelled
    ? "Task cancelled"
    : "Task did not complete";
  $("result-status").textContent = cancelled ? "CANCELLED" : "FAILED";
  $("result-body").textContent =
    event.error || event.message || "The run ended without an error message.";
  $("artifact-list").innerHTML = "";
}

async function handleSecondaryAction() {
  if (state.runPhase === "running" && state.runId) {
    const runId = state.runId;
    setRunControls("cancelling");
    setRunState("Cancelling…", "warning");
    try {
      const body = await fetchJson(
        `/api/runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      if (state.runPhase === "cancelling") {
        handleEvent({
          type: "run.cancelled",
          timestamp: new Date().toISOString(),
          message: "Task cancelled.",
          metrics: body.metrics,
        });
      }
    } catch (error) {
      if (state.runPhase === "cancelling") {
        setRunControls("running");
        setRunState("Cancel failed · still running", "error");
        setFormMessage(error.message || "Unable to cancel the run.", "error");
      }
    }
    return;
  }

  if (state.runPhase !== "idle") return;
  $("task-input").value = "";
  state.selectedTask = null;
  syncSuggestionSelection();
  updateCharacterCount();
  resetDisplay();
  $("task-input").focus();
}

$("task-input").addEventListener("input", () => {
  if (
    state.selectedTask &&
    $("task-input").value !== String(state.selectedTask.prompt || "")
  ) {
    state.selectedTask = null;
    syncSuggestionSelection();
  }
  $("task-input").removeAttribute("aria-invalid");
  setFormMessage("");
  updateCharacterCount();
});

$("task-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    void startRun();
  }
});

$("run-button").addEventListener("click", () => {
  void startRun();
});

$("clear-button").addEventListener("click", () => {
  void handleSecondaryAction();
});

window.addEventListener("beforeunload", () => {
  if (state.eventSource) state.eventSource.close();
});

async function initialize() {
  renderSuggestions();
  renderModelPool();
  resetDisplay();
  const [configLoaded] = await Promise.all([loadConfig(), refreshSystem()]);
  if (!configLoaded) {
    setFormMessage(
      "Live configuration is unavailable; showing the fallback model pool.",
      "warning",
    );
  }
  window.setInterval(refreshSystem, 10000);
}

void initialize();
