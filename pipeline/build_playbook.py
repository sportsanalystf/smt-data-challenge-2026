"""
build_playbook.py — Stage 7: the per-play "watchable" bundle.

For the showcase game this assembles, for EVERY at-bat:

  * the animation frames (ball + players) so the play can be replayed
  * the pitch-by-pitch sequence with tunneling, break, and nastiness
  * the play anatomy (who fielded it, ground covered, transfer, throw, the race)
  * league percentile comparisons for every headline measurement
  * the story cards that fire, and the narration

This is the file the interactive dashboard reads.

Usage: python pipeline/build_playbook.py [game_string]
"""
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config, dataio                        # noqa: E402
from smtstory.analytics.tunneling import (PitchSequenceAnalyzer,   # noqa: E402
                                          trajectory_polyline)
from smtstory.analytics.baselines import (build_from_features,  # noqa: E402
                                          grade_for)
from smtstory.playanatomy import PlayAnatomy                 # noqa: E402
from smtstory.playback import export_game_playback           # noqa: E402
from smtstory.cards import default_registry, PlayContext     # noqa: E402
from smtstory.narrative import NarrativeGenerator            # noqa: E402

OUT = config.ENGINE_OUT
FEAT = os.path.join(config.OUTPUT_DIR, "feat")


def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if not np.isfinite(f) else round(f, 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return v


def main(game_string=None):
    scored = pd.read_csv(os.path.join(OUT, "atbats_scored.csv"), low_memory=False)
    summaries = pd.read_csv(os.path.join(OUT, "game_summaries.csv"))
    if game_string is None:
        with open(os.path.join(OUT, "highlight_packages.json")) as f:
            game_string = json.load(f)["game_string"]

    with open(os.path.join(OUT, "probability_models.pkl"), "rb") as f:
        pm = pickle.load(f)

    print(f"building playbook for {game_string}")

    # ------------------------------------------------------------ baselines
    base = build_from_features(FEAT, OUT)
    base.to_json(os.path.join(OUT, "league_baselines.json"))
    print(f"baselines: {list(base.summary)}")

    game = dataio.load_game(dataio.game_dir_from_string(game_string),
                            with_player_tracking=True)
    ab = scored[scored.game_string == game_string].copy().reset_index(drop=True)
    srow = summaries[summaries.game_string == game_string]
    summary = srow.iloc[0].to_dict() if len(srow) else {"game_string": game_string}

    # Pitch velocities for this game, keyed by play.
    pl = pd.read_csv(os.path.join(OUT, "pitch_locations.csv"))
    pg = pl[pl.game_string == game_string]
    velos = dict(zip(pg.play, pg.pitch_velo_mph))

    analyzer = PitchSequenceAnalyzer(pm["zone"])
    anatomy = PlayAnatomy(pm["catch"], base)
    registry = default_registry()
    narrator = NarrativeGenerator({
        "max_exit_velo_game": ab.exit_velo_mph.max()
        if "exit_velo_mph" in ab else None,
        "max_pitch_velo_game": ab.pitch_velo_mph.max()
        if "pitch_velo_mph" in ab else None,
    })

    # -------------------------------------------------- per at-bat assembly
    lu = game.lineups.groupby("at_bat").play_per_game.apply(list).to_dict()
    entries = []
    spray = []

    for _, r in ab.iterrows():
        row = {k: _clean(v) for k, v in r.items()}
        at_bat = int(row["at_bat"])
        plays = sorted(set(int(p) for p in lu.get(at_bat, [int(row["last_play"])])))

        # ---- pitch sequence + tunneling
        pitches = analyzer.analyze_at_bat(game.ball, game.events, plays, velos)
        seq = []
        for p in pitches:
            traj = p.pop("_traj", None)
            item = {k: _clean(v) for k, v in p.items()}
            if traj is not None:
                item["polyline"] = trajectory_polyline(traj)
            seq.append(item)
        verdict = None
        if row.get("outcome") == "out" and not row.get("ball_in_play"):
            verdict = analyzer.strikeout_verdict(pitches)
            if verdict:
                verdict = {k: _clean(v) if not isinstance(v, (dict, list)) else v
                           for k, v in verdict.items()}

        # ---- anatomy
        anat = anatomy.analyze(game, row, row.get("launch_deg"))
        if anat:
            anat = json.loads(json.dumps(anat, default=_clean))

        # ---- league comparisons
        comps = {}
        run = (anat or {}).get("running") or {}
        fld = (anat or {}).get("fielding") or {}
        if run.get("top_speed_mph"):
            comps["sprint"] = base.compare("sprint_mph", run["top_speed_mph"])
        if fld.get("route_ft"):
            comps["route"] = base.compare("route_ft", fld["route_ft"])
        if fld.get("throw_velo_mph"):
            comps["throw"] = base.compare("throw_velo_mph", fld["throw_velo_mph"])
        if row.get("exit_velo_mph"):
            comps["exit_velo"] = base.compare("exit_velo_mph", row["exit_velo_mph"])
        if row.get("pitch_velo_mph"):
            comps["pitch_velo"] = base.compare("pitch_velo_mph",
                                               row["pitch_velo_mph"])

        # ---- context for the cards
        ctx_d = dict(row)
        ctx_d.update({
            "strikeout_verdict": verdict,
            "fielding": fld or None,
            "running": run or None,
            "close_play": (anat or {}).get("close_play"),
            "double_play": (anat or {}).get("double_play"),
            "sprint_percentile": (comps.get("sprint") or {}).get("percentile"),
            "sprint_grade": (comps.get("sprint") or {}).get("grade"),
            "route_percentile": (comps.get("route") or {}).get("percentile"),
            "throw_percentile": (comps.get("throw") or {}).get("percentile"),
            "pitch_velo_percentile": (comps.get("pitch_velo") or {}).get("percentile"),
        })
        if seq:
            last = seq[-1]
            for k in ("tunnel_ratio", "tunnel_distance_in", "plate_distance_in",
                      "break_vertical_in", "break_horizontal_in",
                      "effective_velo_mph", "velo_mph", "extension_ft"):
                if last.get(k) is not None:
                    ctx_d.setdefault(k, last[k])
        if run.get("time_to_base_s"):
            ctx_d["home_to_first_s"] = run["time_to_base_s"]
        if run.get("burst_ft_s2"):
            ctx_d["burst_ft_s2"] = run["burst_ft_s2"]

        cards = [c.to_dict() for c in registry.surface(PlayContext(ctx_d), limit=5)]

        if row.get("hit_distance_ft") and fld.get("fielder_end"):
            spray.append({"x": fld["fielder_end"][0], "y": fld["fielder_end"][1],
                          "ev": row.get("exit_velo_mph"),
                          "outcome": row.get("outcome")})

        entries.append({
            "at_bat": at_bat,
            "inning": row.get("inning"),
            "half": row.get("half_inning"),
            "batter": row.get("batter"),
            "pitcher": row.get("pitcher"),
            "outcome": row.get("outcome"),
            "runs": row.get("runs"),
            "outs_before": row.get("outs_before"),
            "base_state": row.get("base_state_before"),
            "home_score": row.get("home_score_after"),
            "away_score": row.get("away_score_after"),
            "wp_home": (row.get("wp_after") if row.get("half_inning") == "Bottom"
                        else (1 - row["wp_after"]) if row.get("wp_after") is not None
                        else None),
            "wpa": row.get("wpa"), "leverage": row.get("leverage_index"),
            "highlight": row.get("highlight_score"),
            "play_type": (anat or {}).get("play_type", "unknown"),
            "plays": plays,
            "key_play": int(row["last_play"]),
            "situation": narrator.situation_line(row),
            "narrative": narrator.play_line(row),
            "insights": narrator.insight_lines(row),
            "pitches": seq,
            "strikeout_verdict": verdict,
            "anatomy": anat,
            "comparisons": comps,
            "cards": cards,
        })

    # ---------------------------------------------------------- animation
    all_plays = sorted({p for e in entries for p in e["plays"]})
    playback = export_game_playback(game, all_plays)
    print(f"playback: {len(playback)} plays with tracking")

    bundle = {
        "game_string": game_string,
        "meta": {"home": summary.get("home_team"), "away": summary.get("away_team"),
                 "home_final": _clean(summary.get("home_final")),
                 "away_final": _clean(summary.get("away_final"))},
        "zone": {"bottom": pm["zone"].bottom, "top": pm["zone"].top,
                 "half_width": pm["zone"].half_width},
        "baselines": base.summary,
        "at_bats": entries,
        "playback": playback,
    }

    dest = os.path.join(OUT, "playbook.json")
    with open(dest, "w") as f:
        json.dump(bundle, f, default=_clean, separators=(",", ":"))
    mb = os.path.getsize(dest) / 1e6
    print(f"wrote {dest} ({mb:.2f} MB)")

    # ------------------------------------------------------------- report
    types = pd.Series([e["play_type"] for e in entries]).value_counts()
    print("\nplay types:", types.to_dict())
    ks = [e for e in entries if e.get("strikeout_verdict")]
    print(f"strikeouts with a verdict: {len(ks)}")
    for e in ks[:3]:
        v = e["strikeout_verdict"]
        print(f"  {e['batter']}: {v['verdict']} ({v['nastiness']:.0f}) — "
              f"{v['narrative']}")
    ncards = sum(len(e["cards"]) for e in entries)
    print(f"cards fired: {ncards} across {len(entries)} at-bats "
          f"(registry has {len(registry.cards)} cards)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
