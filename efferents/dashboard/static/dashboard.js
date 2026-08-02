let csrfToken = "";
let controlState = { connected: false, hydrated: false };
let portfolioState = { labs: [], edges: [], public_network: {} };
let isConnecting = false;
let runtimeAction = "start";
let networkScope = "internal";
let networkFocusLabId = "";
let renderedRoute = "";

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

function quantile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const remainder = position - lower;
  return sorted[lower + 1] == null
    ? sorted[lower]
    : sorted[lower] + remainder * (sorted[lower + 1] - sorted[lower]);
}

function compactRunId(value) {
  const runId = String(value || "");
  if (runId.length <= 22) return runId || "—";
  return `…${runId.slice(-21)}`;
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

function formatRelativeTime(value) {
  if (!value) return "no activity";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return formatTimestamp(value, true);
  const elapsed = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
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
  return ["connect", "steer", "observe", "network"].includes(route) ? route : "connect";
}

function renderRoute() {
  let route = currentRoute();
  if (controlState.hydrated && !controlState.connected && !["connect", "network"].includes(route)) {
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
  const labRail = document.getElementById("lab-rail");
  const showRail = route !== "connect" && portfolioState.labs.length > 0;
  labRail.hidden = !showRail;
  document.getElementById("workspace-frame").classList.toggle("with-lab-rail", showRail);
  if (renderedRoute && renderedRoute !== route) window.scrollTo(0, 0);
  renderedRoute = route;
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
    element.innerHTML = '<div class="empty-state">No directions</div>';
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
  controlState.hydrated = true;

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
  text("observe-lab-title", info.lab_id || "unnamed-lab");
  text("observe-lab-meta", `${info.domain || "unclassified"} / ${info.status || "stopped"}`);
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

function selectedPortfolioLab() {
  return portfolioState.labs.find((lab) => lab.selected) || null;
}

function renderLabRail() {
  const labs = Array.isArray(portfolioState.labs) ? portfolioState.labs : [];
  text("lab-portfolio-count", String(labs.length).padStart(2, "0"));
  const list = document.getElementById("lab-list");
  if (!labs.length) {
    list.innerHTML = '<div class="empty-state">No local labs</div>';
    renderRoute();
    return;
  }
  list.innerHTML = labs.map((lab, index) => {
    const headline = lab.headline || {};
    const metric = headline.best == null
      ? `${headline.observations || 0} observations`
      : `${esc(headline.column || "metric")} ${esc(formatMetric(headline.best))}`;
    return `<button class="lab-list-item${lab.selected ? " selected" : ""}" ` +
      `type="button" data-lab-select="${esc(lab.lab_id)}" role="listitem" ` +
      `aria-current="${lab.selected ? "true" : "false"}">` +
      `<span class="lab-seq">${String(index + 1).padStart(2, "0")}</span>` +
      `<span class="lab-list-copy"><strong>${esc(lab.lab_id)}</strong>` +
      `<small>${esc(lab.domain || "unclassified")}</small>` +
      `<span>${metric}</span></span>` +
      `<span class="lab-list-state ${esc(lab.status || "stopped")}">` +
      `<i aria-hidden="true"></i>${esc(formatRelativeTime(lab.last_activity))}</span>` +
      `</button>`;
  }).join("");
  list.querySelectorAll("[data-lab-select]").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectPortfolioLab(button.dataset.labSelect, false);
    });
  });
  renderRoute();
}

function portfolioNodePosition(index, count) {
  const angle = (-Math.PI / 2) + ((Math.PI * 2 * index) / Math.max(count, 1));
  return {
    x: 50 + Math.cos(angle) * (count < 3 ? 29 : 35),
    y: 50 + Math.sin(angle) * (count < 3 ? 27 : 34),
  };
}

