"""
c07_defense.py — COMPONENT 7: Defense & Fielding.

Mirrors R/R07_defense.R.

Scoreboard products in this file
    The Robbery Meter    catch probability and Outs Above Expected
    Outfield Cannons     throw (arm) velocity leaderboard
    Ground Crew Range    distance covered and closing speed chasing fly balls
    Web Gem of the Game  the single most improbable completed catch
    Double-Play Ballet   pivot time on the turn
    Pop-Time Pipeline    catcher exchange and throw to second
"""
import numpy as np
import pandas as pd

from smtstory import config
from smtstory.probability import CatchProbabilityModel

POS_COL = config.POS_COL


def _fielder_name(df, lineups):
    """Map fielder_id + play -> the actual player code via the lineup.

    The lineup table carries one row per play, but a play can appear more than
    once; de-duplicating first keeps the lookup returning a scalar rather than a
    Series (which would silently poison the whole column).
    """
    key = (lineups.drop_duplicates(subset=["game_string", "play_per_game"])
                  .set_index(["game_string", "play_per_game"]))
    names = []
    for r in df.itertuples():
        col = POS_COL.get(int(r.fielder_id))
        try:
            val = key.loc[(r.game_string, r.play), col]
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            names.append(val)
        except Exception:
            names.append(None)
    out = df.copy()
    out["player"] = names
    out["pos"] = out.fielder_id.map(config.POS_ABBR)
    out["team"] = out.player.str.split("-").str[0]
    return out


# --------------------------------------------------------- The Robbery Meter
def fit_catch_model(catches):
    """Catch probability from route distance, hang time and required speed."""
    return CatchProbabilityModel().fit(catches)


def catch_model_metrics(model):
    m = model.metrics
    return pd.DataFrame({
        "metric": ["opportunities", "base catch rate", "accuracy", "AUC",
                   "Brier score"],
        "value": [m["n"], round(m["base_rate"], 3), round(m["accuracy"], 3),
                  round(m["auc"], 3), round(m["brier"], 3)],
    })


def outs_above_expected(catches, model, lineups, min_opps=12, top=15):
    """Catches made beyond what an average defender would make."""
    scored = model.score_frame(catches)
    scored = _fielder_name(scored, lineups).dropna(subset=["player"])
    lb = (scored.groupby("player")
            .agg(opportunities=("oae", "size"),
                 catches_made=("catch_made", "sum"),
                 expected=("catch_prob", "sum"),
                 oae=("oae", "sum"),
                 pos=("pos", "first"), team=("team", "first"))
            .reset_index())
    lb = lb[lb.opportunities >= min_opps]
    lb["expected"] = lb.expected.round(1)
    lb["oae"] = lb.oae.round(2)
    return lb.sort_values("oae", ascending=False).head(top).reset_index(drop=True)


def web_gem(catches, model, lineups, top=10):
    """The most improbable completed catches — auto-selected highlights."""
    scored = model.score_frame(catches)
    gems = scored[scored.catch_made == 1].copy()
    gems = _fielder_name(gems, lineups)
    cols = ["game_string", "play", "player", "pos", "route_ft", "hang_s",
            "catch_prob", "robbery_score"]
    cols = [c for c in cols if c in gems.columns]
    return (gems.sort_values("catch_prob")[cols].head(top).round(3)
                .reset_index(drop=True))


def catch_or_no_catch(catches, model, lineups, top=10):
    """The plays worth putting to a crowd vote: closest to a coin flip."""
    scored = model.score_frame(catches)
    scored = _fielder_name(scored, lineups)
    cols = ["game_string", "play", "player", "pos", "route_ft", "hang_s",
            "catch_prob", "catch_made", "suspense"]
    cols = [c for c in cols if c in scored.columns]
    return (scored.sort_values("suspense", ascending=False)[cols]
                  .head(top).round(3).reset_index(drop=True))


