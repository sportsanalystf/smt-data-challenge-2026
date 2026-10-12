"""
components — the Python half of the parallel R/Python implementation.

Each module here is ONE self-contained analysis component, mirroring an R file
of the same number in `../R/`. The Quarto documents call these so that the R and
Python chunks in each document do the same work and can be compared directly:

    components/c01_play_by_play.py   <->   R/R01_play_by_play.R
    components/c02_wpa_leverage.py   <->   R/R02_wpa_leverage.R
    ...

Every function returns a tidy DataFrame (or a matplotlib figure), so a Quarto
chunk is usually a single call. The heavy lifting lives in the validated
`smtstory` engine; these modules are the thin, readable presentation layer.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SUB = os.path.dirname(_HERE)
if _SUB not in sys.path:
    sys.path.insert(0, _SUB)

__all__ = [
    "c01_play_by_play", "c02_wpa_leverage", "c03_tracking_features",
    "c04_speed_baserunning", "c05_power_hitting", "c06_pitching",
    "c07_defense", "c08_fan_interactive", "c09_composite", "c10_animation",
]
