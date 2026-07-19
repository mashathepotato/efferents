let csrfToken = "";
let controlState = { connected: false };
let isConnecting = false;
let runtimeAction = "start";

async function getJSON(path) {
  const response = await fetch(path);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `${path} returned ${response.status}`);
  }
  return payload;
}

async function postJSON(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Efferents-CSRF": csrfToken,
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `${path} returned ${response.status}`);
  }
  return body;
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function text(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value == null ? "" : String(value);
}

function showMessage(id, message = "", type = "") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = message;
  element.className = `form-message${type ? ` ${type}` : ""}`;
}

function formatMetric(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const number = Number(value);
  const magnitude = Math.abs(number);
  if (magnitude !== 0 && (magnitude >= 10000 || magnitude < 0.0001)) {
    return number.toExponential(3);
  }
  return number.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}

function formatTimestamp(value, compact = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).replace("T", " ").slice(0, compact ? 16 : 19);
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: compact ? undefined : "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}` +
    (compact ? "" : `:${get("second")}`);
}

function setTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  text("theme-label", dark ? "Light" : "Dark");
  const toggle = document.getElementById("theme-toggle");
  toggle.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
}

function initTheme() {
  const stored = localStorage.getItem("efferents-theme");
  setTheme(stored === "dark" ? "dark" : "light");
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("efferents-theme", next);
    setTheme(next);
  });
}

function currentRoute() {
  const route = window.location.hash.replace(/^#/, "");
  return ["connect", "steer", "observe"].includes(route) ? route : "connect";
}

function renderRoute() {
  let route = currentRoute();
  if (!controlState.connected && route !== "connect") {
    route = "connect";
    if (window.location.hash !== "#connect") {
      history.replaceState(null, "", "#connect");
    }
  }
  document.querySelectorAll("[data-route-view]").forEach((view) => {
    view.hidden = view.dataset.routeView !== route;
  });
  document.querySelectorAll("[data-route-link]").forEach((link) => {
    if (link.dataset.routeLink === route) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  document.title = `efferents — ${route}`;
}

function initRouting() {
  window.addEventListener("hashchange", renderRoute);
  document.querySelectorAll("[data-route-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
        showMessage("connect-message", "Connect a lab before opening this workspace.", "error");
      }
    });
  });
  renderRoute();
}

function setRuntimeStatus(status) {
  const normalized = String(status || "stopped").toLowerCase();
  const badge = document.getElementById("status-badge");
  badge.className = `status-badge ${normalized}`;
  text("status-text", normalized);
  text("connected-summary-status", normalized);
  text("steer-runtime-state", normalized === "running" ? "agent is running" : "queued locally");
}

function setContractState(contract, phase = "result") {
  document.querySelectorAll("[data-contract]").forEach((item) => {
    const key = item.dataset.contract;
    const state = item.querySelector(".check-state");
    item.classList.remove("checking", "passed");
    if (phase === "checking") {
      item.classList.add("checking");
      state.textContent = "checking";
    } else if (contract?.[key]) {
      item.classList.add("passed");
      state.textContent = "passed";
    } else {
      state.textContent = "waiting";
    }
  });
}

function renderSteering(records) {
  const steering = Array.isArray(records) ? records : [];
  text("steering-count", `${steering.length} ${steering.length === 1 ? "record" : "records"}`);
  const element = document.getElementById("steering-history");
  if (!steering.length) {
    element.innerHTML = '<div class="empty-state">No human directions recorded yet</div>';
    return;
  }
  element.innerHTML = steering.map((record) => {
    const mode = String(record.mode || "auto").replace(/_/g, " ");
    return `<article class="steering-record">` +
      `<div class="steering-record-meta">` +
        `<time>${esc(formatTimestamp(record.timestamp, true))} UTC</time>` +
        `<span class="steering-mode">${esc(mode)}</span>` +
      `</div>` +
      `<p>${esc(record.message || "")}</p>` +
    `</article>`;
  }).join("");
}

