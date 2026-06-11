async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

function text(id, value) { document.getElementById(id).textContent = value || ""; }

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
    tr.innerHTML = `<td>${(r.run_id || "").slice(0, 6)}</td>` +
                   `<td class="muted">${r.started_at || ""}</td><td>${v}</td>`;
    tbody.appendChild(tr);
  });
  renderTrend(d.series);
}

function renderTrend(series) {
  const svg = document.getElementById("trend");
  svg.innerHTML = "";
  if (!series.length) return;
  const vals = series.map(p => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const pts = series.map((p, i) => {
    const x = series.length === 1 ? 0 : (i / (series.length - 1)) * 100;
    const y = 40 - ((p.value - min) / span) * 38 - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("points", pts);
  svg.appendChild(poly);
  const best = Math.min(...vals);
  text("trend-caption", `${series.length} runs · best ${best}`);
}

function renderPapers(papers) {
  const el = document.getElementById("papers");
  if (!papers.length) { el.innerHTML = '<div class="muted small">no papers yet</div>'; return; }
  el.innerHTML = papers.map(p =>
    `<div class="paper"><div><b>${p.title}</b></div>` +
    `<div class="muted small">${p.status} · ${p.published_at}</div></div>`).join("");
}

function renderActivity(acts) {
  const el = document.getElementById("activity");
  el.innerHTML = acts.map(a =>
    `<div class="act"><span class="when">${a.timestamp}</span> — ${a.title}</div>`
  ).join("") || '<div class="muted small">no activity yet</div>';
}

async function tick() {
  try {
    renderState(await getJSON("/api/state"));
    renderRuns(await getJSON("/api/runs"));
    renderPapers(await getJSON("/api/papers"));
    renderActivity(await getJSON("/api/activity"));
  } catch (e) {
    console.error(e);
  }
}

tick();
setInterval(tick, 4000);
