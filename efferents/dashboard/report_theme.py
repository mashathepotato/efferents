"""Shared visual system for self-contained offline research reports."""

REPORT_CSS = r"""
:root {
  color-scheme: light;
  --bg: #ffffff;
  --panel: #ffffff;
  --raised: #ffffff;
  --line: #03befc;
  --line-soft: #03befc;
  --fg: #003b80;
  --muted: #003b80;
  --dim: #03befc;
  --signal: #03befc;
  --signal-strong: #003b80;
  --on-signal: #003b80;
  --cyan: #03befc;
  --mono: "SFMono-Regular", Menlo, Monaco, "Cascadia Mono", "Liberation Mono", monospace;
  --display: "American Typewriter", "Rockwell Nova", Rockwell, "Courier New", monospace;
  --sans: var(--display);
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  min-width: 320px;
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 14px/1.55 var(--sans);
  font-variant-numeric: tabular-nums;
}
header {
  padding: 30px clamp(20px,4vw,56px);
  border-bottom: 1px solid var(--line);
  background: var(--bg);
}
header::before {
  display: block;
  margin-bottom: 8px;
  color: var(--signal);
  content: "efferents / research record";
  font: 9px/1 var(--mono);
  letter-spacing: .12em;
}
h1 {
  max-width: 1060px;
  margin: 0 0 7px;
  font-size: clamp(24px,3vw,40px);
  font-weight: 700;
  letter-spacing: -.04em;
  line-height: 1.08;
}
.muted { color: var(--muted); }
.small { font: 10px/1.5 var(--mono); letter-spacing: .035em; text-transform: uppercase; }
code {
  padding: 1px 4px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--signal);
  font: 11px/1.4 var(--mono);
}
main {
  width: min(1180px,100%);
  margin: 0 auto;
  padding: 26px clamp(16px,3vw,36px) 60px;
}
.banner {
  position: relative;
  margin-bottom: 14px;
  padding: 13px 16px 13px 142px;
  border: 1px solid var(--line);
  border-radius: 0;
  background: var(--panel);
  color: var(--muted);
  font: 10px/1.55 var(--mono);
}
.banner::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  display: grid;
  width: 122px;
  place-items: center;
  border-right: 1px solid var(--line);
  color: var(--dim);
  content: "DATA SOURCE";
  font-size: 8px;
  letter-spacing: .12em;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit,minmax(200px,1fr));
  gap: 1px;
  margin: 14px 0 34px !important;
  padding: 1px;
  background: var(--line);
}
.card {
  min-width: 0;
  padding: 17px 18px 20px;
  border: 0;
  border-radius: 0;
  background: var(--panel);
}
.card .k {
  margin-bottom: 12px;
  color: var(--dim);
  font: 8px/1 var(--mono);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.card .v {
  margin-top: 0;
  color: var(--fg);
  font: 700 clamp(24px,3vw,42px)/1 var(--mono);
  letter-spacing: -.055em;
  overflow-wrap: anywhere;
}
.card .v.ok,
.v.ok { color: var(--signal); }
.section { margin: 32px 0; }
.section h2 {
  display: grid;
  grid-template-columns: 34px minmax(0,1fr);
  align-items: center;
  min-height: 38px;
  margin: 0 0 14px;
  padding: 0;
  border: 1px solid var(--line);
  color: var(--fg);
  font: 650 10px/1 var(--mono);
  letter-spacing: .09em;
  text-transform: uppercase;
}
.section h2::before {
  display: grid;
  align-self: stretch;
  place-items: center;
  border-right: 1px solid var(--line);
  color: var(--dim);
  content: "·";
}
.section > p {
  max-width: 920px;
  margin: 20px 14px;
  color: var(--muted);
  font-size: clamp(16px,1.7vw,21px);
  line-height: 1.55;
}
.bar-row {
  display: grid;
  grid-template-columns: 64px minmax(12px,1fr) 92px;
  align-items: center;
  gap: 12px;
  margin: 8px 14px;
}
.coef {
  width: auto;
  color: var(--muted);
  font: 10px/1 var(--mono);
  text-align: right;
}
.bar {
  height: 10px;
  border-radius: 0;
  background: var(--cyan);
}
.val {
  color: var(--muted);
  font: 10px/1 var(--mono);
}
.val.best {
  color: var(--signal);
  font-weight: 700;
}
table {
  width: 100%;
  border-collapse: collapse;
  font: 10px/1.45 var(--mono);
}
th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line-soft);
  text-align: left;
  white-space: nowrap;
}
th {
  color: var(--on-signal);
  background: var(--signal);
  font-size: 8px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}
td { color: var(--muted); }
tr.best {
  background: var(--panel);
  box-shadow: inset 2px 0 0 var(--signal);
}
tr.best td { background: transparent; }
.memos {
  display: grid;
  grid-template-columns: repeat(2,minmax(0,1fr));
  gap: 1px;
  background: var(--line);
}
.memos h2 {
  grid-column: 1 / -1;
  margin-bottom: 0;
  background: var(--bg);
}
.memos a {
  display: block;
  padding: 14px 16px;
  background: var(--panel);
  color: var(--cyan);
  font: 11px/1.35 var(--mono);
  text-decoration: none;
}
.memos a:hover {
  background: var(--signal);
  color: var(--on-signal);
}
@media (max-width: 660px) {
  .banner { padding: 48px 13px 13px; }
  .banner::before { top: 0; right: 0; bottom: auto; width: auto; height: 34px;
                    border-right: 0; border-bottom: 1px solid var(--line); }
  .section { overflow-x: auto; }
  table { min-width: 700px; }
  .memos { grid-template-columns: 1fr; }
}
""".strip()