function renderControl(info) {
  if (info.csrf_token) csrfToken = info.csrf_token;
  controlState = { ...controlState, ...info };
  const connected = Boolean(info.connected);
  controlState.connected = connected;

  document.querySelectorAll('[data-route-link="steer"], [data-route-link="observe"]').forEach((link) => {
    link.setAttribute("aria-disabled", connected ? "false" : "true");
  });

  const connectionBar = document.getElementById("connection-bar");
  const summary = document.getElementById("connected-summary");
  const budget = document.getElementById("budget-meta");
  connectionBar.hidden = !connected;
  summary.hidden = !connected;
  budget.hidden = !connected;

  if (!connected) {
    text("lab-id", "connect a lab");
    text("domain", "local");
    setRuntimeStatus("disconnected");
    if (!isConnecting) setContractState(info.contract);
    renderSteering([]);
    renderRoute();
    return;
  }

  text("lab-id", info.lab_id || "unnamed-lab");
  text("domain", info.domain || "unclassified");
  text("connection-source", info.source || info.submission_dir || "local submission");
  text("connected-summary-name", info.lab_id || "unnamed-lab");
  text("connected-summary-domain", info.domain || "unclassified");
  text("connected-summary-path", info.submission_dir || "—");
  setRuntimeStatus(info.status);
  setContractState(info.contract);
  renderSteering(info.steering);

  const keyState = document.getElementById("api-key-state");
  keyState.textContent = info.has_api_key ? "API key ready" : "API key missing";
  keyState.classList.toggle("ready", Boolean(info.has_api_key));
  document.getElementById("start-lab").hidden = info.status === "running";
  document.getElementById("stop-lab").hidden = info.status !== "running";
  renderRoute();
}

function renderState(state) {
  if (!controlState.connected) return;
  setRuntimeStatus(state.status || controlState.status);

  const spent = Number(state.budget?.spent || 0);
  const cap = Number(state.budget?.cap || 0);
  const percent = cap > 0 ? Math.min(100, Math.max(0, (spent / cap) * 100)) : 0;
  text("budget", `$${spent.toFixed(2)} / $${cap.toFixed(2)} daily`);
  document.getElementById("budget-fill").style.width = `${percent}%`;

  const hypothesis = state.hypothesis || {};
  text("student", hypothesis.student ? `student / ${hypothesis.student}` : "student / —");
  text("question", hypothesis.question || "No open campaign. The lab is waiting for its next falsifiable question.");
  text("claim", hypothesis.claim || "No claim has been recorded.");
  text("falsifier", hypothesis.falsifier || "No falsification condition has been recorded.");
}

