"""
win_probability.py — win probability from game state.

WP is the probability that the BATTING team eventually wins, given
(inning, half, outs, base state, score differential).

Implementation notes
--------------------
* A logistic model is used rather than an empirical lookup: with 250 games the
  24 base-out states x innings x score margins grid is far too sparse to fill
  by counting, and a lookup would produce jagged, non-monotonic probabilities
  that look broken on a scoreboard.
* Features are chosen so the model can express the things that actually matter:
  the value of a lead, the fact that a lead is worth more as innings run out
  (score_diff x innings_remaining), the run potential of the current state
  (its run expectancy), and home-field advantage in the bottom half.
* Fitted with gradient descent in NumPy (no sklearn dependency), matching the
  approach already used by the project's catch-probability model.
"""
import numpy as np
import pandas as pd

from .. import config


FEATURES = [
    "score_diff", "innings_left", "score_diff_x_innings_left",
    "score_diff_per_inning_left", "outs", "re_state", "is_bottom",
    "runners_on", "in_scoring_position",
]


class WinProbabilityModel:
    def __init__(self, l2=1.0, iters=4000, lr=0.5):
        self.l2, self.iters, self.lr = l2, iters, lr
        self.w = None
        self.mu = None
        self.sd = None
        self.metrics = {}

    # ------------------------------------------------------------- features
    @staticmethod
    def build_features(df, re_model=None):
        """Build the design matrix from at-bat state columns."""
        innings_left = np.maximum(
            0.0, config.INNINGS_REGULATION - df["inning"].to_numpy(float)
            + np.where(df["half_inning"].to_numpy() == "Top", 0.5, 0.0))
        score_diff = df["score_diff_before"].to_numpy(float)
        outs = df["outs_before"].to_numpy(float)
        base = df["base_state_before"].to_numpy(int)
        is_bottom = (df["half_inning"].to_numpy() == "Bottom").astype(float)

        runners_on = ((base & 1) > 0).astype(float) + ((base & 2) > 0).astype(float) \
            + ((base & 4) > 0).astype(float)
        in_sp = (((base & 2) > 0) | ((base & 4) > 0)).astype(float)

        if re_model is not None:
            re_state = np.array([re_model.re(int(b), int(o))
                                 for b, o in zip(base, outs)], dtype=float)
        else:
            re_state = np.zeros(len(df))

        X = pd.DataFrame({
            "score_diff": score_diff,
            "innings_left": innings_left,
            "score_diff_x_innings_left": score_diff * innings_left,
            # A one-run lead in the 9th is worth far more than in the 1st.
            "score_diff_per_inning_left": score_diff / (innings_left + 1.0),
            "outs": outs,
            "re_state": re_state,
            "is_bottom": is_bottom,
            "runners_on": runners_on,
            "in_scoring_position": in_sp,
        })
        return X[FEATURES]

    # ------------------------------------------------------------------ fit
    def fit(self, atbats, re_model=None):
        df = atbats.dropna(subset=["score_diff_before"]).copy()
        X = self.build_features(df, re_model).to_numpy(float)
        y = df["batting_team_won"].to_numpy(float)

        self.mu, self.sd = X.mean(0), X.std(0)
        self.sd[self.sd == 0] = 1.0
        Xs = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])

        w = np.zeros(Xs.shape[1])
        n = len(y)
        for _ in range(self.iters):
            p = 1.0 / (1.0 + np.exp(-(Xs @ w)))
            grad = Xs.T @ (p - y) / n + self.l2 * np.r_[0, w[1:]] / n
            w -= self.lr * grad
        self.w = w

        p = self.predict(df, re_model)
        eps = 1e-9
        self.metrics = {
            "n": int(n),
            "accuracy": float(((p >= .5).astype(int) == y).mean()),
            "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(p + eps) +
                                       (1 - y) * np.log(1 - p + eps))),
            "base_rate": float(y.mean()),
        }
        return self

    # -------------------------------------------------------------- predict
    def predict(self, df, re_model=None):
        """Win probability for the BATTING team, as an array."""
        X = self.build_features(df, re_model).to_numpy(float)
        Xs = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])
        return 1.0 / (1.0 + np.exp(-(Xs @ self.w)))

    # ------------------------------------------------------ fast array path
    def predict_array(self, inning, is_bottom, outs, base_state, score_diff,
                      re_model=None):
        """Vectorized win probability with no pandas overhead.

        The scoreboard needs this to run in milliseconds, and leverage requires
        six evaluations per plate appearance across the whole season, so the
        hot path avoids DataFrame construction entirely.
        """
        inning = np.asarray(inning, dtype=float)
        is_bottom = np.asarray(is_bottom, dtype=float)
        outs = np.asarray(outs, dtype=float)
        base = np.asarray(base_state, dtype=int)
        sd = np.asarray(score_diff, dtype=float)

        innings_left = np.maximum(
            0.0, config.INNINGS_REGULATION - inning + np.where(is_bottom > 0, 0.0, 0.5))
        runners_on = ((base & 1) > 0) + ((base & 2) > 0) + ((base & 4) > 0)
        in_sp = (((base & 2) > 0) | ((base & 4) > 0)).astype(float)

        if re_model is not None:
            re_state = re_model.lookup_array(base, outs)
        else:
            re_state = np.zeros_like(sd)

        X = np.column_stack([
            sd, innings_left, sd * innings_left, sd / (innings_left + 1.0),
            outs, re_state, is_bottom, runners_on.astype(float), in_sp,
        ])
        Xs = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])
        return 1.0 / (1.0 + np.exp(-(Xs @ self.w)))

    def predict_state(self, inning, half_inning, outs, base_state, score_diff,
                      re_model=None):
        """Win probability for a single hypothetical state (used for leverage
        and for the live scoreboard feed)."""
        return float(self.predict_array(
            [inning], [1.0 if half_inning == "Bottom" else 0.0], [outs],
            [base_state], [score_diff], re_model)[0])

    def coefficients(self):
        if self.w is None:
            return {}
        return dict(zip(["intercept"] + FEATURES, np.round(self.w, 4).tolist()))
