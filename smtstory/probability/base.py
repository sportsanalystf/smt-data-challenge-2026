"""
base.py — a small, dependency-free logistic regression.

The project deliberately avoids scikit-learn: the original catch-probability
model was written in NumPy, and keeping one implementation means every
probability in the system is fit, regularized, and calibrated the same way.
Having a single shared class also makes the models trivially comparable, since
they all report the same metrics.
"""
import numpy as np


class LogisticModel:
    """L2-regularized logistic regression fit by gradient descent."""

    def __init__(self, feature_names=None, l2=1.0, iters=3000, lr=0.4):
        self.feature_names = list(feature_names or [])
        self.l2, self.iters, self.lr = l2, iters, lr
        self.w = None
        self.mu = None
        self.sd = None
        self.metrics = {}

    # ------------------------------------------------------------------ fit
    def fit(self, X, y, sample_weight=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X, y = X[ok], y[ok]
        if len(y) == 0:
            raise ValueError("no usable rows to fit")

        self.mu, self.sd = X.mean(0), X.std(0)
        self.sd = np.where(self.sd == 0, 1.0, self.sd)
        Xs = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])

        w = np.zeros(Xs.shape[1])
        sw = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight)[ok]
        sw = sw / sw.mean()
        n = len(y)
        for _ in range(self.iters):
            p = 1.0 / (1.0 + np.exp(-(Xs @ w)))
            grad = Xs.T @ (sw * (p - y)) / n + self.l2 * np.r_[0, w[1:]] / n
            w -= self.lr * grad
        self.w = w

        p = self._sigmoid(Xs)
        eps = 1e-9
        self.metrics = {
            "n": int(n),
            "base_rate": float(y.mean()),
            "accuracy": float(((p >= 0.5).astype(int) == y).mean()),
            "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))),
            "auc": self._auc(y, p),
        }
        return self

    # -------------------------------------------------------------- predict
    def _sigmoid(self, Xs):
        return 1.0 / (1.0 + np.exp(-(Xs @ self.w)))

    def predict(self, X):
        X = np.atleast_2d(np.asarray(X, dtype=float))
        Xs = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])
        return self._sigmoid(Xs)

    # --------------------------------------------------------------- utils
    @staticmethod
    def _auc(y, p):
        """Area under the ROC curve via rank statistics."""
        pos, neg = y == 1, y == 0
        if pos.sum() == 0 or neg.sum() == 0:
            return float("nan")
        order = np.argsort(p)
        ranks = np.empty(len(p), dtype=float)
        ranks[order] = np.arange(1, len(p) + 1)
        return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2.0)
                     / (pos.sum() * neg.sum()))

    def coefficients(self):
        if self.w is None:
            return {}
        names = ["intercept"] + (self.feature_names or
                                 [f"x{i}" for i in range(len(self.w) - 1)])
        return dict(zip(names, np.round(self.w, 4).tolist()))