# --------------------------------------------------------- Outfield Cannons
def outfield_cannons(throws, lineups, min_throws=3, top=15):
    """Arm strength leaderboard."""
    t = throws.copy()
    t = _fielder_name(t, lineups).dropna(subset=["player"])
    lb = (t.groupby("player")
            .agg(max_throw_mph=("throw_velo_mph", "max"),
                 avg_throw_mph=("throw_velo_mph", "mean"),
                 throws=("throw_velo_mph", "size"),
                 pos=("pos", "first"), team=("team", "first"))
            .reset_index())
    lb = lb[lb.throws >= min_throws].sort_values("max_throw_mph", ascending=False)
    lb["avg_throw_mph"] = lb.avg_throw_mph.round(1)
    return lb.head(top).reset_index(drop=True)


# -------------------------------------------------------- Ground Crew Range
def ground_crew_range(catches, lineups, min_catches=8, top=15):
    """Ground covered and top closing speed on balls caught."""
    made = catches[catches.catch_made == 1].copy()
    made = _fielder_name(made, lineups).dropna(subset=["player"])
    lb = (made.groupby("player")
            .agg(avg_route_ft=("route_ft", "mean"),
                 max_route_ft=("route_ft", "max"),
                 top_closing_ftps=("close_ftps", "max"),
                 catches=("route_ft", "size"),
                 pos=("pos", "first"), team=("team", "first"))
            .reset_index())
    lb = lb[lb.catches >= min_catches].copy()
    lb["avg_route_ft"] = lb.avg_route_ft.round(1)
    lb["top_closing_mph"] = (lb.top_closing_ftps * config.FT_S_TO_MPH).round(1)
    return lb.sort_values("avg_route_ft", ascending=False).head(top).reset_index(drop=True)


# ------------------------------------------------------- Double-Play Ballet
def double_play_ballet(game, plays, top=10):
    """Pivot time: glove-to-release for the middle infielders on a relay."""
    EV = config.EVENT
    rows = []
    for play in plays:
        ev = game.events[game.events.play_per_game == play]
        for pid in (config.PLAYER_IDS["second_baseman"],
                    config.PLAYER_IDS["shortstop"]):
            a = ev[(ev.player_id == pid) & (ev.ball_eventcode == EV["ACQUIRED"])]
            t = ev[(ev.player_id == pid) & (ev.ball_eventcode == EV["THROW"])]
            if a.empty or t.empty:
                continue
            dt = (int(t.iloc[0].timestamp) - int(a.iloc[0].timestamp)) / 1000.0
            if 0 <= dt < 2.0:
                rows.append({"play": int(play), "pos": config.POS_ABBR[pid],
                             "pivot_s": round(dt, 2)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("pivot_s").head(top).reset_index(drop=True)


# -------------------------------------------------------- Pop-Time Pipeline
def pop_time_pipeline(game, plays, top=10):
    """Catcher exchange time and throw velocity to second base."""
    EV = config.EVENT
    from smtstory.tracking import kinematics as K
    c = config.PLAYER_IDS["catcher"]
    rows = []
    for play in plays:
        ev = game.events[game.events.play_per_game == play]
        a = ev[(ev.player_id == c) & (ev.ball_eventcode == EV["ACQUIRED"])]
        t = ev[(ev.player_id == c) &
               (ev.ball_eventcode.isin([EV["THROW"], EV["THROW_UNK"]]))]
        if a.empty or t.empty:
            continue
        t_thr = int(t.iloc[0].timestamp)
        dt = (t_thr - int(a.iloc[0].timestamp)) / 1000.0
        if not (0 <= dt < 3.0):
            continue
        w = game.ball[(game.ball.play_per_game == play) &
                      (game.ball.timestamp >= t_thr) &
                      (game.ball.timestamp <= t_thr + 600)]
        velo = None
        if len(w) >= 3:
            v = K.top_speed(K.ball_speed_3d(w), 90) * config.FT_S_TO_MPH
            if 30 < v < 100:
                velo = round(float(v), 1)
        rows.append({"play": int(play), "exchange_s": round(dt, 2),
                     "throw_velo_mph": velo})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("exchange_s").head(top).reset_index(drop=True)
