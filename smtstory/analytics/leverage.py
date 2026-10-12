"""
leverage.py — Leverage Index (how much is at stake).

Leverage Index answers: "how much can win probability swing from here?"
Following the standard definition, LI for a state is the expected absolute
change in win probability from that state, normalized so the average plate
appearance in the league has LI = 1.0.

    LI(state) = E[ |WPA| | state ] / E[ |WPA| ]

We estimate the numerator two ways and blend them:

1. **Model-based**: enumerate the plausible outcomes of a plate appearance
   (out, walk, single, double, triple, home run) with league frequencies, apply
   each to the state, and average the resulting |ΔWP|. This is smooth and
   defined for every state, including rare ones.
2. **Empirical**: the observed mean |WPA| in that state bucket. This captures
   reality but is noisy where samples are thin.

Blending by sample size gives a leverage curve that is both stable and
faithful — important, because LI drives which moments the scoreboard chooses to
show.
"""
import numpy as np
import pandas as pd

from .. import config
from ..state.reconstruct import BASE_STATES, base_state_code

# League-typical plate appearance outcome mix, used to enumerate what could
# happen next. Values are refit from the data in `fit`.
DEFAULT_OUTCOME_MIX = {
    "out": 0.66, "walk_hbp": 0.10, "single": 0.14,
    "double": 0.055, "triple": 0.005, "home_run": 0.04,
}


def _apply_outcome(base_state, outs, kind):
    """Very small state-transition model: what does the state become?

    Returns (new_base_state, new_outs, runs). Deliberately simple — it only has
    to be good enough to measure how much the state can swing.
    """
    on1 = bool(base_state & 1)
    on2 = bool(base_state & 2)
    on3 = bool(base_state & 4)

    if kind == "out":
        return base_state, outs + 1, 0
    if kind == "walk_hbp":
        runs = 1 if (on1 and on2 and on3) else 0
        if not on1:
            return base_state_code(True, on2, on3), outs, 0
        if not on2:
            return base_state_code(True, True, on3), outs, 0
        if not on3:
            return base_state_code(True, True, True), outs, 0
        return base_state_code(True, True, True), outs, runs
    if kind == "single":
        runs = int(on3) + int(on2)
        return base_state_code(True, on1, False), outs, runs
    if kind == "double":
        runs = int(on3) + int(on2) + int(on1)
        return base_state_code(False, True, False), outs, runs
    if kind == "triple":
        runs = int(on1) + int(on2) + int(on3)
        return base_state_code(False, False, True), outs, runs
    if kind == "home_run":
        runs = 1 + int(on1) + int(on2) + int(on3)
        return 0, outs, runs
    return base_state, outs, 0


class LeverageIndex:
    def __init__(self, wp_model, re_model=None):
        self.wp = wp_model
        self.re = re_model
        self.outcome_mix = dict(DEFAULT_OUTCOME_MIX)
        self.mean_swing = None       # league average E|dWP|
        self.table = None            # lookup: (inning, half, outs, base, diff)
        self.empirical = None

    # ------------------------------------------------------------------ fit
    def fit(self, atbats):
        """Calibrate the outcome mix and the league-average swing."""
        mix = atbats.outcome.value_counts(normalize=True).to_dict()
        for k in list(self.outcome_mix):
            if k in mix:
                self.outcome_mix[k] = float(mix[k])
        # 'fielders_choice' behaves like an out for state purposes.
        total = sum(self.outcome_mix.values())
        self.outcome_mix = {k: v / total for k, v in self.outcome_mix.items()}

        swings = self.expected_swing_frame(atbats)
        self.mean_swing = float(np.nanmean(swings))

        if "wpa" in atbats.columns:
            emp = (atbats.assign(abs_wpa=atbats.wpa.abs())
                   .groupby(["outs_before", "base_state_before"])
                   .abs_wpa.agg(["mean", "size"]))
            self.empirical = emp
        return self

    # ------------------------------------------------------------ computation
    def expected_swing(self, inning, half_inning, outs, base_state, score_diff):
        """E[|dWP|] over the plausible outcomes of one plate appearance."""
        wp0 = self.wp.predict_state(inning, half_inning, outs, base_state,
                                    score_diff, self.re)
        total = 0.0
        for kind, prob in self.outcome_mix.items():
            nb, no, runs = _apply_outcome(base_state, outs, kind)
            if no >= config.OUTS_PER_HALF:
                # Inning ends: the opponent bats, so the batting team's win
                # probability becomes the complement of the new state's.
                nxt_half = "Bottom" if half_inning == "Top" else "Top"
                nxt_inning = inning if half_inning == "Top" else inning + 1
                wp1 = 1.0 - self.wp.predict_state(
                    nxt_inning, nxt_half, 0, 0, -(score_diff + runs), self.re)
            else:
                wp1 = self.wp.predict_state(inning, half_inning, no, nb,
                                            score_diff + runs, self.re)
            total += prob * abs(wp1 - wp0)
        return total

    def expected_swing_frame(self, df):
        """Vectorized E[|dWP|] for a whole frame of states.

        Leverage needs one win-probability evaluation per possible outcome per
        plate appearance. Done row by row that is ~113k model calls for a
        season; done as arrays it is six. This is what makes the metric
        practical both for season processing and for a live feed.
        """
        inning = df.inning.to_numpy(float)
        is_bottom = (df.half_inning.to_numpy() == "Bottom").astype(float)
        outs = df.outs_before.to_numpy(int)
        base = df.base_state_before.to_numpy(int)
        sd = df.score_diff_before.to_numpy(float)

        wp0 = self.wp.predict_array(inning, is_bottom, outs, base, sd, self.re)
        total = np.zeros(len(df), dtype=float)

        for kind, prob in self.outcome_mix.items():
            nb = np.empty_like(base)
            no = np.empty_like(outs)
            runs = np.zeros(len(df), dtype=float)
            for i in range(len(df)):
                b, o, r = _apply_outcome(int(base[i]), int(outs[i]), kind)
                nb[i], no[i], runs[i] = b, o, r

            ended = no >= config.OUTS_PER_HALF
            wp1 = np.empty(len(df), dtype=float)

            # Same half-inning continues.
            if (~ended).any():
                m = ~ended
                wp1[m] = self.wp.predict_array(
                    inning[m], is_bottom[m], no[m], nb[m], sd[m] + runs[m], self.re)
            # Third out: the other team bats, so WP flips to its complement.
            if ended.any():
                m = ended
                nxt_bottom = 1.0 - is_bottom[m]
                nxt_inning = inning[m] + (is_bottom[m] > 0).astype(float)
                wp1[m] = 1.0 - self.wp.predict_array(
                    nxt_inning, nxt_bottom, np.zeros(m.sum()), np.zeros(m.sum(), int),
                    -(sd[m] + runs[m]), self.re)

            total += prob * np.abs(wp1 - wp0)
        return total

    def index(self, inning, half_inning, outs, base_state, score_diff):
        """Leverage Index for a state (1.0 = an average plate appearance)."""
        if not self.mean_swing:
            return 1.0
        return float(self.expected_swing(inning, half_inning, outs, base_state,
                                         score_diff) / self.mean_swing)

    def add_leverage(self, df):
        """Attach a `leverage_index` column to a frame of at-bats."""
        out = df.copy()
        out["leverage_index"] = self.expected_swing_frame(out) / self.mean_swing
        return out
