"""
base.py — the Story Card framework.

A Story Card is the atomic unit of the fan experience: one idea, one number,
one sentence, one graphic. Cards are deliberately dumb about presentation —
they emit a `CardPayload`, and the viz layer or the web dashboard decides how
to draw it. That separation is what lets the same card appear as a PNG in the
paper, a panel on the scoreboard, and a tile in the HTML dashboard.

Every card implements two methods:

    applies(ctx)  -> bool          should this card fire for this play?
    build(ctx)    -> CardPayload   the numbers and words to show

`ctx` is a PlayContext: a plain dict-like bundle of everything known about the
play (state, tracking measurements, probabilities, player codes). Cards never
reach back into the data layer, so they are trivial to unit-test.

The registry auto-surfaces cards: given a play, it asks every registered card
whether it applies and returns the ones that do, ranked by priority. That is
the mechanism behind "the right graphic appears at the right moment".
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import numpy as np


# --------------------------------------------------------------------- payload
@dataclass
class CardPayload:
    """What a card wants shown on screen."""
    card_id: str
    title: str                       # e.g. "BURNER BOARD"
    headline: str                    # the big number, preformatted, e.g. "22.8"
    unit: str = ""                   # e.g. "MPH"
    subtitle: str = ""               # who / what
    narrative: str = ""              # broadcast-ready sentence
    detail: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"        # speed | power | pitching | defense | fan | story
    priority: float = 0.0            # higher = more deserving of screen time
    viz_hint: str = "stat"           # stat | field | timeline | zone | vote | gauge

    def to_dict(self):
        d = asdict(self)
        # Make everything JSON-safe for the web dashboard.
        for k, v in list(d["detail"].items()):
            if isinstance(v, (np.integer,)):
                d["detail"][k] = int(v)
            elif isinstance(v, (np.floating,)):
                d["detail"][k] = float(v)
            elif isinstance(v, (np.bool_,)):
                d["detail"][k] = bool(v)
        return d


# --------------------------------------------------------------------- context
class PlayContext(dict):
    """Everything known about one play. Missing keys return None, so cards can
    ask for a measurement without defensive boilerplate."""

    def __getattr__(self, name):
        return self.get(name)

    def has(self, *keys):
        """True when every requested measurement is present and finite."""
        for k in keys:
            v = self.get(k)
            if v is None:
                return False
            if isinstance(v, float) and not np.isfinite(v):
                return False
        return True


# ------------------------------------------------------------------------ card
class StoryCard:
    """Base class for all cards."""
    card_id = "base"
    title = "STORY"
    category = "general"
    viz_hint = "stat"
    base_priority = 1.0

    def applies(self, ctx: PlayContext) -> bool:
        raise NotImplementedError

    def build(self, ctx: PlayContext) -> CardPayload:
        raise NotImplementedError

    # Convenience for subclasses -------------------------------------------
    def _payload(self, headline, unit="", subtitle="", narrative="",
                 detail=None, priority=None):
        return CardPayload(
            card_id=self.card_id, title=self.title, headline=headline, unit=unit,
            subtitle=subtitle, narrative=narrative, detail=detail or {},
            category=self.category,
            priority=self.base_priority if priority is None else priority,
            viz_hint=self.viz_hint)


# -------------------------------------------------------------------- registry
class CardRegistry:
    """Holds card instances and surfaces the ones that fit a moment."""

    def __init__(self, cards=None):
        self.cards: List[StoryCard] = list(cards or [])

    def register(self, card):
        self.cards.append(card)
        return self

    def surface(self, ctx, limit=None, categories=None):
        """Return payloads for every card that applies, best first."""
        out = []
        for card in self.cards:
            if categories and card.category not in categories:
                continue
            try:
                if card.applies(ctx):
                    out.append(card.build(ctx))
            except Exception:
                # A single misbehaving card must never take down the scoreboard.
                continue
        out.sort(key=lambda p: p.priority, reverse=True)
        return out[:limit] if limit else out

    def card_ids(self):
        return [c.card_id for c in self.cards]


def default_registry():
    """The full card library, assembled in one place."""
    from . import (speed, power, pitching, defense, interactive, storytelling,
                   advanced)
    reg = CardRegistry()
    for mod in (speed, power, pitching, defense, interactive, storytelling,
                advanced):
        for card in mod.CARDS:
            reg.register(card)
    return reg
