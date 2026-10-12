"""
config.py — shared constants, paths, and the broadcast theme.

Also bootstraps access to the project's original `code/smt_utils.py` so the new
engine REUSES the existing tracking helpers rather than duplicating them.
"""
import os
import sys

# ---------------------------------------------------------------- paths
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
SUBMISSION_DIR = os.path.dirname(PKG_DIR)
LEGACY_CODE_DIR = os.path.join(SUBMISSION_DIR, "code")
OUTPUT_DIR = os.path.join(SUBMISSION_DIR, "outputs")
ENGINE_OUT = os.path.join(OUTPUT_DIR, "engine")

# Make the original smt_utils importable so we can reuse it.
if LEGACY_CODE_DIR not in sys.path:
    sys.path.insert(0, LEGACY_CODE_DIR)


def data_root():
    """Root folder holding ball-events/, ball-positions/, player-positions/, etc."""
    return os.environ.get("SMT_DATA_ROOT", os.path.dirname(SUBMISSION_DIR))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------- units
FT_S_TO_MPH = 0.681818
FRAME_MS = 50            # 20 Hz tracking
FRAME_HZ = 20

# ---------------------------------------------------------------- baseball
INNINGS_REGULATION = 9
OUTS_PER_HALF = 3

PLAYER_IDS = {
    "pitcher": 1, "catcher": 2, "first_baseman": 3, "second_baseman": 4,
    "third_baseman": 5, "shortstop": 6, "left_fielder": 7, "center_fielder": 8,
    "right_fielder": 9, "batter": 10, "runner_1b": 11, "runner_2b": 12,
    "runner_3b": 13,
}
POS_COL = {v: k for k, v in PLAYER_IDS.items() if v <= 10}
POS_ABBR = {
    1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
    7: "LF", 8: "CF", 9: "RF", 10: "BAT",
}
OUTFIELD_IDS = [7, 8, 9]
INFIELD_IDS = [3, 4, 5, 6]

EVENT = {
    "PITCH": 1, "ACQUIRED": 2, "THROW": 3, "HIT_INTO_PLAY": 4, "END_OF_PLAY": 5,
    "PICKOFF": 6, "ACQUIRED_UNK": 7, "THROW_UNK": 8, "DEFLECTION": 9,
    "DEFLECTION_WALL": 10, "HOME_RUN": 11, "BOUNCE": 16,
}
EVENT_LABEL = {v: k for k, v in EVENT.items()}

# ---------------------------------------------------------------- theme
# High-contrast palette chosen for legibility on a stadium scoreboard.
THEME = {
    "field_green": "#0b6b3a",
    "field_green_dark": "#07502b",
    "accent": "#c8102e",
    "gold": "#ffc72c",
    "ink": "#12181f",
    "panel": "#161f2b",
    "panel_light": "#22303f",
    "text": "#ffffff",
    "muted": "#9fb0c0",
    "good": "#22c55e",
    "bad": "#ef4444",
    "home": "#2f80ed",
    "away": "#f2994a",
}

# Minimum font sizes for scoreboard legibility (points, at 1x figure scale).
SCOREBOARD_MIN_LABEL_PT = 11
SCOREBOARD_TITLE_PT = 20
