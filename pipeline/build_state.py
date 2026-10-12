"""
build_state.py — Stage 1 of the pipeline.

Reconstructs game state (outs, runs, score, outcomes) for every game and caches
the season-level at-bat table. Runs without player tracking, so it is fast.

Usage:
    python pipeline/build_state.py [start] [end]
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config, dataio                      # noqa: E402
from smtstory.state import reconstruct_game              # noqa: E402

OUT = config.ensure_dir(config.ENGINE_OUT)
AB_PATH = os.path.join(OUT, "atbats.csv")
SUM_PATH = os.path.join(OUT, "game_summaries.csv")


def main(start=0, end=10**6):
    games = dataio.list_games()
    frames, sums, errors = [], [], []
    for i in range(start, min(end, len(games))):
        rel = games[i]
        try:
            g = dataio.load_game(rel, with_player_tracking=False)
            df, s = reconstruct_game(g)
            frames.append(df)
            sums.append(s)
        except Exception as exc:  # keep going; report at the end
            errors.append((rel, str(exc)))
    if not frames:
        print("no games reconstructed")
        return

    ab = pd.concat(frames, ignore_index=True)
    summ = pd.DataFrame(sums)

    # Attach the eventual game result so win probability has a target.
    finals = summ.set_index("game_string")[["home_final", "away_final"]]
    ab = ab.join(finals, on="game_string")
    home_won = (ab.home_final > ab.away_final)
    batting_is_home = ab.half_inning.eq("Bottom")
    ab["batting_team_won"] = (batting_is_home & home_won) | (~batting_is_home & ~home_won)
    ab["batting_team_won"] = ab["batting_team_won"].astype(int)

    header = not os.path.exists(AB_PATH) or start == 0
    ab.to_csv(AB_PATH, mode="w" if header else "a", header=header, index=False)
    summ.to_csv(SUM_PATH, mode="w" if header else "a", header=header, index=False)

    print(f"games={len(summ)} at_bats={len(ab)} errors={len(errors)}")
    print(f"  runs/game={summ.total_runs.mean():.2f} hits/game={summ.hits.mean():.2f} "
          f"balanced={summ.balanced_rate.mean():.3f}")
    for rel, msg in errors[:5]:
        print("  ERR", rel, msg)


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 10**6
    main(a, b)
