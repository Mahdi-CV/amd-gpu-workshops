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
  callRecords: new Map(),
  routeRecords: new Map(),
  routeSequence: 0,
  activeRouteId: null,
  routeTrigger: null,
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

function reportedNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function firstReported(...values) {
  return values.find(
    (value) =>
      value !== null &&
      value !== undefined &&
      !(typeof value === "string" && !value.trim()),
  );
}

function readableValue(value, fallback = "Not reported", limit = 8000) {
  if (value === null || value === undefined || value === "") return fallback;
  let text = "";
  if (typeof value === "string") {
    text = value.trim();
  } else {
    try {
      text = JSON.stringify(value, null, 2);
    } catch {
      text = String(value);
    }
  }
  if (!text) return fallback;
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
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
  const inline = objectValue(inlineInfo);
  const configured = objectValue(state.config?.models?.[model]);
  const fallbackLabel = titleCase(String(model || "Unknown model").split("/").at(-1));
  return {
    label: inline.label || configured.label || fallbackLabel,
    location: inline.location || configured.location || "Location not reported",
    tier: inline.tier || configured.tier || "unknown",
    color: safeColor(inline.color || configured.color),
    input_rate: numeric(inline.input_rate ?? configured.input_rate),
    cached_rate: numeric(inline.cached_rate ?? configured.cached_rate),
    output_rate: numeric(inline.output_rate ?? configured.output_rate),
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
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) => {
      if (item === false || item === null || item === undefined) return [];
      if (item === true) return [key];
      if (typeof item === "string" || typeof item === "number") {
        return [`${key}: ${item}`];
      }
      return splitSignals(item);
    });
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
    .replace(/\s*:\s*/g, ": ")
    .replace(/\s*=\s*/g, " = ")
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

