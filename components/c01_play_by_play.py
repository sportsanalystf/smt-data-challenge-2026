"""
c01_play_by_play.py — COMPONENT 1: tracking data -> play-by-play.

Mirrors R/R01_play_by_play.R.

This is the foundation. The SMT tables record base occupancy but NOT outs, runs,
or the score, so a play-by-play table has to be reconstructed before any
situational metric can exist. The reconstruction logic lives in
`smtstory.state`; this component exposes it as one call and formats the result
the way a broadcast play-by-play would read.
"""
import os

import numpy as np
import pandas as pd

from smtstory import config, dataio
from smtstory.state import reconstruct_game
from smtstory.narrative import NarrativeGenerator, describe_state, ordinal

PBP_COLUMNS = [
    "inning", "half_inning", "at_bat", "batter", "pitcher", "outs_before",
    "base_state_before", "outcome", "runs", "outs_on_play",
    "away_score_after", "home_score_after", "description",
]


def play_by_play(game_string=None, rel_path=None, data_root=None):
    """Reconstruct a full play-by-play table for one game.

    Returns one row per plate appearance with the game state before it, what
    happened, and a readable description.
    """
    if rel_path is None:
        if game_string is None:
            raise ValueError("pass game_string or rel_path")
        rel_path = dataio.game_dir_from_string(game_string)

    game = dataio.load_game(rel_path, data_root=data_root,
                            with_player_tracking=False)
    df, summary = reconstruct_game(game)

    narrator = NarrativeGenerator()
    df = df.copy()
    df["situation"] = [
        f"{'Top' if h == 'Top' else 'Bot'} {ordinal(i)}, "
        f"{describe_state(b, o)}"
        for h, i, b, o in zip(df.half_inning, df.inning,
                              df.base_state_before, df.outs_before)
    ]
    df["description"] = [narrator.play_line(r) for r in df.to_dict("records")]
    return df, summary


def pbp_table(df, n=15):
    """The columns a reader actually wants, ready to print."""
    cols = [c for c in PBP_COLUMNS if c in df.columns]
    out = df[cols].head(n).copy()
    out = out.rename(columns={
        "half_inning": "half", "outs_before": "outs",
        "base_state_before": "bases", "outs_on_play": "outs_made",
        "away_score_after": "away", "home_score_after": "home",
    })
    return out


def state_summary(df):
    """Distribution of the reconstructed state — the validation view."""
    return pd.DataFrame({
        "metric": ["plate appearances", "half-innings", "runs", "hits",
                   "home runs", "walks/HBP", "half-innings balanced (%)"],
        "value": [
            len(df),
            df.groupby(["inning", "half_inning"]).ngroups,
            int(df.runs.sum()),
            int(df.outcome.isin(["single", "double", "triple", "home_run"]).sum()),
            int((df.outcome == "home_run").sum()),
            int((df.outcome == "walk_hbp").sum()),
            round(100 * df.groupby(["inning", "half_inning"])
                  .half_balanced.first().mean(), 1),
        ],
    })


def season_play_by_play(path=None):
    """Load the cached season-wide play-by-play built by the pipeline."""
    path = path or os.path.join(config.ENGINE_OUT, "atbats.csv")
    return pd.read_csv(path)


def season_validation(df=None):
    """Compare the reconstruction against real baseball rates."""
    df = season_play_by_play() if df is None else df
    n_games = df.game_string.nunique()
    per_game = {
        "runs_per_game": df.runs.sum() / n_games,
        "hits_per_game": df.outcome.isin(
            ["single", "double", "triple", "home_run"]).sum() / n_games,
        "walks_per_game": (df.outcome == "walk_hbp").sum() / n_games,
        "home_runs_per_game": (df.outcome == "home_run").sum() / n_games,
        "plate_appearances_per_game": len(df) / n_games,
    }
    reference = {"runs_per_game": 9.5, "hits_per_game": 18.0,
                 "walks_per_game": 7.0, "home_runs_per_game": 2.0,
                 "plate_appearances_per_game": 76.0}
    return pd.DataFrame({
        "metric": list(per_game),
        "reconstructed": [round(v, 2) for v in per_game.values()],
        "real_milb_reference": [reference[k] for k in per_game],
    })
