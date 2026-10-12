"""
extract_hits_v2.py
-------------------
Cleaner batted-ball metrics using ONLY ball-events + ball-positions (fast, no
player tracking needed). Improves on the first pass by measuring carry distance
at the ball's first bounce / landing rather than the max distance over the whole
play (which was inflated by relay throws), and by using a lightly smoothed peak
exit velocity.

Usage: python extract_hits_v2.py <data_root> <out_csv> <start> <end>
"""
import sys, os
import numpy as np, pandas as pd
import smt_utils as U

DATA, OUT, START, END = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
games = U.list_game_dirs(DATA)
rows = []
for i in range(START, min(END, len(games))):
    rel = games[i]
    try:
        ev = pd.read_csv(os.path.join(DATA, "ball-events", rel, "ball_events.csv"))
        bp = pd.read_csv(os.path.join(DATA, "ball-positions", rel, "ball-positions.csv"))
    except Exception as e:
        print("ERR", rel, e); continue
    ev = ev.dropna(subset=["play_per_game", "timestamp"])
    bp = bp.dropna(subset=["play_per_game", "timestamp"])
    if ev.empty or bp.empty:
        print("skip empty", rel); continue
    ev["play_per_game"] = ev.play_per_game.astype(int)
    bp["play_per_game"] = bp.play_per_game.astype(int)
    gs = ev.game_string.iloc[0]
    for play, e in ev.groupby("play_per_game"):
      try:
        hit = e[e.ball_eventcode == 4]
        if hit.empty:
            continue
        t_hit = int(hit.timestamp.iloc[0])
        b = bp[(bp.play_per_game == play) & (bp.timestamp >= t_hit)].sort_values("timestamp")
        if len(b) < 4:
            continue
        b = b.reset_index(drop=True)
        # exit velo: smoothed peak speed in first 400 ms
        w = b[b.timestamp <= t_hit + 400]
        if len(w) < 3:
            continue
        sp, _ = U.ball_speed_3d(w)
        sp = sp[np.isfinite(sp)]
        if len(sp) == 0:
            continue
        ev_mph = float(np.percentile(sp, 90)) * U.FT_S_TO_MPH
        # launch angle from first ~150 ms
        n = min(4, len(w) - 1)
        ww = w.reset_index(drop=True)
        horiz = np.hypot(ww.ball_position_x[n]-ww.ball_position_x[0],
                         ww.ball_position_y[n]-ww.ball_position_y[0])
        vert = ww.ball_position_z[n]-ww.ball_position_z[0]
        launch = np.degrees(np.arctan2(vert, horiz)) if horiz > 0 else np.nan
        # carry distance: distance from home at the first bounce (code 16) if present,
        # else at the ball's first local z-minimum (landing). Cap at plausible range.
        bounce = e[(e.ball_eventcode == 16) & (e.timestamp > t_hit)]
        land_dist = np.nan
        if not bounce.empty:
            tb = int(bounce.timestamp.iloc[0])
            near = b.iloc[(b.timestamp - tb).abs().argmin()]
            land_dist = float(np.hypot(near.ball_position_x, near.ball_position_y))
        else:
            # first time the descending ball reaches ~ contact height again
            z = b.ball_position_z.to_numpy()
            if len(z) > 3:
                apex = z.argmax()
                after = z[apex:]
                idx = apex + (np.argmin(np.abs(after - z[0])) if len(after) else 0)
                row = b.iloc[min(idx, len(b)-1)]
                land_dist = float(np.hypot(row.ball_position_x, row.ball_position_y))
        is_hr = int(not e[(e.ball_eventcode == 11)].empty)
        if 20 < ev_mph < 122 and np.isfinite(land_dist) and land_dist < 480:
            rows.append((gs, play, round(ev_mph, 1),
                         round(float(launch), 1) if np.isfinite(launch) else np.nan,
                         round(land_dist, 1), is_hr))
      except Exception:
        continue
    print("done", i, rel)

df = pd.DataFrame(rows, columns=["game_string", "play", "exit_velo_mph",
                                 "launch_deg", "carry_ft", "is_hr"])
header = not os.path.exists(OUT)
df.to_csv(OUT, mode="a", header=header, index=False)
