"""
loaders.py — read the SMT tables.

REUSE NOTE: the original project's `code/smt_utils.py` already implements robust
game listing/loading (including the NaN-play_per_game cleanup we discovered).
This module wraps it and adds a typed container plus lineup/game-info caching,
rather than reimplementing the reader.
"""
import os
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from .. import config

import smt_utils as U  # provided by the original project (path set in config)


@dataclass
class GameData:
    """All tables for one game, plus its identifiers."""
    game_string: str
    rel_path: str
    events: pd.DataFrame        # ball-events
    ball: pd.DataFrame          # ball-positions
    player: pd.DataFrame        # player-positions
    lineups: pd.DataFrame       # lineups rows for this game
    home_team: str = ""
    away_team: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def n_plays(self):
        return int(self.events.play_per_game.max()) if len(self.events) else 0


def list_games(data_root=None):
    """Relative game paths, e.g. 'ANI/IGL/y1/d173'."""
    return U.list_game_dirs(data_root or config.data_root())


def game_dir_from_string(game_string):
    """'y1_d061_VKA_PHD' -> 'PHD/VKA/y1/d061'  (home/away/year/day)."""
    year, day, away, home = game_string.split("_")
    return f"{home}/{away}/{year}/{day}"


@lru_cache(maxsize=4)
def load_lineups(data_root=None):
    return pd.read_csv(os.path.join(data_root or config.data_root(), "lineups.csv"))


@lru_cache(maxsize=4)
def load_game_info(data_root=None):
    return pd.read_csv(os.path.join(data_root or config.data_root(), "game-info.csv"))


def load_game(rel_path, data_root=None, with_player_tracking=True):
    """Load one game. Set with_player_tracking=False to skip the large
    player-positions file when only events/ball are needed (much faster)."""
    root = data_root or config.data_root()
    if with_player_tracking:
        g = U.load_game(root, rel_path)
        events, ball, player = g["events"], g["ball"], g["player"]
        gs = g["game_string"]
    else:
        events = pd.read_csv(os.path.join(root, "ball-events", rel_path, "ball_events.csv"))
        ball = pd.read_csv(os.path.join(root, "ball-positions", rel_path, "ball-positions.csv"))
        events = events.dropna(subset=["play_per_game", "timestamp"])
        ball = ball.dropna(subset=["play_per_game", "timestamp"])
        for d in (events, ball):
            d["play_per_game"] = d["play_per_game"].astype("int64")
        player = pd.DataFrame(columns=["game_string", "play_per_game", "timestamp",
                                       "player_id", "field_x", "field_y"])
        gs = events.game_string.iloc[0] if len(events) else ""

    lu = load_lineups(root)
    lu_game = lu[lu.game_string == gs].copy()
    gi = load_game_info(root)
    row = gi[gi.game_string == gs]
    home = row.home_team.iloc[0] if len(row) else ""
    away = row.away_team.iloc[0] if len(row) else ""
    meta = row.iloc[0].to_dict() if len(row) else {}

    return GameData(game_string=gs, rel_path=rel_path, events=events, ball=ball,
                    player=player, lineups=lu_game, home_team=home,
                    away_team=away, meta=meta)
