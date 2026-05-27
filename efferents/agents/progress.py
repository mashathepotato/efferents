"""Self-contained progress dashboard at lab/progress.html.

One file. Open in a browser, AirDrop to phone, scp anywhere — all embedded
(matplotlib charts as base64 PNG, sample images as base64 PNG, no external
deps at view time).

Layout:
- Two-way conversation panel: context/research_log.md tail + lab/lab_notebook.md tail
  side-by-side, so the user can see what they told the orchestrator and what it
  said back.
- Trend chart: best W1 per campaign (or per run when no campaigns yet).
- Campaigns: per-campaign cards with hypothesis, status, best sample inline.
- Architectures: runs grouped by git_commit (each Coder commit = an architectural
  variant). Card per variant with commit message + best sample; click to expand
  the full run list for that architecture.
- Galleries: best-surviving samples + recent scored runs. Each tile clickable to
  reveal full per-run metadata.

Hook: agents/analyst.py:write_digest calls write_progress on every digest.
On-demand: `python -m agents progress-now`.

Resilient to:
- Pre-migration DBs (no campaigns table) — fallback to flat view.
- Missing sample PNGs — gracefully skipped.
- Runs without e_w1 — excluded from trend / best-of computations.
- Git commits no longer resolvable — shown by SHA only.
"""
from __future__ import annotations

import base64
import html as _html
import io
import re as _re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

from efferents.agents.state import LabPaths  # noqa: E402
from efferents import lab as _lab  # noqa: E402


_MAX_RECENT_SAMPLES = 9
_MAX_BEST_SAMPLES = 6
_MAX_ARCHITECTURES = 12
_MAX_RUNS_PER_ARCH = 6

def _panel_metrics() -> list[tuple[str, str, float | None]]:
    """Return per-lab panel definitions from the active LabConfig.

    Each entry is (column_name, axis_label, target_value | None).
    target_value=None means lower-is-better; a numeric target draws a
    horizontal reference line and selects the nearest-to-target row as best.
    """
    cfg = _lab.get_config()
    return [(p.column, p.label, p.target) for p in cfg.metrics.panels]


def _headline_metric() -> tuple[str, str]:
    """Return (column, direction) for the lab's headline metric."""
    h = _lab.get_config().metrics.headline
    return (h.column, h.direction)


def _metric_best(rows: list[dict], col: str, target: float | None):
    """Return (value, row) for the best row in `rows` by metric `col`.

    Lower-is-better when target is None; closest-to-target otherwise.
    Returns (None, None) if no row has a value for that metric.
    """
    have = [r for r in rows if r.get(col) is not None]
    if not have:
        return None, None
    if target is None:
        r = min(have, key=lambda r: r[col])
    else:
        r = min(have, key=lambda r: abs(r[col] - target))
    return r[col], r


def write_progress(paths: LabPaths, context_dir: Path | str = "context") -> Path:
    """Render lab/progress.html. Idempotent — full rewrite. Returns the path."""
    out_path = paths.root / "progress.html"
    snap = _snapshot(paths)
    html = _render_html(snap, paths=paths, context_dir=Path(context_dir))
    out_path.write_text(html)
    return out_path


# ---------- snapshot ----------


def _snapshot(paths: LabPaths) -> dict[str, Any]:
    if not paths.runs_db.exists():
        return {"runs": [], "campaigns": [], "has_campaigns_table": False}
    conn = sqlite3.connect(paths.runs_db)
    conn.row_factory = sqlite3.Row
    try:
        # Pick column list based on what's actually in the schema — survives
        # both pre-migration DBs and any future column drift.
        wanted = [
            "run_id", "started_at", "model", "eval_kind", "raw_q", "epochs",
            "aug_depth", "seed", "e_w1", "val_x0_mse", "gen_max_to_real_max",
            "active_frac_w1", "radial_l2_log", "samples_png", "git_commit",
            "config_hash", "notes", "campaign_id", "researcher_mode",
        ]
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        cols = [c for c in wanted if c in existing]
        runs = [
            dict(r)
            for r in conn.execute(
                f"SELECT {','.join(cols)} FROM runs ORDER BY started_at ASC"
            ).fetchall()
        ]
        try:
            campaigns = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, lab_id, question, hypothesis_path, hypothesis_hash,"
                    " opened_at, closed_at, close_reason"
                    " FROM campaigns ORDER BY opened_at ASC"
                ).fetchall()
            ]
            has_campaigns = True
        except sqlite3.OperationalError:
            campaigns = []
            has_campaigns = False
    finally:
        conn.close()
    return {"runs": runs, "campaigns": campaigns, "has_campaigns_table": has_campaigns}


