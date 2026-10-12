"""
smt_utils.py
------------
Shared data-loading, geometry, and physics helpers for the SMT Data Challenge 2026
("On the Big Screen!"). All idea scripts import from this module.

Coordinate system (from the official Data Description):
  x = 0 on the home-plate -> second-base line, x > 0 toward first base (feet)
  y = 0 at the back of home plate, y > 0 toward second base (feet)
  z = height (feet); z = 0 is a real-world datum, not necessarily the ground
Tracking is sampled at 20 Hz (one frame every 50 ms). Timestamps are in ms and
begin ~3 s before the pitch is released.

player_id lookup:
  1 P, 2 C, 3 1B, 4 2B, 5 3B, 6 SS, 7 LF, 8 CF, 9 RF, 10 Batter,
  11 R1, 12 R2, 13 R3, 14 HP ump, 15-17 field ump, 18 1B coach, 19 3B coach,
  255 no-player ball event

ball_eventcode lookup:
  1 Pitch, 2 Ball Acquired, 3 Throw (BIP), 4 Ball Hit Into Play, 5 End of Play,
  6 Pickoff Throw, 7 Ball Acquired (unknown pos), 8 Throw (unknown pos),
  9 Ball Deflection, 10 Deflection off wall, 11 Home Run, 16 Ball Bounce
"""

import os
import glob
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
FT_S_TO_MPH = 0.681818          # 1 ft/s = 0.681818 mph
FRAME_MS = 50                   # 20 Hz
BASE_PATH = 8.485 * 7.5         # not used; kept for reference

# Base bag centers in field coordinates (90 ft basepaths, rotated 45 deg).
# 90 / sqrt(2) = 63.64
HOME = np.array([0.0, 0.0])
FIRST = np.array([63.64, 63.64])
SECOND = np.array([0.0, 127.28])
THIRD = np.array([-63.64, 63.64])
MOUND = np.array([0.0, 60.5])

PLAYER_LABELS = {
    1: "Pitcher", 2: "Catcher", 3: "First Baseman", 4: "Second Baseman",
    5: "Third Baseman", 6: "Shortstop", 7: "Left Fielder", 8: "Center Fielder",
    9: "Right Fielder", 10: "Batter", 11: "Runner 1B", 12: "Runner 2B",
    13: "Runner 3B",
}
INFIELD_IDS = [3, 4, 5, 6]
OUTFIELD_IDS = [7, 8, 9]

EVENT_LABELS = {
    1: "Pitch", 2: "Ball Acquired", 3: "Throw", 4: "Hit Into Play",
    5: "End of Play", 6: "Pickoff", 7: "Acquired(unk)", 8: "Throw(unk)",
    9: "Deflection", 10: "Deflection off wall", 11: "Home Run", 16: "Bounce",
}


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def list_game_dirs(data_root):
    """Return list of (game_string, dir_path) for every game that has all files."""
    out = []
    for ev in glob.glob(os.path.join(data_root, "ball-events", "*", "*", "*", "*")):
        rel = os.path.relpath(ev, os.path.join(data_root, "ball-events"))
        bp = os.path.join(data_root, "ball-positions", rel)
        pp = os.path.join(data_root, "player-positions", rel)
        if os.path.isdir(bp) and os.path.isdir(pp):
            # game_string is read from the events file
            out.append(rel)
    return sorted(out)


def load_game(data_root, rel):
    """Load the three tracking tables for one game directory (rel path like
    'ANI/IGL/y1/d173'). Returns dict of DataFrames."""
    ev = pd.read_csv(os.path.join(data_root, "ball-events", rel, "ball_events.csv"))
    bp = pd.read_csv(os.path.join(data_root, "ball-positions", rel, "ball-positions.csv"))
    pp = pd.read_csv(os.path.join(data_root, "player-positions", rel, "player-positions.csv"))
    ev = ev.dropna(subset=["play_per_game", "timestamp"])
    bp = bp.dropna(subset=["play_per_game", "timestamp"])
    pp = pp.dropna(subset=["play_per_game", "timestamp"])
    for d in (ev, bp, pp):
        # play_per_game sometimes parses as float; keep int
        d["play_per_game"] = d["play_per_game"].astype("int64")
    return {"events": ev, "ball": bp, "player": pp,
            "game_string": ev["game_string"].iloc[0]}


def load_lineups(data_root):
    return pd.read_csv(os.path.join(data_root, "lineups.csv"))


def load_game_info(data_root):
    return pd.read_csv(os.path.join(data_root, "game-info.csv"))


# ----------------------------------------------------------------------------
# Physics / geometry helpers
# ----------------------------------------------------------------------------
def _smooth(a, k=3):
    if len(a) < k or k < 2:
        return a
    kernel = np.ones(k) / k
    return np.convolve(a, kernel, mode="same")


def speed_series(df_xy, x="field_x", y="field_y", smooth=True):
    """Given a time-sorted DataFrame with x,y,timestamp, return instantaneous
    speed in ft/s (length n-1) and midpoint timestamps."""
    d = df_xy.sort_values("timestamp")
    t = d["timestamp"].to_numpy(float)
    xs = d[x].to_numpy(float)
    ys = d[y].to_numpy(float)
    if smooth:
        xs = _smooth(xs)
        ys = _smooth(ys)
    dt = np.diff(t) / 1000.0
    dist = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        sp = np.where(dt > 0, dist / dt, np.nan)
    return sp, (t[:-1] + t[1:]) / 2.0


def ball_speed_3d(df_ball):
    """Instantaneous 3-D ball speed in ft/s and midpoint timestamps."""
    d = df_ball.sort_values("timestamp")
    t = d["timestamp"].to_numpy(float)
    x = d["ball_position_x"].to_numpy(float)
    y = d["ball_position_y"].to_numpy(float)
    z = d["ball_position_z"].to_numpy(float)
    dt = np.diff(t) / 1000.0
    dist = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        sp = np.where(dt > 0, dist / dt, np.nan)
    return sp, (t[:-1] + t[1:]) / 2.0


def dist2d(p, q):
    return float(np.hypot(p[0] - q[0], p[1] - q[1]))


def player_track(player_df, play, pid):
    """Sorted track for one player in one play."""
    d = player_df[(player_df.play_per_game == play) & (player_df.player_id == pid)]
    return d.sort_values("timestamp")


def event_row(ev_df, play, code, which="first"):
    """Return the timestamp of a given event code within a play, or None."""
    r = ev_df[(ev_df.play_per_game == play) & (ev_df.ball_eventcode == code)]
    if r.empty:
        return None
    return int(r["timestamp"].iloc[0] if which == "first" else r["timestamp"].iloc[-1])


def team_from_player(code):
    """'PHD-4341' -> 'PHD'."""
    if isinstance(code, str) and "-" in code:
        return code.split("-")[0]
    return None
