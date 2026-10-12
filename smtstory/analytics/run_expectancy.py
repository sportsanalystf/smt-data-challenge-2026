"""
run_expectancy.py — the 24-state run expectancy matrix.

RE(base_state, outs) is the average number of runs a team scores from that
state until the end of the half-inning. It is the foundation for Expected Runs
Added (RE24): the run value of any event is

    RE24 = RE(after) - RE(before) + runs_scored_on_play

Everything is estimated empirically from the reconstructed at-bats, so the
matrix reflects THIS league and season rather than an imported MLB assumption.
"""
import numpy as np
import pandas as pd

from ..state.reconstruct import BASE_STATES
from .. import config


class RunExpectancy:
    """Empirical 24-state (8 base states x 3 out states) run expectancy matrix."""

    def __init__(self):
        self.matrix = None      # DataFrame indexed by base_state, columns outs
        self.n = None           # sample counts
        self.league_runs_per_inning = np.nan
        self._values = None     # cached numpy view for the fast path

    # ------------------------------------------------------------------ fit
    def fit(self, atbats):
        """Estimate RE from reconstructed at-bats.

        Only half-innings whose out accounting balanced are used, since a
        half-inning with unresolved outs has an unreliable "runs to end of
        inning" total.
        """
        df = atbats[atbats.half_balanced].copy()
        df = df.sort_values(["game_string", "inning", "half_inning", "at_bat"])

        # Runs scored from this at-bat to the end of its half-inning.
        grp = df.groupby(["game_string", "inning", "half_inning"], sort=False)
        df["runs_rest_of_inning"] = (
            grp["runs"].transform(lambda s: s[::-1].cumsum()[::-1]))

        valid = df[df.outs_before < config.OUTS_PER_HALF]
        cell = valid.groupby(["base_state_before", "outs_before"])
        mat = cell["runs_rest_of_inning"].mean().unstack()
        cnt = cell["runs_rest_of_inning"].size().unstack()

        mat = mat.reindex(index=range(8), columns=range(3))
        cnt = cnt.reindex(index=range(8), columns=range(3)).fillna(0)
        # Fill any empty cell with the row/column-informed league mean.
        mat = mat.fillna(valid["runs_rest_of_inning"].mean())

        mat.index = [BASE_STATES[i] for i in mat.index]
        cnt.index = mat.index
        mat.columns.name = "outs"
        self.matrix = mat
        self.n = cnt
        self.league_runs_per_inning = float(
            valid[valid.outs_before == 0].groupby(
                ["game_string", "inning", "half_inning"])["runs_rest_of_inning"]
            .first().mean())
        return self

    # ------------------------------------------------------------------ use
    def re(self, base_state, outs):
        """Run expectancy for a state. Returns 0.0 once the inning is over."""
        if outs is None or outs >= config.OUTS_PER_HALF:
            return 0.0
        if isinstance(base_state, (int, np.integer)):
            base_state = BASE_STATES[int(base_state)]
        try:
            return float(self.matrix.loc[base_state, int(outs)])
        except (KeyError, IndexError):
            return float(np.nanmean(self.matrix.values))

    def lookup_array(self, base_state, outs):
        """Vectorized RE lookup. States with 3+ outs return 0 (inning over)."""
        if self._values is None:
            self._values = self.matrix.to_numpy(float)
        b = np.asarray(base_state, dtype=int).clip(0, 7)
        o = np.asarray(outs, dtype=int)
        valid = o < config.OUTS_PER_HALF
        out = np.zeros(len(b), dtype=float)
        oc = o.clip(0, config.OUTS_PER_HALF - 1)
        out[valid] = self._values[b[valid], oc[valid]]
        return out

    def re24(self, state_before, state_after, runs_scored):
        """Expected Runs Added for a play.

        state_before / state_after are (base_state, outs) tuples. A state whose
        outs have reached three has RE = 0 (inning over).
        """
        rb = self.re(*state_before)
        ra = self.re(*state_after)
        return float(ra - rb + runs_scored)

    def to_frame(self):
        m = self.matrix.copy().round(3)
        m.columns = [f"{c}_out" if c == 1 else f"{c}_outs" for c in m.columns]
        return m
