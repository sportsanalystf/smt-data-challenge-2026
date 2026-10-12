"""
zone.py — pitch location, the strike zone, and contact probability.

HONEST SCOPE NOTE
-----------------
The SMT data contains no umpire calls, so a true "called strike probability"
cannot be supervised — there are no ball/strike labels to learn from. Claiming
one would be dishonest. What the data DOES support:

  * where every pitch crossed the plate (interpolated from ball tracking)
  * whether the pitch was put in play (an event-stream label)

So this module provides two things:

  1. `in_zone` — a geometric判定 of whether the pitch passed through the strike
     zone, with the zone's vertical bounds CALIBRATED FROM THE DATA rather than
     assumed, because z = 0 in this coordinate system is a datum and not the
     ground.
  2. `ContactInPlayModel` — a supervised model of P(ball in play | location),
     which has real labels and drives the "attack zone" heat maps.
"""
import numpy as np
import pandas as pd

from .base import LogisticModel
from ..tracking.geometry import ZONE_HALF_WIDTH_FT


class ZoneModel:
    """Calibrates the strike zone and models contact by location."""

    def __init__(self):
        self.bottom = None
        self.top = None
        self.half_width = ZONE_HALF_WIDTH_FT
        self.contact_model = None
        self.metrics = {}

    # ------------------------------------------------------------ calibrate
    def fit(self, pitches, low_q=0.12, high_q=0.88):
        """Calibrate zone height from the pitches batters actually swung at.

        Rationale: hitters offer at strikes far more often than at balls, so the
        central mass of BATTED pitch heights is a data-driven estimate of the
        zone. Using batted balls avoids having to assume where the ground is.
        """
        df = pitches.dropna(subset=["plate_x", "plate_z"]).copy()
        batted = df[df.batted == 1]
        src = batted if len(batted) > 500 else df
        self.bottom = float(src.plate_z.quantile(low_q))
        self.top = float(src.plate_z.quantile(high_q))

        df["in_zone"] = self.in_zone(df.plate_x, df.plate_z).astype(int)

        # Supervised: P(ball in play | location).
        # Features are expressed as normalized distances from the CENTRE of the
        # zone. Raw (x, z, x^2, z^2) terms are strongly collinear and left the
        # optimizer unable to recover the vertical effect at all; centring and
        # scaling each axis by its own half-height/half-width makes the problem
        # well conditioned and lets the model express the inverted-U in height
        # that the raw data clearly shows.
        X = self._design(df.plate_x.to_numpy(float), df.plate_z.to_numpy(float))
        y = df.batted.to_numpy(float)
        self.contact_model = LogisticModel(
            ["dx", "dz", "dx_sq", "dz_sq", "radial"], iters=8000, lr=0.5).fit(X, y)

        self.metrics = {
            "zone_bottom_ft": round(self.bottom, 3),
            "zone_top_ft": round(self.top, 3),
            "zone_half_width_ft": self.half_width,
            "in_zone_rate": float(df.in_zone.mean()),
            "contact_model": self.contact_model.metrics,
            "n_pitches": int(len(df)),
        }
        return self

    # ------------------------------------------------------------- features
    def _design(self, x, z):
        """Location features, centred and scaled on the calibrated zone."""
        x = np.asarray(x, dtype=float)
        z = np.asarray(z, dtype=float)
        z_center = (self.bottom + self.top) / 2.0
        z_half = max(1e-6, (self.top - self.bottom) / 2.0)
        dx = x / self.half_width
        dz = (z - z_center) / z_half
        return np.column_stack([np.abs(dx), np.abs(dz), dx ** 2, dz ** 2,
                                np.sqrt(dx ** 2 + dz ** 2)])

    # ------------------------------------------------------------------ use
    def in_zone(self, plate_x, plate_z):
        x = np.abs(np.asarray(plate_x, dtype=float))
        z = np.asarray(plate_z, dtype=float)
        return (x <= self.half_width) & (z >= self.bottom) & (z <= self.top)

    def contact_probability(self, plate_x, plate_z):
        """P(the pitch is put in play) at a location — the 'attack zone' map."""
        x = np.atleast_1d(np.asarray(plate_x, dtype=float))
        z = np.atleast_1d(np.asarray(plate_z, dtype=float))
        return self.contact_model.predict(self._design(x, z))

    def zone_grid(self, n=25, pad=0.8):
        """A grid of contact probabilities for heat-map rendering."""
        xs = np.linspace(-self.half_width - pad, self.half_width + pad, n)
        zs = np.linspace(self.bottom - pad, self.top + pad, n)
        XX, ZZ = np.meshgrid(xs, zs)
        P = self.contact_probability(XX.ravel(), ZZ.ravel()).reshape(XX.shape)
        return xs, zs, P
