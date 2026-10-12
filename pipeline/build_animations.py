"""
build_animations.py — render play animations as GIFs.

Picks representative plays from the showcase game (the biggest swing, a web gem,
a strikeout) and renders each as an animated GIF, plus a pitch-sequence
animation for the strikeout.

Usage: python pipeline/build_animations.py [game_string]
"""
import json
import os
import pickle
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config, dataio                       # noqa: E402
from components import c10_animation as anim              # noqa: E402
from components import c03_tracking_features as c03       # noqa: E402

OUT = config.ensure_dir(os.path.join(config.OUTPUT_DIR, "animations"))
ENGINE = config.ENGINE_OUT


def main(game_string=None):
    if game_string is None:
        with open(os.path.join(ENGINE, "highlight_packages.json")) as f:
            game_string = json.load(f)["game_string"]

    print(f"animating plays from {game_string}")
    game = dataio.load_game(dataio.game_dir_from_string(game_string),
                            with_player_tracking=True)
    scored = pd.read_csv(os.path.join(ENGINE, "atbats_scored.csv"),
                         low_memory=False)
    g = scored[scored.game_string == game_string].copy()

    made = []

    # ---- 1. the biggest swing of the game
    top = g.loc[g.wpa.abs().idxmax()]
    p = anim.animate_play(
        game, int(top.last_play),
        os.path.join(OUT, "play_turning_point.gif"),
        title="THE TURNING POINT",
        subtitle=(f"{top.batter} — {str(top.outcome).replace('_', ' ')} — "
                  f"WPA {top.wpa*100:+.0f}%"))
    made.append(p)
    print("  turning point ->", os.path.basename(p))

    # ---- 2. the best defensive play, if the game had one
    try:
        cs = pd.read_csv(os.path.join(ENGINE, "catches_scored.csv"))
        cg = cs[(cs.game_string == game_string) & (cs.catch_made == 1)]
        if len(cg):
            gem = cg.sort_values("catch_prob").iloc[0]
            p = anim.animate_play(
                game, int(gem.play),
                os.path.join(OUT, "play_web_gem.gif"),
                title="WEB GEM",
                subtitle=(f"{gem.route_ft:.0f} ft in {gem.hang_s:.1f}s — "
                          f"{gem.catch_prob*100:.0f}% catch probability"))
            made.append(p)
            print("  web gem ->", os.path.basename(p))
    except Exception as exc:
        print("  web gem skipped:", exc)

    # ---- 3. a strikeout: field replay plus the pitch sequence
    try:
        with open(os.path.join(ENGINE, "playbook.json")) as f:
            pb = json.load(f)
        ks = [a for a in pb["at_bats"] if a.get("strikeout_verdict")]
        ks.sort(key=lambda a: -(a["strikeout_verdict"].get("nastiness") or 0))
        if ks:
            k = ks[0]
            v = k["strikeout_verdict"]
            seq = pd.DataFrame(k["pitches"])
            p = anim.animate_pitch_sequence(
                seq, pb["zone"],
                os.path.join(OUT, "pitch_sequence_strikeout.gif"),
                title=f"PUTAWAY — {v['verdict']} ({v['nastiness']:.0f}/100)")
            made.append(p)
            print("  pitch sequence ->", os.path.basename(p))

            p = anim.animate_play(
                game, int(k["key_play"]),
                os.path.join(OUT, "play_strikeout.gif"),
                title="THE PUTAWAY PITCH",
                subtitle=v["narrative"][:70])
            made.append(p)
            print("  strikeout replay ->", os.path.basename(p))
    except Exception as exc:
        print("  strikeout skipped:", exc)

    idx = anim.animation_index(made)
    idx.to_csv(os.path.join(OUT, "animation_index.csv"), index=False)
    print("\n" + idx[["animation", "size_kb"]].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
