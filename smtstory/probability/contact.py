"""
contact.py — what happens after the ball is struck.

Given exit velocity and launch angle (both measured directly from ball
tracking), these models estimate the outcome distribution of a batted ball:

    P(hit)          — does it fall in?
    P(extra_base)   — double, triple or home run?
    P(home_run)     — does it leave the yard?

Labels come from the reconstructed at-bat outcomes, so these are genuinely
supervised, and they are what let the scoreboard say "that ball had a 78%
chance of being a home run" the instant it is hit.
"""
import numpy as np
import pandas as pd

from .base import LogisticModel

FEATURES = ["exit_velo", "launch", "launch_sq", "ev_x_launch", "ev_sq"]


def _design(ev, la):
    ev = np.asarray(ev, dtype=float)
    la = np.asarray(la, dtype=float)
    return np.column_stack([ev, la, la ** 2, ev * la, ev ** 2])


class ContactOutcomeModel:
    """Three linked models over the same (exit velocity, launch angle) space."""

    def __init__(self):
        self.models = {}
        self.metrics = {}

    def fit(self, batted):
        """`batted` needs columns: exit_velo_mph, launch_deg, outcome."""
        df = batted.dropna(subset=["exit_velo_mph", "launch_deg", "outcome"]).copy()
        X = _design(df.exit_velo_mph, df.launch_deg)

        targets = {
            "hit": df.outcome.isin(["single", "double", "triple", "home_run"]),
            "extra_base": df.outcome.isin(["double", "triple", "home_run"]),
            "home_run": df.outcome.eq("home_run"),
        }
        for name, y in targets.items():
            self.models[name] = LogisticModel(FEATURES).fit(X, y.to_numpy(float))
            self.metrics[name] = self.models[name].metrics
        self.metrics["n"] = int(len(df))
        return self

    # ------------------------------------------------------------------ use
    def predict(self, exit_velo, launch):
        """Return a dict of outcome probabilities for one or many batted balls."""
        X = _design(np.atleast_1d(exit_velo), np.atleast_1d(launch))
        out = {name: m.predict(X) for name, m in self.models.items()}
        # Enforce logical ordering: P(HR) <= P(XBH) <= P(hit).
        out["extra_base"] = np.minimum(out["extra_base"], out["hit"])
        out["home_run"] = np.minimum(out["home_run"], out["extra_base"])
        return out

    def predict_one(self, exit_velo, launch):
        p = self.predict([exit_velo], [launch])
        return {k: float(v[0]) for k, v in p.items()}

    def barrel(self, exit_velo, launch):
        """The classic 'barrel': hit hard, in the sweet-spot launch window."""
        return (np.asarray(exit_velo, float) >= 95.0) & \
               (np.asarray(launch, float) >= 20.0) & \
               (np.asarray(launch, float) <= 35.0)