def _resolve_commit_metadata(sha: str, cache: dict[str, dict]) -> dict:
    """Look up commit subject + ISO date for a short or long SHA. Cached.

    Returns {"sha": short, "subject": str, "date": iso, "author": str}. On lookup
    failure (commit GC'd, wrong repo, no git binary) returns a stub with sha only.
    """
    if sha in cache:
        return cache[sha]
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%h%x09%ai%x09%an%x09%s", sha],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        short, date, author, subject = out.split("\t", 3)
        result = {"sha": short, "date": date, "author": author, "subject": subject}
    except (subprocess.SubprocessError, ValueError, OSError):
        result = {"sha": sha, "date": "", "author": "", "subject": "(commit not resolvable)"}
    cache[sha] = result
    return result


def _group_runs_by_commit(runs: list[dict]) -> dict[str, list[dict]]:
    """Bucket runs by git_commit (None bucket dropped)."""
    out: dict[str, list[dict]] = {}
    for r in runs:
        sha = r.get("git_commit")
        if sha:
            out.setdefault(sha, []).append(r)
    return out


def _scored_sample_runs(runs: list[dict]) -> list[dict]:
    """Filter to sample-eval rows with e_w1 set.

    `eval_kind` distinguishes single-step recon from full DDPM sampling.
    Their `e_w1` values aren't comparable, so we restrict trend / best-of
    displays to sample-evals only.
    """
    return [
        r for r in runs
        if r.get("e_w1") is not None and r.get("eval_kind") == "sample"
    ]


def _best_run_in(runs: list[dict]) -> dict | None:
    scored = _scored_sample_runs(runs)
    if not scored:
        return None
    return min(scored, key=lambda r: r["e_w1"])


def _group_runs_by_campaign(runs: list[dict]) -> dict[str | None, list[dict]]:
    out: dict[str | None, list[dict]] = {}
    for r in runs:
        out.setdefault(r.get("campaign_id"), []).append(r)
    return out


def _campaign_status(c: dict) -> tuple[str, str]:
    """Return (label, css_class)."""
    if c.get("closed_at") is None:
        return ("open", "open")
    reason = c.get("close_reason") or "closed"
    css = {
        "stale": "stale",
        "resolved": "resolved",
        "no novel publishable result": "no-novel",
    }.get(reason, "closed")
    return (reason, css)


# ---------- chart ----------


_STATUS_COLORS = {
    "open": "#1f77b4",
    "resolved": "#2ca02c",
    "stale": "#7f7f7f",
    "no-novel": "#d62728",
    "closed": "#9467bd",
    "uncampaigned": "#999999",
}


