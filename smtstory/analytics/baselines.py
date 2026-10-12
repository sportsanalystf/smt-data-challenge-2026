"""
baselines.py — league reference distributions.

A number only becomes a story when it has something to be compared against.
"20.1 mph" means nothing; "faster than 84% of the league" means everything.
This module holds the season distributions and turns any measurement into a
percentile and a plain-English grade.
"""
import json
import os

import numpy as np
import pandas as pd

# Scouting-style grades, keyed on percentile.
GRADES = [
    (97, "ELITE"), (85, "PLUS-PLUS"), (70, "PLUS"),
    (45, "AVERAGE"), (25, "BELOW AVG"), (0, "WELL BELOW"),
]


def grade_for(pct):
    if pct is None or not np.isfinite(pct):
        return None
    for threshold, label in GRADES:
        if pct >= threshold:
            return label
    return "WELL BELOW"


class LeagueBaselines:
    """Empirical distributions for every measurable the scoreboard shows."""

    # Metrics where a LOWER value is better.
    LOWER_IS_BETTER = {"home_to_first_s", "time_to_base_s", "transfer_s",
                       "exchange_s", "pivot_s", "time_to_ball_s"}

    def __init__(self):
        self.dists = {}     # metric -> sorted numpy array of season values
        self.summary = {}   # metric -> mean/median/percentile table

    # ------------------------------------------------------------------ fit
    def add(self, metric, values):
        v = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
        if len(v) < 20:
            return self
        arr = np.sort(v.to_numpy(float))
        self.dists[metric] = arr
        self.summary[metric] = {
            "n": int(len(arr)),
            "mean": float(arr.mean()),
            "median": float(np.median(arr)),
            "p10": float(np.percentile(arr, 10)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "p99": float(np.percentile(arr, 99)),
            "min": float(arr.min()), "max": float(arr.max()),
        }
        return self

    # ------------------------------------------------------------------ use
    def percentile(self, metric, value):
        """Where a value sits in the league, 0-100 (100 = best)."""
        arr = self.dists.get(metric)
        if arr is None or value is None or not np.isfinite(value):
            return None
        pct = 100.0 * float(np.searchsorted(arr, value) / len(arr))
        if metric in self.LOWER_IS_BETTER:
            pct = 100.0 - pct
        return round(pct, 1)

    def compare(self, metric, value):
        """Full comparison payload for a single measurement."""
        s = self.summary.get(metric)
        if s is None or value is None or not np.isfinite(value):
            return None
        pct = self.percentile(metric, value)
        return {
            "value": float(value),
            "percentile": pct,
            "grade": grade_for(pct),
            "league_mean": round(s["mean"], 2),
            "league_p90": round(s["p90"], 2),
            "vs_mean": round(float(value) - s["mean"], 2),
            "n": s["n"],
        }

    def phrase(self, metric, value, unit=""):
        """A ready-to-say comparison line."""
        c = self.compare(metric, value)
        if not c:
            return None
        better = "faster" if metric in self.LOWER_IS_BETTER else "better"
        return (f"{c['value']:.1f}{unit} — {better} than {c['percentile']:.0f}% "
                f"of the league (avg {c['league_mean']:.1f}{unit}).")

    # ------------------------------------------------------------ i/o
    def to_json(self, path):
        with open(path, "w") as f:
            json.dump(self.summary, f, indent=2)
        return path

    def save_arrays(self, path):
        np.savez_compressed(path, **{k: v for k, v in self.dists.items()})
        return path

    @classmethod
    def load_arrays(cls, path):
        obj = cls()
        with np.load(path) as z:
            for k in z.files:
                obj.add(k, z[k])
        return obj


def build_from_features(feat_dir, engine_dir):
    """Assemble baselines from the season feature tables."""
    b = LeagueBaselines()

    def rd(name, folder=feat_dir):
        p = os.path.join(folder, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    sprints = rd("sprints.csv")
    if len(sprints):
        b.add("sprint_mph", sprints.sprint_mph)

    hits = rd("hits_v2.csv")
    if len(hits):
        b.add("exit_velo_mph", hits.exit_velo_mph)
        b.add("launch_deg", hits.launch_deg)
        b.add("carry_ft", hits.carry_ft)

    throws = rd("throws.csv")
    if len(throws):
        b.add("throw_velo_mph", throws.throw_velo_mph)

    catches = rd("catches.csv")
    if len(catches):
        b.add("route_ft", catches.route_ft)
        b.add("hang_s", catches.hang_s)
        b.add("closing_ftps", catches.close_ftps)

    pitches = rd("pitch_locations.csv", engine_dir)
    if len(pitches):
        # Drop single-frame tracking spikes: 103 mph is the plausible ceiling
        # at this level, and leaving a 193 mph artifact in the distribution
        # would distort every percentile built from it.
        v = pitches.pitch_velo_mph
        b.add("pitch_velo_mph", v[(v > 50) & (v <= 103)])

    return b
