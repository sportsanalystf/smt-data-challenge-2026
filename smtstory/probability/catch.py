"""
catch.py — the Robbery Meter, as a reusable component.

This is the project's original flagship model, refactored into the shared
probability interface so it can sit alongside the other live models and be
driven by the same pipeline. The methodology is unchanged: three physically
meaningful features engineered from tracking —

    route_ft   how far the fielder had to travel
    hang_s     how long the ball was in the air
    req_speed  the closing speed those two imply (route / hang)

— fed to a logistic model. Route and hang are the physics; their ratio is what
separates a routine fly from a highlight.
"""
import numpy as np
import pandas as pd

from .base import LogisticModel

FEATURES = ["route_ft", "hang_s", "req_speed"]


class CatchProbabilityModel:
    def __init__(self, max_route_ft=160.0, min_hang_s=0.4, max_req_speed=45.0):
        self.max_route_ft = max_route_ft
        self.min_hang_s = min_hang_s
        self.max_req_speed = max_req_speed
        self.model = None
        self.metrics = {}

    # ----------------------------------------------------------- preparation
    def prepare(self, catches):
        df = catches.copy()
        df = df[(df.hang_s > self.min_hang_s) &
                (df.route_ft >= 0) & (df.route_ft < self.max_route_ft)]
        df["req_speed"] = (df.route_ft / df.hang_s).clip(0, self.max_req_speed)
        return df

    def fit(self, catches):
        df = self.prepare(catches)
        X = df[FEATURES].to_numpy(float)
        y = df.catch_made.to_numpy(float)
        self.model = LogisticModel(FEATURES).fit(X, y)
        self.metrics = dict(self.model.metrics)
        return self

    # ------------------------------------------------------------------ use
    def predict(self, route_ft, hang_s):
        route = np.atleast_1d(np.asarray(route_ft, float))
        hang = np.atleast_1d(np.asarray(hang_s, float))
        req = np.clip(route / np.maximum(hang, 1e-6), 0, self.max_req_speed)
        return self.model.predict(np.column_stack([route, hang, req]))

    def score_frame(self, catches):
        """Attach catch probability, Outs Above Expected, and Robbery Score."""
        df = self.prepare(catches)
        df["catch_prob"] = self.model.predict(df[FEATURES].to_numpy(float))
        df["oae"] = df.catch_made - df.catch_prob
        df["robbery_score"] = np.where(df.catch_made == 1,
                                       100.0 * (1.0 - df.catch_prob), 0.0)
        # A play is most fun to vote on when the model is least certain.
        df["suspense"] = 1.0 - (2.0 * (df.catch_prob - 0.5)).abs()
        return df

    def difficulty_label(self, p):
        """Fan-facing wording for a catch probability."""
        if p >= 0.90:
            return "Routine"
        if p >= 0.70:
            return "Makeable"
        if p >= 0.40:
            return "Tough"
        if p >= 0.15:
            return "Highlight Reel"
        return "Web Gem"
