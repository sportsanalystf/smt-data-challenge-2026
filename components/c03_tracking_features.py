"""
c03_tracking_features.py — COMPONENT 3: physical measurements from tracking.

Mirrors R/R03_tracking_features.R.

Everything the scoreboard shows begins here: speeds differenced from 20 Hz
positions, batted-ball measurements from the ball's flight, pitch trajectories
fit as quadratics, and fielder routes. Each function is pure — tracking frames
in, numbers out — so it can be tested and reused by any component downstream.
"""
import os

import numpy as np
import pandas as pd

from smtstory import config, dataio
from smtstory.tracking import kinematics as K
from smtstory.analytics.tunneling import (fit_trajectory, late_break_in,
                                          tunnel_pair, effective_velocity,
                                          PitchSequenceAnalyzer)
from smtstory.analytics.baselines import build_from_features

FEAT_DIR = os.path.join(config.OUTPUT_DIR, "feat")


# ---------------------------------------------------------------- season sets
def load_feature_tables(feat_dir=None, engine_dir=None):
    """The season-level feature tables produced by the extraction pipeline."""
    feat_dir = feat_dir or FEAT_DIR
    engine_dir = engine_dir or config.ENGINE_OUT

    def rd(name, folder):
        p = os.path.join(folder, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    return {
        "hits": rd("hits_v2.csv", feat_dir).rename(
            columns={"carry_ft": "hit_distance_ft"}),
        "sprints": rd("sprints.csv", feat_dir),
        "throws": rd("throws.csv", feat_dir),
        "catches": rd("catches.csv", feat_dir),
        "pitches": rd("pitch_locations.csv", engine_dir),
    }


def league_baselines():
    """Season distributions used to turn any measurement into a percentile."""
    return build_from_features(FEAT_DIR, config.ENGINE_OUT)


def baseline_table(baselines):
    rows = []
    for metric, s in baselines.summary.items():
        rows.append({"metric": metric, "n": s["n"], "mean": round(s["mean"], 2),
                     "p10": round(s["p10"], 2), "median": round(s["median"], 2),
                     "p90": round(s["p90"], 2), "max": round(s["max"], 2)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- single play
def player_speed_series(game, play, player_id):
    """Speed (mph) frame by frame for one tracked player."""
    trk = game.player[(game.player.play_per_game == play) &
                      (game.player.player_id == player_id)].sort_values("timestamp")
    if len(trk) < 3:
        return pd.DataFrame(columns=["t_s", "speed_mph"])
    sp = K.player_speed(trk)
    t = trk.timestamp.to_numpy(float)[:-1]
    return pd.DataFrame({"t_s": (t - t[0]) / 1000.0,
                         "speed_mph": sp * config.FT_S_TO_MPH})


def batted_ball_measures(game, play):
    """Exit velocity, launch angle and carry for one batted ball."""
    ev = game.events[game.events.play_per_game == play]
    hit = ev[ev.ball_eventcode == config.EVENT["HIT_INTO_PLAY"]]
    if hit.empty:
        return None
    t_hit = int(hit.iloc[0].timestamp)
    ball = game.ball[game.ball.play_per_game == play]
    return {
        "exit_velo_mph": K.exit_velocity(ball, t_hit),
        "launch_deg": K.launch_angle(ball, t_hit),
        "carry_ft": K.carry_distance(ball, t_hit),
    }


def pitch_measures(game, play, velo_mph=None):
    """Release, extension, break and plate location for one pitch."""
    ev = game.events[game.events.play_per_game == play]
    p = ev[ev.ball_eventcode == config.EVENT["PITCH"]]
    if p.empty:
        return None
    t = int(p.iloc[0].timestamp)
    ball = game.ball[game.ball.play_per_game == play]
    traj = fit_trajectory(ball, t)
    if traj is None:
        return None
    hb, ivb, grav = late_break_in(traj, velo_mph)
    return {
        "release_y_ft": round(traj["release_y"], 2),
        "extension_ft": round(traj["extension_ft"], 2),
        "plate_x_ft": round(traj["plate_x"], 3),
        "plate_z_ft": round(traj["plate_z"], 3),
        "horizontal_break_in": round(hb, 1),
        "induced_vertical_break_in": round(ivb, 1) if np.isfinite(ivb) else None,
        "gravity_drop_in": round(grav, 1) if np.isfinite(grav) else None,
        "velo_mph": velo_mph,
    }


def pitch_sequence(game, plays, velos=None, zone_model=None):
    """Every pitch of an at-bat with tunneling between consecutive pitches."""
    an = PitchSequenceAnalyzer(zone_model)
    out = an.analyze_at_bat(game.ball, game.events, plays, velos or {})
    rows = []
    for p in out:
        p.pop("_traj", None)
        rows.append(p)
    return pd.DataFrame(rows)


def fielder_route(game, play, fielder_id, t_start, t_end):
    """Distance covered, path length and route efficiency for a fielder."""
    trk = game.player[(game.player.play_per_game == play) &
                      (game.player.player_id == fielder_id)]
    return {
        "route_ft": K.route_distance(trk, t_start, t_end),
        "path_ft": K.path_length(trk, t_start, t_end),
        "route_efficiency": K.route_efficiency(trk, t_start, t_end),
    }
