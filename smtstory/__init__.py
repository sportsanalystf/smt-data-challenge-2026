"""
smtstory — A Real-Time Baseball Storytelling Engine
====================================================
SMT Data Challenge 2026 · "On the Big Screen!"

This package turns raw SMT tracking data into fan-facing stories. It is layered
so each component can be read, tested, and reused independently:

    smtstory/
      config.py          constants, theme colors, paths
      dataio/            loading the SMT tables (wraps existing smt_utils)
      tracking/          geometry + kinematics from 20 Hz tracking
      state/             GAME STATE RECONSTRUCTION (outs, runs, score)
      analytics/         run expectancy, win probability, leverage, WPA, highlight
      probability/       live probability models (zone, contact, catch, baserunning)
      cards/             reusable fan-facing story cards
      narrative/         broadcast-ready sentence generation
      viz/               broadcast-quality PNG visualizations
      web/               self-contained interactive HTML dashboard

Design principle: every layer depends only on layers above it in this list.
State reconstruction knows nothing about visualization; cards know nothing about
how they are rendered. This keeps components swappable and reviewable.
"""

__version__ = "1.0.0"

# Importing config has the side effect of putting the original project's
# `code/` directory on sys.path, so `import smt_utils` works from any submodule
# regardless of import order. Done here so that `import smtstory.anything`
# is always sufficient.
from . import config  # noqa: F401,E402
