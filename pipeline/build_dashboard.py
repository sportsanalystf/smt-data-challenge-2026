"""
build_dashboard.py — Stage 6 of the pipeline.

Writes the self-contained interactive scoreboard for the showcase game.

Usage: python pipeline/build_dashboard.py [game_string]
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config              # noqa: E402
from smtstory.web import build_dashboard  # noqa: E402

OUT = config.ENGINE_OUT


def main(game_string=None):
    scored = pd.read_csv(os.path.join(OUT, "atbats_scored.csv"), low_memory=False)
    summaries = pd.read_csv(os.path.join(OUT, "game_summaries.csv"))

    if game_string is None:
        with open(os.path.join(OUT, "highlight_packages.json")) as f:
            game_string = json.load(f)["game_string"]

    game = scored[scored.game_string == game_string].copy()
    srow = summaries[summaries.game_string == game_string]
    summary = srow.iloc[0].to_dict() if len(srow) else {"game_string": game_string}

    dest = os.path.join(config.OUTPUT_DIR, "scoreboard_dashboard.html")
    build_dashboard(game, summary, dest)
    size_kb = os.path.getsize(dest) / 1024
    print(f"wrote {dest} ({size_kb:.0f} KB, {len(game)} plays)")
    print(f"game: {summary.get('away_team')} {summary.get('away_final')} @ "
          f"{summary.get('home_team')} {summary.get('home_final')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
