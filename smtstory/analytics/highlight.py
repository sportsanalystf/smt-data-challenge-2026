"""
highlight.py — the Highlight Score.

This is the engine that decides what goes on the big screen. It fuses game
importance with physical spectacle, because fans respond to both: a walk-off
matters because of the situation, a 115 mph laser or a diving catch matters
because of what the body did.

Every component is mapped onto a common 0-1 "excitement" scale before being
combined, so that quantities in different units (mph, feet, probability) can be
weighed against each other honestly. Components that are missing for a given
play (no batted ball, no catch opportunity) are simply dropped and the weights
renormalize — a play is never penalized for lacking a measurement.

    HighlightScore = 100 * sum(w_i * s_i) / sum(w_i)

The weights are exposed and documented so a club can retune the personality of
its scoreboard (more defense, more power, more drama) without touching code.
"""
import numpy as np
import pandas as pd

# Component weights. These encode editorial judgment about what makes a
# baseball moment worth showing, and are intentionally easy to change.
HIGHLIGHT_WEIGHTS = {
    "wpa": 2.6,                 # how much the play changed the game
    "leverage": 1.8,            # how much was at stake
    "exit_velocity": 1.2,       # how hard it was hit
    "hit_distance": 1.0,        # how far it went
    "sprint_speed": 1.0,        # how fast the runner moved
    "pitch_velocity": 0.8,      # how hard it was thrown
    "catch_difficulty": 1.8,    # how unlikely the catch was
    "defensive_range": 1.0,     # how much ground was covered
    "late_inning": 0.8,         # drama of the moment in the game
    "close_game": 0.8,          # drama of the scoreline
    "crowd": 1.0,               # crowd-reaction potential (scoring, HR, gems)
}


def _scale(value, lo, hi):
    """Map a physical quantity to 0-1 with saturation at both ends."""
    if value is None or not np.isfinite(value):
        return None
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


class HighlightScorer:
    """Turns a play's measurements into a single 0-100 broadcast-worthiness score."""

    def __init__(self, weights=None):
        self.w = dict(HIGHLIGHT_WEIGHTS)
        if weights:
            self.w.update(weights)

    # --------------------------------------------------------- components
    def components(self, play):
        """Map one play (a dict-like of measurements) to 0-1 components.

        Unknown measurements return None and are excluded from the average.
        """
        g = play.get
        c = {}

        # Game impact -------------------------------------------------
        c["wpa"] = _scale(abs(g("wpa")) if g("wpa") is not None else None, 0.02, 0.35)
        c["leverage"] = _scale(g("leverage_index"), 0.5, 4.0)

        # Offense -----------------------------------------------------
        c["exit_velocity"] = _scale(g("exit_velo_mph"), 85.0, 112.0)
        c["hit_distance"] = _scale(g("hit_distance_ft"), 250.0, 430.0)

        # Speed -------------------------------------------------------
        c["sprint_speed"] = _scale(g("sprint_mph"), 16.0, 22.0)

        # Pitching ----------------------------------------------------
        c["pitch_velocity"] = _scale(g("pitch_velo_mph"), 88.0, 100.0)

        # Defense -----------------------------------------------------
        cp = g("catch_prob")
        if cp is not None and np.isfinite(cp) and g("catch_made"):
            # Only a catch that was actually MADE earns difficulty credit.
            c["catch_difficulty"] = _scale(1.0 - cp, 0.15, 0.85)
        else:
            c["catch_difficulty"] = None
        c["defensive_range"] = _scale(g("route_ft"), 40.0, 120.0)

        # Situation ---------------------------------------------------
        inning = g("inning")
        c["late_inning"] = _scale(inning, 5.0, 9.0) if inning is not None else None
        sd = g("score_diff_before")
        c["close_game"] = (_scale(-abs(sd), -4.0, 0.0)
                           if sd is not None and np.isfinite(sd) else None)

        # Crowd reaction ----------------------------------------------
        crowd = 0.0
        if g("outcome") == "home_run":
            crowd = 1.0
        elif (g("runs") or 0) > 0:
            crowd = 0.75
        elif g("catch_made") and cp is not None and np.isfinite(cp) and cp < 0.5:
            crowd = 0.8
        elif g("outcome") in ("triple", "double"):
            crowd = 0.55
        elif g("outcome") in ("single", "walk_hbp"):
            crowd = 0.3
        c["crowd"] = crowd

        return c

    # ------------------------------------------------------------- score
    def score(self, play):
        c = self.components(play)
        num = 0.0
        den = 0.0
        for k, v in c.items():
            if v is None:
                continue
            w = self.w.get(k, 0.0)
            num += w * v
            den += w
        if den == 0:
            return 0.0, c
        return float(100.0 * num / den), c

    def score_frame(self, df):
        """Vectorized-ish scoring over a DataFrame of plays."""
        scores = []
        comps = []
        for row in df.to_dict("records"):
            s, c = self.score(row)
            scores.append(s)
            comps.append(c)
        out = df.copy()
        out["highlight_score"] = scores
        comp_df = pd.DataFrame(comps, index=out.index).add_prefix("hs_")
        return pd.concat([out, comp_df], axis=1)

    def explain(self, play, top_n=3):
        """Which components drove this play's score? Used by the narrator."""
        _, c = self.score(play)
        contrib = {k: self.w.get(k, 0) * v for k, v in c.items() if v is not None}
        return sorted(contrib.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
