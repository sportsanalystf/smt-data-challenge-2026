"""
build_probability.py — Stage 3 of the pipeline.

Joins the tracking feature tables (produced by the ORIGINAL project's
extractors, reused as-is) onto the reconstructed at-bats, then fits the live
probability models.

Key join: a plate appearance is decided by its LAST play, so batted-ball
features join on `last_play`; pitch features are per pitch.

Usage: python pipeline/build_probability.py
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                                   # noqa: E402
from smtstory.probability import (ZoneModel, ContactOutcomeModel,   # noqa: E402
                                  CatchProbabilityModel, BaserunningModel)

OUT = config.ensure_dir(config.ENGINE_OUT)
FEAT = os.path.join(config.OUTPUT_DIR, "feat")     # reused legacy extractions


def load_feat(name):
    p = os.path.join(FEAT, name)
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def main():
    ab = pd.read_csv(os.path.join(OUT, "atbats_enriched.csv"))
    print(f"at-bats: {len(ab)}")

    # ---------------------------------------------------- reuse legacy features
    hits = load_feat("hits_v2.csv").rename(columns={"carry_ft": "hit_distance_ft"})
    sprints = load_feat("sprints.csv")
    catches = load_feat("catches.csv")
    throws = load_feat("throws.csv")
    pitches = pd.read_csv(os.path.join(OUT, "pitch_locations.csv"))
    print(f"features -> hits {len(hits)}, sprints {len(sprints)}, "
          f"catches {len(catches)}, throws {len(throws)}, pitches {len(pitches)}")

    # ------------------------------------------- join batted-ball to at-bats
    key = ["game_string", "play"]
    ab2 = ab.merge(hits[key + ["exit_velo_mph", "launch_deg", "hit_distance_ft"]],
                   left_on=["game_string", "last_play"], right_on=key, how="left") \
            .drop(columns=["play"], errors="ignore")
    if len(sprints):
        ab2 = ab2.merge(sprints[key + ["sprint_mph"]],
                        left_on=["game_string", "last_play"], right_on=key,
                        how="left").drop(columns=["play"], errors="ignore")
    # Pitch velocity of the deciding pitch.
    ab2 = ab2.merge(pitches[["game_string", "play", "pitch_velo_mph",
                             "plate_x", "plate_z"]],
                    left_on=["game_string", "last_play"],
                    right_on=["game_string", "play"], how="left") \
             .drop(columns=["play"], errors="ignore")

    # -------------------------------------------------------------- 1. zone
    zone = ZoneModel().fit(pitches)
    print("\nZONE:", json.dumps(zone.metrics, indent=2, default=float)[:400])

    # ----------------------------------------------------------- 2. contact
    batted = ab2.dropna(subset=["exit_velo_mph", "launch_deg"])
    contact = ContactOutcomeModel().fit(batted)
    print("\nCONTACT OUTCOME MODELS:")
    for k in ("hit", "extra_base", "home_run"):
        m = contact.metrics[k]
        print(f"  {k:11s} n={m['n']:6d} base={m['base_rate']:.3f} "
              f"acc={m['accuracy']:.3f} auc={m['auc']:.3f} brier={m['brier']:.3f}")

    # ------------------------------------------------------------- 3. catch
    catch = CatchProbabilityModel().fit(catches)
    print(f"\nCATCH (Robbery Meter): n={catch.metrics['n']} "
          f"acc={catch.metrics['accuracy']:.3f} auc={catch.metrics['auc']:.3f} "
          f"brier={catch.metrics['brier']:.3f}")
    scored = catch.score_frame(catches)
    scored.to_csv(os.path.join(OUT, "catches_scored.csv"), index=False)

    # ------------------------------------------------------- 4. baserunning
    br = BaserunningModel().fit(ab2)
    print(f"\nBASERUNNING: situations={br.metrics['n_situations']} "
          f"score_rate_risp={br.metrics['score_rate_risp']:.3f}")

    # ---------------------------------------- attach live probabilities to ABs
    m = batted.index
    probs = contact.predict(ab2.loc[m, "exit_velo_mph"], ab2.loc[m, "launch_deg"])
    for name, vals in probs.items():
        ab2.loc[m, f"p_{name}"] = vals

    # Catch probability for the play, when there was a catch opportunity.
    if len(scored):
        cs = scored[["game_string", "play", "catch_prob", "catch_made",
                     "route_ft", "hang_s", "robbery_score"]]
        ab2 = ab2.merge(cs, left_on=["game_string", "last_play"],
                        right_on=["game_string", "play"], how="left") \
                 .drop(columns=["play"], errors="ignore")

    ab2.to_csv(os.path.join(OUT, "atbats_full.csv"), index=False)
    with open(os.path.join(OUT, "probability_models.pkl"), "wb") as f:
        pickle.dump({"zone": zone, "contact": contact, "catch": catch,
                     "baserunning": br}, f)

    summary = {"zone": zone.metrics, "contact": contact.metrics,
               "catch": catch.metrics, "baserunning": br.metrics}
    with open(os.path.join(OUT, "probability_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)

    print(f"\nwrote atbats_full.csv ({len(ab2)} rows, "
          f"{ab2.exit_velo_mph.notna().sum()} with batted-ball tracking)")


if __name__ == "__main__":
    main()