function renderNetworkDetail(lab) {
  const detail = document.getElementById("network-detail");
  if (!lab) {
    text("network-detail-status", networkScope === "public" ? "not connected" : "private");
    detail.innerHTML = `<span class="route-kicker">${networkScope === "public" ? "Public registry" : "Lab node"}</span>` +
      `<h3>${networkScope === "public" ? "No linked labs." : "Select a node."}</h3>` +
      `<p>${networkScope === "public" ? "Private until authorized." : "Hypothesis · signal · budget · artifacts"}</p>`;
    return;
  }
  const headline = lab.headline || {};
  const budget = lab.budget || {};
  const hypothesis = lab.hypothesis || {};
  text("network-detail-status", lab.visibility || "private");
  detail.innerHTML = `<span class="route-kicker">${esc(lab.domain || "unclassified")} / ${esc(lab.status || "stopped")}</span>` +
    `<h3>${esc(lab.lab_id)}</h3>` +
    `<p>${esc(hypothesis.question || "No open campaign.")}</p>` +
    `<dl class="node-facts">` +
      `<div><dt>Best signal</dt><dd>${esc(headline.column || "metric")} / ${esc(formatMetric(headline.best))}</dd></div>` +
      `<div><dt>Evidence</dt><dd>${headline.observations || 0} runs / ${lab.papers || 0} papers</dd></div>` +
      `<div><dt>Budget</dt><dd>$${Number(budget.spent || 0).toFixed(2)} / $${Number(budget.cap || 0).toFixed(2)}</dd></div>` +
      `<div><dt>Last signal</dt><dd>${esc(formatRelativeTime(lab.last_activity))}</dd></div>` +
    `</dl>` +
    `<button class="primary-button node-inspect-button" type="button" data-network-inspect="${esc(lab.lab_id)}">Inspect node</button>`;
  const inspect = detail.querySelector("[data-network-inspect]");
  inspect.addEventListener("click", async () => {
    await selectPortfolioLab(inspect.dataset.networkInspect, true);
  });
}

function renderNetwork() {
  const labs = (portfolioState.labs || []).filter((lab) =>
    networkScope === "internal" || lab.visibility === "public"
  );
  const lines = document.getElementById("network-lines");
  const nodes = document.getElementById("network-nodes");
  const empty = document.getElementById("network-empty");
  const hub = document.querySelector(".network-hub");
  const positions = new Map();
  lines.innerHTML = "";
  nodes.innerHTML = "";
  text("network-node-count", `${labs.length} ${labs.length === 1 ? "node" : "nodes"}`);
  text("network-scope-note", networkScope === "internal" ? "file-backed local registry" : "authorized publication layer");
  text("network-hub-label", networkScope === "internal" ? "local control plane" : "public journal");
  document.querySelectorAll("[data-network-scope]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.networkScope === networkScope));
  });

  if (!labs.length) {
    empty.hidden = false;
    empty.textContent = networkScope === "public" ? "No public nodes" : "Connect a lab";
    hub.hidden = networkScope === "public";
    renderNetworkDetail(null);
    return;
  }
  empty.hidden = true;
  hub.hidden = false;

  labs.forEach((lab, index) => {
    const position = portfolioNodePosition(index, labs.length);
    positions.set(lab.lab_id, position);
    lines.appendChild(svgElement("line", {
      x1: 500,
      y1: 280,
      x2: position.x * 10,
      y2: position.y * 5.6,
      class: "hub-edge",
    }));
    const button = document.createElement("button");
    button.type = "button";
    button.className = `map-node ${lab.status || "stopped"}${lab.selected ? " selected" : ""}`;
    button.dataset.mapLab = lab.lab_id;
    button.style.left = `${position.x}%`;
    button.style.top = `${position.y}%`;
    button.innerHTML = `<span class="map-node-state"><i aria-hidden="true"></i>${esc(lab.status || "stopped")}</span>` +
      `<strong>${esc(lab.lab_id)}</strong><small>${esc(lab.domain || "unclassified")}</small>`;
    button.addEventListener("click", () => {
      networkFocusLabId = lab.lab_id;
      renderNetwork();
    });
    nodes.appendChild(button);
  });

  (portfolioState.edges || []).forEach((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return;
    lines.appendChild(svgElement("line", {
      x1: source.x * 10,
      y1: source.y * 5.6,
      x2: target.x * 10,
      y2: target.y * 5.6,
      class: "domain-edge",
    }));
  });

  const focused = labs.find((lab) => lab.lab_id === networkFocusLabId) ||
    labs.find((lab) => lab.selected) || labs[0];
  networkFocusLabId = focused.lab_id;
  nodes.querySelectorAll("[data-map-lab]").forEach((button) => {
    button.classList.toggle("focused", button.dataset.mapLab === networkFocusLabId);
  });
  renderNetworkDetail(focused);
}

