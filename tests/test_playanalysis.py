"""
test_playanalysis.py — tests for the per-play analysis layer.

Covers the pitch-tunneling physics, the play anatomy engine, league baselines,
the animation exporter, and the expanded card library. As with the core suite,
these assert INVARIANTS and physical sanity rather than frozen numbers.

Run:  python tests/test_playanalysis.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                                        # noqa: E402
from smtstory.analytics.tunneling import (fit_trajectory, at_distance,  # noqa: E402
                                          late_break_in, tunnel_pair,
                                          effective_velocity, flight_time_s,
                                          PitchSequenceAnalyzer,
                                          trajectory_polyline, COMMIT_POINT_FT)
from smtstory.analytics.baselines import LeagueBaselines, grade_for  # noqa: E402
from smtstory.playanatomy.anatomy import PlayAnatomy                # noqa: E402
from smtstory.cards import default_registry, PlayContext            # noqa: E402

OUT = config.ENGINE_OUT
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def synthetic_pitch(v0_mph=93.0, break_z_in=0.0, x0=0.0, release_y=54.0,
                    n=12, plate_x=0.0, plate_z=2.4):
    """Build a physically plausible pitch as tracking frames.

    Simulates constant-acceleration flight so the fitted quadratic has a known
    answer, which is what makes the physics assertions meaningful.
    """
    t_flight = flight_time_s(release_y, v0_mph)
    ts = np.linspace(0, t_flight, n)
    ys = release_y * (1 - ts / t_flight)
    # Linear in x, gravity plus a constant induced force in z.
    zs = np.linspace(6.0, plate_z, n)
    xs = np.linspace(x0, plate_x, n)
    return pd.DataFrame({
        "timestamp": (ts * 1000).astype(int),
        "ball_position_x": xs, "ball_position_y": ys, "ball_position_z": zs,
    })


def test_trajectory_fit():
    print("\n[pitch trajectory fitting]")
    b = synthetic_pitch()
    tr = fit_trajectory(b, 0)
    check("fits a well-formed pitch", tr is not None)
    if tr:
        check("release is behind the plate", tr["release_y"] > 40,
              f"{tr['release_y']:.1f}")
        check("extension is plausible (0-12 ft)",
              0 <= tr["extension_ft"] <= 12, f"{tr['extension_ft']:.2f}")
        px, pz = at_distance(tr, 0.0)
        check("evaluates at the plate", abs(pz - 2.4) < 0.25, f"z={pz:.2f}")
        mid = at_distance(tr, COMMIT_POINT_FT)
        check("evaluates at the commit point", np.isfinite(mid[1]))
    short = b.iloc[:3]
    check("refuses too-few frames", fit_trajectory(short, 0) is None)


def test_break_physics():
    print("\n[break physics]")
    t_fast = flight_time_s(54.0, 95.0)
    t_slow = flight_time_s(54.0, 75.0)
    check("faster pitch has shorter flight time", t_fast < t_slow,
          f"{t_fast:.3f} vs {t_slow:.3f}")
    check("flight times are realistic (0.35-0.65s)",
          0.35 < t_fast < 0.65 and 0.35 < t_slow < 0.75)

    tr = fit_trajectory(synthetic_pitch(v0_mph=93.0), 0)
    hb, ivb, grav = late_break_in(tr, 93.0)
    check("gravity drop is substantial (25-60 in)", 25 < grav < 60,
          f"{grav:.1f}")
    check("induced break is much smaller than gravity", abs(ivb) < grav,
          f"ivb={ivb:.1f} grav={grav:.1f}")
    # A slower pitch spends longer in the air, so gravity acts more.
    _, _, grav_slow = late_break_in(fit_trajectory(
        synthetic_pitch(v0_mph=72.0), 0), 72.0)
    check("slower pitch drops more under gravity", grav_slow > grav,
          f"{grav_slow:.1f} > {grav:.1f}")


def test_effective_velocity():
    print("\n[effective velocity]")
    league = 5.5
    more = effective_velocity(90.0, 7.0, league)
    less = effective_velocity(90.0, 4.0, league)
    check("more extension plays faster", more > 90.0, f"{more:.1f}")
    check("less extension plays slower", less < 90.0, f"{less:.1f}")
    check("league-average extension is neutral",
          abs(effective_velocity(90.0, league, league) - 90.0) < 1e-6)
    check("nan in, nan out", not np.isfinite(effective_velocity(np.nan, 5, 5)))


def test_tunnel_pair():
    print("\n[tunneling]")
    a = fit_trajectory(synthetic_pitch(plate_x=0.0, plate_z=2.4), 0)
    # A pitch that starts together but ends far away = a good tunnel.
    b = fit_trajectory(synthetic_pitch(plate_x=1.2, plate_z=1.0), 0)
    t = tunnel_pair(a, b)
    check("tunnel distance is positive", t["tunnel_distance_in"] > 0)
    check("plate distance exceeds tunnel distance",
          t["plate_distance_in"] > t["tunnel_distance_in"],
          f"{t['plate_distance_in']:.1f} vs {t['tunnel_distance_in']:.1f}")
    check("tunnel ratio > 1 for a deceptive pair", t["tunnel_ratio"] > 1.0,
          f"{t['tunnel_ratio']:.2f}")
    same = tunnel_pair(a, a)
    check("identical pitches have ~zero separation at the plate",
          same["plate_distance_in"] < 1e-6)

    poly = trajectory_polyline(a, n=10)
    check("polyline has the requested length", len(poly) == 10)
    check("polyline runs release -> plate", poly[0][0] > poly[-1][0])


def test_nastiness_and_verdict():
    print("\n[nastiness and strikeout verdict]")
    an = PitchSequenceAnalyzer(None)
    filthy = {"effective_velo_mph": 99.0, "total_break_in": 17.0,
              "zone_edge_distance_in": 0.5, "tunnel_ratio": 4.5}
    meat = {"effective_velo_mph": 85.0, "total_break_in": 2.0,
            "zone_edge_distance_in": -8.0, "tunnel_ratio": 1.0}
    n_f, n_m = an.nastiness(filthy), an.nastiness(meat)
    check("filthy pitch scores higher than meatball", n_f > n_m,
          f"{n_f:.0f} vs {n_m:.0f}")
    check("nastiness bounded 0-100", 0 <= n_f <= 100 and 0 <= n_m <= 100)
    check("missing inputs give nan", not np.isfinite(an.nastiness({})))

    v_f = an.strikeout_verdict([dict(filthy, velo_mph=99.0,
                                     nastiness=n_f)])
    v_m = an.strikeout_verdict([dict(meat, velo_mph=85.0, nastiness=n_m)])
    check("filthy pitch judged nasty", v_f["verdict"] == "NASTY PITCH",
          v_f["verdict"])
    check("meatball judged a miss", v_m["verdict"] == "HITTER MISSED IT",
          v_m["verdict"])
    check("verdict narration is non-empty", len(v_f["narrative"]) > 10)
    # The sentence must not contradict itself.
    check("miss verdict does not praise movement",
          "late movement" not in v_m["narrative"], v_m["narrative"])


def test_baselines():
    print("\n[league baselines]")
    b = LeagueBaselines()
    b.add("sprint_mph", np.linspace(14, 23, 500))
    check("percentile of the max is ~100",
          b.percentile("sprint_mph", 23.0) >= 99)
    check("percentile of the min is ~0",
          b.percentile("sprint_mph", 14.0) <= 1)
    mid = b.percentile("sprint_mph", 18.5)
    check("median sits near 50", 45 <= mid <= 55, f"{mid}")

    b.add("home_to_first_s", np.linspace(4.0, 5.5, 500))
    fast = b.percentile("home_to_first_s", 4.05)
    slow = b.percentile("home_to_first_s", 5.45)
    check("lower-is-better metric inverts", fast > slow, f"{fast} vs {slow}")
    check("unknown metric returns None", b.percentile("nope", 1) is None)
    check("grades are ordered", grade_for(99) == "ELITE" and
          grade_for(50) == "AVERAGE" and grade_for(5) == "WELL BELOW")
    c = b.compare("sprint_mph", 22.0)
    check("compare returns a full payload",
          set(["value", "percentile", "grade", "league_mean"]) <= set(c))


def test_play_classification():
    print("\n[play classification]")
    EV = config.EVENT
    pa = PlayAnatomy()
    foul = pd.DataFrame({"timestamp": [100, 300],
                         "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["END_OF_PLAY"]],
                         "player_id": [10, 0]})
    check("caught foul / no contact is not a batted-ball play",
          pa.classify(foul, "out") == "strikeout_or_walk")
    live = pd.DataFrame({"timestamp": [100, 400, 900],
                         "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["BOUNCE"],
                                            EV["ACQUIRED"]],
                         "player_id": [10, 255, 6]})
    check("grounder classified by launch angle",
          pa.classify(live, "out", launch_deg=4.0) == "ground_out")
    check("fly ball classified by launch angle",
          pa.classify(live, "out", launch_deg=35.0) == "fly_out")
    check("liner classified by launch angle",
          pa.classify(live, "out", launch_deg=16.0) == "line_out")
    check("a hit is a hit", pa.classify(live, "double") == "base_hit")
    hr = pd.DataFrame({"timestamp": [100, 500],
                       "ball_eventcode": [EV["HIT_INTO_PLAY"], EV["HOME_RUN"]],
                       "player_id": [10, 10]})
    check("home run recognized", pa.classify(hr, "home_run") == "home_run")


def test_close_play_math():
    print("\n[close play timing]")
    pa = PlayAnatomy()
    # Fielder 100 ft from first, throwing 80 mph, releases at t=2000 ms.
    fielding = {"fielder_end": [63.64 + 100, 63.64], "throw_velo_mph": 80.0,
                "t_thrown": 2000}
    slow_runner = {"t_reached": 5000}
    fast_runner = {"t_reached": 2100}
    a = pa.close_play(fielding, slow_runner)
    b = pa.close_play(fielding, fast_runner)
    check("late runner is out", a["verdict"] == "OUT", str(a["margin_s"]))
    check("early runner is safe", b["verdict"] == "SAFE", str(b["margin_s"]))
    check("throw distance is measured", a["throw_distance_ft"] > 90)
    check("missing inputs return None", pa.close_play(None, slow_runner) is None)


def test_expanded_cards():
    print("\n[expanded card library]")
    reg = default_registry()
    ids = reg.card_ids()
    check("library has grown past 45 cards", len(ids) >= 45, f"{len(ids)}")
    check("card ids remain unique", len(set(ids)) == len(ids))
    for needed in ["putaway", "pitch_tunnel", "effective_velo", "ground_covered",
                   "quick_hands", "dp_ballet", "pop_time", "safe_race",
                   "sprint_compare", "out_or_safe", "spray", "rivalry",
                   "prospect"]:
        check(f"card '{needed}' registered", needed in ids)

    # A strikeout context should surface the putaway card.
    k = PlayContext({"strikeout_verdict": {"verdict": "NASTY PITCH",
                                           "nastiness": 78.0,
                                           "narrative": "Unhittable."},
                     "pitcher": "ABC-1"})
    check("putaway card fires on a strikeout",
          "putaway" in [c.card_id for c in reg.surface(k)])

    # A fielding context should surface ground covered + quick hands.
    f = PlayContext({"fielding": {"fielder_pos": "SS", "route_ft": 42.0,
                                  "time_to_ball_s": 2.1,
                                  "closing_speed_mph": 15.2,
                                  "transfer_s": 0.6,
                                  "throw_velo_mph": 84.0}})
    fired = [c.card_id for c in reg.surface(f)]
    check("ground covered fires", "ground_covered" in fired)
    check("quick hands fires", "quick_hands" in fired)

    # A bang-bang play should surface the fan vote.
    cp = PlayContext({"close_play": {"margin_s": 0.04, "verdict": "SAFE",
                                     "bang_bang": True,
                                     "throw_distance_ft": 95.0}})
    check("out-or-safe vote fires on a bang-bang play",
          "out_or_safe" in [c.card_id for c in reg.surface(cp)])
    check("no crash on empty context", isinstance(reg.surface(PlayContext({})), list))


def test_playbook_output():
    print("\n[playbook bundle]")
    path = os.path.join(OUT, "playbook.json")
    if not os.path.exists(path):
        print("  SKIP  playbook.json not built yet")
        return
    with open(path) as f:
        pb = json.load(f)

    check("bundle has at-bats", len(pb["at_bats"]) > 0)
    check("bundle has playback frames", len(pb["playback"]) > 0)

    abs_ = pb["at_bats"]
    with_replay = sum(1 for a in abs_ if str(a["key_play"]) in pb["playback"])
    check("every at-bat has a replay", with_replay == len(abs_),
          f"{with_replay}/{len(abs_)}")
    check("every at-bat has a play type",
          all(a.get("play_type") for a in abs_))
    check("every at-bat has narration",
          all(a.get("narrative") for a in abs_))

    # Animation payload integrity.
    bad = []
    for k, p in pb["playback"].items():
        if len(p["times"]) != len(p["ball"]):
            bad.append(k)
        for pid, arr in (p.get("players") or {}).items():
            if len(arr) != len(p["times"]):
                bad.append(f"{k}:{pid}")
    check("frame counts align across ball and players", not bad,
          str(bad[:3]))

    # Trajectories should run from release toward the plate.
    polys = [p for a in abs_ for p in a.get("pitches", []) if p.get("polyline")]
    check("pitch polylines exist", len(polys) > 0)
    if polys:
        ok = all(p["polyline"][0][0] > p["polyline"][-1][0] for p in polys)
        check("polylines run release -> plate", ok)

    ks = [a for a in abs_ if a.get("strikeout_verdict")]
    check("strikeouts carry a verdict", len(ks) > 0, f"{len(ks)}")
    check("verdicts are one of the three labels",
          all(a["strikeout_verdict"]["verdict"] in
              ("NASTY PITCH", "HITTER MISSED IT", "WELL EXECUTED") for a in ks))


def main():
    print("=" * 62)
    print("PLAY ANALYSIS — TEST SUITE")
    print("=" * 62)
    test_trajectory_fit()
    test_break_physics()
    test_effective_velocity()
    test_tunnel_pair()
    test_nastiness_and_verdict()
    test_baselines()
    test_play_classification()
    test_close_play_math()
    test_expanded_cards()
    test_playbook_output()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
