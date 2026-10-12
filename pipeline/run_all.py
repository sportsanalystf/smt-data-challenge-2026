"""
run_all.py — run the entire storytelling engine end to end.

Stages, in dependency order:

  1. build_state           reconstruct outs/runs/score for every game
  2. build_pitch_locations per-pitch plate location (skipped if cached)
  3. build_analytics       run expectancy, win probability, leverage, WPA
  4. build_probability     zone / contact / catch / baserunning models
  5. build_highlights      highlight scores and auto-generated packages
  6. build_visuals         broadcast PNG graphics
  7. build_dashboard       self-contained interactive scoreboard
  8. tests                 invariant test suite

Usage:  python pipeline/run_all.py [--skip-pitch-locations]
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STAGES = [
    ("Reconstruct game state", ["build_state.py", "0", "250"]),
    ("Extract pitch locations", ["build_pitch_locations.py", "0", "250"]),
    ("Fit core analytics", ["build_analytics.py"]),
    ("Fit probability models", ["build_probability.py"]),
    ("Score highlights", ["build_highlights.py"]),
    ("Render broadcast graphics", ["build_visuals.py"]),
    ("Build interactive dashboard", ["build_dashboard.py"]),
    ("Build per-play playbook", ["build_playbook.py"]),
    ("Build interactive Play Explorer", ["build_replay.py"]),
]


def run(name, args):
    print("\n" + "=" * 66)
    print(f"STAGE: {name}")
    print("=" * 66)
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, args[0])] + args[1:],
                       cwd=ROOT)
    print(f"[{name}] finished in {time.time()-t:.1f}s (exit {r.returncode})")
    return r.returncode


def main():
    skip_pitch = "--skip-pitch-locations" in sys.argv
    failed = []
    for name, args in STAGES:
        if skip_pitch and args[0] == "build_pitch_locations.py":
            print(f"\n[skipping] {name} (cached)")
            continue
        if run(name, args) != 0:
            failed.append(name)

    print("\n" + "=" * 66)
    print("STAGE: Tests")
    print("=" * 66)
    if subprocess.run([sys.executable, os.path.join(ROOT, "tests", "test_engine.py")],
                      cwd=ROOT).returncode != 0:
        failed.append("tests")

    print("\n" + "=" * 66)
    print("PIPELINE COMPLETE" if not failed else f"PIPELINE FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
