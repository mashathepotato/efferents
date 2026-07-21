"""Score the early-warning detector on held-out series.

Headline metric: mean detection lead time (timesteps before the known
transition at T_C where the alarm first fires, sustained threshold crossing).
A missed transition scores 0 lead. Also reports the held-out control
false-alarm rate so the lead time can't be bought with a hair-trigger alarm.

Emits a trailing JSON line: {"metrics": {"mean_lead_time": ...}}.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import datagen


def _first_alarm(series: list[float], window: int, threshold: float) -> int | None:
    """First t where rolling AC exceeds threshold on 2 consecutive steps."""
    ac = datagen.rolling_ac1(series, window)
    for i in range(1, len(ac)):
        if ac[i][1] > threshold and ac[i - 1][1] > threshold:
            return ac[i][0]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()
    model = json.loads(Path(args.checkpoint).read_text())
    window, threshold = int(model["window"]), float(model["threshold"])

    ensemble = datagen.make_ensemble()
    _, control_eval = datagen.split(ensemble["control"])
    _, trans_eval = datagen.split(ensemble["transitioning"])

    leads = []
    for series in trans_eval:
        t = _first_alarm(series, window, threshold)
        leads.append(max(0, datagen.T_C - t) if t is not None and t <= datagen.T_C else 0)
    mean_lead = sum(leads) / len(leads) if leads else 0.0

    false_alarms = sum(
        1 for s in control_eval if _first_alarm(s, window, threshold) is not None
    )
    fa_rate = false_alarms / len(control_eval) if control_eval else 0.0

    print(json.dumps({"metrics": {
        "mean_lead_time": round(mean_lead, 2),
        "detected_frac": round(sum(1 for v in leads if v > 0) / len(leads), 3),
        "control_false_alarm_rate": round(fa_rate, 3),
    }}))


if __name__ == "__main__":
    main()
