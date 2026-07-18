async function getJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json();
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
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, compact ? 16 : 19);
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

function renderState(state) {
  text("lab-id", state.lab_id || "unnamed-lab");
  text("domain", state.domain || "unclassified");

  const status = String(state.status || "stopped").toLowerCase();
  const badge = document.getElementById("status-badge");
  badge.className = `status-badge ${status}`;
  text("status-text", status);

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

async function renderFrom(path, renderer) {
  renderer(await getJSON(path));
}

async function tick() {
  const results = await Promise.allSettled([
    renderFrom("/api/state", renderState),
    renderFrom("/api/runs", renderRuns),
    renderFrom("/api/papers", renderPapers),
    renderFrom("/api/activity", renderActivity),
  ]);
  const errors = results.filter((result) => result.status === "rejected");
  errors.forEach((error) => console.error(error.reason));
  text("last-sync", `${new Date().toISOString().slice(0, 19).replace("T", " ")} UTC`);
}

tick();
setInterval(tick, 4000);
