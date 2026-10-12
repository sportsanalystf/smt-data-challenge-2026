"""Data access layer for the SMT tables."""
from .loaders import (  # noqa: F401
    list_games, load_game, load_lineups, load_game_info,
    game_dir_from_string, GameData,
)
