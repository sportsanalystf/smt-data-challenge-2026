"""
validate.py — independent verification of the reconstructed game state.

The reconstruction in `reconstruct.py` infers runs from base-occupancy
transitions, which needs no player tracking and is therefore fast enough to run
over the whole season. This module provides a SECOND, physically independent
estimate of the same quantity: it watches the 20 Hz player tracking and counts
runners who actually cross home plate.

Agreement between two independent methods is the evidence that the
reconstruction is trustworthy. Disagreement localizes exactly where it is not.
"""
import numpy as np
import pandas as pd

# A runner is "at home" inside this radius of the plate (feet).
HOME_RADIUS_FT = 8.0
# A runner must have been at least this far from home to count as having scored.
AWAY_RADIUS_FT = 25.0
# The batter starts at home, so he must round the bases (travel at least this
# far) before returning home to be credited with a run.
BATTER_TRIP_FT = 60.0

RUNNER_IDS = (11, 12, 13)
BATTER_ID = 10


def runs_from_tracking(game):
    """Count runs by watching players cross the plate.

    Returns a DataFrame with one row per detected run: play, player_id.
    """
    pp = game.player
    if pp is None or pp.empty:
        return pd.DataFrame(columns=["play_per_game", "player_id"])

    rows = []
    sub = pp[pp.player_id.isin(list(RUNNER_IDS) + [BATTER_ID])]
    for (play, pid), t in sub.groupby(["play_per_game", "player_id"]):
        t = t.sort_values("timestamp")
        dist = np.hypot(t.field_x.to_numpy(float), t.field_y.to_numpy(float))
        if dist.size < 2:
            continue
        start, far = dist[0], dist.max()
        # Use CLOSEST APPROACH, not final position: player tracking stops at
        # end-of-play, so a runner who has already touched the plate may still
        # be recorded drifting away from it, and a runner who scores just after
        # the play is whistled dead is otherwise missed entirely.
        if pid == BATTER_ID:
            # The batter STARTS at home, so his closest approach must be
            # measured only after he has rounded the bases.
            apex = int(dist.argmax())
            closest_after = dist[apex:].min() if apex < dist.size else np.inf
            scored = (far > BATTER_TRIP_FT) and (closest_after < HOME_RADIUS_FT)
        else:
            scored = (start > AWAY_RADIUS_FT) and (dist.min() < HOME_RADIUS_FT)
        if scored:
            rows.append({"play_per_game": int(play), "player_id": int(pid)})
    return pd.DataFrame(rows)


def compare_runs(game, atbats):
    """Compare reconstructed runs against tracking-detected runs for one game.

    Returns a dict with both totals and their difference.
    """
    tr = runs_from_tracking(game)
    recon_runs = int(atbats.runs.sum())
    track_runs = int(len(tr))
    return {
        "game_string": game.game_string,
        "runs_reconstructed": recon_runs,
        "runs_tracking": track_runs,
        "difference": recon_runs - track_runs,
        "abs_difference": abs(recon_runs - track_runs),
    }


def validation_report(rows):
    """Aggregate per-game comparisons into a summary table."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df, {}
    summary = {
        "games": int(len(df)),
        "mean_runs_reconstructed": float(df.runs_reconstructed.mean()),
        "mean_runs_tracking": float(df.runs_tracking.mean()),
        "mean_abs_difference": float(df.abs_difference.mean()),
        "exact_agreement_rate": float((df.difference == 0).mean()),
        "within_one_rate": float((df.abs_difference <= 1).mean()),
        "within_two_rate": float((df.abs_difference <= 2).mean()),
        "correlation": float(df.runs_reconstructed.corr(df.runs_tracking))
        if len(df) > 2 else float("nan"),
    }
    return df, summary
