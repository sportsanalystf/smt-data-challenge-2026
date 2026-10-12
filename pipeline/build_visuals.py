"""
build_visuals.py — Stage 5 of the pipeline.

Renders the broadcast graphics for the showcase game: win probability, leverage,
momentum, the top play's field overlay, the attack-zone heat map, and the story
cards that fired on the biggest moment.

Usage: python pipeline/build_visuals.py
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config, dataio                       # noqa: E402
from smtstory.cards import default_registry, PlayContext  # noqa: E402
from smtstory.viz import (win_probability_chart, leverage_timeline,   # noqa: E402
                          momentum_timeline, play_overlay, spray_chart,
                          render_card, render_card_strip, zone_heatmap)

OUT = config.ENGINE_OUT
FIG = config.ensure_dir(os.path.join(config.OUTPUT_DIR, "engine_figures"))


def main():
    game = pd.read_csv(os.path.join(OUT, "showcase_game.csv"), low_memory=False)
    with open(os.path.join(OUT, "highlight_packages.json")) as f:
        bundle = json.load(f)
    gs = bundle["game_string"]
    summary = bundle.get("summary", {})
    home = summary.get("home_team", "HOME")
    away = summary.get("away_team", "AWAY")
    print(f"showcase: {gs}  ({away} at {home})")

    made = []

    # ------------------------------------------------------------ timelines
    made.append(win_probability_chart(
        game, home, away, os.path.join(FIG, "wp_chart.png")))
    made.append(leverage_timeline(game, os.path.join(FIG, "leverage.png")))
    made.append(momentum_timeline(game, out_path=os.path.join(FIG, "momentum.png")))

    # ------------------------------------------------------- attack zone map
    try:
        with open(os.path.join(OUT, "probability_models.pkl"), "rb") as f:
            pm = pickle.load(f)
        made.append(zone_heatmap(pm["zone"], os.path.join(FIG, "attack_zone.png")))
    except Exception as exc:
        print("zone heatmap skipped:", exc)

    # ------------------------------------------------------------ spray chart
    try:
        scored = pd.read_csv(os.path.join(OUT, "catches_scored.csv"))
        sub = scored[scored.game_string == gs]
        if len(sub) >= 5:
            made.append(spray_chart(
                sub.rename(columns={"land_x": "land_x", "land_y": "land_y"}),
                os.path.join(FIG, "spray_chart.png"),
                title="BALLS TO THE OUTFIELD",
                subtitle=f"{away} at {home} — colored by catch probability",
                color_by="catch_prob"))
    except Exception as exc:
        print("spray chart skipped:", exc)

    # -------------------------------------------------- top play field overlay
    top = bundle["game_recap"]["top_play"]
    try:
        rel = dataio.game_dir_from_string(gs)
        g = dataio.load_game(rel, with_player_tracking=True)
        play_no = int(top["play"])
        ball = g.ball[g.ball.play_per_game == play_no].sort_values("timestamp")
        batter = g.player[(g.player.play_per_game == play_no) &
                          (g.player.player_id == 10)].sort_values("timestamp")
        ann = (f"{top['description']}\n"
               f"WPA {top['wpa']*100:+.0f}%   ·   Leverage {top['leverage_index']:.1f}")
        made.append(play_overlay(
            ball, fielder_frames=None, runner_frames=batter,
            out_path=os.path.join(FIG, "top_play.png"),
            title="THE BIGGEST MOMENT", subtitle=top["narrative"][:90],
            annotation=ann))
    except Exception as exc:
        print("top play overlay skipped:", exc)

    # ------------------------------------------------------------ story cards
    registry = default_registry()
    rows = game.to_dict("records")
    best = max(rows, key=lambda r: r.get("highlight_score") or 0)
    ctx = PlayContext({k: (None if (isinstance(v, float) and not np.isfinite(v))
                           else v) for k, v in best.items()})
    payloads = registry.surface(ctx, limit=4)
    if payloads:
        made.append(render_card_strip(
            payloads, os.path.join(FIG, "story_cards_strip.png")))
        made.append(render_card(payloads[0],
                                os.path.join(FIG, "story_card_hero.png"),
                                gauge_fraction=0.8))

    # -------------------------------------------- a defensive card, if present
    try:
        scored = pd.read_csv(os.path.join(OUT, "catches_scored.csv"))
        gem = scored.sort_values("catch_prob").iloc[0]
        gctx = PlayContext({"catch_prob": float(gem.catch_prob), "catch_made": 1,
                            "route_ft": float(gem.route_ft),
                            "hang_s": float(gem.hang_s), "fielder": "OUTFIELDER"})
        gpayloads = registry.surface(gctx, limit=3)
        if gpayloads:
            made.append(render_card(gpayloads[0],
                                    os.path.join(FIG, "story_card_webgem.png")))
    except Exception as exc:
        print("web gem card skipped:", exc)

    print(f"\nrendered {len([m for m in made if m])} figures into {FIG}")
    for m in made:
        if m:
            print("  ", os.path.basename(m))


if __name__ == "__main__":
    main()