function renderRuns(data) {
  const headline = data.headline || { column: "metric", direction: "min" };
  const direction = headline.direction === "max" ? "max" : "min";
  const directionLabel = direction === "max" ? "higher is better" : "lower is better";
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const values = runs
    .map((run) => Number(run.value))
    .filter((value) => Number.isFinite(value));
  const best = values.length
    ? (direction === "max" ? Math.max(...values) : Math.min(...values))
    : null;
  const latest = runs.length && Number.isFinite(Number(runs[0].value))
    ? Number(runs[0].value)
    : null;

  text("metric-label", headline.column || "Headline metric");
  text("metric-direction", directionLabel);
  text("run-metric-header", headline.column || "Result");
  text("run-count", `${runs.length} ${runs.length === 1 ? "record" : "records"}`);
  text("metric-best", formatMetric(best));

  if (latest == null || best == null) {
    text("metric-delta", "—");
  } else {
    const gap = latest - best;
    const prefix = gap > 0 ? "+" : "";
    text("metric-delta", gap === 0 ? "at best" : `${prefix}${formatMetric(gap)}`);
  }

  const tbody = document.querySelector("#runs tbody");
  tbody.innerHTML = "";
  const firstBestIndex = runs.findIndex((run) =>
    Number.isFinite(Number(run.value)) && Number(run.value) === best
  );
  runs.forEach((run, index) => {
    const numericValue = Number(run.value);
    const hasValue = Number.isFinite(numericValue);
    const tiesBest = hasValue && best != null && numericValue === best;
    const isBest = tiesBest && index === firstBestIndex;
    const row = document.createElement("tr");
    if (isBest) row.className = "is-best";
    row.innerHTML =
      `<td>${String(runs.length - index).padStart(2, "0")}</td>` +
      `<td class="run-id" title="${esc(run.run_id || "")}">${esc(run.run_id || "—")}</td>` +
      `<td title="${esc(run.started_at || "")}">${esc(formatTimestamp(run.started_at))}</td>` +
      `<td class="metric-cell">${esc(formatMetric(run.value))}</td>` +
      `<td><span class="signal-tag${isBest ? " best" : ""}">` +
      `${isBest ? "best" : tiesBest ? "ties best" : hasValue ? "observed" : "missing"}</span></td>`;
    tbody.appendChild(row);
  });

  if (!runs.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5"><div class="empty-state">No run records available</div></td>';
    tbody.appendChild(row);
  }

  renderTrend(Array.isArray(data.series) ? data.series : [], direction);
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function renderTrend(series, direction) {
  const svg = document.getElementById("trend");
  svg.innerHTML = "";

  if (!series.length) {
    text("trend-caption", "No metric observations");
    text("metric-range", "—");
    return;
  }

  const width = 600;
  const height = 180;
  const padding = { top: 14, right: 18, bottom: 24, left: 42 };
  const values = series.map((point) => Number(point.value));
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const rawSpan = rawMax - rawMin;
  const span = rawSpan || Math.max(Math.abs(rawMax) * 0.1, 1);
  const min = rawMin - span * 0.08;
  const max = rawMax + span * 0.08;
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (chartHeight / 4) * index;
    svg.appendChild(svgElement("line", {
      x1: padding.left,
      x2: width - padding.right,
      y1: y,
      y2: y,
      class: "grid-line",
    }));
  }

  const coordinates = series.map((point, index) => {
    const x = series.length === 1
      ? padding.left + chartWidth / 2
      : padding.left + (index / (series.length - 1)) * chartWidth;
    const y = padding.top + (1 - ((Number(point.value) - min) / (max - min))) * chartHeight;
    return { x, y, value: Number(point.value) };
  });

  if (coordinates.length > 1) {
    const linePoints = coordinates.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
    const areaPoints = `${padding.left},${height - padding.bottom} ${linePoints} ` +
      `${width - padding.right},${height - padding.bottom}`;
    svg.appendChild(svgElement("polygon", { points: areaPoints, class: "area" }));
    svg.appendChild(svgElement("polyline", { points: linePoints, class: "trend-line" }));
  }

  const best = direction === "max" ? rawMax : rawMin;
  coordinates.forEach((point) => {
    const isBest = point.value === best;
    svg.appendChild(svgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: isBest ? 3.7 : 2.5,
      class: `point${isBest ? " best" : ""}`,
    }));
  });

  const topLabel = svgElement("text", { x: 2, y: padding.top + 3 });
  topLabel.textContent = formatMetric(rawMax);
  svg.appendChild(topLabel);
  const bottomLabel = svgElement("text", { x: 2, y: height - padding.bottom + 3 });
  bottomLabel.textContent = formatMetric(rawMin);
  svg.appendChild(bottomLabel);

  const startLabel = svgElement("text", {
    x: padding.left,
    y: height - 6,
    "text-anchor": "start",
  });
  startLabel.textContent = formatTimestamp(series[0].started_at, true);
  svg.appendChild(startLabel);
  const endLabel = svgElement("text", {
    x: width - padding.right,
    y: height - 6,
    "text-anchor": "end",
  });
  endLabel.textContent = formatTimestamp(series[series.length - 1].started_at, true);
  svg.appendChild(endLabel);

  text("trend-caption", `${series.length} observations / chronological`);
  text("metric-range", `range ${formatMetric(rawMin)} — ${formatMetric(rawMax)}`);
}

function renderPapers(papers) {
  const records = Array.isArray(papers) ? papers : [];
  const element = document.getElementById("papers");
  text("paper-count", `${records.length} ${records.length === 1 ? "record" : "records"}`);

  if (!records.length) {
    element.innerHTML = '<div class="empty-state">No publishable artifact has cleared the gate</div>';
    return;
  }

  element.innerHTML = records.map((paper) =>
    `<article class="paper-record">` +
      `<div class="record-glyph" aria-hidden="true">↗</div>` +
      `<div><div class="paper-title">${esc(paper.title || "Untitled artifact")}</div>` +
      `<div class="paper-meta">${esc(paper.campaign_id || "no campaign")} · ${esc(paper.published_at || "undated")}</div></div>` +
      `<div class="paper-status">${esc(paper.status || "draft")}</div>` +
    `</article>`
  ).join("");
}

function renderActivity(activities) {
  const records = Array.isArray(activities) ? activities : [];
  const element = document.getElementById("activity");

  if (!records.length) {
    element.innerHTML = '<div class="empty-state">No agent events in the notebook</div>';
    return;
  }

  element.innerHTML = records.map((activity) => {
    const body = String(activity.body || "").replace(/\s+/g, " ").trim();
    return `<article class="activity-item">` +
      `<time class="activity-when">${esc(formatTimestamp(activity.timestamp, true))} UTC</time>` +
      `<div class="activity-content"><div class="activity-title" title="${esc(activity.title)}">${esc(activity.title)}</div>` +
      (body ? `<div class="activity-body">${esc(body)}</div>` : "") +
      `</div></article>`;
  }).join("");
}