function renderPortfolio(payload) {
  portfolioState = {
    labs: Array.isArray(payload?.labs) ? payload.labs : [],
    edges: Array.isArray(payload?.edges) ? payload.edges : [],
    public_network: payload?.public_network || {},
  };
  const selected = selectedPortfolioLab();
  if (!networkFocusLabId && selected) networkFocusLabId = selected.lab_id;
  text("public-network-message", portfolioState.public_network.connected
    ? "Public registry connected."
    : "Private until authorized.");
  renderLabRail();
  renderNetwork();
}

async function refreshPortfolio() {
  renderPortfolio(await getJSON("/api/labs"));
}

async function selectPortfolioLab(labId, openObserver) {
  const info = await postJSON("/api/labs/select", { lab_id: labId });
  renderControl(info);
  networkFocusLabId = labId;
  await Promise.all([refreshPortfolio(), refreshObserver()]);
  if (openObserver) window.location.hash = "observe";
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
  const question = hypothesis.question || "No open campaign.";
  const claim = hypothesis.claim || "No claim.";
  text("question", question);
  text("claim", question.replace(/\s+/g, " ").trim() === claim.replace(/\s+/g, " ").trim()
    ? "Matches the active hypothesis above."
    : claim);
  text("falsifier", hypothesis.falsifier || "No falsifier.");
}

