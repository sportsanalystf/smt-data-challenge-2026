"""
Live probability engine.

Each model is an independent, swappable component exposing the same tiny
interface:

    model.fit(df)      -> self
    model.predict(...) -> probabilities in [0, 1]
    model.metrics      -> dict of fit quality

They are deliberately small and separately testable so a reviewer can read any
one of them in a couple of minutes, and so a live scoreboard can load only the
models it needs.
"""
from .base import LogisticModel  # noqa: F401
from .zone import ZoneModel  # noqa: F401
from .contact import ContactOutcomeModel  # noqa: F401
from .catch import CatchProbabilityModel  # noqa: F401
from .baserunning import BaserunningModel  # noqa: F401