async function refreshObserver() {
  if (!controlState.connected) return;
  const requests = [
    ["/api/state", renderState],
    ["/api/runs", renderRuns],
    ["/api/papers", renderPapers],
    ["/api/activity", renderActivity],
  ];
  const results = await Promise.allSettled(
    requests.map(async ([path, renderer]) => renderer(await getJSON(path)))
  );
  results
    .filter((result) => result.status === "rejected")
    .forEach((result) => console.error(result.reason));
}

async function refresh() {
  try {
    const info = await getJSON("/api/control");
    renderControl(info);
    await refreshObserver();
    text("last-sync", `${new Date().toISOString().slice(0, 19).replace("T", " ")} UTC`);
  } catch (error) {
    console.error(error);
  }
}

function initConnectForm() {
  const form = document.getElementById("connect-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const source = document.getElementById("github-source").value.trim();
    const button = document.getElementById("connect-submit");
    isConnecting = true;
    button.disabled = true;
    button.textContent = "Connecting…";
    setContractState({}, "checking");
    showMessage("connect-message", "Checking out and validating the submission contract…");
    try {
      const info = await postJSON("/api/connect", { source });
      renderControl(info);
      showMessage(
        "connect-message",
        `${info.lab_id} is connected. Repository code has not been executed.`,
        "success",
      );
      window.location.hash = "steer";
      await refreshObserver();
    } catch (error) {
      setContractState({});
      showMessage("connect-message", error.message, "error");
    } finally {
      isConnecting = false;
      button.disabled = false;
      button.textContent = "Connect lab";
    }
  });
}

function initSteeringForm() {
  const form = document.getElementById("steer-form");
  const message = document.getElementById("steer-message");
  message.addEventListener("input", () => text("steer-count", message.value.length));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    showMessage("steer-message-state", "Recording direction in the local research log…");
    try {
      const result = await postJSON("/api/steer", {
        message: message.value,
        mode: document.getElementById("steer-mode").value,
      });
      message.value = "";
      text("steer-count", "0");
      renderSteering(result.steering);
      showMessage(
        "steer-message-state",
        result.status === "running"
          ? "Direction recorded. The running agent will read it on its next research pass."
          : "Direction recorded locally. It will be read when the lab starts.",
        "success",
      );
    } catch (error) {
      showMessage("steer-message-state", error.message, "error");
    } finally {
      submit.disabled = false;
    }
  });
}

function openRuntimeDialog(action) {
  runtimeAction = action;
  const starting = action === "start";
  text("runtime-dialog-kicker", starting ? "Local execution" : "Stop local execution");
  text("runtime-dialog-title", starting ? "Start this lab?" : "Stop this lab?");
  text(
    "runtime-dialog-copy",
    starting
      ? "Starting executes repository-defined commands and can incur local compute and LLM cost under the configured budget."
      : "Stopping interrupts the local agent loop after its current process receives the shutdown signal.",
  );
  text(
    "runtime-confirm-label",
    starting
      ? "I understand and authorize this local run."
      : "I understand and want to stop this local run.",
  );
  text("runtime-confirm-button", starting ? "Confirm start" : "Confirm stop");
  const checkbox = document.getElementById("runtime-confirm-check");
  checkbox.checked = false;
  document.getElementById("runtime-confirm-button").disabled = true;
  showMessage("runtime-dialog-message");
  document.getElementById("runtime-dialog").showModal();
}

function initRuntimeControls() {
  const dialog = document.getElementById("runtime-dialog");
  const checkbox = document.getElementById("runtime-confirm-check");
  const confirm = document.getElementById("runtime-confirm-button");
  document.getElementById("start-lab").addEventListener("click", () => openRuntimeDialog("start"));
  document.getElementById("stop-lab").addEventListener("click", () => openRuntimeDialog("stop"));
  checkbox.addEventListener("change", () => {
    confirm.disabled = !checkbox.checked;
  });
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    showMessage(
      "runtime-dialog-message",
      runtimeAction === "start" ? "Starting the local daemon…" : "Stopping the local daemon…",
    );
    try {
      const info = await postJSON(`/api/lab/${runtimeAction}`, { confirmed: true });
      renderControl(info);
      dialog.close();
      await refreshObserver();
    } catch (error) {
      showMessage("runtime-dialog-message", error.message, "error");
      confirm.disabled = false;
    }
  });
}

initTheme();
initRouting();
initConnectForm();
initSteeringForm();
initRuntimeControls();
refresh();
setInterval(refresh, 4000);
