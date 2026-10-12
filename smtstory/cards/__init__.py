"""
Story card library.

Cards are grouped by category so a scoreboard operator can enable or disable a
whole family (say, all fan-vote games) without touching the rest of the system.
"""
from .base import (StoryCard, CardPayload, PlayContext,  # noqa: F401
                   CardRegistry, default_registry)
from . import speed, power, pitching, defense, interactive, storytelling  # noqa: F401

CATEGORIES = ["speed", "power", "pitching", "defense", "fan", "story"]

__all__ = ["StoryCard", "CardPayload", "PlayContext", "CardRegistry",
           "default_registry", "CATEGORIES"]
