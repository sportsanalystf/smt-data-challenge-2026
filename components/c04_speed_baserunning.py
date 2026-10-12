"""
c04_speed_baserunning.py — COMPONENT 4: Speed & Baserunning.

Mirrors R/R04_speed_baserunning.R.

Scoreboard products in this file
    Burner Board          peak sprint speed to first, ranked across the league
    Home-to-First Dash    contact to the bag, as a beat-the-clock graphic
    Fastest Out of the Box acceleration in the first 1.5 seconds
    Extra-Base Instinct   speed and path efficiency when taking an extra base
    Pickoff Jump          secondary lead distance and burst

Each product is a single function returning a tidy, print-ready leaderboard.
"""
import numpy as np
import pandas as pd

from smtstory import config
from smtstory.tracking.geometry import FIRST, SECOND, THIRD

MIN_RUNS = 3


def _attach(df, lineups, column, play_col="play"):
    m = lineups[["game_string", "play_per_game", column]].rename(
        columns={"play_per_game": play_col, column: "player"})
    out = df.merge(m, on=["game_string", play_col], how="left")
    out["team"] = out.player.str.split("-").str[0]
    return out


# ------------------------------------------------------------ Burner Board
def burner_board(sprints, lineups, min_runs=MIN_RUNS, top=15):
    """Peak sprint speed on the way to first, ranked across the league."""
    s = _attach(sprints, lineups, "batter").dropna(subset=["player"])
    lb = (s.groupby("player")
            .agg(top_speed_mph=("sprint_mph", "max"),
                 avg_speed_mph=("sprint_mph", "mean"),
                 runs=("sprint_mph", "size"),
                 team=("team", "first"))
            .reset_index())
    lb = lb[lb.runs >= min_runs].sort_values("top_speed_mph", ascending=False)
    lb["avg_speed_mph"] = lb.avg_speed_mph.round(2)
    lb["league_percentile"] = (100 * lb.top_speed_mph.rank(pct=True)).round(1)
    return lb.head(top).reset_index(drop=True)


# -------------------------------------------------------- Home-to-First Dash
def home_to_first(anatomy_rows, top=15):
    """Elapsed time from contact to the first-base bag.

    `anatomy_rows` is a frame with batter, time_to_base_s (from the play
    anatomy engine, which measures the moment the runner enters the bag radius).
    """
    df = anatomy_rows.dropna(subset=["time_to_base_s"]).copy()
    df = df[(df.time_to_base_s > 3.0) & (df.time_to_base_s < 7.5)]
    lb = (df.groupby("batter")
            .agg(best_time_s=("time_to_base_s", "min"),
                 avg_time_s=("time_to_base_s", "mean"),
                 tries=("time_to_base_s", "size"))
            .reset_index()
            .sort_values("best_time_s"))
    lb["avg_time_s"] = lb.avg_time_s.round(2)
    lb["grade"] = np.where(lb.best_time_s < 4.2, "ELITE",
                    np.where(lb.best_time_s < 4.5, "PLUS", "AVERAGE"))
    return lb.head(top).reset_index(drop=True)


# ---------------------------------------------------- Fastest Out of the Box
def out_of_the_box(anatomy_rows, top=15):
    """Acceleration in the first stride and a half after contact."""
    df = anatomy_rows.dropna(subset=["burst_ft_s2"]).copy()
    df = df[df.burst_ft_s2 > 0]
    lb = (df.groupby("batter")
            .agg(best_burst=("burst_ft_s2", "max"),
                 avg_burst=("burst_ft_s2", "mean"),
                 n=("burst_ft_s2", "size"))
            .reset_index()
            .sort_values("best_burst", ascending=False))
    lb["avg_burst"] = lb.avg_burst.round(1)
    return lb.head(top).reset_index(drop=True)


# ------------------------------------------------------- Extra-Base Instinct
def extra_base_instinct(pbp, sprints, lineups, top=15):
    """Speed and path efficiency when a runner takes an extra base."""
    extra = pbp[pbp.outcome.isin(["double", "triple"])]
    key = extra[["game_string", "last_play", "batter", "outcome"]].rename(
        columns={"last_play": "play"})
    s = sprints.merge(key, on=["game_string", "play"], how="inner")
    if s.empty:
        return pd.DataFrame(columns=["player", "top_speed_mph", "extra_bases"])
    lb = (s.groupby("batter")
            .agg(top_speed_mph=("sprint_mph", "max"),
                 avg_speed_mph=("sprint_mph", "mean"),
                 extra_bases=("sprint_mph", "size"),
                 triples=("outcome", lambda x: int((x == "triple").sum())))
            .reset_index()
            .rename(columns={"batter": "player"})
            .sort_values(["extra_bases", "top_speed_mph"], ascending=False))
    lb["avg_speed_mph"] = lb.avg_speed_mph.round(2)
    return lb.head(top).reset_index(drop=True)


# -------------------------------------------------------------- Pickoff Jump
def pickoff_jump(game, lineups, top=15):
    """Secondary lead distance and burst on pickoff plays.

    SCOPE NOTE: the data flags pickoff attempts (`is_pickoff`) but records no
    outcome, so this reports the MEASURED lead and burst rather than a modelled
    steal probability.
    """
    picks = lineups[lineups.is_pickoff.fillna(False).astype(bool)]
    if picks.empty or game.player is None or game.player.empty:
        return pd.DataFrame(columns=["play", "runner_id", "lead_ft", "burst_mph"])

    base_xy = {11: FIRST, 12: SECOND, 13: THIRD}
    rows = []
    for play in picks.play_per_game.unique():
        for rid, bag in base_xy.items():
            trk = game.player[(game.player.play_per_game == play) &
                              (game.player.player_id == rid)].sort_values("timestamp")
            if len(trk) < 3:
                continue
            start = trk.iloc[0][["field_x", "field_y"]].to_numpy(float)
            lead = float(np.hypot(start[0] - bag[0], start[1] - bag[1]))
            dx = np.diff(trk.field_x.to_numpy(float))
            dy = np.diff(trk.field_y.to_numpy(float))
            dt = np.diff(trk.timestamp.to_numpy(float)) / 1000.0
            with np.errstate(divide="ignore", invalid="ignore"):
                sp = np.where(dt > 0, np.hypot(dx, dy) / dt, np.nan)
            burst = np.nanmax(sp) * config.FT_S_TO_MPH if np.isfinite(sp).any() else np.nan
            if 0 < lead < 30:
                rows.append({"play": int(play), "runner_id": rid,
                             "lead_ft": round(lead, 1),
                             "burst_mph": round(float(burst), 1)
                             if np.isfinite(burst) else None})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("lead_ft", ascending=False).head(top).reset_index(drop=True)
