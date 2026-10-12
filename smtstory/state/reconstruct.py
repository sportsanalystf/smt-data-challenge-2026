"""
reconstruct.py — GAME STATE RECONSTRUCTION
===========================================
The SMT dataset provides base occupancy but **no outs, no count, and no score**.
Win Probability, Leverage Index, Run Expectancy and WPA are all functions of
(inning, half, outs, base state, score differential), so none of them can be
computed until that state is recovered. This module recovers it.

METHOD
------
For each half-inning we walk the at-bats in order and apply an accounting
identity. Let

    B = runners on base before the at-bat        (from `lineups`)
    A = runners on base after the at-bat         (occupancy at the next at-bat)
    d = 1 if the batter reached base, else 0

Every person who was on base before, plus the batter, must end the at-bat in
exactly one of three places: still on base, across the plate (a run), or retired
(an out). That gives the identity

    |B| + 1 = |A| + runs + outs                                     (1)

We observe |B|, |A| and (via `outcomes.classify_atbat`) whether the batter
reached. We also know the half-inning must end with exactly three outs unless
the game ended mid-inning (walk-off) or the home team did not bat. That
constraint closes the system:

    sum(outs over the half-inning) = 3                              (2)

ALGORITHM
---------
1. Classify each at-bat's batter outcome from occupancy + events.
2. Identify runners who disappeared without being on base afterwards. Each is
   either a run or a baserunning out.
3. Apply (1) per at-bat to get the total "vanished" count, then use (2) to
   allocate vanished runners between runs and outs across the half-inning,
   preferring to charge outs to at-bats where the batter was also retired
   (double plays, fielder's choices) and to charge runs to at-bats where the
   batter hit the ball.
4. Home runs are handled explicitly: batter and all runners score, no outs.

ASSUMPTIONS AND LIMITS (documented for reviewers)
-------------------------------------------------
* A half-inning ends at 3 outs. Half-innings that end otherwise (walk-off, or a
  final home half that is not played) are flagged `partial=True` and excluded
  from the run-expectancy fit.
* Occupancy is read at the START of each at-bat, so mid-at-bat baserunning
  events (a steal, a pickoff) resolve into the next at-bat's state.
* Pickoff plays (`is_pickoff`) are not plate appearances and are excluded from
  the at-bat sequence, but their plays remain available for baserunning models.
* Where the identity cannot be closed, the at-bat is marked
  `confidence='low'` and the half-inning `balanced=False`. Downstream models
  can and do filter on this.

Everything here is deterministic and unit-tested in `tests/test_state.py`.
"""
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .. import config
from .outcomes import classify_atbat

BASE_COLS = ["on_1b", "on_2b", "on_3b"]

# The 8 base states, indexed by (1B, 2B, 3B) occupancy bits.
BASE_STATES = ["___", "1__", "_2_", "12_", "__3", "1_3", "_23", "123"]


class GameStateError(Exception):
    pass


def base_state_code(on1, on2, on3):
    """Return an integer 0-7 encoding which bases are occupied."""
    return int(bool(on1)) + 2 * int(bool(on2)) + 4 * int(bool(on3))


def _occupants(row):
    """Set of player codes on base for a lineup row."""
    out = set()
    for c in BASE_COLS:
        v = row.get(c)
        if isinstance(v, str) and v:
            out.add(v)
    return out


def max_plausible_runs(kind, on1, on2, on3):
    """Upper bound on how many runners can score, given what the batter did.

    Occupancy transitions alone cannot distinguish a runner who scored from a
    runner who was replaced by a pinch-runner or otherwise left the tracked
    state. Baseball physics constrains the answer: a runner on first cannot
    score on an infield out, and a batter who is retired cannot drive in a
    runner from first. Applying this bound removes the dominant source of
    phantom runs without discarding real ones.
    """
    n1, n2, n3 = int(bool(on1)), int(bool(on2)), int(bool(on3))
    on_base = n1 + n2 + n3
    if kind == "home_run":
        return on_base + 1
    if kind == "triple":
        return on_base
    if kind == "double":
        # Runners from second and third score; a runner from first can score
        # on a ball in the gap.
        return n2 + n3 + n1
    if kind == "single":
        # Second and third can score; first almost never does.
        return n2 + n3
    if kind == "walk_hbp":
        # Only a forced run with the bases loaded.
        return 1 if (n1 and n2 and n3) else 0
    if kind in ("out", "fielders_choice"):
        # Sacrifice fly or run-scoring groundout: only from third.
        return n3
    return on_base


def _dest_base(player, row):
    """Which base `player` occupies in a lineup row (1-3), else None."""
    for i, c in enumerate(BASE_COLS, start=1):
        if row.get(c) == player:
            return i
    return None


