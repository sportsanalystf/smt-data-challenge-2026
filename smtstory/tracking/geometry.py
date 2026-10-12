"""
geometry.py — field geometry and the strike zone.

Coordinate system (per the SMT Data Description):
  x = 0 on the home-plate/second-base line, x > 0 toward first base (feet)
  y = 0 at the back of home plate, y > 0 toward second base (feet)
  z = height in feet (z = 0 is a datum, not necessarily ground level)

REUSE NOTE: base coordinates come from the original smt_utils so the two
codebases can never drift apart.
"""
import numpy as np

import smt_utils as U

# Re-export the canonical base locations from the original project.
HOME = U.HOME
FIRST = U.FIRST
SECOND = U.SECOND
THIRD = U.THIRD
MOUND = U.MOUND

# Approximate strike zone. Plate half-width is 8.5 in = 0.708 ft; a ball
# (1.45 in radius) catches the corner, giving ~0.83 ft half-width.
ZONE_HALF_WIDTH_FT = 0.83
# Vertical zone in the tracking system's z units. z=0 is a datum rather than the
# ground, so the zone is calibrated empirically from the data (see
# probability/zone.py, which re-estimates these from pitch heights).
ZONE_BOTTOM_DEFAULT = 1.5
ZONE_TOP_DEFAULT = 3.6


def in_strike_zone(x, z, bottom=ZONE_BOTTOM_DEFAULT, top=ZONE_TOP_DEFAULT,
                   half_width=ZONE_HALF_WIDTH_FT):
    """Boolean: does a pitch at horizontal offset x and height z cross the zone?"""
    return (np.abs(x) <= half_width) & (z >= bottom) & (z <= top)


def dist_2d(p, q):
    return float(np.hypot(p[0] - q[0], p[1] - q[1]))


def bearing_from_home(x, y):
    """Spray angle in degrees: 0 = straight up the middle, negative = left field,
    positive = right field."""
    return float(np.degrees(np.arctan2(x, y)))


def field_zone(x, y):
    """Coarse zone label used by spray charts and story cards."""
    d = float(np.hypot(x, y))
    b = bearing_from_home(x, y)
    depth = "infield" if d < 130 else ("outfield" if d < 330 else "deep")
    if b < -15:
        side = "left"
    elif b > 15:
        side = "right"
    else:
        side = "center"
    return f"{depth}_{side}"
