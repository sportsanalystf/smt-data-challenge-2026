"""
build_replay.py — Stage 8: the interactive Play Explorer.

Reads the playbook bundle and writes a single self-contained HTML file in which
every at-bat can be clicked, watched, and understood.

Usage: python pipeline/build_replay.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smtstory import config                     # noqa: E402
from smtstory.web.replay import build_replay_dashboard  # noqa: E402

OUT = config.ENGINE_OUT


def main():
    src = os.path.join(OUT, "playbook.json")
    with open(src) as f:
        playbook = json.load(f)

    dest = os.path.join(config.OUTPUT_DIR, "play_explorer.html")
    build_replay_dashboard(playbook, dest)
    mb = os.path.getsize(dest) / 1e6

    abs_ = playbook["at_bats"]
    with_track = sum(1 for a in abs_ if str(a["key_play"]) in playbook["playback"])
    with_pitch = sum(1 for a in abs_ if a.get("pitches"))
    with_anat = sum(1 for a in abs_ if (a.get("anatomy") or {}).get("fielding"))
    print(f"wrote {dest} ({mb:.2f} MB)")
    print(f"  at-bats: {len(abs_)}")
    print(f"  with field replay: {with_track}")
    print(f"  with pitch trajectories: {with_pitch}")
    print(f"  with fielding anatomy: {with_anat}")
    print(f"  playback plays embedded: {len(playbook['playback'])}")


if __name__ == "__main__":
    main()