def _trend_png_b64(snap: dict) -> str | None:
    """Render a 2x2 small-multiples trend chart (one panel per metric).

    Each panel: x = campaign opened-at order (or recent-run order when no
    campaigns exist), y = best value of that metric across the units on the
    x-axis. W1 alone is a thin signal; the other panels expose pathologies
    (gen_max=0 → all-zero collapse; flat radial_l2 → wrong physics).
    """
    campaigns = snap["campaigns"]
    by_c = _group_runs_by_campaign(snap["runs"])

    # Build the row-set for each x position. Each position is (label, status, rows).
    positions: list[tuple[str, str, list[dict]]] = []
    if campaigns:
        for c in campaigns:
            _, css = _campaign_status(c)
            rows = _scored_sample_runs(by_c.get(c["id"], []))
            if rows:
                positions.append((c["id"][:10], css, rows))
    else:
        # Pre-campaigns fallback: each scored sample-eval run is its own position
        scored = _scored_sample_runs(snap["runs"])[-60:]
        if not scored:
            return None
        for i, r in enumerate(scored):
            positions.append((f"r{i}", "uncampaigned", [r]))

    if not positions:
        return None

    fig, axes = plt.subplots(2, 2, figsize=(13, 7), dpi=110)
    axes = axes.flatten()

    n_panels_with_data = 0
    for ax, (col, label, target) in zip(axes, _panel_metrics()):
        xs, ys, cs = [], [], []
        for i, (xlabel, css, rows) in enumerate(positions):
            val, _ = _metric_best(rows, col, target)
            if val is None:
                continue
            xs.append(i)
            ys.append(val)
            cs.append(_STATUS_COLORS.get(css, "#333333"))
        if not xs:
            ax.text(0.5, 0.5, f"no data for {col}", ha="center", va="center",
                    transform=ax.transAxes, color="#999", fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(label, fontsize=10)
            continue
        n_panels_with_data += 1
        ax.plot(xs, ys, color="#cccccc", linewidth=1, zorder=1)
        ax.scatter(xs, ys, c=cs, s=40, zorder=2, edgecolor="white", linewidth=0.8)
        if target is not None:
            ax.axhline(target, color="#ff8c00", linestyle="--", linewidth=1,
                       alpha=0.6, zorder=0)
        ax.set_title(label, fontsize=10)
        # Tick labels on the bottom-row panels only (so labels don't fight each other)
        ax.set_xticks(list(range(len(positions))))
        ax.set_xticklabels(
            [p[0] for p in positions], rotation=45, ha="right", fontsize=7
        )
        ax.grid(True, alpha=0.3)

    if n_panels_with_data == 0:
        plt.close(fig)
        return None

    fig.suptitle(
        f"Trend per metric — {'best per campaign' if campaigns else 'recent runs (no campaigns yet)'}",
        fontsize=12,
    )
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- samples ----------


def _sample_b64(samples_png: str | None, repo_root: Path) -> str | None:
    if not samples_png:
        return None
    p = (repo_root / samples_png).resolve()
    if not p.exists():
        return None
    try:
        return base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError:
        return None


# ---------- html ----------


_CSS = """
body { font-family: -apple-system, system-ui, sans-serif; max-width: 1200px;
       margin: 24px auto; padding: 0 16px; color: #222; }
h1 { margin-bottom: 4px; }
.meta { color: #666; font-size: 14px; margin-bottom: 24px; }
.trend img { max-width: 100%; border: 1px solid #eee; border-radius: 6px; }

/* Campaign card */
.card { border: 1px solid #ddd; border-radius: 8px; padding: 16px;
        margin: 16px 0; display: grid; grid-template-columns: 1fr 280px;
        gap: 16px; align-items: start; }
.card-text h3 { margin: 0 0 6px 0; font-size: 16px; }
.card-text .q { color: #444; margin-bottom: 8px; }
.card-text .meta-row { font-family: ui-monospace, monospace; font-size: 12px;
                       color: #555; }
.card img { width: 100%; border-radius: 4px; border: 1px solid #eee; }
.status { display: inline-block; padding: 2px 8px; border-radius: 4px;
          font-size: 11px; font-weight: 600; text-transform: uppercase;
          letter-spacing: 0.5px; }
.status-open { background: #e0f0ff; color: #1f6fc4; }
.status-resolved { background: #e6f7e6; color: #1f8a3a; }
.status-stale { background: #eee; color: #666; }
.status-no-novel { background: #fde7e7; color: #c44; }
.status-closed { background: #f0e6f9; color: #693f9c; }

/* Architecture card (collapsible) */
.arch { border: 1px solid #ddd; border-radius: 8px; margin: 12px 0;
        background: #fff; }
.arch summary { padding: 10px 16px; cursor: pointer; display: grid;
                grid-template-columns: 72px 90px 1fr 140px 100px 16px;
                gap: 12px; align-items: center; list-style: none; }
.arch summary::-webkit-details-marker { display: none; }
.arch summary .marker { color: #999; transition: transform .15s;
                        text-align: center; font-size: 12px; }
.arch[open] summary .marker { transform: rotate(180deg); }
.arch summary:hover { background: #f5f5f5; }
.arch[open] summary { border-bottom: 1px solid #eee; }
.arch .arch-thumb { width: 64px; height: 64px; object-fit: cover;
                    border-radius: 4px; border: 1px solid #eee; }
.arch .arch-thumb-empty { width: 64px; height: 64px; border-radius: 4px;
                          border: 1px dashed #ddd; color: #bbb; font-size: 10px;
                          display: flex; align-items: center; justify-content: center;
                          text-align: center; padding: 4px; box-sizing: border-box; }
.arch .arch-sha { font-family: ui-monospace, monospace; font-size: 12px;
                  color: #693f9c; font-weight: 600; }
.arch .arch-subject { font-size: 14px; color: #222; }
.arch .arch-date { font-size: 11px; color: #999; font-family: ui-monospace, monospace; }
.arch .arch-stats { font-size: 11px; color: #555; text-align: right;
                    font-family: ui-monospace, monospace; }
.arch-body { padding: 12px 16px 16px 16px; }
.arch-stats-block { font-size: 12px; color: #555;
                    font-family: ui-monospace, monospace; line-height: 1.6;
                    margin-bottom: 12px; padding: 8px 12px;
                    background: #fafafa; border-radius: 4px;
                    border-left: 3px solid #693f9c; }

/* Galleries */
.section-h { margin-top: 32px; padding-bottom: 4px; border-bottom: 1px solid #eee; }
.runs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
             gap: 12px; margin-top: 12px; }
.run-tile { margin: 0; border: 1px solid #eee; border-radius: 6px;
            background: #fff; overflow: hidden; }
.run-tile > summary { list-style: none; cursor: pointer; }
.run-tile > summary::-webkit-details-marker { display: none; }
.run-tile img { width: 100%; display: block; }
.run-tile .cap { padding: 6px 8px; font-size: 11px; color: #666;
                 font-family: ui-monospace, monospace; }
.run-tile[open] > summary .cap { color: #1f6fc4; }
.run-detail { padding: 8px 12px 12px 12px; border-top: 1px solid #eee;
              font-size: 11px; color: #444;
              font-family: ui-monospace, monospace; line-height: 1.5;
              background: #fafafa; }
.run-detail .kv { display: grid; grid-template-columns: 110px 1fr; gap: 4px; }
.run-detail .kv .k { color: #999; }
.run-detail .commit-msg { margin-top: 6px; padding-top: 6px;
                          border-top: 1px dashed #ddd; color: #693f9c; }

.empty { color: #999; font-style: italic; padding: 24px;
         text-align: center; border: 1px dashed #ddd; border-radius: 6px; }

/* Lightbox (CSS-only, :target-driven). Click thumbnail to enlarge; click
   backdrop or × to dismiss. <a> inside <summary> navigates without
   toggling the parent <details> in modern browsers. */
.thumb-link { display: block; cursor: zoom-in; }
.lightbox { display: none; }
.lightbox:target {
  display: flex;
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.92);
  z-index: 9999;
  align-items: center; justify-content: center;
  padding: 32px;
}
.lightbox-backdrop {
  position: absolute; inset: 0;
  cursor: zoom-out;
}
.lightbox-img {
  max-width: 95vw; max-height: 90vh;
  position: relative; z-index: 1;
  border-radius: 6px;
  box-shadow: 0 4px 40px rgba(0, 0, 0, 0.6);
  image-rendering: pixelated;  /* keep low-res samples crisp when scaled up */
}
.lightbox-caption {
  position: absolute; bottom: 24px; left: 50%;
  transform: translateX(-50%);
  color: white; font-family: ui-monospace, monospace; font-size: 12px;
  background: rgba(0, 0, 0, 0.55); padding: 6px 14px; border-radius: 4px;
  z-index: 2; max-width: 90vw; text-align: center;
}
.lightbox-close {
  position: absolute; top: 16px; right: 24px;
  color: white; text-decoration: none;
  font-size: 32px; line-height: 1;
  z-index: 2; padding: 4px 14px;
  background: rgba(0, 0, 0, 0.4); border-radius: 4px;
}
.lightbox-close:hover { background: rgba(0, 0, 0, 0.7); }
""".strip()


def _esc(s: Any) -> str:
    return _html.escape(str(s)) if s is not None else ""


def _fmt_w1(v: float | None) -> str:
    return f"{v:.4f}" if isinstance(v, (int, float)) else "—"


def _render_card(c: dict, best: dict | None, sample_b64: str | None) -> str:
    label, css = _campaign_status(c)
    img_html = (
        f'<img src="data:image/png;base64,{sample_b64}" alt="best sample">'
        if sample_b64
        else '<div class="empty">no sample for best run</div>'
    )
    if best:
        meta = (
            f"<div class=\"meta-row\">"
            f"best W1: {_fmt_w1(best.get('e_w1'))} &nbsp;|&nbsp; "
            f"model: {_esc(best.get('model'))} &nbsp;|&nbsp; "
            f"raw_q: {_esc(best.get('raw_q'))} &nbsp;|&nbsp; "
            f"aug_depth: {_esc(best.get('aug_depth'))} &nbsp;|&nbsp; "
            f"epochs: {_esc(best.get('epochs'))} &nbsp;|&nbsp; "
            f"seed: {_esc(best.get('seed'))}"
            f"</div>"
        )
    else:
        meta = '<div class="meta-row">no scored runs yet</div>'

    return f"""<section class="card">
  <div class="card-text">
    <h3><span class="status status-{css}">{_esc(label)}</span> &nbsp; {_esc(c.get('id'))}</h3>
    <p class="q">{_esc(c.get('question'))}</p>
    {meta}
    <div class="meta-row">hypothesis: <code>{_esc(c.get('hypothesis_hash', '')[:22])}...</code> &middot;
       <a href="{_esc(c.get('hypothesis_path'))}">{_esc(c.get('hypothesis_path'))}</a></div>
    <div class="meta-row">opened: {_esc(c.get('opened_at', '')[:19])}
       {' &middot; closed: ' + _esc(c.get('closed_at', '')[:19]) if c.get('closed_at') else ''}</div>
  </div>
  <div class="card-image">{img_html}</div>
</section>"""


def _zoom_id(run_id: str | None) -> str:
    """Stable, fragment-safe id for the lightbox of a given run."""
    safe = _re.sub(r"[^a-zA-Z0-9]+", "-", run_id or "").strip("-")
    return f"zoom-{safe}" if safe else "zoom-anon"


def _render_run_tile(
    r: dict, repo_root: Path, commit_cache: dict, lightboxes: list[tuple[str, str, str]]
) -> str | None:
    """One clickable sample tile. <details> expands to show full per-run metadata.
    The image itself is wrapped in <a href="#zoom-..."> so clicking opens the
    lightbox (which appends to `lightboxes` for end-of-page rendering); clicking
    outside the image still toggles the metadata <details>.

    Returns None if the run has no resolvable sample PNG.
    """
    b64 = _sample_b64(r.get("samples_png"), repo_root)
    if b64 is None:
        return None
    sha = r.get("git_commit")
    commit = _resolve_commit_metadata(sha, commit_cache) if sha else None
    cap = (
        f"W1={_fmt_w1(r.get('e_w1'))} &middot; "
        f"{_esc(r.get('model'))}/raw{_esc(r.get('raw_q'))}/"
        f"seed{_esc(r.get('seed'))}"
    )
    zid = _zoom_id(r.get("run_id"))
    lightboxes.append((zid, b64, cap))
    kv_rows = [
        ("run_id", r.get("run_id", "")[:48]),
        ("started", str(r.get("started_at", ""))[:19]),
        ("model", r.get("model", "")),
        ("eval_kind", r.get("eval_kind", "")),
        ("raw_q", r.get("raw_q")),
        ("epochs", r.get("epochs")),
        ("aug_depth", r.get("aug_depth")),
        ("seed", r.get("seed")),
        ("e_w1", _fmt_w1(r.get("e_w1"))),
        ("val_x0_mse", _fmt_w1(r.get("val_x0_mse"))),
        ("gen_max/real", _fmt_w1(r.get("gen_max_to_real_max"))),
        ("active_frac_w1", _fmt_w1(r.get("active_frac_w1"))),
        ("radial_l2_log", _fmt_w1(r.get("radial_l2_log"))),
        ("config_hash", r.get("config_hash", "")[:12]),
        ("campaign_id", r.get("campaign_id") or "—"),
        ("researcher_mode", r.get("researcher_mode") or "—"),
        ("git_commit", commit["sha"] if commit else "—"),
    ]
    kv_html = "".join(
        f'<div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div>'
        for k, v in kv_rows
    )
    commit_block = ""
    if commit and commit.get("subject"):
        commit_block = (
            f'<div class="commit-msg">commit {_esc(commit["sha"])}: '
            f'{_esc(commit["subject"])}'
            + (f' &middot; {_esc(commit["date"][:10])}' if commit.get("date") else "")
            + "</div>"
        )
    return (
        f'<details class="run-tile"><summary>'
        f'<a class="thumb-link" href="#{zid}" aria-label="enlarge sample">'
        f'<img src="data:image/png;base64,{b64}" alt="run sample">'
        f'</a>'
        f'<div class="cap">{cap}</div>'
        f'</summary>'
        f'<div class="run-detail"><div class="kv">{kv_html}</div>{commit_block}</div>'
        f'</details>'
    )


def _render_runs_grid(
    runs: list[dict],
    repo_root: Path,
    title: str,
    commit_cache: dict,
    lightboxes: list[tuple[str, str, str]],
) -> str:
    tiles = []
    for r in runs:
        tile = _render_run_tile(r, repo_root, commit_cache, lightboxes)
        if tile is not None:
            tiles.append(tile)
    if not tiles:
        return ""
    return f'<h2 class="section-h">{_esc(title)}</h2><div class="runs-grid">{"".join(tiles)}</div>'


def _render_architectures(
    runs: list[dict],
    repo_root: Path,
    commit_cache: dict,
    lightboxes: list[tuple[str, str, str]],
) -> str:
    """One <details> card per git_commit. Headline = best sample for that commit.
    Inside the card: every run in that architectural slice, clickable."""
    by_commit = _group_runs_by_commit(runs)
    if not by_commit:
        return ""
    # Sort architectures by most-recent run, descending; cap at _MAX_ARCHITECTURES.
    sorted_shas = sorted(
        by_commit.keys(),
        key=lambda sha: max(r.get("started_at", "") for r in by_commit[sha]),
        reverse=True,
    )[:_MAX_ARCHITECTURES]

    cards = []
    for sha in sorted_shas:
        slice_runs = by_commit[sha]
        sample_runs = _scored_sample_runs(slice_runs)
        commit = _resolve_commit_metadata(sha, commit_cache)
        n_total = len(slice_runs)
        n_scored = len(sample_runs)
        if sample_runs:
            best = min(sample_runs, key=lambda r: r["e_w1"])
            best_w1 = f"best W1: {_fmt_w1(best['e_w1'])}"
            best_sample_b64 = _sample_b64(best.get("samples_png"), repo_root)
        else:
            best = None
            best_w1 = "no scored sample-evals"
            best_sample_b64 = None

        # Most-recent run date
        last = max(slice_runs, key=lambda r: r.get("started_at", ""))
        last_date = str(last.get("started_at", ""))[:10]

        # Thumbnail for the summary row — visible BEFORE expand so the user
        # picks which architecture to drill into by visual, not just SHA.
        thumb_html = (
            f'<img class="arch-thumb" src="data:image/png;base64,{best_sample_b64}" alt="best sample for this arch">'
            if best_sample_b64
            else '<div class="arch-thumb-empty">no surviving sample</div>'
        )

        # Stats block inside the expanded view (no separate headline image —
        # the inner-tiles grid below already shows the best sample as tile #1).
        if best:
            stat_block = (
                '<div class="arch-stats-block">'
                f'best W1: <strong>{_fmt_w1(best.get("e_w1"))}</strong> &middot; '
                f'model: {_esc(best.get("model"))} &middot; '
                f'raw_q: {_esc(best.get("raw_q"))} &middot; '
                f'aug_depth: {_esc(best.get("aug_depth"))} &middot; '
                f'epochs: {_esc(best.get("epochs"))} &middot; '
                f'seed: {_esc(best.get("seed"))}<br>'
                f'val_x0_mse: {_fmt_w1(best.get("val_x0_mse"))} &middot; '
                f'gen_max/real: {_fmt_w1(best.get("gen_max_to_real_max"))} &middot; '
                f'config_hash: {_esc(best.get("config_hash", "")[:12])}'
                '</div>'
            )
        else:
            stat_block = '<div class="arch-stats-block">no scored sample-evals under this architecture</div>'

        # Inner tiles: cap at _MAX_RUNS_PER_ARCH (lowest-W1 first); the rest are
        # available in the raw runs.sqlite for anyone who wants the long tail.
        inner_runs = sorted(sample_runs, key=lambda r: r["e_w1"])[:_MAX_RUNS_PER_ARCH]
        inner_tiles = [
            t for t in
            (_render_run_tile(r, repo_root, commit_cache, lightboxes) for r in inner_runs)
            if t is not None
        ]
        truncated_note = ""
        if len(sample_runs) > _MAX_RUNS_PER_ARCH:
            truncated_note = (
                f'<p style="font-size: 11px; color: #999; margin: 8px 0 0 0;">'
                f'showing top {len(inner_tiles)} of {len(sample_runs)} scored runs '
                f'(lowest W1 first)</p>'
            )
        inner_grid = (
            f'<div class="runs-grid">{"".join(inner_tiles)}</div>{truncated_note}'
            if inner_tiles
            else '<div class="empty">no surviving samples under this architecture</div>'
        )

        cards.append(
            f'<details class="arch">'
            f'<summary>'
            f'{thumb_html}'
            f'<span class="arch-sha">{_esc(commit["sha"])}</span>'
            f'<span class="arch-subject">{_esc(commit.get("subject", ""))}</span>'
            f'<span class="arch-date">{_esc(commit.get("date", "")[:10])}<br>'
            f'last: {_esc(last_date)}</span>'
            f'<span class="arch-stats">{n_scored}/{n_total} runs<br>{best_w1}</span>'
            f'<span class="marker">▾</span>'
            f'</summary>'
            f'<div class="arch-body">'
            f'{stat_block}'
            f'{inner_grid}'
            f'</div>'
            f'</details>'
        )

    return (
        '<h2 class="section-h">Architectures</h2>'
        '<p style="font-size: 12px; color: #666; margin: 4px 0 12px 0;">'
        'Each row groups all runs that share a git commit (i.e., an architectural '
        'variant produced by the Coder). Click to expand the full run set.'
        '</p>'
        + "".join(cards)
    )




def _render_lightboxes(boxes: list[tuple[str, str, str]]) -> str:
    """Emit one CSS-only lightbox <div> per (id, base64_png, caption).
    Hidden by default; shown via :target when an <a href="#id"> is clicked."""
    if not boxes:
        return ""
    # Deduplicate by zoom id — multiple tiles for the same run share one box.
    seen: set[str] = set()
    parts = []
    for zid, b64, cap in boxes:
        if zid in seen:
            continue
        seen.add(zid)
        parts.append(
            f'<div class="lightbox" id="{_esc(zid)}">'
            f'<a class="lightbox-backdrop" href="#" aria-label="close enlarged view"></a>'
            f'<img class="lightbox-img" src="data:image/png;base64,{b64}" alt="enlarged sample">'
            f'<div class="lightbox-caption">{cap}</div>'
            f'<a class="lightbox-close" href="#" aria-label="close">&times;</a>'
            f'</div>'
        )
    return "".join(parts)


def _render_html(snap: dict, *, paths: LabPaths, context_dir: Path) -> str:
    runs = snap["runs"]
    campaigns = snap["campaigns"]
    repo_root = Path.cwd()
    commit_cache: dict[str, dict] = {}
    lightboxes: list[tuple[str, str, str]] = []

    scored = _scored_sample_runs(runs)

    n_runs = len(runs)
    n_campaigns = len(campaigns)
    n_open = sum(1 for c in campaigns if c.get("closed_at") is None)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # "Best of each metric" stat row — replaces the single best-W1 stat.
    best_bits = []
    for col, label, target in _panel_metrics():
        val, _row = _metric_best(scored, col, target)
        if val is None:
            continue
        # Short label for the stat (strip the parenthetical hint)
        short = label.split(" (")[0]
        best_bits.append(f"<strong>{short}</strong>: {_fmt_w1(val)}")
    best_line = (" &middot; ".join(best_bits)) if best_bits else "no scored sample-evals yet"

    header = f"""
<h1>{_esc(_lab.LAB_ID)} — progress</h1>
<div class="meta">
  domain: <code>{_esc(_lab.DOMAIN)}</code> &middot;
  {n_runs} runs ({len(scored)} scored) &middot;
  {n_campaigns} campaigns ({n_open} open) &middot;
  updated {_esc(now)}
</div>
<div class="meta" style="margin-top: -16px;">best so far &middot; {best_line}</div>
""".strip()

    trend_b64 = _trend_png_b64(snap)
    trend_html = (
        f'<div class="trend"><img src="data:image/png;base64,{trend_b64}" alt="trend"></div>'
        if trend_b64
        else '<div class="empty">no scored runs yet — trend will appear after the first eval</div>'
    )

    by_c = _group_runs_by_campaign(runs)

    # Sort campaigns: open first (most recent opened_at), then closed (most recent closed_at)
    open_cs = sorted(
        (c for c in campaigns if c.get("closed_at") is None),
        key=lambda c: c.get("opened_at", ""),
        reverse=True,
    )
    closed_cs = sorted(
        (c for c in campaigns if c.get("closed_at") is not None),
        key=lambda c: c.get("closed_at", ""),
        reverse=True,
    )

    cards: list[str] = []
    for c in open_cs + closed_cs:
        best = _best_run_in(by_c.get(c["id"], []))
        sample_b64 = (
            _sample_b64(best.get("samples_png"), repo_root) if best else None
        )
        cards.append(_render_card(c, best, sample_b64))

    if cards:
        campaigns_block = (
            '<h2 class="section-h">Campaigns</h2>' + "\n".join(cards)
        )
    else:
        campaigns_block = (
            '<h2 class="section-h">Campaigns</h2>'
            '<div class="empty">no campaigns opened yet — the Researcher will open one '
            "on its next call (look for &lt;&lt;MODE: ...&gt;&gt; entries in lab_notebook.md)</div>"
        )

    # Architectures section — group runs by git_commit
    arch_block = _render_architectures(runs, repo_root, commit_cache, lightboxes)

    # Filter to runs whose sample PNGs still exist on disk (samples get pruned over time).
    with_samples = [
        r for r in scored
        if r.get("samples_png") and (repo_root / r["samples_png"]).exists()
    ]

    by_run_recent = list(reversed(with_samples))[:_MAX_RECENT_SAMPLES]
    recent_block = _render_runs_grid(
        by_run_recent, repo_root, "Recent scored runs", commit_cache, lightboxes,
    )

    top_best = sorted(with_samples, key=lambda r: r["e_w1"])[:_MAX_BEST_SAMPLES]
    best_block = _render_runs_grid(
        top_best, repo_root,
        "Best surviving samples (lowest W1 still on disk)", commit_cache, lightboxes,
    )

    lightbox_block = _render_lightboxes(lightboxes)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{_esc(_lab.LAB_ID)} — progress</title>
<style>{_CSS}</style></head>
<body>
{header}
{trend_html}
{campaigns_block}
{arch_block}
{best_block}
{recent_block}
{lightbox_block}
</body></html>
"""
