"""
c05_power_hitting.py — COMPONENT 5: Power & Hitting.

Mirrors R/R05_power_hitting.R.

Scoreboard products in this file
    Statcast Smash        exit velocity leaderboard
    Moonshot Meter        estimated carry distance of flies and home runs
    Barrel Zone           the sweet-spot exit-velo x launch-angle combination
    Launch Angle Rainbow  a hitter's spray of launch angles and outcomes
    Clutch Contact        hardest contact weighted by leverage
"""
import numpy as np
import pandas as pd

BARREL_MIN_EV = 95.0
BARREL_LA = (20.0, 35.0)


def _attach(df, lineups, column, play_col="play"):
    m = lineups[["game_string", "play_per_game", column]].rename(
        columns={"play_per_game": play_col, column: "player"})
    out = df.merge(m, on=["game_string", play_col], how="left")
    out["team"] = out.player.str.split("-").str[0]
    return out


# ---------------------------------------------------------- Statcast Smash
def statcast_smash(hits, lineups, min_balls=5, top=15):
    """Hardest-hit balls, by 90th-percentile exit velocity."""
    h = _attach(hits, lineups, "batter").dropna(subset=["player"])
    lb = (h.groupby("player")
            .agg(max_exit_velo=("exit_velo_mph", "max"),
                 p90_exit_velo=("exit_velo_mph",
                                lambda x: round(float(np.percentile(x, 90)), 1)),
                 avg_exit_velo=("exit_velo_mph", "mean"),
                 balls=("exit_velo_mph", "size"),
                 team=("team", "first"))
            .reset_index())
    lb = lb[lb.balls >= min_balls].sort_values(
        ["p90_exit_velo", "max_exit_velo"], ascending=False)
    lb["avg_exit_velo"] = lb.avg_exit_velo.round(1)
    return lb.head(top).reset_index(drop=True)


def hardest_hit_balls(hits, lineups, top=10):
    """The single hardest-hit balls — the nightly highlight list."""
    h = _attach(hits, lineups, "batter").dropna(subset=["player"])
    cols = ["game_string", "play", "player", "team", "exit_velo_mph",
            "launch_deg", "hit_distance_ft"]
    cols = [c for c in cols if c in h.columns]
    return h.sort_values("exit_velo_mph", ascending=False)[cols].head(top).reset_index(drop=True)


# ---------------------------------------------------------- Moonshot Meter
def moonshot_meter(hits, lineups, min_flies=3, top=15):
    """Estimated carry distance on balls hit in the air."""
    h = _attach(hits, lineups, "batter").dropna(subset=["player"])
    fly = h[(h.launch_deg >= 10) & (h.hit_distance_ft >= 150)]
    lb = (fly.groupby("player")
            .agg(longest_ft=("hit_distance_ft", "max"),
                 avg_ft=("hit_distance_ft", "mean"),
                 flies=("hit_distance_ft", "size"),
                 team=("team", "first"))
            .reset_index())
    lb = lb[lb.flies >= min_flies].sort_values("longest_ft", ascending=False)
    lb["avg_ft"] = lb.avg_ft.round(1)
    return lb.head(top).reset_index(drop=True)


# ------------------------------------------------------------- Barrel Zone
def barrel_zone(hits, lineups, min_balls=8, top=15):
    """Barrels: hit hard, in the sweet-spot launch window."""
    h = _attach(hits, lineups, "batter").dropna(subset=["player"]).copy()
    h["is_barrel"] = ((h.exit_velo_mph >= BARREL_MIN_EV) &
                      (h.launch_deg.between(*BARREL_LA))).astype(int)
    lb = (h.groupby("player")
            .agg(barrels=("is_barrel", "sum"), balls=("is_barrel", "size"),
                 team=("team", "first"))
            .reset_index())
    lb["barrel_rate_pct"] = (100 * lb.barrels / lb.balls).round(1)
    lb = lb[lb.balls >= min_balls].sort_values(
        ["barrels", "barrel_rate_pct"], ascending=False)
    return lb.head(top).reset_index(drop=True)


def barrel_grid(hits, ev_step=5, la_step=5):
    """Outcome rate across the exit-velo x launch-angle plane.

    This is the data behind the classic 'sweet spot' heat map.
    """
    h = hits.dropna(subset=["exit_velo_mph", "launch_deg"]).copy()
    h["ev_bin"] = (h.exit_velo_mph // ev_step * ev_step).astype(int)
    h["la_bin"] = (h.launch_deg // la_step * la_step).astype(int)
    g = (h.groupby(["ev_bin", "la_bin"])
           .agg(n=("exit_velo_mph", "size"),
                hr_rate=("is_hr", "mean") if "is_hr" in h.columns
                else ("exit_velo_mph", "size"))
           .reset_index())
    return g[g.n >= 5]


# ------------------------------------------------------ Launch Angle Rainbow
def launch_angle_rainbow(hits, lineups, player=None):
    """A hitter's distribution of launch angles and what they produced."""
    h = _attach(hits, lineups, "batter").dropna(subset=["player"])
    if player:
        h = h[h.player == player]
    h = h.dropna(subset=["launch_deg"]).copy()
    h["batted_ball_type"] = pd.cut(
        h.launch_deg, bins=[-90, 10, 25, 50, 90],
        labels=["ground ball", "line drive", "fly ball", "pop up"])
    summary = (h.groupby("batted_ball_type", observed=True)
                 .agg(n=("launch_deg", "size"),
                      avg_exit_velo=("exit_velo_mph", "mean"),
                      avg_distance=("hit_distance_ft", "mean"))
                 .reset_index().round(1))
    return h, summary


# --------------------------------------------------------- Clutch Contact
def clutch_contact(enriched, top=15):
    """Hardest contact when it mattered most: exit velo weighted by leverage."""
    df = enriched.dropna(subset=["exit_velo_mph", "leverage_index"]).copy()
    df["clutch_contact_score"] = (
        df.exit_velo_mph.clip(lower=60) / 100.0 * np.sqrt(df.leverage_index))
    cols = ["game_string", "inning", "half_inning", "batter", "outcome",
            "exit_velo_mph", "leverage_index", "wpa", "clutch_contact_score"]
    cols = [c for c in cols if c in df.columns]
    return (df.sort_values("clutch_contact_score", ascending=False)[cols]
              .head(top).round(3).reset_index(drop=True))