function isGuardRoute(event) {
  const decision = String(event?.decision || "").trim().toLowerCase();
  const model = String(event?.model || "").trim().toLowerCase();
  return decision === "guard" || model.includes("safety guard");
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

function normalizeCallId(value) {
  return compactText(value, 180);
}

function rememberModelEvent(event) {
  if (
    event.type !== "llm.request" &&
    event.type !== "route.selected" &&
    event.type !== "llm.error"
  ) {
    return "";
  }

  const callId = normalizeCallId(event.call_id);
  let record = callId ? state.callRecords.get(callId) : null;
  if (!record && callId) {
    record = {
      callId,
      request: null,
      route: null,
      error: null,
      routeId: "",
    };
    state.callRecords.set(callId, record);
  }

  if (!record && event.type === "route.selected") {
    record = {
      callId: "",
      request: null,
      route: null,
      error: null,
      routeId: "",
    };
  }
  if (!record) return "";

  if (event.type === "llm.request") {
    record.request = event;
  } else if (event.type === "route.selected") {
    record.route = event;
    if (!record.routeId) {
      state.routeSequence += 1;
      record.routeId = `route-${state.routeSequence}`;
      state.routeRecords.set(record.routeId, record);
    }
  } else if (event.type === "llm.error") {
    record.error = event;
  }

  if (record.routeId && state.activeRouteId === record.routeId) {
    renderRouteInspector(record);
  }
  return record.routeId;
}

function resetRouteInspectionState() {
  closeRouteInspector({ restoreFocus: false });
  state.callRecords = new Map();
  state.routeRecords = new Map();
  state.routeSequence = 0;
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
  resetRouteInspectionState();
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
  resetRouteInspectionState();
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
    if (!event || typeof event !== "object" || Array.isArray(event)) {
      console.warn("Ignored non-object booth event", event);
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
  if (!event || typeof event !== "object" || Array.isArray(event)) return;
  const routeId = rememberModelEvent(event);
  recordAgentEvent(event);
  appendEvent(event, routeId);
  if (event.type === "route.selected") updateRoute(event, routeId);
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

function appendEvent(event, routeInspectorId = "") {
  if (event.type === "metrics.updated") return;
  const description = eventDescription(event);
  if (!description) return;
  const timeline = $("timeline");
  const shouldFollow =
    timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 90;
  const route = event.type === "route.selected";
  const inspectorId =
    routeInspectorId || (route ? rememberModelEvent(event) : "");
  const effort = route ? effortInfo(event) : null;
  const usage = objectValue(event.usage);
  const latency = reportedNumber(event.latency_seconds);
  const cloudCost = reportedNumber(event.estimated_cost);
  const promptTokens = reportedNumber(usage.prompt_tokens);
  const completionTokens = reportedNumber(usage.completion_tokens);
  const reasoningTokens = reportedNumber(usage.reasoning_tokens);
  const stats = route
    ? `<div class="event-stats">
        <span>${latency === null ? "—" : `${Math.max(0, latency).toFixed(2)}s`} latency</span>
        <span>${promptTokens === null ? "—" : count(promptTokens)} prompt</span>
        <span>${completionTokens === null ? "—" : count(completionTokens)} output</span>
        <span>${reasoningTokens === null ? "—" : count(reasoningTokens)} reasoning</span>
        <span>${cloudCost === null ? "—" : money(cloudCost)} cloud API*</span>
      </div>`
    : "";
  const signals = route
    ? uniqueSignals([
        ...splitSignals(event.decision_signals),
        ...splitSignals(event.conversation_signals),
        ...splitSignals(event.projection_signals),
        ...splitSignals(event.keyword_signals),
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
  const cardContent = `
    <div class="event-badges">${agent}${effortBadge}</div>
    <div class="event-title">${escapeHtml(description.title)}</div>
    <div class="event-copy">${escapeHtml(description.copy || "")}</div>
    ${signals ? `<div class="chips">${signals}</div>` : ""}
    ${stats}
    ${
      route && inspectorId
        ? `<span class="event-route-action" aria-hidden="true">
             Inspect routing decision <strong>↗</strong>
           </span>`
        : ""
    }`;
  const card =
    route && inspectorId
      ? `<button
           class="event-card route route-trigger"
           type="button"
           data-route-id="${escapeHtml(inspectorId)}"
           aria-haspopup="dialog"
           aria-controls="route-inspector"
           aria-label="${escapeHtml(
             `${description.title}. Open routing decision inspector.`,
           )}"
           style="border-left-color:${safeColor(description.color)}"
         >
           ${cardContent}
         </button>`
      : `<div
           class="event-card ${route ? "route" : ""}"
           style="border-left-color:${safeColor(description.color)}"
         >
           ${cardContent}
         </div>`;
  const html = `
    <div class="event">
      <div class="event-meta">${eventTime(event.timestamp)}</div>
      ${card}
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

function updateRoute(event, routeInspectorId = "") {
  const info = modelInfo(event.model, event.model_info);
  const narrative = routeNarrative(event);
  const effort = effortInfo(event);
  const confidence = confidenceLabel(event.confidence);
  const latency = reportedNumber(event.latency_seconds);
  const cloudCost = reportedNumber(event.estimated_cost);
  const ranking = compactText(
    readableValue(event.decision_ranking, ""),
  );
  const signalGroups = [
    renderSignalGroup("Semantic signals", event.decision_signals),
    renderSignalGroup("Conversation signals", event.conversation_signals),
    renderSignalGroup("Projection signals", event.projection_signals),
    renderSignalGroup("Keyword signals", event.keyword_signals),
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
      <span><small>LATENCY</small><strong>${
        latency === null ? "—" : `${Math.max(0, latency).toFixed(2)}s`
      }</strong></span>
      <span><small>CLOUD API*</small><strong>${
        cloudCost === null ? "—" : money(cloudCost)
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

    ${
      routeInspectorId
        ? `<button class="route-detail-action" type="button"
                   data-route-id="${escapeHtml(routeInspectorId)}"
                   aria-haspopup="dialog" aria-controls="route-inspector">
             Inspect full routing decision <span aria-hidden="true">↗</span>
           </button>`
        : ""
    }
  `;
}

function inspectorAgentIdentity(value) {
  const id = compactText(value, 120);
  if (!id) {
    return {
      label: "Not reported",
      detail: "Agent identity was not included",
    };
  }
  const catalog = agentCatalogEntry(id);
  const known = state.agents.get(id);
  const label = known?.label || catalog?.label || titleCase(id) || "Agent";
  const kind =
    known?.kind || catalog?.kind || (id === "main" ? "MAIN" : "SUBAGENT");
  return {
    label,
    detail: `${kind === "MAIN" ? "Main agent" : "Subagent"} · ${id}`,
  };
}

function inspectorCount(value) {
  const number = reportedNumber(value);
  return number === null ? null : Math.max(0, Math.round(number));
}

function inspectorText(value, fallback = "—", limit = 260) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return readableValue(value, fallback, limit);
}

function inspectorStringList(value) {
  if (Array.isArray(value)) {
    return uniqueSignals(
      value
        .map((item) => compactText(item, 180))
        .filter(Boolean),
    );
  }
  const text = String(value || "").trim();
  if (!text) return [];
  if (text.startsWith("[") && text.endsWith("]")) {
    try {
      return inspectorStringList(JSON.parse(text));
    } catch {
      // Fall through to the comma-separated representation.
    }
  }
  return uniqueSignals(
    text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function renderMessagesSummary(value) {
  if (!Array.isArray(value)) {
    return `<pre>${escapeHtml(
      readableValue(value, "No conversation summary was reported for this call."),
    )}</pre>`;
  }
  const rows = value.filter(
    (row) => row && typeof row === "object" && !Array.isArray(row),
  );
  if (!rows.length) {
    return `<p class="inspector-empty-copy">No conversation messages were reported for this call.</p>`;
  }
  return `
    <div class="inspector-message-list">
      ${rows
        .map((row) => {
          const role = compactText(row.role, 60) || "unknown";
          const chars = inspectorCount(row.chars);
          const toolCallId = compactText(row.tool_call_id, 100);
          const metadata = [
            chars === null ? "" : `${count(chars)} chars`,
            toolCallId ? `tool call ${toolCallId}` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `
            <div class="inspector-message">
              <div>
                <span>${escapeHtml(role)}</span>
                ${metadata ? `<small>${escapeHtml(metadata)}</small>` : ""}
              </div>
              <p>${escapeHtml(
                readableValue(row.preview, "No message preview reported.", 1200),
              )}</p>
            </div>`;
        })
        .join("")}
    </div>`;
}

function renderInspectorMetadata(items, className = "") {
  return `
    <div class="inspector-metadata-grid ${escapeHtml(className)}">
      ${items
        .map(
          ({ label, value, detail = "" }) => `
            <article>
              <small>${escapeHtml(label)}</small>
              <strong>${escapeHtml(value)}</strong>
              ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
            </article>`,
        )
        .join("")}
    </div>`;
}

function renderInspectorSignalGroup(label, values, tone) {
  const signals = uniqueSignals(splitSignals(values));
  return `
    <article class="inspector-signal-group ${escapeHtml(tone)}">
      <div class="inspector-signal-heading">
        <span aria-hidden="true"></span>
        <div>
          <h4>${escapeHtml(label)}</h4>
          <small>${
            signals.length
              ? `${count(signals.length)} matched`
              : "None reported"
          }</small>
        </div>
      </div>
      ${
        signals.length
          ? `<div class="chips">
               ${signals
                 .map(
                   (signal) =>
                     `<span class="chip">${escapeHtml(
                       humanizeSignal(signal),
                     )}</span>`,
                 )
                 .join("")}
             </div>`
          : `<p>No ${escapeHtml(label.toLowerCase())} were included in this route event.</p>`
      }
    </article>`;
}

function routeExplanationSteps(record) {
  const route = objectValue(record.route);
  const request = objectValue(record.request);
  const agent = inspectorAgentIdentity(
    firstReported(route.agent, request.agent),
  );
  const info = modelInfo(route.model, route.model_info);
  const narrative = routeNarrative(route);
  const effort = effortInfo(route);
  const guard = isGuardRoute(route);
  const semantic = uniqueSignals(splitSignals(route.decision_signals)).map(
    humanizeSignal,
  );
  const conversation = uniqueSignals(
    splitSignals(route.conversation_signals),
  ).map(humanizeSignal);
  const projection = uniqueSignals(
    splitSignals(route.projection_signals),
  ).map(humanizeSignal);
  const keywords = uniqueSignals(splitSignals(route.keyword_signals)).map(
    humanizeSignal,
  );
  const toolCount = inspectorCount(
    firstReported(request.tool_count, route.tool_count),
  );
  const toolNames = inspectorStringList(
    firstReported(request.tool_names, route.tool_names),
  );
  const ranking = readableValue(route.decision_ranking, "");
  const confidence =
    confidenceLabel(route.confidence) ||
    compactText(firstReported(route.confidence, ""), 80);
  const algorithm = compactText(route.selected_algorithm, 180);
  const recipe = compactText(route.selected_recipe, 180);
  const steps = [];

  steps.push(
    record.request
      ? `${agent.label} submitted the model request${
          toolCount === null
            ? ""
            : ` with ${count(toolCount)} ${
                toolCount === 1 ? "tool" : "tools"
              } available`
        }${
          toolNames.length
            ? ` (${toolNames.slice(0, 6).join(", ")}${
                toolNames.length > 6 ? ", …" : ""
              })`
            : ""
        }. The prompt shown above comes from the llm.request event matched to this route by call ID.`
      : `The route event identifies ${agent.label}, but no matching llm.request payload was available, so prompt and tool context may be incomplete.`,
  );
  steps.push(
    semantic.length
      ? `Semantic matching identified: ${semantic.join(", ")}.`
      : "The route event did not report a matched semantic signal.",
  );
  steps.push(
    conversation.length
      ? `Conversation context added: ${conversation.join(", ")}.`
      : "No conversation-level signal was reported for this call.",
  );
  steps.push(
    projection.length
      ? `The projection layer added: ${projection.join(", ")}.`
      : "No projection signal was reported; the configured effort is taken from the selected route metadata when available.",
  );
  if (keywords.length) {
    steps.push(`Keyword matching also identified: ${keywords.join(", ")}.`);
  }
  steps.push(
    guard
      ? "Those inputs triggered the safety guard before normal model generation, so a standard model candidate did not need to win."
      : `The router applied the “${narrative.label}” policy. ${narrative.explanation}`,
  );
  if (algorithm || recipe) {
    steps.push(
      `Candidate selection used${
        algorithm ? ` the ${algorithm} algorithm` : " the reported algorithm"
      }${recipe ? ` with recipe ${recipe}` : ""}.`,
    );
  }
  steps.push(
    ranking || confidence
      ? `The router${
          confidence ? ` reported ${confidence}` : ""
        }${
          ranking
            ? `${confidence ? " and" : ""} emitted the candidate ranking shown above`
            : ""
        }.`
      : "No candidate ranking or confidence was reported, so the selected decision and matched signals are the available routing evidence.",
  );
  steps.push(
    guard
      ? "The safety policy returned the guard route. Token, latency, and cost fields are shown only when the backend reported them."
      : `That policy selected ${info.label} at ${info.location} and configured ${effort.label.toLowerCase()} reasoning effort. ${effort.explanation}`,
  );
  return steps;
}

function renderRouteInspector(record) {
  const route = objectValue(record.route);
  if (!route || !Object.keys(route).length) return;
  const request = objectValue(record.request);
  const errorEvent = objectValue(record.error);
  const guard = isGuardRoute(route);
  const info = modelInfo(route.model, route.model_info);
  const narrative = routeNarrative(route);
  const effort = effortInfo(route);
  const agent = inspectorAgentIdentity(
    firstReported(route.agent, request.agent),
  );
  const prompt = readableValue(
    firstReported(request.prompt, route.prompt),
    record.request
      ? "The request event did not include a prompt."
      : "Prompt unavailable because no matching llm.request event was received.",
  );
  const messagesSummary = firstReported(
    request.messages_summary,
    route.messages_summary,
  );
  const toolCount = inspectorCount(
    firstReported(request.tool_count, route.tool_count),
  );
  const toolNames = inspectorStringList(
    firstReported(request.tool_names, route.tool_names),
  );
  const promptChars = inspectorCount(request.prompt_chars);
  const messageCount = inspectorCount(request.message_count);
  const maxTokens = inspectorCount(request.max_tokens);
  const requestMetadata = [
    {
      label: "REQUESTED MODEL",
      value: inspectorText(request.requested_model),
    },
    {
      label: "API PATH",
      value: inspectorText(request.request_path),
    },
    {
      label: "MESSAGES",
      value: messageCount === null ? "—" : count(messageCount),
    },
    {
      label: "PROMPT CHARS",
      value: promptChars === null ? "—" : count(promptChars),
    },
    {
      label: "STREAMING",
      value:
        typeof request.stream === "boolean"
          ? request.stream
            ? "Yes"
            : "No"
          : "—",
    },
    {
      label: "MAX OUTPUT TOKENS",
      value: maxTokens === null ? "—" : count(maxTokens),
    },
    {
      label: "TEMPERATURE",
      value: inspectorText(request.temperature),
    },
  ];
  const usage = objectValue(route.usage);
  const promptTokens = inspectorCount(usage.prompt_tokens);
  const completionTokens = inspectorCount(usage.completion_tokens);
  const cachedTokens = inspectorCount(usage.cached_tokens);
  const reasoningTokens = inspectorCount(usage.reasoning_tokens);
  let totalTokens = inspectorCount(usage.total_tokens);
  if (
    totalTokens === null &&
    (promptTokens !== null || completionTokens !== null)
  ) {
    totalTokens = (promptTokens || 0) + (completionTokens || 0);
  }
  const latency = reportedNumber(route.latency_seconds);
  const cloudCost = reportedNumber(route.estimated_cost);
  const routingLatencyNumber = reportedNumber(route.routing_latency_ms);
  const routingLatency =
    routingLatencyNumber === null
      ? inspectorText(route.routing_latency_ms)
      : `${Math.max(0, routingLatencyNumber).toFixed(
          routingLatencyNumber >= 10 ? 0 : 2,
        )} ms`;
  const contextTokens = inspectorCount(route.context_tokens);
  const routerCostValue = inspectorText(route.router_cost);
  const routerCostCurrency = compactText(route.router_cost_currency, 40);
  const routerCost =
    routerCostValue === "—"
      ? "—"
      : `${routerCostValue}${routerCostCurrency ? ` ${routerCostCurrency}` : ""}`;
  const routerMetadata = [
    {
      label: "SELECTED ALGORITHM",
      value: inspectorText(route.selected_algorithm),
    },
    {
      label: "SELECTED RECIPE",
      value: inspectorText(route.selected_recipe),
    },
    {
      label: "ROUTER LATENCY",
      value: routingLatency,
    },
    {
      label: "CONTEXT TOKENS",
      value: contextTokens === null ? "—" : count(contextTokens),
    },
    {
      label: "ROUTER-REPORTED COST",
      value: routerCost,
    },
    {
      label: "RESPONSE MODEL",
      value: inspectorText(route.response_model),
    },
  ];
  const confidence =
    confidenceLabel(route.confidence) ||
    compactText(firstReported(route.confidence, ""), 80) ||
    "Not reported";
  const ranking = readableValue(
    route.decision_ranking,
    "No candidate ranking was reported by the router.",
  );
  const selectedModelId = compactText(route.model, 220);
  const modelLabel = selectedModelId
    ? info.label
    : guard
      ? "vLLM-SR safety guard"
      : "Not reported";
  const modelLocation = guard
    ? "Policy layer · before model generation"
    : info.location;
  const callId = record.callId || normalizeCallId(route.call_id);
  const errorText = readableValue(
    firstReported(errorEvent.error, route.error),
    "",
    1800,
  );
  const correlationNote = record.request
    ? `Request context and routing result correlated by call_id ${callId || "not reported"}.`
    : callId
      ? `No matching llm.request event was received for call_id ${callId}; route-only fields are shown.`
      : "This route did not include a call_id, so request context could not be correlated.";
  const steps = routeExplanationSteps(record);

  $("route-inspector-title").textContent = guard
    ? "Safety guard decision"
    : `${modelLabel} route`;
  $("route-inspector-summary").textContent =
    `${agent.label} · ${narrative.label} · ${effort.label} reasoning`;
  $("route-inspector-call-id").textContent = callId
    ? `MODEL ROUTE · CALL ${callId}`
    : "MODEL ROUTE · CALL ID NOT REPORTED";
  $("route-inspector-content").innerHTML = `
    <section class="inspector-hero" style="--route-accent:${info.color}">
      <div class="inspector-model">
        <span>SELECTED MODEL</span>
        <h3>${escapeHtml(modelLabel)}</h3>
        <p>
          ${escapeHtml(modelLocation)}
          ${
            selectedModelId && selectedModelId !== modelLabel
              ? `<small>${escapeHtml(selectedModelId)}</small>`
              : ""
          }
        </p>
      </div>
      <span class="inspector-decision">${escapeHtml(narrative.label)}</span>
    </section>

    ${
      guard
        ? `<div class="inspector-alert guard" role="note">
             <strong>Safety guard route</strong>
             <span>Normal generation routing was intercepted by policy.</span>
           </div>`
        : ""
    }
    ${
      errorText
        ? `<div class="inspector-alert error" role="note">
             <strong>Model call error</strong>
             <span>${escapeHtml(errorText)}</span>
           </div>`
        : ""
    }

    <section class="inspector-overview" aria-label="Routing summary">
      <article>
        <small>AGENT IDENTITY</small>
        <strong>${escapeHtml(agent.label)}</strong>
        <span>${escapeHtml(agent.detail)}</span>
      </article>
      <article>
        <small>DECISION</small>
        <strong>${escapeHtml(narrative.label)}</strong>
        <span>${escapeHtml(
          compactText(route.decision, 100) || "Decision key not reported",
        )}</span>
      </article>
      <article>
        <small>REASONING EFFORT</small>
        <strong>${escapeHtml(effort.label)}</strong>
        <span>Configured by the router</span>
      </article>
      <article>
        <small>ROUTER CONFIDENCE</small>
        <strong>${escapeHtml(confidence)}</strong>
        <span>Selected-route confidence</span>
      </article>
    </section>

    <section class="inspector-section" aria-labelledby="inspector-request-heading">
      <div class="inspector-section-heading">
        <div>
          <span>REQUEST CONTEXT</span>
          <h3 id="inspector-request-heading">What the model call received</h3>
        </div>
        <span class="inspector-tool-count">${
          toolCount === null
            ? "TOOLS · NOT REPORTED"
            : `TOOLS · ${count(toolCount)}`
        }</span>
      </div>
      <div class="inspector-prompt-grid">
        <article>
          <h4>Prompt sent to the model</h4>
          <pre>${escapeHtml(prompt)}</pre>
        </article>
        <article class="inspector-summary-card">
          <h4>Conversation summary</h4>
          ${renderMessagesSummary(messagesSummary)}
        </article>
      </div>
      <div class="inspector-tools">
        <div>
          <h4>Declared tools</h4>
          <span>${
            toolCount === null
              ? "Count not reported"
              : `${count(toolCount)} ${toolCount === 1 ? "tool" : "tools"} available`
          }</span>
        </div>
        ${
          toolNames.length
            ? `<div class="chips">
                 ${toolNames
                   .map(
                     (name) =>
                       `<span class="chip">${escapeHtml(name)}</span>`,
                   )
                   .join("")}
               </div>`
            : `<p>${
                toolCount === 0
                  ? "No tools were declared for this model call."
                  : "Declared tool names were not reported."
              }</p>`
        }
      </div>
      ${renderInspectorMetadata(requestMetadata, "request")}
      <p class="inspector-correlation ${record.request ? "matched" : "warning"}">
        ${escapeHtml(correlationNote)}
      </p>
    </section>

    <section class="inspector-section" aria-labelledby="inspector-signals-heading">
      <div class="inspector-section-heading">
        <div>
          <span>ROUTING EVIDENCE</span>
          <h3 id="inspector-signals-heading">Matched router signals</h3>
        </div>
      </div>
      <div class="inspector-signal-grid">
        ${renderInspectorSignalGroup(
          "Semantic signals",
          route.decision_signals,
          "semantic",
        )}
        ${renderInspectorSignalGroup(
          "Conversation signals",
          route.conversation_signals,
          "conversation",
        )}
        ${renderInspectorSignalGroup(
          "Projection signals",
          route.projection_signals,
          "projection",
        )}
        ${renderInspectorSignalGroup(
          "Keyword signals",
          route.keyword_signals,
          "keyword",
        )}
      </div>
      <div class="inspector-ranking-grid">
        <article class="inspector-confidence">
          <span>ROUTER CONFIDENCE</span>
          <strong>${escapeHtml(confidence)}</strong>
          <p>Confidence reported for the selected routing decision.</p>
        </article>
        <article class="inspector-ranking">
          <span>CANDIDATE RANKING</span>
          <pre>${escapeHtml(ranking)}</pre>
        </article>
      </div>
      <div class="inspector-router-trace">
        <h4>Router trace metadata</h4>
        ${renderInspectorMetadata(routerMetadata, "router")}
      </div>
    </section>

    <section class="inspector-section" aria-labelledby="inspector-telemetry-heading">
      <div class="inspector-section-heading">
        <div>
          <span>CALL TELEMETRY</span>
          <h3 id="inspector-telemetry-heading">Usage, latency, and cloud cost</h3>
        </div>
      </div>
      <div class="inspector-metric-grid">
        <article><small>TOOLS AVAILABLE</small><strong>${
          toolCount === null ? "—" : count(toolCount)
        }</strong></article>
        <article><small>LATENCY</small><strong>${
          latency === null ? "—" : `${Math.max(0, latency).toFixed(2)}s`
        }</strong></article>
        <article><small>CLOUD API COST*</small><strong>${
          cloudCost === null ? "—" : money(cloudCost)
        }</strong></article>
        <article><small>TOTAL TOKENS</small><strong>${
          totalTokens === null ? "—" : count(totalTokens)
        }</strong></article>
        <article><small>PROMPT TOKENS</small><strong>${
          promptTokens === null ? "—" : count(promptTokens)
        }</strong></article>
        <article><small>OUTPUT TOKENS</small><strong>${
          completionTokens === null ? "—" : count(completionTokens)
        }</strong></article>
        <article><small>CACHED TOKENS</small><strong>${
          cachedTokens === null ? "—" : count(cachedTokens)
        }</strong></article>
        <article><small>REASONING TOKENS</small><strong>${
          reasoningTokens === null ? "—" : count(reasoningTokens)
        }</strong></article>
      </div>
      <p class="inspector-cost-note">
        * Cloud token/API estimate only. Local AMD Instinct hardware and
        operating costs are outside this value.
      </p>
    </section>

    <section class="inspector-section inspector-explanation"
             aria-labelledby="inspector-explanation-heading">
      <div class="inspector-section-heading">
        <div>
          <span>PLAIN-LANGUAGE TRACE</span>
          <h3 id="inspector-explanation-heading">Why this route won</h3>
        </div>
      </div>
      <ol>
        ${steps
          .map(
            (step) => `
              <li>
                <span aria-hidden="true"></span>
                <p>${escapeHtml(step)}</p>
              </li>`,
          )
          .join("")}
      </ol>
      <p class="inspector-explanation-note">
        This explanation is assembled from reported router metadata. It
        describes the routing policy and does not expose private model
        chain-of-thought.
      </p>
    </section>
  `;
}

function openRouteInspector(routeId, trigger) {
  const record = state.routeRecords.get(String(routeId || ""));
  if (!record?.route) return;
  const modal = $("route-inspector");
  state.activeRouteId = record.routeId;
  state.routeTrigger =
    trigger instanceof HTMLElement ? trigger : document.activeElement;
  renderRouteInspector(record);
  document.body.classList.add("route-inspector-open");
  if (!modal.open) {
    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  }
  $("route-inspector-announcer").textContent =
    `Opened routing decision inspector for ${
      modelInfo(record.route.model, record.route.model_info).label
    }.`;
  window.requestAnimationFrame(() => {
    $("route-inspector-close").focus();
  });
}

function closeRouteInspector({ restoreFocus = true } = {}) {
  const modal = $("route-inspector");
  if (!modal) return;
  const trigger = state.routeTrigger;
  state.activeRouteId = null;
  state.routeTrigger = null;
  document.body.classList.remove("route-inspector-open");
  if (modal.open && typeof modal.close === "function") {
    modal.close();
  } else {
    modal.removeAttribute("open");
  }
  $("route-inspector-announcer").textContent = "";
  if (
    restoreFocus &&
    trigger instanceof HTMLElement &&
    trigger.isConnected
  ) {
    window.requestAnimationFrame(() => {
      trigger.focus({ preventScroll: true });
    });
  }
}

function handleRouteInspectorTrigger(event) {
  const target =
    event.target instanceof Element
      ? event.target.closest("[data-route-id]")
      : null;
  if (!target) return;
  openRouteInspector(target.dataset.routeId, target);
}

function handleRouteInspectorKeydown(event) {
  const modal = $("route-inspector");
  if (!modal.open && !modal.hasAttribute("open")) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeRouteInspector();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = [...modal.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hidden);
  if (!focusable.length) {
    event.preventDefault();
    modal.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
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

$("timeline").addEventListener("click", handleRouteInspectorTrigger);
$("route-detail").addEventListener("click", handleRouteInspectorTrigger);
$("route-inspector-close").addEventListener("click", () => {
  closeRouteInspector();
});
$("route-inspector").addEventListener("click", (event) => {
  if (event.target === $("route-inspector")) closeRouteInspector();
});
$("route-inspector").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeRouteInspector();
});
$("route-inspector").addEventListener(
  "keydown",
  handleRouteInspectorKeydown,
);

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
