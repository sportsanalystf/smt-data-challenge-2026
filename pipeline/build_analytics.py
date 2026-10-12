"""
build_analytics.py — Stage 2 of the pipeline.

Fits the core analytics on the reconstructed season:
  * Run Expectancy matrix (24 states)
  * Win Probability model
  * Leverage Index calibration
  * WPA / RE24 / Clutch for every at-bat

Writes the fitted artifacts and the enriched at-bat table.

Usage:  python pipeline/build_analytics.py
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                                    # noqa: E402
from smtstory.analytics import (RunExpectancy, WinProbabilityModel,   # noqa: E402
                                LeverageIndex, add_wpa, clutch_score)

OUT = config.ensure_dir(config.ENGINE_OUT)


def main():
    ab = pd.read_csv(os.path.join(OUT, "atbats.csv"))
    print(f"loaded {len(ab)} at-bats from {ab.game_string.nunique()} games")

    # ---------------------------------------------------------- 1. RE matrix
    re_model = RunExpectancy().fit(ab)
    re_tbl = re_model.to_frame()
    re_tbl.to_csv(os.path.join(OUT, "run_expectancy_matrix.csv"))
    print("\nRUN EXPECTANCY (runs to end of inning):")
    print(re_tbl.to_string())

    # ------------------------------------------------------ 2. Win probability
    wp_model = WinProbabilityModel().fit(ab, re_model)
    print("\nWIN PROBABILITY MODEL:", {k: round(v, 4) if isinstance(v, float) else v
                                       for k, v in wp_model.metrics.items()})

    # ------------------------------------------------- 3. WPA per game, then LI
    frames = []
    for gs, g in ab.groupby("game_string", sort=False):
        frames.append(add_wpa(g, wp_model, re_model))
    enriched = pd.concat(frames, ignore_index=True)
    print(f"WPA attached to {len(enriched)} at-bats "
          f"(mean |WPA| = {enriched.wpa.abs().mean():.4f})")

    li = LeverageIndex(wp_model, re_model).fit(enriched)
    enriched = li.add_leverage(enriched)
    enriched["clutch_score"] = clutch_score(enriched.wpa, enriched.leverage_index)
    print(f"LEVERAGE: mean={enriched.leverage_index.mean():.3f} "
          f"p95={enriched.leverage_index.quantile(.95):.2f} "
          f"max={enriched.leverage_index.max():.2f}")

    enriched.to_csv(os.path.join(OUT, "atbats_enriched.csv"), index=False)

    # ------------------------------------------------------------ 4. artifacts
    with open(os.path.join(OUT, "models.pkl"), "wb") as f:
        pickle.dump({"re": re_model, "wp": wp_model, "li": li}, f)

    meta = {
        "run_expectancy": {"league_runs_per_inning": re_model.league_runs_per_inning},
        "win_probability": {**wp_model.metrics,
                            "coefficients": wp_model.coefficients()},
        "leverage": {"mean_swing": li.mean_swing,
                     "outcome_mix": li.outcome_mix},
        "wpa": {"mean_abs": float(enriched.wpa.abs().mean()),
                "max_abs": float(enriched.wpa.abs().max())},
        "n_atbats": int(len(enriched)),
        "n_games": int(enriched.game_string.nunique()),
    }
    with open(os.path.join(OUT, "analytics_summary.json"), "w") as f:
        json.dump(meta, f, indent=2, default=float)

    # -------------------------------------------------------- 5. sanity checks
    print("\nSANITY CHECKS")
    top = enriched.reindex(enriched.wpa.abs().sort_values(ascending=False).index).head(5)
    print(top[["game_string", "inning", "half_inning", "outcome", "runs",
               "wp_before", "wp_after", "wpa", "leverage_index"]]
          .round(3).to_string(index=False))


if __name__ == "__main__":
    main()
