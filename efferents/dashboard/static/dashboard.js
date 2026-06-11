async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function text(id, value) {
  document.getElementById(id).textContent = value == null ? "" : String(value);
}

function renderState(s) {
  text("lab-id", s.lab_id);
  text("domain", "· " + s.domain);
  const badge = document.getElementById("status-badge");
  badge.textContent = s.status;
  badge.className = "badge " + s.status;
  text("budget", `budget $${(s.budget.spent).toFixed(2)} / $${s.budget.cap}`);
  text("student", s.hypothesis.student ? "· " + s.hypothesis.student : "");
  text("question", s.hypothesis.question || "(no open campaign)");
  text("claim", s.hypothesis.claim);
  text("falsifier", s.hypothesis.falsifier);
}

function renderRuns(d) {
  text("metric-label", `${d.headline.column} (${d.headline.direction})`);
  const tbody = document.querySelector("#runs tbody");
  tbody.innerHTML = "";
  d.runs.forEach(r => {
    const tr = document.createElement("tr");
    const v = r.value == null ? "—" : r.value;
    tr.innerHTML = `<td>${esc((r.run_id || "").slice(0, 6))}</td>` +
                   `<td class="muted">${esc(r.started_at || "")}</td><td>${esc(v)}</td>`;
    tbody.appendChild(tr);
  });
  renderTrend(d.series, d.headline.direction);
}

function renderTrend(series, direction) {
  const svg = document.getElementById("trend");
  svg.innerHTML = "";
  if (!series.length) { text("trend-caption", ""); return; }
  const vals = series.map(p => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const coords = (p, i) => {
    const x = series.length === 1 ? 50 : (i / (series.length - 1)) * 100;
    const y = 40 - ((p.value - min) / span) * 38 - 1;
    return [x, y];
  };
  if (series.length === 1) {
    const [x, y] = coords(series[0], 0);
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y.toFixed(1));
    c.setAttribute("r", "1.5");
    c.setAttribute("fill", "#4a9");
    svg.appendChild(c);
  } else {
    const pts = series.map((p, i) => coords(p, i).map(n => n.toFixed(1)).join(",")).join(" ");
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    poly.setAttribute("points", pts);
    svg.appendChild(poly);
  }
  const best = direction === "max" ? Math.max(...vals) : Math.min(...vals);
  text("trend-caption", `${series.length} runs · best ${best}`);
}

function renderPapers(papers) {
  const el = document.getElementById("papers");
  if (!papers.length) { el.innerHTML = '<div class="muted small">no papers yet</div>'; return; }
  el.innerHTML = papers.map(p =>
    `<div class="paper"><div><b>${esc(p.title)}</b></div>` +
    `<div class="muted small">${esc(p.status)} · ${esc(p.published_at)}</div></div>`).join("");
}

function renderActivity(acts) {
  const el = document.getElementById("activity");
  el.innerHTML = acts.map(a =>
    `<div class="act"><span class="when">${esc(a.timestamp)}</span> — ${esc(a.title)}</div>`
  ).join("") || '<div class="muted small">no activity yet</div>';
}

async function renderFrom(path, fn) {
  try { fn(await getJSON(path)); }
  catch (e) { console.error(e); }
}

async function tick() {
  await Promise.allSettled([
    renderFrom("/api/state", renderState),
    renderFrom("/api/runs", renderRuns),
    renderFrom("/api/papers", renderPapers),
    renderFrom("/api/activity", renderActivity),
  ]);
}

tick();
setInterval(tick, 4000);
