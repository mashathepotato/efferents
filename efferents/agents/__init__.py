"""Multi-agent research loop: Researcher / Executor / Analyst / Writer.

Designed for 24/7 operation under a soft daily cost cap. State lives on disk
(lab/runs.sqlite, lab/queue.jsonl, lab/lab_notebook.md, lab/digests/, lab/budget.jsonl)
so the loop is restart-safe.

Modules:
    state          File/DB I/O shared by all agents.
    budget         Spend tracking, daily cap, model routing.
    notify         macOS osascript + ntfy.sh push.
    researcher     Proposes next configs given recent runs + notebook + context/.
    executor       Pops a proposal, runs the lab's command, appends outcome to notebook.
    analyst        Periodic digest writer (Opus 4.7).
    orchestrator   The while-True loop tying it all together.
"""

__version__ = "0.1.0"
