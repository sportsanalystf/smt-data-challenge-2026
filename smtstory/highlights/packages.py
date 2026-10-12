"""
packages.py — the highlight package generator.

Given a scored game (every play carrying WPA, leverage, tracking measurements
and a Highlight Score), this assembles the reels a broadcast actually uses:
top plays, best defense, best offense, best pitching, highest leverage,
per-player and per-team packages, inning recaps, and a full game recap.

A "package" is declarative: a filter, a ranking key, and a size. Adding a new
reel is one entry in PACKAGE_SPECS, not new code — which is the point of
building it this way.

Each highlight entry carries everything a control room needs to cut it:
the timestamp window from the tracking clock, the players involved, the event
description, its WPA and leverage, the cards to display, and a
broadcast-ready line of copy.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from ..cards import default_registry, PlayContext
from ..narrative import NarrativeGenerator


# A package spec: (filter function, sort key, ascending, size, description)
PACKAGE_SPECS = {
    "top_plays": {
        "filter": lambda d: d,
        "sort": "highlight_score", "ascending": False, "size": 10,
        "title": "Top Plays of the Game",
    },
    "best_defense": {
        "filter": lambda d: d[(d.get("catch_made") == 1) if "catch_made" in d else []],
        "sort": "robbery_score", "ascending": False, "size": 5,
        "title": "Best Defensive Plays",
    },
    "best_offense": {
        "filter": lambda d: d[d.outcome.isin(["single", "double", "triple", "home_run"])],
        "sort": "highlight_score", "ascending": False, "size": 5,
        "title": "Best Offensive Plays",
    },
    "best_pitching": {
        "filter": lambda d: d[(d.outcome.isin(["out", "fielders_choice"])) &
                              (d.leverage_index >= 1.5)],
        "sort": "wpa", "ascending": True, "size": 5,
        "title": "Best Pitching Moments",
    },
    "highest_leverage": {
        "filter": lambda d: d,
        "sort": "leverage_index", "ascending": False, "size": 5,
        "title": "Highest Leverage Moments",
    },
    "power_show": {
        "filter": lambda d: d[d.exit_velo_mph.notna()],
        "sort": "exit_velo_mph", "ascending": False, "size": 5,
        "title": "Hardest Hit Balls",
    },
    "speed_show": {
        "filter": lambda d: d[d.sprint_mph.notna()] if "sprint_mph" in d else d.iloc[0:0],
        "sort": "sprint_mph", "ascending": False, "size": 5,
        "title": "Fastest Runs of the Night",
    },
}


@dataclass
class Highlight:
    """One clip-ready moment."""
    rank: int
    game_string: str
    inning: int
    half_inning: str
    play: int
    timestamp_start_ms: Any = None
    timestamp_end_ms: Any = None
    players: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    narrative: str = ""
    insights: List[str] = field(default_factory=list)
    wpa: float = 0.0
    leverage_index: float = 0.0
    highlight_score: float = 0.0
    cards: List[Dict] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class HighlightEngine:
    """Builds highlight packages from a scored game."""

    def __init__(self, registry=None, narrator=None):
        self.registry = registry or default_registry()
        self.narrator = narrator or NarrativeGenerator()

    # ------------------------------------------------------------- context
    def context_for(self, row):
        """Convert a scored at-bat row into a PlayContext for the cards."""
        d = {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v)
             for k, v in row.items()}
        return PlayContext(d)

    def build_highlight(self, rank, row, card_limit=3):
        ctx = self.context_for(row)
        cards = self.registry.surface(ctx, limit=card_limit)
        g = row.get
        return Highlight(
            rank=rank,
            game_string=g("game_string"),
            inning=int(g("inning") or 0),
            half_inning=g("half_inning") or "",
            play=int(g("last_play") or 0),
            timestamp_start_ms=g("ts_start"),
            timestamp_end_ms=g("ts_end"),
            players={k: g(k) for k in ("batter", "pitcher", "fielder")
                     if g(k) is not None},
            description=self.narrator.situation_line(row),
            narrative=self.narrator.play_line(row),
            insights=self.narrator.insight_lines(row),
            wpa=float(g("wpa") or 0.0),
            leverage_index=float(g("leverage_index") or 0.0),
            highlight_score=float(g("highlight_score") or 0.0),
            cards=[c.to_dict() for c in cards],
            metrics={k: g(k) for k in
                     ("exit_velo_mph", "launch_deg", "hit_distance_ft",
                      "pitch_velo_mph", "sprint_mph", "catch_prob", "route_ft",
                      "hang_s", "re24", "clutch_score")
                     if g(k) is not None},
        )

    # ------------------------------------------------------------ packages
    def package(self, plays, name):
        spec = PACKAGE_SPECS[name]
        try:
            sub = spec["filter"](plays)
        except Exception:
            sub = plays.iloc[0:0]
        if sub is None or len(sub) == 0:
            return {"name": name, "title": spec["title"], "highlights": []}
        key = spec["sort"]
        if key not in sub.columns:
            return {"name": name, "title": spec["title"], "highlights": []}
        sub = sub.dropna(subset=[key]).sort_values(key, ascending=spec["ascending"])
        sub = sub.head(spec["size"])
        hs = [self.build_highlight(i + 1, r) for i, r in
              enumerate(sub.to_dict("records"))]
        return {"name": name, "title": spec["title"],
                "highlights": [h.to_dict() for h in hs]}

    def all_packages(self, plays):
        return {name: self.package(plays, name) for name in PACKAGE_SPECS}

    # ------------------------------------------------------- player / team
    def player_package(self, plays, player, size=5):
        mask = pd.Series(False, index=plays.index)
        for col in ("batter", "pitcher", "fielder"):
            if col in plays.columns:
                mask |= plays[col].eq(player)
        sub = plays[mask].sort_values("highlight_score", ascending=False).head(size)
        return {"name": f"player:{player}", "title": f"{player} Highlights",
                "highlights": [self.build_highlight(i + 1, r).to_dict()
                               for i, r in enumerate(sub.to_dict("records"))]}

    def team_package(self, plays, team, size=8):
        if "batting_team" not in plays.columns:
            return {"name": f"team:{team}", "title": f"{team} Highlights",
                    "highlights": []}
        sub = plays[plays.batting_team.eq(team)] \
            .sort_values("highlight_score", ascending=False).head(size)
        return {"name": f"team:{team}", "title": f"{team} Highlights",
                "highlights": [self.build_highlight(i + 1, r).to_dict()
                               for i, r in enumerate(sub.to_dict("records"))]}

    # ---------------------------------------------------------- recaps
    def inning_recaps(self, plays):
        out = []
        for (inn, half), g in plays.groupby(["inning", "half_inning"], sort=False):
            recs = g.to_dict("records")
            best = max(recs, key=lambda r: r.get("highlight_score") or 0)
            out.append({
                "inning": int(inn), "half_inning": half,
                "runs": int(g.runs.sum()),
                "summary": self.narrator.inning_recap(inn, half, recs),
                "best_play": self.build_highlight(1, best).to_dict(),
            })
        return out

    def game_recap(self, plays, summary):
        recs = plays.to_dict("records")
        if not recs:
            return {}
        top = max(recs, key=lambda r: r.get("highlight_score") or 0)
        turning = max(recs, key=lambda r: abs(r.get("wpa") or 0))
        # Player of the game: largest total win probability contribution.
        potg, potg_wpa = None, 0.0
        if "batter" in plays.columns:
            by = plays.groupby("batter").wpa.sum()
            if len(by):
                potg = by.abs().idxmax()
                potg_wpa = float(by.loc[potg])
        return {
            "headline": self.narrator.game_recap(summary, top),
            "final": {"home": summary.get("home_team"),
                      "away": summary.get("away_team"),
                      "home_runs": summary.get("home_final"),
                      "away_runs": summary.get("away_final")},
            "top_play": self.build_highlight(1, top).to_dict(),
            "turning_point": self.build_highlight(1, turning).to_dict(),
            "player_of_the_game": {"player": potg, "wpa": potg_wpa},
        }
