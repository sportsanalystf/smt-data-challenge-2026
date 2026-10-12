# How to run this

Everything runs from the `submission/` folder.

```bash
cd ~/Desktop/SMT-Data-Challenge-2026/submission
```

---

## ⭐ START HERE — the R document

**`SMT_Play_Explorer.qmd`** is the R deliverable. One file, no other R sources,
renders to a standalone HTML you can email or open offline:

```bash
quarto render SMT_Play_Explorer.qmd
```

It does the whole chain in R: reconstructs play-by-play, fits run expectancy and
win probability, computes **WPA and Leverage together**, and ends with a
**clickable Play Explorer** — pick any plate appearance and watch it replay from
the tracking data with the numbers that explain it.

Takes ~2–3 minutes to render (it reconstructs 250 games to fit the models). To
render faster while drafting, open the file and set `N_GAMES <- 40` near the top.

> The earlier multi-file R version (`R/R01…R10`) and the ten-chapter Quarto book
> now live in `archive/` — kept for reference, not needed to run anything.

---

## 0. Check your machine first

```bash
python3 doctor.py
```

This tells you where it found the data, which packages you have, which pipeline
stages are already built, and **exactly what command to run next**. If it says
`READY`, you're good.

You do **not** need to set a data path — the engine auto-detects it, because
`submission/` lives inside the data folder. (If you move it, set
`export SMT_DATA_ROOT=/path/to/SMT-Data-Challenge-2026`.)

---

## 1. The results are already built

The outputs are committed, so you can look at them right now without running
anything:

| Open this | What it is |
|---|---|
| `outputs/play_explorer.html` | **Start here.** Click any at-bat and watch it — field replay, pitch tunnels, adaptive analysis |
| `outputs/scoreboard_dashboard.html` | Game-flow scoreboard with live win probability |
| `outputs/animations/*.gif` | Four rendered play animations |
| `outputs/engine_figures/*.png` | Broadcast graphics (win probability, leverage, attack zone…) |
| `outputs/engine/*.csv` | Every leaderboard and the full play-by-play table |

Double-click the HTML files — no server needed.

---

## 2. Rebuild everything from the raw data

```bash
python3 pipeline/run_all.py
```

Takes about 4 minutes and runs all nine stages in order. If you've already built
the slow pitch-location stage:

```bash
python3 pipeline/run_all.py --skip-pitch-locations    # ~30 seconds
```

### Or run a single stage

They must run in this order the first time, because each one consumes the
previous one's output:

```bash
python3 pipeline/build_state.py 0 250          # 1. outs/runs/score  (~20 s)
python3 pipeline/build_pitch_locations.py 0 250 # 2. plate locations (~3 min)
python3 pipeline/build_analytics.py             # 3. RE, WP, leverage, WPA (~5 s)
python3 pipeline/build_probability.py           # 4. catch/contact/zone models
python3 pipeline/build_highlights.py            # 5. highlight scores + packages
python3 pipeline/build_visuals.py               # 6. PNG broadcast graphics
python3 pipeline/build_playbook.py              # 7. per-play bundle
python3 pipeline/build_replay.py                # 8. play_explorer.html
python3 pipeline/build_animations.py            # 9. GIFs
```

---

## 3. Run the tests

```bash
python3 tests/test_engine.py         # state, RE/WP/leverage, cards, narration
python3 tests/test_playanalysis.py   # tunneling physics, anatomy, baselines
```

Both should end with `ALL TESTS PASSED`.

---

## 4. Requirements

Python 3.8+ and four packages:

```bash
pip install pandas numpy matplotlib pillow
```

That's the whole list — no scikit-learn, no polars. Every model is implemented
directly in NumPy.

---

## 5. The R side — details

Everything is in the single file `SMT_Play_Explorer.qmd` (see START HERE above).
There are no other R sources to load.

### 5.1 Install R and packages

Get R from [cran.r-project.org](https://cran.r-project.org/) (and optionally
[RStudio](https://posit.co/download/rstudio-desktop/)):

```r
install.packages(c("tidyverse", "arrow", "jsonlite", "scales"))
```

`arrow` is the slow one to install. `jsonlite` usually arrives with rmarkdown.
Nothing else is needed — no sportyR, gganimate, zoo or plyr.

### 5.2 Render

```bash
quarto render SMT_Play_Explorer.qmd
```

Output: `SMT_Play_Explorer.html` — fully standalone (`embed-resources: true`),
with the tracking data, charts and interactive explorer embedded.

### 5.3 Data path

Auto-detected when `submission/` sits inside the challenge folder. Otherwise set
it before rendering:

```r
Sys.setenv(SMT_DATA_ROOT = "/Users/you/Desktop/SMT-Data-Challenge-2026")
```

### 5.4 Verified

The R implementation has been run end to end (R 4.6.0, tidyverse 2.0.0,
arrow 24.0.0) over 250 games / 19,139 plate appearances, and its results match
the Python engine: plate appearances per game 76.6 vs 76.6, win-probability base
rate 0.517 vs 0.517, leverage mean 1.000 vs 1.000, catch-model accuracy 0.959 vs
0.955. Both produce a strictly monotonic run-expectancy matrix and independently
identify the same turning point in the showcase game.

### 5.5 Archived

The earlier multi-file R version (13 sources) and the ten-chapter Quarto book are
in `archive/` for reference. Nothing in `archive/` is needed to run the project.

---

## Troubleshooting

**`ModuleNotFoundError: smtstory`** — the pipeline scripts resolve their own
paths, so they work from any directory. If you hit this, you're calling the
engine directly from your own script; add the `submission/` folder to the path
first:

```python
import sys; sys.path.insert(0, "/path/to/submission")
from smtstory import dataio
```

**`no lineup rows for ...`** — expected for 4 of the 250 games; those have empty
lineup tables and are skipped automatically.

**Animations fail** — `pip install pillow`.

**A stage complains a file is missing** — you skipped an earlier stage. Run
`python3 doctor.py` and it will name the first one that hasn't been built.

**R: `IOError: Cannot list directory 'C:/Users/b.fryer/...'`** — fixed as of the
current version. The organizers' `SMT_Data_Starter.R` hard-codes a Windows path
and assigns it *as it is sourced*, so setting `data_directory` beforehand had no
effect. `source_smt_starter()` now rewrites that one line in memory before
evaluating the file (your copy on disk is never modified). If you still see it,
force the path:

```r
Sys.setenv(SMT_DATA_ROOT = "/Users/you/Desktop/SMT-Data-Challenge-2026")
source_smt_starter()
```

**R: `there is no package called 'plyr'`** — the starter's own `animate_play()`
uses it: `install.packages("plyr")`.
