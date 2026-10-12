"""
baserunning.py — advancement probabilities.

What the data supports: we can see, from reconstructed state transitions,
whether a runner on second scored on a single, whether a runner on first
reached third, and so on. That gives honest, supervised "advance probability"
models keyed on the base-out state and the batted-ball outcome.

What it does NOT support: stolen-base and pickoff probabilities cannot be
supervised, because the data has no steal/caught-stealing labels and pickoff
attempts are flagged only as `is_pickoff` without an outcome. Rather than
invent them, `steal_opportunity_rate` reports the observable quantity (how
often runners are held on and how often pickoff throws occur), and the fan-
facing "Pickoff Jump" card is driven by measured lead distance from tracking
instead of a fabricated probability.
"""
import numpy as np
import pandas as pd


class BaserunningModel:
    """Empirical advancement rates by (base state, outs, batted outcome)."""

    def __init__(self, min_sample=15):
        self.min_sample = min_sample
        self.rates = None
        self.league = {}
        self.metrics = {}

    def fit(self, atbats):
        """Learn how often runners advance/score, by situation.

        Uses only balanced half-innings and high/medium-confidence at-bats, so
        that ambiguous reconstructions do not pollute the rates.
        """
        df = atbats[(atbats.half_balanced) &
                    (atbats.confidence != "low")].copy()
        df["runners_on"] = ((df.base_state_before & 1) > 0).astype(int) + \
                           ((df.base_state_before & 2) > 0).astype(int) + \
                           ((df.base_state_before & 4) > 0).astype(int)
        df["scored_any"] = (df.runs > 0).astype(int)

        grp = df[df.runners_on > 0].groupby(
            ["base_state_before", "outs_before", "outcome"])
        rates = grp.scored_any.agg(["mean", "size"]).reset_index()
        rates = rates[rates["size"] >= self.min_sample]
        self.rates = rates.rename(columns={"mean": "score_rate", "size": "n"})

        self.league = {
            "score_rate_with_runners": float(df[df.runners_on > 0].scored_any.mean()),
            "score_rate_risp": float(
                df[(df.base_state_before & 6) > 0].scored_any.mean()),
        }
        self.metrics = {"n_situations": int(len(self.rates)),
                        "n_atbats": int(len(df)), **self.league}
        return self

    # ------------------------------------------------------------------ use
    def score_probability(self, base_state, outs, outcome):
        """P(at least one run scores) for a situation, backing off to league rates."""
        if self.rates is None:
            return float("nan")
        m = self.rates[(self.rates.base_state_before == int(base_state)) &
                       (self.rates.outs_before == int(outs)) &
                       (self.rates.outcome == outcome)]
        if len(m):
            return float(m.score_rate.iloc[0])
        if int(base_state) & 6:
            return self.league.get("score_rate_risp", float("nan"))
        return self.league.get("score_rate_with_runners", float("nan"))

    def lead_distance(self, player_frames, base_xy, t_pitch):
        """Measured secondary lead: how far off the bag the runner was at the
        moment of the pitch. This is a direct tracking measurement, which is why
        the Pickoff Jump card uses it instead of a modeled probability."""
        trk = player_frames[player_frames.timestamp <= t_pitch].sort_values("timestamp")
        if trk.empty:
            return float("nan")
        pos = trk.iloc[-1][["field_x", "field_y"]].to_numpy(float)
        return float(np.hypot(pos[0] - base_xy[0], pos[1] - base_xy[1]))
