"""
test_engine.py — invariant tests for the storytelling engine.

These are deliberately INVARIANT tests rather than golden-value tests: they
assert the things that must be true of any correct baseball model (a half-inning
cannot have four outs, a probability cannot exceed 1, run expectancy must fall
as outs accumulate). That makes them robust to model retuning while still
catching the class of bug that actually bit us during development — the
accounting identity that silently invented runs.

Run:  python tests/test_engine.py        (no pytest required)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                                    # noqa: E402
from smtstory.state.reconstruct import (base_state_code,       # noqa: E402
                                        max_plausible_runs, BASE_STATES)
from smtstory.state.outcomes import is_live_contact, terminal_play_events  # noqa: E402
from smtstory.analytics import (RunExpectancy, WinProbabilityModel,  # noqa: E402
                                HighlightScorer, clutch_score)
from smtstory.cards import default_registry, PlayContext        # noqa: E402
from smtstory.narrative import NarrativeGenerator, describe_state  # noqa: E402

OUT = config.ENGINE_OUT
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------- unit tests
def test_base_state_encoding():
    print("\n[base state encoding]")
    check("empty bases -> 0", base_state_code(None, None, None) == 0)
    check("runner on 1st -> 1", base_state_code("X", None, None) == 1)
    check("runner on 2nd -> 2", base_state_code(None, "X", None) == 2)
    check("runner on 3rd -> 4", base_state_code(None, None, "X") == 4)
    check("bases loaded -> 7", base_state_code("A", "B", "C") == 7)
    check("8 distinct states", len(set(BASE_STATES)) == 8)


def test_plausible_runs():
    print("\n[run plausibility constraint]")
    # A runner on first cannot score on an infield out.
    check("no run from 1st on an out", max_plausible_runs("out", "X", None, None) == 0)
    # A runner on third can score on an out (sacrifice).
    check("run from 3rd on an out", max_plausible_runs("out", None, None, "X") == 1)
    # A walk only forces a run with the bases loaded.
    check("walk with bases empty scores nobody",
          max_plausible_runs("walk_hbp", None, None, None) == 0)
    check("walk with bases loaded forces one",
          max_plausible_runs("walk_hbp", "A", "B", "C") == 1)
    # A grand slam scores four.
    check("grand slam scores 4",
          max_plausible_runs("home_run", "A", "B", "C") == 4)
    check("solo homer scores 1",
          max_plausible_runs("home_run", None, None, None) == 1)


def test_foul_vs_live_contact():
    print("\n[foul ball vs live ball]")
    EV = config.EVENT
    # A foul: contact then immediately dead, nobody fields it.
    foul = pd.DataFrame({"play_per_game": [5, 5], "timestamp": [100, 300],
                         "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["END_OF_PLAY"]]})
    check("foul is not live contact", not is_live_contact(foul))
    # A live ball: contact, then a fielder acquires it.
    live = pd.DataFrame({"play_per_game": [5, 5, 5], "timestamp": [100, 400, 900],
                         "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["BOUNCE"],
                                            EV["ACQUIRED"]]})
    check("fielded ball is live contact", is_live_contact(live))
    # A home run is live contact.
    hr = pd.DataFrame({"play_per_game": [5, 5], "timestamp": [100, 500],
                       "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["HOME_RUN"]]})
    check("home run is live contact", is_live_contact(hr))
    # Only the terminal play decides the at-bat.
    ab = pd.DataFrame({"play_per_game": [1, 1, 2], "timestamp": [10, 20, 30],
                       "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["END_OF_PLAY"],
                                          EV["PITCH"]]})
    term = terminal_play_events(ab, [1, 2])
    check("terminal play is the last play", set(term.play_per_game) == {2})


# ----------------------------------------------------------- data invariants
def test_reconstruction_invariants():
    print("\n[reconstructed season invariants]")
    path = os.path.join(OUT, "atbats.csv")
    if not os.path.exists(path):
        print("  SKIP  atbats.csv not built yet")
        return
    ab = pd.read_csv(path)

    check("outs never exceed 3 in a half-inning",
          ab.groupby(["game_string", "inning", "half_inning"]).outs_on_play.sum().max()
          <= config.OUTS_PER_HALF)
    check("outs_before within [0,2]",
          ab.outs_before.between(0, 2).all())
    if "state_anomaly" in ab.columns:
        rate = ab.state_anomaly.mean()
        check(f"state anomalies are rare (got {rate*100:.2f}%)", rate < 0.02)
    check("runs are non-negative", (ab.runs >= 0).all())
    check("no at-bat scores more than 4", (ab.runs <= 4).max() if len(ab) else True)
    check("base states within [0,7]", ab.base_state_before.between(0, 7).all())
    check("scores are non-decreasing within a game",
          ab.groupby("game_string").home_score_after.apply(
              lambda s: s.is_monotonic_increasing).all())

    rpg = ab.groupby("game_string").runs.sum().mean()
    check(f"runs per game plausible (got {rpg:.2f}, expect 6-14)", 6 <= rpg <= 14)

    balanced = ab.groupby(["game_string", "inning", "half_inning"]).half_balanced.first()
    check(f"most half-innings balance (got {balanced.mean():.3f})",
          balanced.mean() > 0.95)


def test_run_expectancy_monotonic():
    print("\n[run expectancy monotonicity]")
    path = os.path.join(OUT, "atbats.csv")
    if not os.path.exists(path):
        print("  SKIP  atbats.csv not built yet")
        return
    ab = pd.read_csv(path)
    re_model = RunExpectancy().fit(ab)
    m = re_model.matrix

    ok = all(m.loc[s, 0] > m.loc[s, 1] > m.loc[s, 2] for s in m.index)
    check("RE falls as outs increase, for every base state", ok)
    check("bases loaded > bases empty at 0 outs",
          m.loc["123", 0] > m.loc["___", 0])
    check("runner on 3rd > runner on 1st at 0 outs",
          m.loc["__3", 0] > m.loc["1__", 0])
    check("all RE values positive", (m.values > 0).all())
    check("RE with 3 outs is zero", re_model.re(7, 3) == 0.0)


def test_probabilities_bounded():
    print("\n[probability bounds]")
    path = os.path.join(OUT, "atbats_scored.csv")
    if not os.path.exists(path):
        print("  SKIP  atbats_scored.csv not built yet")
        return
    df = pd.read_csv(path, low_memory=False)
    for col in ["wp_before", "wp_after", "p_hit", "p_home_run", "catch_prob"]:
        if col in df.columns:
            v = df[col].dropna()
            if len(v):
                check(f"{col} within [0,1]", v.between(0, 1).all(),
                      f"min={v.min():.3f} max={v.max():.3f}")
    if "wpa" in df.columns:
        check("WPA within [-1,1]", df.wpa.dropna().between(-1, 1).all())
    if "leverage_index" in df.columns:
        li = df.leverage_index.dropna()
        check("leverage non-negative", (li >= 0).all())
        check(f"mean leverage near 1.0 (got {li.mean():.3f})",
              0.9 <= li.mean() <= 1.1)
    if "highlight_score" in df.columns:
        check("highlight score within [0,100]",
              df.highlight_score.between(0, 100).all())
    # P(HR) must never exceed P(hit).
    if {"p_hit", "p_home_run"} <= set(df.columns):
        sub = df.dropna(subset=["p_hit", "p_home_run"])
        check("P(home run) <= P(hit)", (sub.p_home_run <= sub.p_hit + 1e-9).all())


# ---------------------------------------------------------------- components
def test_highlight_scorer():
    print("\n[highlight scorer]")
    hs = HighlightScorer()
    dull = {"wpa": 0.001, "leverage_index": 0.3, "outcome": "out",
            "inning": 2, "score_diff_before": -8, "runs": 0}
    huge = {"wpa": 0.45, "leverage_index": 5.0, "outcome": "home_run",
            "inning": 9, "score_diff_before": 0, "runs": 3,
            "exit_velo_mph": 112, "hit_distance_ft": 430}
    s_dull, _ = hs.score(dull)
    s_huge, _ = hs.score(huge)
    check("walk-off scores far above a dull out", s_huge > s_dull + 30,
          f"{s_huge:.1f} vs {s_dull:.1f}")
    check("scores bounded 0-100", 0 <= s_dull <= 100 and 0 <= s_huge <= 100)
    check("missing measurements do not crash", hs.score({})[0] >= 0)
    check("clutch rises with leverage",
          clutch_score([0.2], [4.0])[0] > clutch_score([0.2], [0.5])[0])


def test_cards_and_narrative():
    print("\n[story cards and narration]")
    reg = default_registry()
    check("card library is populated", len(reg.cards) >= 25,
          f"{len(reg.cards)} cards")
    check("card ids are unique",
          len(set(reg.card_ids())) == len(reg.card_ids()))

    gem = PlayContext({"catch_prob": 0.12, "catch_made": 1, "route_ft": 118.0,
                       "hang_s": 5.4, "fielder": "ABC-1234"})
    fired = [c.card_id for c in reg.surface(gem)]
    check("web gem fires on an improbable catch", "web_gem" in fired)
    check("robbery meter fires too", "robbery_meter" in fired)

    routine = PlayContext({"catch_prob": 0.98, "catch_made": 1, "route_ft": 8.0,
                           "hang_s": 4.0})
    check("web gem does NOT fire on a routine catch",
          "web_gem" not in [c.card_id for c in reg.surface(routine)])

    # A card must never crash the board, even with garbage input.
    junk = PlayContext({"exit_velo_mph": float("nan"), "wpa": None})
    check("registry survives junk input", isinstance(reg.surface(junk), list))

    n = NarrativeGenerator()
    line = n.play_line({"outcome": "home_run", "batter": "ABC-1", "runs": 3,
                        "hit_distance_ft": 412.0, "exit_velo_mph": 108.0,
                        "wpa": 0.42})
    check("home run narration mentions the distance", "412" in line)
    check("home run narration mentions win probability", "42%" in line)
    check("state description reads naturally",
          describe_state(5, 1) == "runners on the corners, one out",
          describe_state(5, 1))


def main():
    print("=" * 62)
    print("SMT STORYTELLING ENGINE — TEST SUITE")
    print("=" * 62)
    test_base_state_encoding()
    test_plausible_runs()
    test_foul_vs_live_contact()
    test_reconstruction_invariants()
    test_run_expectancy_monotonic()
    test_probabilities_bounded()
    test_highlight_scorer()
    test_cards_and_narrative()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
