"""
c09_composite.py — COMPONENT 9: Composite & Storytelling.

Mirrors R/R09_composite.R.

Scoreboard products in this file
    Five-Tool Scoreboard   percentile blend of speed, power and arm
    Player of the Game     weighted contribution score for a single game
    Rivalry Radar          team-vs-team tale of the tape
    Prospect Spotlight     a player's tool grades, ready to animate
"""
import numpy as np
import pandas as pd

from smtstory.analytics.baselines import grade_for


def _pct(series):
    return (series.rank(pct=True) * 100).round(1)


# ------------------------------------------------------ Five-Tool Scoreboard
def five_tool_scoreboard(burner, smash, cannons, min_tools=2, top=15):
    """Blend speed, power and arm into one number every fan understands.

    Each tool is converted to a league percentile first, so quantities in
    different units (mph off the bat, mph on the run, mph on the throw) can be
    averaged honestly.
    """
    spd = burner[["player", "top_speed_mph"]].rename(
        columns={"top_speed_mph": "speed"})
    pwr = smash[["player", "max_exit_velo"]].rename(
        columns={"max_exit_velo": "power"})
    arm = cannons[["player", "max_throw_mph"]].rename(
        columns={"max_throw_mph": "arm"})

    df = spd.merge(pwr, on="player", how="outer").merge(arm, on="player",
                                                        how="outer")
    for tool in ("speed", "power", "arm"):
        df[f"{tool}_pct"] = _pct(df[tool])

    tools = df[["speed_pct", "power_pct", "arm_pct"]]
    df["tools_measured"] = tools.notna().sum(axis=1)
    df["five_tool_score"] = tools.mean(axis=1).round(1)
    df["grade"] = [grade_for(v) for v in df.five_tool_score]
    df["team"] = df.player.str.split("-").str[0]
    df = df[df.tools_measured >= min_tools]
    return (df.sort_values("five_tool_score", ascending=False)
              .head(top).reset_index(drop=True))


# ------------------------------------------------------- Player of the Game
def player_of_the_game(enriched, game_string, top=5):
    """Who did the most to win it, measured in win probability added."""
    g = enriched[enriched.game_string == game_string]
    if g.empty:
        return pd.DataFrame()

    bat = (g.groupby("batter")
             .agg(plate_appearances=("wpa", "size"),
                  wpa=("wpa", "sum"),
                  hits=("outcome", lambda x: int(x.isin(
                      ["single", "double", "triple", "home_run"]).sum())),
                  home_runs=("outcome", lambda x: int((x == "home_run").sum())),
                  rbi=("runs", "sum"))
             .reset_index().rename(columns={"batter": "player"}))
    bat["role"] = "batting"

    pit = (g.groupby("pitcher")
             .agg(batters_faced=("wpa", "size"), wpa=("wpa", lambda x: -x.sum()))
             .reset_index().rename(columns={"pitcher": "player"}))
    pit["role"] = "pitching"

    both = pd.concat([bat, pit], ignore_index=True, sort=False)
    both["wpa"] = both.wpa.round(3)
    both["potg_score"] = (100 * both.wpa).round(1)
    return (both.sort_values("wpa", ascending=False).head(top)
                .reset_index(drop=True))


# ------------------------------------------------------------ Rivalry Radar
def rivalry_radar(enriched, hits, sprints, lineups, team_a, team_b):
    """Team-vs-team tale of the tape built from tracking aggregates."""
    def team_of(code):
        return code.split("-")[0] if isinstance(code, str) else None

    rows = []
    for team in (team_a, team_b):
        sub = enriched[enriched.batting_team == team] if "batting_team" in enriched else \
            enriched[enriched.batter.map(team_of) == team]
        h = hits.copy()
        h["team"] = h.get("team")
        rows.append({
            "team": team,
            "plate_appearances": int(len(sub)),
            "runs": int(sub.runs.sum()) if "runs" in sub else 0,
            "home_runs": int((sub.outcome == "home_run").sum()) if len(sub) else 0,
            "avg_exit_velo": round(float(sub.exit_velo_mph.mean()), 1)
            if "exit_velo_mph" in sub and sub.exit_velo_mph.notna().any() else None,
            "avg_wpa_per_pa": round(float(sub.wpa.mean()), 4) if len(sub) else None,
            "high_leverage_pa": int((sub.leverage_index >= 2).sum())
            if "leverage_index" in sub else 0,
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------- Prospect Spotlight
def prospect_spotlight(player, burner, smash, cannons, baselines=None):
    """One player's tool grades, in the shape a scoreboard animates."""
    def look(df, key, col):
        r = df[df.player == player]
        return float(r[col].iloc[0]) if len(r) else np.nan

    tools = {
        "speed": look(burner, "player", "top_speed_mph"),
        "power": look(smash, "player", "max_exit_velo"),
        "arm": look(cannons, "player", "max_throw_mph"),
    }
    metric_for = {"speed": "sprint_mph", "power": "exit_velo_mph",
                  "arm": "throw_velo_mph"}
    rows = []
    for tool, value in tools.items():
        pct = (baselines.percentile(metric_for[tool], value)
               if baselines is not None and np.isfinite(value) else None)
        rows.append({"tool": tool,
                     "value": round(value, 1) if np.isfinite(value) else None,
                     "league_percentile": pct,
                     "grade": grade_for(pct) if pct is not None else None})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- game recap
def game_headline(enriched, game_string):
    """The one-line story of a game: final score and its biggest swing."""
    g = enriched[enriched.game_string == game_string]
    if g.empty:
        return {}
    top = g.loc[g.wpa.abs().idxmax()]
    return {
        "game": game_string,
        "final_home": int(g.home_score_after.max()),
        "final_away": int(g.away_score_after.max()),
        "turning_point_batter": top.batter,
        "turning_point_outcome": top.outcome,
        "turning_point_wpa": round(float(top.wpa), 3),
        "turning_point_leverage": round(float(top.leverage_index), 2)
        if "leverage_index" in g.columns else None,
    }