def reconstruct_atbats(game):
    """Reconstruct the at-bat sequence for one game.

    Returns a DataFrame with one row per plate appearance and the full state
    before and after it.
    """
    lu = game.lineups.copy()
    if lu.empty:
        raise GameStateError(f"no lineup rows for {game.game_string}")

    lu = lu.sort_values("play_per_game")
    # Plate appearances only; pickoffs are not at-bats.
    pa = lu[~lu.is_pickoff.fillna(False).astype(bool)]

    # Collapse plays to at-bats: state is taken at the FIRST play of the at-bat.
    ab = (pa.groupby(["inning", "half_inning", "at_bat"], as_index=False)
            .agg(first_play=("play_per_game", "min"),
                 last_play=("play_per_game", "max"),
                 n_pitches=("play_per_game", "count"),
                 batter=("batter", "first"),
                 pitcher=("pitcher", "first"),
                 on_1b=("on_1b", "first"),
                 on_2b=("on_2b", "first"),
                 on_3b=("on_3b", "first"),
                 home_team=("home_team", "first"),
                 away_team=("away_team", "first")))
    # Order of play: away bats in the Top half.
    ab["half_order"] = (ab.half_inning == "Bottom").astype(int)
    ab = ab.sort_values(["inning", "half_order", "at_bat"]).reset_index(drop=True)

    plays_by_ab = (pa.groupby(["inning", "half_inning", "at_bat"])["play_per_game"]
                     .apply(list).to_dict())

    rows = []
    for (inning, half), grp in ab.groupby(["inning", "half_order"], sort=True):
        grp = grp.sort_values("at_bat").reset_index(drop=True)
        half_label = "Bottom" if half == 1 else "Top"
        n = len(grp)

        # ---- pass 1: batter outcomes and raw vanished counts
        recs = []
        for i in range(n):
            r = grp.iloc[i]
            nxt = grp.iloc[i + 1] if i + 1 < n else None
            before = _occupants(r)
            after = _occupants(nxt) if nxt is not None else set()
            dest = _dest_base(r.batter, nxt) if nxt is not None else None
            plays = plays_by_ab.get((r.inning, half_label, r.at_bat), [])

            oc = classify_atbat(game.events, plays, r.batter, dest,
                                next_batter_seen=nxt is not None)

            # Identity (1): pool_before - pool_after = runs + outs.
            # NOTE: for the LAST at-bat of a half-inning there is no observed
            # `after` state, so runners left on base would be indistinguishable
            # from runs. We therefore do not apply the identity there (see
            # pass 2), which is why stranded runners are never miscounted.
            is_last = nxt is None
            gone = 0 if is_last else max(0, len(before) + 1 - len(after))
            batter_out = 0 if oc.on_base else 1
            runner_gone = max(0, gone - batter_out)

            recs.append({
                "inning": int(r.inning), "half_inning": half_label,
                "at_bat": int(r.at_bat), "first_play": int(r.first_play),
                "last_play": int(r.last_play), "n_pitches": int(r.n_pitches),
                "batter": r.batter, "pitcher": r.pitcher,
                "on_1b": r.on_1b if isinstance(r.on_1b, str) else None,
                "on_2b": r.on_2b if isinstance(r.on_2b, str) else None,
                "on_3b": r.on_3b if isinstance(r.on_3b, str) else None,
                "outcome": oc.kind, "batter_dest": oc.batter_dest,
                "ball_in_play": oc.ball_in_play, "confidence": oc.confidence,
                "_gone": int(gone), "_runner_gone": int(runner_gone),
                "_batter_out": int(batter_out), "_is_last": bool(is_last),
                "_n_before": len(before),
            })

        # ---- pass 2: allocate departures between runs and outs
        # Batter outs are observed directly from the occupancy transition.
        batter_outs = [rec["_batter_out"] for rec in recs]
        known_outs = sum(batter_outs)

        # Constraint (2): the half-inning totals three outs. Any shortfall must
        # be runners retired on the bases (double plays, caught stealing,
        # runners thrown out advancing).
        runner_outs_avail = sum(rec["_runner_gone"] for rec in recs)
        runner_outs_needed = max(0, config.OUTS_PER_HALF - known_outs)
        runner_outs_needed = min(runner_outs_needed, runner_outs_avail)

        # Charge runner outs preferentially where the batter was ALSO retired
        # (the double-play signature), then to other balls in play.
        order = sorted(range(len(recs)),
                       key=lambda i: (recs[i]["_batter_out"] == 0,
                                      not recs[i]["ball_in_play"]))
        remaining = runner_outs_needed
        runner_outs = [0] * len(recs)
        for i in order:
            if remaining <= 0:
                break
            if recs[i]["outcome"] == "home_run":
                continue
            take = min(recs[i]["_runner_gone"], remaining)
            runner_outs[i] = take
            remaining -= take

        for i, rec in enumerate(recs):
            if rec["outcome"] == "home_run":
                # Batter and every runner aboard score; no outs recorded.
                rec["runs"] = rec["_n_before"] + 1
                rec["outs_on_play"] = 0
            elif rec["_is_last"]:
                # Final at-bat: outs are pinned by the 3-out constraint and we
                # do not infer runs (stranded runners are not runs).
                rec["outs_on_play"] = max(0, config.OUTS_PER_HALF
                                          - sum(r["outs_on_play"] for r in recs[:i]))
                rec["runs"] = 0
            else:
                rec["outs_on_play"] = batter_outs[i] + runner_outs[i]
                raw_runs = max(0, rec["_runner_gone"] - runner_outs[i])
                # Constrain by what is physically possible for this outcome.
                cap = max_plausible_runs(rec["outcome"], rec["on_1b"],
                                         rec["on_2b"], rec["on_3b"])
                rec["runs"] = int(min(raw_runs, cap))
                if raw_runs > cap:
                    # Departures we could not explain as runs: most likely a
                    # substitution. Flagged so downstream models can filter.
                    rec["confidence"] = "medium"
                    rec["unexplained_departures"] = int(raw_runs - cap)

        half_outs = sum(rec["outs_on_play"] for rec in recs)
        balanced = (half_outs == config.OUTS_PER_HALF)
        for rec in recs:
            rec["half_balanced"] = balanced
            if not balanced:
                rec["confidence"] = "low"

        # ---- pass 3: running outs/score within the half-inning
        # Outs are clamped so the recorded state can never be illegal (a
        # half-inning cannot contain four outs). When the clamp bites, the
        # reconstruction of that half-inning disagreed with itself — usually a
        # batter who reached on an error and was later erased, which looks like
        # an out from occupancy alone. Those at-bats are flagged rather than
        # silently distorted, and downstream models filter on `state_anomaly`.
        outs_before = 0
        for rec in recs:
            allowance = config.OUTS_PER_HALF - outs_before
            anomaly = rec["outs_on_play"] > allowance or outs_before >= config.OUTS_PER_HALF
            rec["outs_on_play"] = int(max(0, min(rec["outs_on_play"], allowance)))
            rec["state_anomaly"] = bool(anomaly)
            if anomaly:
                rec["confidence"] = "low"
                rec["half_balanced"] = False
            rec["outs_before"] = int(min(outs_before, config.OUTS_PER_HALF - 1))
            rec["outs_after"] = int(min(config.OUTS_PER_HALF,
                                        outs_before + rec["outs_on_play"]))
            outs_before = rec["outs_after"]
            rec["base_state_before"] = base_state_code(
                rec["on_1b"], rec["on_2b"], rec["on_3b"])
            rows.append(rec)

    df = pd.DataFrame(rows)
    if df.empty:
        raise GameStateError(f"reconstruction produced no at-bats for {game.game_string}")

    df = df.sort_values(["inning", "half_inning", "at_bat"],
                        key=lambda s: s.map({"Top": 0, "Bottom": 1}) if s.name == "half_inning" else s)
    df = df.sort_values(["inning", "at_bat"]).reset_index(drop=True)

    # ---- game-level score progression
    df["batting_team"] = np.where(df.half_inning == "Top",
                                  game.away_team, game.home_team)
    df["home_runs_scored"] = np.where(df.half_inning == "Bottom", df.runs, 0)
    df["away_runs_scored"] = np.where(df.half_inning == "Top", df.runs, 0)
    df["home_score_before"] = df.home_runs_scored.cumsum() - df.home_runs_scored
    df["away_score_before"] = df.away_runs_scored.cumsum() - df.away_runs_scored
    df["home_score_after"] = df.home_runs_scored.cumsum()
    df["away_score_after"] = df.away_runs_scored.cumsum()
    # Score differential from the perspective of the batting team.
    df["score_diff_before"] = np.where(
        df.half_inning == "Top",
        df.away_score_before - df.home_score_before,
        df.home_score_before - df.away_score_before)
    df["game_string"] = game.game_string
    return df


def reconstruct_game(game):
    """Reconstruct one game and attach summary metadata.

    Returns (atbats_df, summary_dict).
    """
    df = reconstruct_atbats(game)
    n_half = df.groupby(["inning", "half_inning"]).ngroups
    balanced = df.groupby(["inning", "half_inning"]).half_balanced.first()
    summary = {
        "game_string": game.game_string,
        "home_team": game.home_team,
        "away_team": game.away_team,
        "at_bats": int(len(df)),
        "half_innings": int(n_half),
        "half_innings_balanced": int(balanced.sum()),
        "balanced_rate": float(balanced.mean()) if n_half else 0.0,
        "home_final": int(df.home_score_after.max()) if len(df) else 0,
        "away_final": int(df.away_score_after.max()) if len(df) else 0,
        "total_runs": int(df.runs.sum()),
        "hits": int(df.outcome.isin(["single", "double", "triple", "home_run"]).sum()),
        "home_runs": int((df.outcome == "home_run").sum()),
        "walks": int((df.outcome == "walk_hbp").sum()),
        "low_confidence": int((df.confidence == "low").sum()),
    }
    return df, summary
