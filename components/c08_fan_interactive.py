"""
c08_fan_interactive.py — COMPONENT 8: Fan-interactive games.

Mirrors R/R08_fan_interactive.R.

Scoreboard products in this file
    Catch or No Catch?   freeze at contact, crowd votes, model reveals the odds
    Out or Safe?         a bang-bang play at first, put to the crowd
    Guess the Gun        fans guess the pitch speed
    How Far Did It Go?   fans estimate carry distance
    Beat the Burner      a fan's reaction time raced against a real sprint

DESIGN RULE: a question is only worth asking when the answer is genuinely
uncertain. A prompt the crowd gets right 95% of the time is a formality, not a
game — so every selector below ranks candidate plays by SUSPENSE, not by size.
"""
import numpy as np
import pandas as pd


def _bucket_options(value, step, n=3):
    """Build multiple-choice ranges around a true value."""
    base = int(value // step * step) - step
    opts = [f"{base + i*step}-{base + (i+1)*step - 1}" for i in range(n)]
    idx = int(np.clip((value - base) // step, 0, n - 1))
    return opts, opts[idx]


# ------------------------------------------------------- Catch or No Catch?
def catch_or_no_catch(scored_catches, top=10):
    """Fly balls where the model is closest to a coin flip."""
    df = scored_catches.copy()
    if "suspense" not in df.columns:
        df["suspense"] = 1.0 - (2.0 * (df.catch_prob - 0.5)).abs()
    df = df[(df.catch_prob >= 0.25) & (df.catch_prob <= 0.75)]
    cols = [c for c in ["game_string", "play", "route_ft", "hang_s",
                        "catch_prob", "catch_made", "suspense"]
            if c in df.columns]
    out = df.sort_values("suspense", ascending=False)[cols].head(top).round(3)
    out["prompt"] = "Does he come up with it?"
    out["options"] = [["CAUGHT", "DROPS"]] * len(out)
    out["answer"] = np.where(out.catch_made == 1, "CAUGHT", "DROPS")
    return out.reset_index(drop=True)


# ------------------------------------------------------------- Out or Safe?
def out_or_safe(close_plays, max_margin_s=0.15, top=10):
    """Bang-bang plays at first: the throw and the runner arrive together.

    `close_plays` comes from the play anatomy engine and carries the margin
    between the ball's arrival and the runner's.
    """
    df = close_plays.dropna(subset=["margin_s"]).copy()
    df["abs_margin"] = df.margin_s.abs()
    df = df[df.abs_margin <= max_margin_s]
    cols = [c for c in ["game_string", "play", "batter", "margin_s",
                        "verdict", "throw_distance_ft"] if c in df.columns]
    out = df.sort_values("abs_margin")[cols].head(top).round(3)
    out["prompt"] = "Too close to call — what did you see?"
    out["options"] = [["SAFE", "OUT"]] * len(out)
    return out.reset_index(drop=True)


# ------------------------------------------------------------ Guess the Gun
def guess_the_gun(pitches, min_velo=90.0, top=10, step=3):
    """Fans guess the radar reading. Fast pitches make the best prompts."""
    df = pitches.dropna(subset=["pitch_velo_mph"])
    df = df[(df.pitch_velo_mph >= min_velo) & (df.pitch_velo_mph <= 103)]
    df = df.sort_values("pitch_velo_mph", ascending=False).head(top).copy()
    opts, answers = [], []
    for v in df.pitch_velo_mph:
        o, a = _bucket_options(v, step)
        opts.append(o)
        answers.append(a)
    df["prompt"] = "How hard was that one?"
    df["options"] = opts
    df["answer"] = answers
    cols = [c for c in ["game_string", "play", "pitch_velo_mph", "prompt",
                        "options", "answer"] if c in df.columns]
    return df[cols].reset_index(drop=True)


# ------------------------------------------------------- How Far Did It Go?
def how_far_did_it_go(hits, min_distance=330.0, top=10, step=25):
    """Fans estimate carry on a long fly ball."""
    df = hits.dropna(subset=["hit_distance_ft"])
    df = df[df.hit_distance_ft >= min_distance]
    df = df.sort_values("hit_distance_ft", ascending=False).head(top).copy()
    opts, answers = [], []
    for d in df.hit_distance_ft:
        o, a = _bucket_options(d, step)
        opts.append([f"{x} ft" for x in o])
        answers.append(f"{a} ft")
    df["prompt"] = "How far did that ball travel?"
    df["options"] = opts
    df["answer"] = answers
    cols = [c for c in ["game_string", "play", "exit_velo_mph",
                        "hit_distance_ft", "prompt", "options", "answer"]
            if c in df.columns]
    return df[cols].reset_index(drop=True)


# ----------------------------------------------------------- Beat the Burner
def beat_the_burner(sprints, baselines=None, top=10):
    """Race a fan's phone tap against a real sprint.

    Returns the target times plus where each sits in the league, so the crowd
    knows whether they are chasing an average runner or a burner.
    """
    df = sprints.dropna(subset=["sprint_mph"]).copy()
    df = df.sort_values("sprint_mph", ascending=False).head(top)
    if baselines is not None:
        df["league_percentile"] = [
            baselines.percentile("sprint_mph", v) for v in df.sprint_mph]
    # 90 feet at the runner's peak speed = the challenge time.
    df["target_time_s"] = (90.0 / (df.sprint_mph / 0.681818)).round(2)
    df["prompt"] = "Tap when the pitch is released — can you beat him to the bag?"
    cols = [c for c in ["game_string", "play", "sprint_mph", "target_time_s",
                        "league_percentile", "prompt"] if c in df.columns]
    return df[cols].reset_index(drop=True)


# ----------------------------------------------------------------- summary
def game_night_slate(catch_df, gun_df, far_df, burner_df, safe_df=None):
    """One night's interactive slate, ready for the control room."""
    rows = [
        {"game": "Catch or No Catch?", "prompts_available": len(catch_df)},
        {"game": "Guess the Gun", "prompts_available": len(gun_df)},
        {"game": "How Far Did It Go?", "prompts_available": len(far_df)},
        {"game": "Beat the Burner", "prompts_available": len(burner_df)},
    ]
    if safe_df is not None:
        rows.append({"game": "Out or Safe?", "prompts_available": len(safe_df)})
    return pd.DataFrame(rows)
