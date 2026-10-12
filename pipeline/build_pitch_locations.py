"""
build_pitch_locations.py — per-pitch plate location (ball-only, fast pass).

The existing feature tables carry pitch velocity but not WHERE the pitch
crossed the plate. Location is what makes the zone/command story cards
possible, so this stage interpolates the crossing point for every pitch.

Ball tracking only (no player positions), so the full season runs in well under
a minute.

Usage: python pipeline/build_pitch_locations.py [start] [end]
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config, dataio                  # noqa: E402
from smtstory.tracking import kinematics as K        # noqa: E402
from smtstory.tracking.geometry import in_strike_zone  # noqa: E402

OUT = config.ensure_dir(config.ENGINE_OUT)
PATH = os.path.join(OUT, "pitch_locations.csv")
EV = config.EVENT


def process(rel):
    g = dataio.load_game(rel, with_player_tracking=False)
    ev, ball = g.events, g.ball
    if ev.empty or ball.empty:
        return []
    rows = []
    for play, e in ev.groupby("play_per_game"):
        p = e[e.ball_eventcode == EV["PITCH"]]
        if p.empty:
            continue
        t_pitch = int(p.timestamp.iloc[0])
        b = ball[ball.play_per_game == play]
        if len(b) < 3:
            continue
        px, pz = K.plate_crossing(b, t_pitch)
        velo = K.pitch_velocity(b, t_pitch)
        codes = set(e.ball_eventcode.astype(int).tolist())
        rows.append({
            "game_string": g.game_string, "play": int(play),
            "plate_x": round(px, 3) if np.isfinite(px) else np.nan,
            "plate_z": round(pz, 3) if np.isfinite(pz) else np.nan,
            "pitch_velo_mph": round(velo, 1) if np.isfinite(velo) else np.nan,
            # Label available from the event stream: was this pitch put in play?
            "batted": int(EV["HIT_INTO_PLAY"] in codes or EV["HOME_RUN"] in codes),
        })
    return rows


def main(start=0, end=10**6):
    games = dataio.list_games()
    allrows = []
    for i in range(start, min(end, len(games))):
        try:
            allrows.extend(process(games[i]))
        except Exception as exc:
            print("ERR", games[i], exc)
    df = pd.DataFrame(allrows)
    if df.empty:
        print("no pitches extracted")
        return
    ok = df.plate_z.notna() & df.plate_x.notna()
    df["in_zone"] = np.nan
    df.loc[ok, "in_zone"] = in_strike_zone(df.loc[ok, "plate_x"],
                                           df.loc[ok, "plate_z"]).astype(int)
    header = not os.path.exists(PATH) or start == 0
    df.to_csv(PATH, mode="w" if header else "a", header=header, index=False)
    print(f"pitches={len(df)} with_location={int(ok.sum())} "
          f"in_zone_rate={df.in_zone.mean():.3f} batted_rate={df.batted.mean():.3f}")
    print(f"plate_z: p05={df.plate_z.quantile(.05):.2f} median={df.plate_z.median():.2f} "
          f"p95={df.plate_z.quantile(.95):.2f}")
    print(f"plate_x: p05={df.plate_x.quantile(.05):.2f} median={df.plate_x.median():.2f} "
          f"p95={df.plate_x.quantile(.95):.2f}")


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 10**6
    main(a, b)
