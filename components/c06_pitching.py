"""
c06_pitching.py — COMPONENT 6: Pitching.

Mirrors R/R06_pitching.R.

Scoreboard products in this file
    Radar Gun Live      pitch velocity leaderboard and per-pitcher averages
    Velocity Heartbeat  a starter's velocity across an outing
    Effective Velocity  perceived speed adjusted for release extension
    Late Life           movement from release to the plate, gravity removed

SCOPE NOTE: spin rate is not present in the SMT data and cannot be recovered
from positional tracking, so no spin product is offered. Movement, extension and
perceived velocity are all directly measurable and are used instead.
"""
import numpy as np
import pandas as pd

from smtstory.analytics.tunneling import (fit_trajectory, late_break_in,
                                          effective_velocity, RUBBER_TO_PLATE_FT)

MAX_PLAUSIBLE_VELO = 103.0   # elite ceiling for this level; above = tracking spike


def _attach(df, lineups, column, play_col="play"):
    m = lineups[["game_string", "play_per_game", column]].rename(
        columns={"play_per_game": play_col, column: "player"})
    out = df.merge(m, on=["game_string", play_col], how="left")
    out["team"] = out.player.str.split("-").str[0]
    return out


# ----------------------------------------------------------- Radar Gun Live
def radar_gun(pitches, lineups, min_pitches=30, top=15):
    """Pitch velocity leaderboard."""
    p = pitches[pitches.pitch_velo_mph <= MAX_PLAUSIBLE_VELO]
    p = _attach(p, lineups, "pitcher").dropna(subset=["player"])
    lb = (p.groupby("player")
            .agg(max_velo=("pitch_velo_mph", "max"),
                 avg_velo=("pitch_velo_mph", "mean"),
                 p90_velo=("pitch_velo_mph",
                           lambda x: round(float(np.percentile(x, 90)), 1)),
                 pitches=("pitch_velo_mph", "size"),
                 team=("team", "first"))
            .reset_index())
    lb = lb[lb.pitches >= min_pitches].sort_values("max_velo", ascending=False)
    lb["avg_velo"] = lb.avg_velo.round(1)
    return lb.head(top).reset_index(drop=True)


# ------------------------------------------------------ Velocity Heartbeat
def velocity_heartbeat(pitches, lineups, game_string, pitcher=None):
    """How a pitcher's velocity holds across an outing.

    Returns per-pitch velocity in sequence plus a rolling average, which is what
    the scoreboard animates as a heartbeat line.
    """
    p = pitches[(pitches.game_string == game_string) &
                (pitches.pitch_velo_mph <= MAX_PLAUSIBLE_VELO)]
    p = _attach(p, lineups, "pitcher").dropna(subset=["player"])
    if pitcher is None and len(p):
        pitcher = p.player.value_counts().idxmax()
    p = p[p.player == pitcher].sort_values("play").reset_index(drop=True)
    if p.empty:
        return p, {}
    p["pitch_number"] = np.arange(1, len(p) + 1)
    p["rolling_avg"] = p.pitch_velo_mph.rolling(10, min_periods=3).mean().round(1)
    first10 = p.pitch_velo_mph.head(10).mean()
    last10 = p.pitch_velo_mph.tail(10).mean()
    summary = {
        "pitcher": pitcher,
        "pitches": int(len(p)),
        "avg_velo": round(float(p.pitch_velo_mph.mean()), 1),
        "first_10_avg": round(float(first10), 1),
        "last_10_avg": round(float(last10), 1),
        "velo_held": round(float(last10 - first10), 1),
    }
    return p[["pitch_number", "play", "pitch_velo_mph", "rolling_avg"]], summary


# ------------------------------------------------------ Effective Velocity
def effective_velocity_table(game, plays, velos, league_extension_ft=5.5, top=None):
    """Perceived speed once release extension is accounted for.

    A pitcher who releases a foot closer to the plate shortens the flight and
    steals reaction time, so the ball plays faster than the gun reading.
    """
    rows = []
    for play in plays:
        ev = game.events[(game.events.play_per_game == play) &
                         (game.events.ball_eventcode == 1)]
        if ev.empty:
            continue
        t = int(ev.iloc[0].timestamp)
        traj = fit_trajectory(game.ball[game.ball.play_per_game == play], t)
        if traj is None:
            continue
        v = velos.get(play)
        if v is None or not np.isfinite(v) or v > MAX_PLAUSIBLE_VELO:
            continue
        eff = effective_velocity(v, traj["extension_ft"], league_extension_ft)
        rows.append({
            "play": int(play),
            "velo_mph": round(float(v), 1),
            "extension_ft": round(traj["extension_ft"], 2),
            "effective_velo_mph": round(float(eff), 1),
            "gain_mph": round(float(eff - v), 1),
        })
    df = pd.DataFrame(rows)
    if df.empty or top is None:
        return df
    return df.sort_values("effective_velo_mph", ascending=False).head(top)


# --------------------------------------------------------------- Late Life
def late_life_table(game, plays, velos, top=None):
    """Movement at the plate with the gravity component removed.

    Gravity drops a 90 mph pitch about 39 inches regardless of quality, so the
    raw deviation from a straight line makes every pitch look filthy. Induced
    break is what actually separates a four-seamer from a curveball.
    """
    rows = []
    for play in plays:
        ev = game.events[(game.events.play_per_game == play) &
                         (game.events.ball_eventcode == 1)]
        if ev.empty:
            continue
        t = int(ev.iloc[0].timestamp)
        traj = fit_trajectory(game.ball[game.ball.play_per_game == play], t)
        if traj is None:
            continue
        v = velos.get(play)
        hb, ivb, grav = late_break_in(traj, v)
        if not np.isfinite(ivb):
            continue
        rows.append({
            "play": int(play),
            "velo_mph": round(float(v), 1) if v and np.isfinite(v) else None,
            "induced_vertical_break_in": round(float(ivb), 1),
            "horizontal_break_in": round(float(hb), 1),
            "gravity_drop_in": round(float(grav), 1),
            "total_movement_in": round(float(np.hypot(hb, ivb)), 1),
            "pitch_shape": ("riding fastball" if ivb > 12 else
                            "fastball" if ivb > 6 else
                            "changeup / cutter" if ivb > 0 else "breaking ball"),
        })
    df = pd.DataFrame(rows)
    if df.empty or top is None:
        return df
    return df.sort_values("total_movement_in", ascending=False).head(top)
