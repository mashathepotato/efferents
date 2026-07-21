"""Score the forecast model on held-out days: skill x attribution stability.

Skill is measured against a climatology baseline (ridge on the two seasonal
features only), the standard reference in forecast verification:
skill = 1 - rmse_model / rmse_climatology. The headline metric multiplies
skill by the training-time attribution-stability index, so a model can't win
the sweep by being accurate-but-unexplainable or stable-but-useless.

Emits a trailing JSON line: {"metrics": {"trust_adjusted_skill": ...}}.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import datagen
import ridge


def _rmse(pred: list[float], truth: list[float]) -> float:
    n = len(truth)
    return (sum((p - t) ** 2 for p, t in zip(pred, truth)) / n) ** 0.5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()
    model = json.loads(Path(args.checkpoint).read_text())

    X_train, y_train, X_eval, y_eval = datagen.make_dataset()

    def predict(coefs, x_mean, x_std, y_mean, X):
        out = []
        for row in X:
            z = sum(c * (v - m) / s for c, v, m, s in zip(coefs, row, x_mean, x_std))
            out.append(z + y_mean)
        return out

    preds = predict(model["coefs"], model["x_mean"], model["x_std"],
                    model["y_mean"], X_eval)
    rmse_model = _rmse(preds, y_eval)

    # Climatology baseline: seasonal features only, near-zero penalty.
    seas_idx = [1, 2]
    Xtr_s = [[row[i] for i in seas_idx] for row in X_train]
    Xev_s = [[row[i] for i in seas_idx] for row in X_eval]
    scaler = ridge.Scaler(Xtr_s, y_train)
    clim_coefs = ridge.fit_ridge(
        scaler.transform(Xtr_s), [v - scaler.y_mean for v in y_train], 1e-6
    )
    clim_preds = predict(clim_coefs, scaler.x_mean, scaler.x_std,
                         scaler.y_mean, Xev_s)
    rmse_clim = _rmse(clim_preds, y_eval)

    skill = 1.0 - rmse_model / rmse_clim if rmse_clim > 0 else 0.0
    stability = max(0.0, float(model["attribution_stability"]))

    print(json.dumps({"metrics": {
        "trust_adjusted_skill": round(skill * stability, 4),
        "skill_vs_climatology": round(skill, 4),
        "attribution_stability": round(stability, 4),
        "rmse_model": round(rmse_model, 4),
        "rmse_climatology": round(rmse_clim, 4),
    }}))


if __name__ == "__main__":
    main()
