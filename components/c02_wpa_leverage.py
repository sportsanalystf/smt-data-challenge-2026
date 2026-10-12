"""
c02_wpa_leverage.py — COMPONENT 2: Run Expectancy, Win Probability, Leverage, WPA.

Mirrors R/R02_wpa_leverage.R.

Everything here is a function of the play-by-play table built in component 1.
Nothing is imported from an outside league: the run-expectancy matrix and the
win-probability model are both estimated from THIS season.
"""
import os
import pickle

import numpy as np
import pandas as pd

from smtstory import config
from smtstory.analytics import (RunExpectancy, WinProbabilityModel,
                                LeverageIndex, add_wpa, clutch_score)
from smtstory.state.reconstruct import BASE_STATES


def fit_run_expectancy(pbp):
    """The 24-state run expectancy matrix (8 base states x 3 out counts)."""
    return RunExpectancy().fit(pbp)


def run_expectancy_table(re_model):
    m = re_model.matrix.copy().round(3)
    m.columns = ["0 outs", "1 out", "2 outs"]
    m.index.name = "bases (1B/2B/3B)"
    return m


def fit_win_probability(pbp, re_model):
    """Logistic win-probability model on the reconstructed state."""
    return WinProbabilityModel().fit(pbp, re_model)


def wp_metrics(wp_model):
    return pd.DataFrame({
        "metric": ["plate appearances", "accuracy", "Brier score",
                   "log loss", "base rate"],
        "value": [wp_model.metrics["n"],
                  round(wp_model.metrics["accuracy"], 4),
                  round(wp_model.metrics["brier"], 4),
                  round(wp_model.metrics["log_loss"], 4),
                  round(wp_model.metrics["base_rate"], 4)],
    })


def add_win_probability(pbp, wp_model, re_model):
    """Attach WP before/after, WPA and RE24 to every plate appearance."""
    frames = [add_wpa(g, wp_model, re_model)
              for _, g in pbp.groupby("game_string", sort=False)]
    return pd.concat(frames, ignore_index=True)


def add_leverage(enriched, wp_model, re_model):
    """Leverage Index, normalized so an average plate appearance = 1.0."""
    li = LeverageIndex(wp_model, re_model).fit(enriched)
    out = li.add_leverage(enriched)
    out["clutch_score"] = clutch_score(out.wpa, out.leverage_index)
    return out, li


def biggest_swings(enriched, n=10):
    """The plays that moved the game most — the WPA leaderboard."""
    cols = ["game_string", "inning", "half_inning", "batter", "outcome", "runs",
            "wp_before", "wp_after", "wpa", "leverage_index"]
    cols = [c for c in cols if c in enriched.columns]
    idx = enriched.wpa.abs().sort_values(ascending=False).index
    return enriched.loc[idx, cols].head(n).round(3)


def leverage_profile(enriched):
    """How leverage is distributed — the sanity check that it averages 1.0."""
    li = enriched.leverage_index.dropna()
    return pd.DataFrame({
        "statistic": ["mean", "median", "p75", "p90", "p95", "max",
                      "share above 2.0 (high leverage)"],
        "value": [round(li.mean(), 3), round(li.median(), 3),
                  round(li.quantile(.75), 2), round(li.quantile(.90), 2),
                  round(li.quantile(.95), 2), round(li.max(), 2),
                  round(float((li >= 2).mean()), 3)],
    })


def load_fitted(path=None):
    """Load the models the pipeline already fitted (fast path for Quarto)."""
    path = path or os.path.join(config.ENGINE_OUT, "models.pkl")
    with open(path, "rb") as f:
        m = pickle.load(f)
    return m["re"], m["wp"], m["li"]


def load_enriched(path=None):
    path = path or os.path.join(config.ENGINE_OUT, "atbats_enriched.csv")
    return pd.read_csv(path, low_memory=False)


def game_flow(enriched, game_string):
    """The win-probability path through one game, for plotting."""
    g = enriched[enriched.game_string == game_string].reset_index(drop=True)
    g["wp_home"] = np.where(g.half_inning.eq("Bottom"), g.wp_after,
                            1.0 - g.wp_after)
    g["play_index"] = np.arange(len(g))
    return g[["play_index", "inning", "half_inning", "batter", "outcome",
              "wp_home", "wpa", "leverage_index"]]