function renderRuns(data) {
  const headline = data.headline || { column: "metric", direction: "min" };
  const direction = headline.direction === "max" ? "max" : "min";
  const directionLabel = direction === "max" ? "higher is better" : "lower is better";
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const history = data.history || {};
  const observedRuns = runs.filter((run) => Number.isFinite(Number(run.value)));
  const eligibleRuns = observedRuns.filter((run) => run.eligible !== false);
  const eligibleValues = eligibleRuns.map((run) => Number(run.value));
  const recentBest = eligibleValues.length
    ? (direction === "max" ? Math.max(...eligibleValues) : Math.min(...eligibleValues))
    : null;
  const best = Number.isFinite(Number(history.best)) ? Number(history.best) : recentBest;
  const latest = eligibleRuns.length ? Number(eligibleRuns[0].value) : null;
  const bestRunId = history.best_run_id ||
    eligibleRuns.find((run) => Number(run.value) === best)?.run_id || "";
  const median = quantile(eligibleValues, 0.5);
  const lowerQuartile = quantile(eligibleValues, 0.25);
  const upperQuartile = quantile(eligibleValues, 0.75);
  const iqr = lowerQuartile == null || upperQuartile == null
    ? null
    : upperQuartile - lowerQuartile;
  const excludedCount = runs.filter((run) => run.eligible === false).length;

  text("metric-label", headline.column || "Headline metric");
  text("metric-direction", directionLabel);
  text("run-metric-header", headline.column || "Result");
  text("run-count", `${runs.length} recent / ${Number(history.total || runs.length)} total`);
  text("metric-best", formatMetric(best));
  text("metric-latest", formatMetric(latest));
  text("metric-eligible", `${eligibleRuns.length} / ${runs.length}`);
  text("metric-median", formatMetric(median));
  text("metric-iqr", formatMetric(iqr));
  const bestRunElement = document.getElementById("metric-best-run");
  bestRunElement.textContent = compactRunId(bestRunId);
  bestRunElement.title = bestRunId;

  if (latest == null || best == null) {
    text("metric-delta", "—");
  } else {
    const gap = direction === "max" ? best - latest : latest - best;
    text("metric-delta", Math.abs(gap) < Number.EPSILON ? "at best" : formatMetric(gap));
  }

  const tbody = document.querySelector("#runs tbody");
  tbody.innerHTML = "";
  const firstBestIndex = runs.findIndex((run) =>
    run.eligible !== false && Number.isFinite(Number(run.value)) && Number(run.value) === best
  );
  runs.forEach((run, index) => {
    const numericValue = Number(run.value);
    const hasValue = Number.isFinite(numericValue);
    const eligible = hasValue && run.eligible !== false;
    const excluded = run.eligible === false;
    const tiesBest = eligible && best != null && numericValue === best;
    const isBest = tiesBest && index === firstBestIndex;
    const row = document.createElement("tr");
    row.className = isBest ? "is-best" : excluded ? "is-excluded" : "";
    const failures = Array.isArray(run.constraint_failures)
      ? run.constraint_failures.join("; ")
      : "";
    if (failures) row.title = failures;
    const validity = isBest
      ? "best"
      : tiesBest
        ? "ties best"
        : excluded
          ? "excluded"
          : hasValue
            ? "eligible"
            : "missing";
    row.innerHTML =
      `<td>${String(runs.length - index).padStart(2, "0")}</td>` +
      `<td class="run-id" title="${esc(run.run_id || "")}">${esc(run.run_id || "—")}</td>` +
      `<td title="${esc(run.started_at || "")}">${esc(formatTimestamp(run.started_at))}</td>` +
      `<td class="metric-cell">${esc(formatMetric(run.value))}</td>` +
      `<td><span class="signal-tag${isBest ? " best" : excluded ? " excluded" : ""}">` +
      `${validity}</span></td>`;
    tbody.appendChild(row);
  });

  if (!runs.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5"><div class="empty-state">No runs</div></td>';
    tbody.appendChild(row);
  }

  renderTrend(Array.isArray(data.series) ? data.series : [], direction, {
    metric: headline.column || "metric",
    eligible: eligibleRuns.length,
    excluded: excludedCount,
    median,
  });
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function renderTrend(series, direction, summary = {}) {
  const svg = document.getElementById("trend");
  svg.innerHTML = "";
  const finiteSeries = series.filter((point) => Number.isFinite(Number(point.value)));
  svg.setAttribute(
    "aria-label",
    `${summary.metric || "metric"} across ${finiteSeries.length} eligible observations`,
  );

  if (!finiteSeries.length) {
    text("trend-caption", "No eligible metric observations");
    text("metric-range", "—");
    return;
  }

  const width = 600;
  const height = 180;
  const padding = { top: 14, right: 18, bottom: 24, left: 62 };
  const values = finiteSeries.map((point) => Number(point.value));
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
    const tick = svgElement("text", {
      x: padding.left - 7,
      y: y + 3,
      "text-anchor": "end",
    });
    tick.textContent = formatMetric(max - ((max - min) / 4) * index);
    svg.appendChild(tick);
  }

  const coordinates = finiteSeries.map((point, index) => {
    const x = finiteSeries.length === 1
      ? padding.left + chartWidth / 2
      : padding.left + (index / (finiteSeries.length - 1)) * chartWidth;
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

  if (summary.median != null) {
    const medianY = padding.top +
      (1 - ((Number(summary.median) - min) / (max - min))) * chartHeight;
    svg.appendChild(svgElement("line", {
      x1: padding.left,
      x2: width - padding.right,
      y1: medianY,
      y2: medianY,
      class: "reference-line",
    }));
    const medianLabel = svgElement("text", {
      x: width - padding.right,
      y: medianY - 4,
      "text-anchor": "end",
      class: "reference-label",
    });
    medianLabel.textContent = `median ${formatMetric(summary.median)}`;
    svg.appendChild(medianLabel);
  }

  const startLabel = svgElement("text", {
    x: padding.left,
    y: height - 6,
    "text-anchor": "start",
  });
  startLabel.textContent = formatTimestamp(finiteSeries[0].started_at, true);
  svg.appendChild(startLabel);
  const endLabel = svgElement("text", {
    x: width - padding.right,
    y: height - 6,
    "text-anchor": "end",
  });
  endLabel.textContent = formatTimestamp(finiteSeries[finiteSeries.length - 1].started_at, true);
  svg.appendChild(endLabel);

  text(
    "trend-caption",
    `${finiteSeries.length} eligible / chronological` +
      (summary.excluded ? ` · ${summary.excluded} excluded` : ""),
  );
  text("metric-range", `range ${formatMetric(rawMin)} — ${formatMetric(rawMax)}`);
}

function renderEvidence(data) {
  const panel = document.getElementById("evidence-panel");
  const records = Array.isArray(data?.records) ? data.records : [];
  const metricPanels = Array.isArray(data?.panels) ? data.panels : [];
  const constraints = Array.isArray(data?.constraints) ? data.constraints : [];
  panel.hidden = records.length === 0;
  text(
    "evidence-count",
    `${records.length} visual ${records.length === 1 ? "record" : "records"} / ` +
      `${Number(data?.artifact_count || 0)} images`,
  );
  if (!records.length) return;

  const gates = document.getElementById("evidence-gates");
  gates.innerHTML = constraints.length
    ? constraints.map((constraint) =>
      `<span class="evidence-gate"><strong>${esc(constraint.label || constraint.column)}</strong> ` +
      `${esc(constraint.column)} ${esc(constraint.op)} ${esc(formatMetric(constraint.value))}</span>`
    ).join("")
    : '<span class="evidence-axis"><strong>No eligibility gates</strong></span>';
  gates.insertAdjacentHTML(
    "beforeend",
    `<span class="evidence-axis"><strong>${metricPanels.length}</strong> configured metrics</span>`,
  );

  const gallery = document.getElementById("evidence-gallery");
  gallery.innerHTML = records.map((record) => {
    const dimensions = Object.entries(record.dimensions || {});
    const failures = Array.isArray(record.constraint_failures)
      ? record.constraint_failures
      : [];
    const artifact = (record.artifacts || [])[0];
    const metricRows = metricPanels
      .filter((metric) => record.metrics?.[metric.column] != null)
      .map((metric) =>
        `<div><dt title="${esc(metric.label)}">${esc(metric.label)}</dt>` +
        `<dd>${esc(formatMetric(record.metrics[metric.column]))}</dd></div>`
      ).join("");
    return `<article class="evidence-record ${record.eligible ? "is-eligible" : "is-excluded"}">` +
      (artifact
        ? `<a class="evidence-artifact" href="${esc(artifact.url)}" target="_blank" rel="noopener" ` +
          `aria-label="Open ${esc(record.name)} image at full resolution">` +
          `<img src="${esc(artifact.url)}" loading="lazy" alt="${esc(record.name)} visual result"></a>`
        : "") +
      `<div class="evidence-record-body"><div class="evidence-record-head">` +
      `<strong title="${esc(record.run_id)}">${esc(record.name || compactRunId(record.run_id))}</strong>` +
      `<span class="evidence-validity">${record.eligible ? "eligible" : "excluded"}</span></div>` +
      `<div class="evidence-dimensions">` +
      dimensions.map(([key, value]) => `<span>${esc(key)}=<strong>${esc(value)}</strong></span>`).join("") +
      `</div><dl class="evidence-metrics">${metricRows}</dl>` +
      (failures.length
        ? `<p class="evidence-failure">${failures.map(esc).join(" · ")}</p>`
        : "") +
      `</div></article>`;
  }).join("");
}

function renderPapers(papers) {
  const records = Array.isArray(papers) ? papers : [];
  const element = document.getElementById("papers");
  text("paper-count", `${records.length} ${records.length === 1 ? "record" : "records"}`);

  if (!records.length) {
    element.innerHTML = '<div class="empty-state">No cleared papers</div>';
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
    element.innerHTML = '<div class="empty-state">No agent events</div>';
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
    ["/api/evidence", renderEvidence],
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
    await Promise.all([refreshPortfolio(), refreshObserver()]);
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
        `${info.lab_id} connected · not executed`,
        "success",
      );
      window.location.hash = "steer";
      await Promise.all([refreshPortfolio(), refreshObserver()]);
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
          ? "Direction recorded · next agent pass"
          : "Direction recorded · read on start",
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
  text("runtime-dialog-title", starting ? "Start lab?" : "Stop lab?");
  text(
    "runtime-dialog-copy",
    starting
      ? "Repository commands · local compute · configured LLM budget"
      : "Stop after current process · preserve written evidence",
  );
  text(
    "runtime-confirm-label",
    starting
      ? "Authorize this local run."
      : "Authorize this stop request.",
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

function initPanelToggles() {
  document.querySelectorAll("[data-panel-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = button.closest(".panel");
      const collapsed = panel.classList.toggle("collapsed");
      button.setAttribute("aria-expanded", String(!collapsed));
      button.textContent = collapsed ? "Show" : "Hide";
    });
  });
}

function initNetworkScope() {
  document.querySelectorAll("[data-network-scope]").forEach((button) => {
    button.addEventListener("click", () => {
      networkScope = button.dataset.networkScope;
      renderNetwork();
    });
  });
}

initTheme();
initRouting();
initPanelToggles();
initNetworkScope();
initConnectForm();
initSteeringForm();
initRuntimeControls();
refresh();
setInterval(refresh, 4000);
