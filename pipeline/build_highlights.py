"""
build_highlights.py — Stage 4 of the pipeline.

Scores every play with the Highlight Score, attaches per-game context (was this
the hardest-hit ball of the night?), and generates the highlight packages plus
the story cards for a chosen showcase game.

Usage:
    python pipeline/build_highlights.py [game_string]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                                # noqa: E402
from smtstory.analytics import HighlightScorer             # noqa: E402
from smtstory.highlights import HighlightEngine            # noqa: E402
from smtstory.narrative import NarrativeGenerator          # noqa: E402
from smtstory.cards import default_registry                # noqa: E402

OUT = config.ensure_dir(config.ENGINE_OUT)


def add_game_context(df):
    """Per-game superlatives that make the narration concrete."""
    df = df.copy()
    for col, flag in (("exit_velo_mph", "is_hardest_of_game"),
                      ("pitch_velo_mph", "is_fastest_of_game")):
        if col in df.columns:
            mx = df.groupby("game_string")[col].transform("max")
            df[flag] = (df[col] >= mx - 1e-9) & df[col].notna()
        else:
            df[flag] = False
    # Identify the fielder on catch plays for the defensive cards.
    if "fielder_id" in df.columns:
        df["fielder"] = df.get("fielder")
    return df


def main(showcase=None):
    path = os.path.join(OUT, "atbats_full.csv")
    df = pd.read_csv(path, low_memory=False)
    print(f"loaded {len(df)} at-bats / {df.game_string.nunique()} games")

    df = add_game_context(df)

    # ---------------------------------------------------------- score plays
    scorer = HighlightScorer()
    df = scorer.score_frame(df)
    df.to_csv(os.path.join(OUT, "atbats_scored.csv"), index=False)
    print(f"highlight score: mean={df.highlight_score.mean():.1f} "
          f"p95={df.highlight_score.quantile(.95):.1f} "
          f"max={df.highlight_score.max():.1f}")

    # ------------------------------------------------------- season leaders
    top = df.sort_values("highlight_score", ascending=False).head(15)
    cols = [c for c in ["game_string", "inning", "half_inning", "batter", "outcome",
                        "wpa", "leverage_index", "exit_velo_mph", "hit_distance_ft",
                        "catch_prob", "highlight_score"] if c in top.columns]
    print("\nTOP 10 MOMENTS OF THE SEASON")
    print(top[cols].head(10).round(3).to_string(index=False))
    top.to_csv(os.path.join(OUT, "season_top_moments.csv"), index=False)

    # ------------------------------------------------------ showcase game
    summaries = pd.read_csv(os.path.join(OUT, "game_summaries.csv"))
    if showcase is None:
        # Choose the most dramatic game: biggest single swing plus total drama.
        drama = (df.groupby("game_string")
                   .agg(top_hs=("highlight_score", "max"),
                        max_wpa=("wpa", lambda s: s.abs().max()),
                        lead=("leverage_index", "max"))
                   .assign(score=lambda d: d.top_hs + 100 * d.max_wpa + 5 * d.lead)
                   .sort_values("score", ascending=False))
        showcase = drama.index[0]
    print(f"\nSHOWCASE GAME: {showcase}")

    game = df[df.game_string == showcase].copy()
    srow = summaries[summaries.game_string == showcase]
    summary = srow.iloc[0].to_dict() if len(srow) else {}

    narrator = NarrativeGenerator({
        "max_exit_velo_game": game.exit_velo_mph.max()
        if "exit_velo_mph" in game else None,
        "max_pitch_velo_game": game.pitch_velo_mph.max()
        if "pitch_velo_mph" in game else None,
    })
    engine = HighlightEngine(default_registry(), narrator)

    packages = engine.all_packages(game)
    recaps = engine.inning_recaps(game)
    recap = engine.game_recap(game, summary)

    bundle = {
        "game_string": showcase,
        "summary": {k: (int(v) if isinstance(v, (np.integer,)) else v)
                    for k, v in summary.items()},
        "game_recap": recap,
        "packages": packages,
        "inning_recaps": recaps,
    }
    with open(os.path.join(OUT, "highlight_packages.json"), "w") as f:
        json.dump(bundle, f, indent=2, default=str)

    print(f"\nGAME RECAP: {recap.get('headline','')}")
    print("\nPACKAGES BUILT:")
    for name, p in packages.items():
        print(f"  {p['title']:28s} {len(p['highlights'])} clips")

    tp = recap.get("top_play", {})
    print(f"\nTOP PLAY: {tp.get('description','')}")
    print(f"  -> {tp.get('narrative','')}")
    for ins in tp.get("insights", []):
        print(f"  -> {ins}")
    print(f"  cards: {[c['title'] for c in tp.get('cards', [])]}")

    game.to_csv(os.path.join(OUT, "showcase_game.csv"), index=False)
    print(f"\nwrote highlight_packages.json and showcase_game.csv")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
