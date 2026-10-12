"""
wpa.py — Win Probability Added and Clutch.

WPA is the change in the batting team's win probability across a plate
appearance:

    WPA = WP(after) - WP(before)

The subtlety is the half-inning flip: after the third out the other team bats,
so "the batting team" changes. We always express WP from the perspective of the
team that was batting BEFORE the play, converting when the sides change.

Clutch weights an event by how much was at stake: a two-run homer in a blowout
moves win probability very little, while the same swing in a one-run ninth is
the whole game.
"""
import numpy as np
import pandas as pd

from .. import config


def _next_state_rows(df):
    """For each at-bat, the state at the START of the following at-bat, which is
    exactly the state AFTER the current one."""
    nxt = df.shift(-1)
    return nxt


def add_wpa(atbats, wp_model, re_model=None):
    """Attach WP before/after, WPA, and RE24 to each at-bat of a game.

    `atbats` must be a single game's reconstruction, in play order.
    """
    df = atbats.sort_values(["inning", "at_bat"]).reset_index(drop=True).copy()

    # WP for the batting team before each plate appearance.
    df["wp_before"] = wp_model.predict(df, re_model)

    # The state AFTER at-bat i is the state BEFORE at-bat i+1, so the whole
    # column can be produced with one vectorized model call.
    n = len(df)
    wp_after = np.full(n, np.nan)
    if n > 1:
        nxt = df.iloc[1:]
        wp_next = wp_model.predict_array(
            nxt.inning.to_numpy(float),
            (nxt.half_inning.to_numpy() == "Bottom").astype(float),
            nxt.outs_before.to_numpy(int),
            nxt.base_state_before.to_numpy(int),
            nxt.score_diff_before.to_numpy(float),
            re_model)
        same_side = ((nxt.half_inning.to_numpy() == df.half_inning.to_numpy()[:-1]) &
                     (nxt.inning.to_numpy() == df.inning.to_numpy()[:-1]))
        # If the sides changed, the next state's WP belongs to the OTHER team;
        # the batting team's win probability is its complement.
        wp_after[:-1] = np.where(same_side, wp_next, 1.0 - wp_next)
    # Final plate appearance resolves to the actual game result.
    wp_after[-1] = float(df.at[n - 1, "batting_team_won"])

    df["wp_after"] = wp_after
    df["wpa"] = df["wp_after"] - df["wp_before"]

    # Expected Runs Added (RE24), also vectorized.
    if re_model is not None:
        base_b = df.base_state_before.to_numpy(int)
        outs_b = df.outs_before.to_numpy(int)
        re_before = re_model.lookup_array(base_b, outs_b)

        base_a = np.zeros(n, dtype=int)
        outs_a = np.full(n, config.OUTS_PER_HALF, dtype=int)  # default: inning over
        if n > 1:
            same = ((df.half_inning.to_numpy()[1:] == df.half_inning.to_numpy()[:-1]) &
                    (df.inning.to_numpy()[1:] == df.inning.to_numpy()[:-1]))
            base_a[:-1] = np.where(same, base_b[1:], 0)
            outs_a[:-1] = np.where(same, outs_b[1:], config.OUTS_PER_HALF)
        re_after = re_model.lookup_array(base_a, outs_a)
        df["re24"] = re_after - re_before + df.runs.to_numpy(float)
    else:
        df["re24"] = np.nan

    return df


def clutch_score(wpa, leverage):
    """Leverage-weighted win impact, scaled to a friendly 0-100 range.

    Uses a square-root compression so that a genuinely enormous swing does not
    dwarf every other play on the leaderboard.
    """
    wpa = np.asarray(wpa, dtype=float)
    lev = np.asarray(leverage, dtype=float)
    raw = np.abs(wpa) * np.sqrt(np.maximum(lev, 0.0))
    return 100.0 * np.tanh(3.0 * raw)
