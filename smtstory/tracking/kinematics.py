"""
kinematics.py — physical measurements derived from 20 Hz tracking.

Every function here is pure: it takes tracking frames and returns numbers, with
no knowledge of game state or presentation. This is what makes the same code
usable by the offline pipeline and by a live scoreboard feed.

REUSE NOTE: speed differencing/smoothing is delegated to the original
smt_utils implementations that were already validated on this dataset.
"""
import numpy as np

import smt_utils as U

from .. import config

FT_S_TO_MPH = config.FT_S_TO_MPH


def ball_speed_3d(ball_frames):
    """Instantaneous 3-D ball speed (ft/s) between consecutive frames."""
    sp, _ = U.ball_speed_3d(ball_frames)
    return sp


def player_speed(player_frames):
    """Instantaneous 2-D player speed (ft/s), lightly smoothed."""
    sp, _ = U.speed_series(player_frames)
    return sp


def top_speed(speeds, pct=90):
    """Robust peak speed: a high percentile resists single-frame tracking spikes."""
    s = np.asarray(speeds, dtype=float)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return np.nan
    return float(np.percentile(s, pct))


def distance_2d(p, q):
    return float(np.hypot(p[0] - q[0], p[1] - q[1]))


# ---------------------------------------------------------------- batted ball
def exit_velocity(ball_frames, t_hit, window_ms=400, pct=90):
    """Exit velocity in mph from the ball's flight just after contact."""
    w = ball_frames[(ball_frames.timestamp >= t_hit) &
                    (ball_frames.timestamp <= t_hit + window_ms)]
    if len(w) < 3:
        return np.nan
    return top_speed(ball_speed_3d(w), pct) * FT_S_TO_MPH


def launch_angle(ball_frames, t_hit, frames=4):
    """Launch angle (degrees) from the initial velocity vector after contact."""
    w = ball_frames[ball_frames.timestamp >= t_hit].sort_values("timestamp")
    if len(w) < 2:
        return np.nan
    n = min(frames, len(w) - 1)
    x = w.ball_position_x.to_numpy(float)
    y = w.ball_position_y.to_numpy(float)
    z = w.ball_position_z.to_numpy(float)
    horiz = np.hypot(x[n] - x[0], y[n] - y[0])
    if horiz <= 0:
        return np.nan
    return float(np.degrees(np.arctan2(z[n] - z[0], horiz)))


def carry_distance(ball_frames, t_hit, bounce_ts=None):
    """Horizontal distance from home plate where the ball first lands.

    Uses the first recorded bounce when available; otherwise the point after the
    apex where the ball returns to roughly its contact height. This avoids the
    common error of measuring the ball's maximum distance over the whole play,
    which is inflated by relay throws.
    """
    b = ball_frames[ball_frames.timestamp >= t_hit].sort_values("timestamp")
    if len(b) < 3:
        return np.nan
    if bounce_ts is not None:
        near = b.iloc[(b.timestamp - bounce_ts).abs().argmin()]
        return float(np.hypot(near.ball_position_x, near.ball_position_y))
    z = b.ball_position_z.to_numpy(float)
    apex = int(z.argmax())
    after = z[apex:]
    if after.size == 0:
        return np.nan
    idx = apex + int(np.argmin(np.abs(after - z[0])))
    row = b.iloc[min(idx, len(b) - 1)]
    return float(np.hypot(row.ball_position_x, row.ball_position_y))


# ---------------------------------------------------------------- pitching
def pitch_velocity(ball_frames, t_pitch, window_ms=800, pct=90):
    """Pitch velocity in mph measured over the flight to the plate."""
    w = ball_frames[(ball_frames.timestamp >= t_pitch) &
                    (ball_frames.timestamp <= t_pitch + window_ms)]
    if len(w) < 3:
        return np.nan
    return top_speed(ball_speed_3d(w), pct) * FT_S_TO_MPH


def plate_crossing(ball_frames, t_pitch, plate_y=0.0):
    """Interpolate where the pitch crosses the front of home plate.

    Returns (x, z) in feet, or (nan, nan). The ball travels from large y toward
    y = 0, so we find the first frame pair that brackets the plate and linearly
    interpolate between them.
    """
    w = ball_frames[ball_frames.timestamp >= t_pitch].sort_values("timestamp")
    if len(w) < 2:
        return (np.nan, np.nan)
    y = w.ball_position_y.to_numpy(float)
    x = w.ball_position_x.to_numpy(float)
    z = w.ball_position_z.to_numpy(float)
    for i in range(len(w) - 1):
        if y[i] > plate_y >= y[i + 1]:
            span = y[i] - y[i + 1]
            f = (y[i] - plate_y) / span if span > 0 else 0.0
            return (float(x[i] + f * (x[i + 1] - x[i])),
                    float(z[i] + f * (z[i + 1] - z[i])))
    return (np.nan, np.nan)


# ---------------------------------------------------------------- defense
def route_distance(player_frames, t_start, t_end):
    """Straight-line distance a fielder covered between two timestamps."""
    trk = player_frames.sort_values("timestamp")
    a = trk[trk.timestamp <= t_start]
    b = trk[trk.timestamp <= t_end]
    if a.empty or b.empty:
        return np.nan
    p = a.iloc[-1][["field_x", "field_y"]].to_numpy(float)
    q = b.iloc[-1][["field_x", "field_y"]].to_numpy(float)
    return distance_2d(p, q)


def path_length(player_frames, t_start, t_end):
    """Actual distance travelled along the fielder's path (for route efficiency)."""
    trk = player_frames[(player_frames.timestamp >= t_start) &
                        (player_frames.timestamp <= t_end)].sort_values("timestamp")
    if len(trk) < 2:
        return np.nan
    dx = np.diff(trk.field_x.to_numpy(float))
    dy = np.diff(trk.field_y.to_numpy(float))
    return float(np.sum(np.hypot(dx, dy)))


def route_efficiency(player_frames, t_start, t_end):
    """Straight-line distance / actual path length, in (0, 1]. 1.0 = perfect route."""
    direct = route_distance(player_frames, t_start, t_end)
    actual = path_length(player_frames, t_start, t_end)
    if not np.isfinite(direct) or not np.isfinite(actual) or actual <= 0:
        return np.nan
    return float(min(1.0, direct / actual))
