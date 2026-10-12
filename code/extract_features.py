"""
extract_features.py
--------------------
Single-pass feature extraction over SMT tracking data. For each game it emits
play-level rows for six metric families that power the Top-10 scoreboard ideas:

  hits    -> exit velocity, launch angle, hit distance      (ideas 2,3)
  pitches -> pitch velocity                                  (idea 4)
  throws  -> fielder throw (arm) velocity                    (idea 5)
  sprints -> batter sprint speed & burst to first base       (ideas 1,9)
  catches -> outfield catch opportunities + features         (ideas 6,7,8)

Usage:
  python extract_features.py <data_root> <out_dir> <start_idx> <end_idx>
Runs on games[start_idx:end_idx] and appends to CSVs in out_dir.
"""
import sys
import os
import numpy as np
import pandas as pd
import smt_utils as U

DATA_ROOT = sys.argv[1]
OUT = sys.argv[2]
START = int(sys.argv[3])
END = int(sys.argv[4])
os.makedirs(OUT, exist_ok=True)


def robust_top_speed(sp, pct=90):
    sp = sp[np.isfinite(sp)]
    if len(sp) == 0:
        return np.nan
    return float(np.percentile(sp, pct))


def process_game(rel):
    g = U.load_game(DATA_ROOT, rel)
    ev, ball, pl, gs = g["events"], g["ball"], g["player"], g["game_string"]
    hits, pitches, throws, sprints, catches = [], [], [], [], []

    ev_sorted = ev.sort_values(["play_per_game", "timestamp"]).reset_index(drop=True)

    for play, e in ev_sorted.groupby("play_per_game"):
        e = e.reset_index(drop=True)
        b = ball[ball.play_per_game == play].sort_values("timestamp")
        if b.empty:
            continue
        codes = e.ball_eventcode.tolist()

        # ---- PITCH VELOCITY ----
        t_pitch = U.event_row(e, play, 1)
        if t_pitch is not None:
            w = b[(b.timestamp >= t_pitch) & (b.timestamp <= t_pitch + 800)]
            if len(w) >= 3:
                sp, _ = U.ball_speed_3d(w)
                pv = robust_top_speed(sp, 90) * U.FT_S_TO_MPH
                if 40 < pv < 110:
                    pitches.append((gs, play, round(pv, 1)))

        # ---- HIT: exit velo, launch, distance ----
        t_hit = U.event_row(e, play, 4)
        if t_hit is not None:
            w = b[(b.timestamp >= t_hit) & (b.timestamp <= t_hit + 400)]
            if len(w) >= 3:
                ww = w.sort_values("timestamp").reset_index(drop=True)
                sp, _ = U.ball_speed_3d(ww)
                ev_mph = robust_top_speed(sp, 95) * U.FT_S_TO_MPH
                # launch angle from first ~150ms velocity vector
                dz = ww.ball_position_z.values
                dy = ww.ball_position_y.values
                dx = ww.ball_position_x.values
                n = min(4, len(ww) - 1)
                horiz = np.hypot(dx[n] - dx[0], dy[n] - dy[0])
                vert = dz[n] - dz[0]
                launch = np.degrees(np.arctan2(vert, horiz)) if horiz > 0 else np.nan
                # hit distance: max horizontal distance of ball from home in play
                ballplay = b
                hd = np.max(np.hypot(ballplay.ball_position_x, ballplay.ball_position_y))
                if 20 < ev_mph < 125:
                    hits.append((gs, play, round(ev_mph, 1),
                                 round(float(launch), 1) if np.isfinite(launch) else np.nan,
                                 round(float(hd), 1)))

            # ---- SPRINT to first (batter id 10) ----
            bat = U.player_track(pl, play, 10)
            bat = bat[bat.timestamp >= t_hit]
            if len(bat) >= 5:
                sp, tm = U.speed_series(bat)
                top = robust_top_speed(sp, 95)
                # burst: peak accel over 150ms early
                spf = sp[np.isfinite(sp)]
                if np.isfinite(top) and top > 5:
                    # only count as a real run if batter moves toward 1B a good distance
                    xy0 = bat.iloc[0][["field_x", "field_y"]].values.astype(float)
                    moved = np.max(np.hypot(bat.field_x - xy0[0], bat.field_y - xy0[1]))
                    if moved > 30 and top < 35:  # filter tracking glitches
                        sprints.append((gs, play, round(top, 2),
                                        round(top * U.FT_S_TO_MPH, 2), round(float(moved), 1)))

        # ---- THROWS (arm strength): event code 3 = throw BIP ----
        thr = e[e.ball_eventcode == 3]
        for _, tr in thr.iterrows():
            tt = int(tr.timestamp)
            pid = int(tr.player_id)
            if pid not in (U.INFIELD_IDS + U.OUTFIELD_IDS + [2]):
                continue
            w = b[(b.timestamp >= tt) & (b.timestamp <= tt + 500)]
            if len(w) >= 3:
                sp, _ = U.ball_speed_3d(w)
                tv = robust_top_speed(sp, 90) * U.FT_S_TO_MPH
                if 30 < tv < 105:
                    throws.append((gs, play, pid, round(tv, 1)))

        # ---- CATCH OPPORTUNITIES (outfield) ----
        # a hit (code4) followed within the play by an outfielder acquire (code2)
        if t_hit is not None:
            after = e[e.timestamp > t_hit].reset_index(drop=True)
            caught = 0
            fielder = None
            t_end = None
            catch_xy = None
            for _, r in after.iterrows():
                if r.ball_eventcode == 2 and int(r.player_id) in U.OUTFIELD_IDS:
                    caught = 1
                    fielder = int(r.player_id)
                    t_end = int(r.timestamp)
                    break
                if r.ball_eventcode in (2, 5) and int(r.player_id) in U.INFIELD_IDS:
                    break  # infield play, not an OF fly
            # ball landing region: use max horizontal distance & final descent
            hd = np.max(np.hypot(b.ball_position_x, b.ball_position_y))
            if hd > 130:  # ball reached the outfield
                if caught and fielder is not None and t_end is not None:
                    # fielder position at hit and at catch
                    ftrk = U.player_track(pl, play, fielder)
                    p_hit = ftrk[ftrk.timestamp <= t_hit]
                    p_catch = ftrk[ftrk.timestamp <= t_end]
                    if not p_hit.empty and not p_catch.empty:
                        start = p_hit.iloc[-1][["field_x", "field_y"]].values.astype(float)
                        end = p_catch.iloc[-1][["field_x", "field_y"]].values.astype(float)
                        route = U.dist2d(start, end)
                        hang = (t_end - t_hit) / 1000.0
                        # closing speed on the ball
                        sp, _ = U.speed_series(ftrk[(ftrk.timestamp >= t_hit) &
                                                    (ftrk.timestamp <= t_end)])
                        closem = robust_top_speed(sp, 90) if len(sp) else np.nan
                        if 0.4 < hang < 8 and route < 160:
                            catches.append((gs, play, fielder, 1, round(route, 1),
                                            round(hang, 2),
                                            round(float(closem) if np.isfinite(closem) else 0, 2),
                                            round(float(end[0]), 1), round(float(end[1]), 1)))
                else:
                    # non-catch fly to OF: landing point = ball xy at min z after hit
                    bpost = b[b.timestamp >= t_hit]
                    if len(bpost) >= 3:
                        idx = bpost.ball_position_z.values.argmin()
                        land = bpost.iloc[idx][["ball_position_x", "ball_position_y"]].values.astype(float)
                        t_land = int(bpost.iloc[idx].timestamp)
                        # nearest OF at hit
                        best, bestd = None, 1e9
                        for oid in U.OUTFIELD_IDS:
                            ot = U.player_track(pl, play, oid)
                            oh = ot[ot.timestamp <= t_hit]
                            if oh.empty:
                                continue
                            pos = oh.iloc[-1][["field_x", "field_y"]].values.astype(float)
                            d = U.dist2d(pos, land)
                            if d < bestd:
                                bestd, best = d, (oid, pos)
                        if best is not None:
                            hang = (t_land - t_hit) / 1000.0
                            if 0.4 < hang < 8 and bestd < 200:
                                catches.append((gs, play, best[0], 0, round(bestd, 1),
                                                round(hang, 2), 0.0,
                                                round(float(land[0]), 1), round(float(land[1]), 1)))
    return hits, pitches, throws, sprints, catches


def append(path, rows, cols):
    if not rows:
        return
    df = pd.DataFrame(rows, columns=cols)
    header = not os.path.exists(path)
    df.to_csv(path, mode="a", header=header, index=False)


games = U.list_game_dirs(DATA_ROOT)
for i in range(START, min(END, len(games))):
    rel = games[i]
    try:
        h, p, t, s, c = process_game(rel)
    except Exception as ex:
        print("ERR", rel, ex)
        continue
    append(os.path.join(OUT, "hits.csv"), h,
           ["game_string", "play", "exit_velo_mph", "launch_deg", "hit_distance_ft"])
    append(os.path.join(OUT, "pitches.csv"), p,
           ["game_string", "play", "pitch_velo_mph"])
    append(os.path.join(OUT, "throws.csv"), t,
           ["game_string", "play", "fielder_id", "throw_velo_mph"])
    append(os.path.join(OUT, "sprints.csv"), s,
           ["game_string", "play", "sprint_ftps", "sprint_mph", "dist_moved_ft"])
    append(os.path.join(OUT, "catches.csv"), c,
           ["game_string", "play", "fielder_id", "catch_made", "route_ft",
            "hang_s", "close_ftps", "land_x", "land_y"])
    print("done", i, rel)
