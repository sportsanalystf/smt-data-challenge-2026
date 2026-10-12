"""
doctor.py — preflight check. Run this first.

Tells you, in one command, whether this machine can run the project: where it
found the data, which Python packages are present, which pipeline stages have
already produced output, and what to run next.

    python doctor.py
"""
import importlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OK, WARN, BAD = "  OK  ", " WARN ", " MISS "


def line(status, label, detail=""):
    print(f"[{status}] {label:38s} {detail}")


def main():
    print("=" * 74)
    print("SMT STORYTELLING ENGINE — PREFLIGHT")
    print("=" * 74)
    problems, warnings = [], []

    # ---------------------------------------------------------------- python
    print("\nPYTHON")
    v = sys.version_info
    ok_py = v >= (3, 8)
    line(OK if ok_py else BAD, "python version", f"{v.major}.{v.minor}.{v.micro}")
    if not ok_py:
        problems.append("Python 3.8+ required")

    required = ["pandas", "numpy", "matplotlib"]
    optional = {"PIL": "Pillow — needed to write animated GIFs"}
    for mod in required:
        try:
            m = importlib.import_module(mod)
            line(OK, mod, getattr(m, "__version__", ""))
        except ImportError:
            line(BAD, mod, "REQUIRED")
            problems.append(f"pip install {mod}")
    for mod, why in optional.items():
        try:
            importlib.import_module(mod)
            line(OK, mod, why)
        except ImportError:
            line(WARN, mod, f"optional — {why}")
            warnings.append("pip install pillow   (for animations)")

    # ------------------------------------------------------------------ data
    print("\nDATA")
    try:
        from smtstory import config
        root = config.data_root()
    except Exception as exc:
        line(BAD, "import smtstory", str(exc))
        problems.append("could not import the engine")
        root = None

    if root:
        line(OK, "data root", root)
        env = os.environ.get("SMT_DATA_ROOT")
        line(OK if env else WARN, "SMT_DATA_ROOT",
             env or "not set (auto-detected from folder layout)")
        for name, kind in [("ball-events", "dir"), ("ball-positions", "dir"),
                           ("player-positions", "dir"), ("lineups.csv", "file"),
                           ("game-info.csv", "file")]:
            p = os.path.join(root, name)
            good = os.path.isdir(p) if kind == "dir" else os.path.isfile(p)
            line(OK if good else BAD, name, p if good else "NOT FOUND")
            if not good:
                problems.append(f"missing {name} — set SMT_DATA_ROOT to the "
                                f"folder containing it")

    # ---------------------------------------------------------- stage output
    print("\nPIPELINE OUTPUT (what has already been built)")
    eng = os.path.join(HERE, "outputs", "engine")
    stages = [
        ("1. game state", os.path.join(eng, "atbats.csv"),
         "python pipeline/build_state.py 0 250"),
        ("2. pitch locations", os.path.join(eng, "pitch_locations.csv"),
         "python pipeline/build_pitch_locations.py 0 250"),
        ("3. analytics (WPA/LI)", os.path.join(eng, "atbats_enriched.csv"),
         "python pipeline/build_analytics.py"),
        ("4. probability models", os.path.join(eng, "probability_models.pkl"),
         "python pipeline/build_probability.py"),
        ("5. highlights", os.path.join(eng, "highlight_packages.json"),
         "python pipeline/build_highlights.py"),
        ("6. figures", os.path.join(HERE, "outputs", "engine_figures",
                                    "wp_chart.png"),
         "python pipeline/build_visuals.py"),
        ("7. playbook", os.path.join(eng, "playbook.json"),
         "python pipeline/build_playbook.py"),
        ("8. play explorer", os.path.join(HERE, "outputs",
                                          "play_explorer.html"),
         "python pipeline/build_replay.py"),
        ("9. animations", os.path.join(HERE, "outputs", "animations",
                                       "play_turning_point.gif"),
         "python pipeline/build_animations.py"),
    ]
    missing_stage = None
    for label, path, cmd in stages:
        good = os.path.exists(path)
        size = f"{os.path.getsize(path)/1e6:.1f} MB" if good else "not built"
        line(OK if good else WARN, label, size)
        if not good and missing_stage is None:
            missing_stage = (label, cmd)

    # -------------------------------------------------------------- optional
    print("\nOPTIONAL TOOLCHAINS")
    for exe, why in [("quarto", "render the R + Python book"),
                     ("Rscript", "run the R implementation")]:
        p = shutil.which(exe)
        line(OK if p else WARN, exe, p or f"not installed — needed to {why}")

    # ----------------------------------------------------------------- verdict
    print("\n" + "=" * 74)
    if problems:
        print("NOT READY — fix these first:")
        for p in dict.fromkeys(problems):
            print("   *", p)
        return 1

    print("READY")
    if warnings:
        for w in dict.fromkeys(warnings):
            print("   note:", w)
    if missing_stage:
        print(f"\nNext step ({missing_stage[0]} not built yet):")
        print(f"   {missing_stage[1]}")
        print("\nOr build everything at once:")
        print("   python pipeline/run_all.py")
    else:
        print("\nAll stages built. Open the results:")
        print("   outputs/play_explorer.html          click any at-bat and watch it")
        print("   outputs/scoreboard_dashboard.html   game-flow scoreboard")
        print("   outputs/animations/*.gif            rendered play animations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
