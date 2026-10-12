# SMT Data Challenge 2026 — "On the Big Screen!"

A **Real-Time Baseball Storytelling Engine**: instead of showing raw statistics,
it automatically finds the interesting moments in a game, explains why they
matter, and presents them as broadcast-quality graphics a fan understands
instantly.

Built on 250 games of SMT player and ball tracking (Level-7 MiLB, one season).

---

## Quick start

```bash
export SMT_DATA_ROOT=/path/to/SMT-Data-Challenge-2026

python pipeline/run_all.py           # full pipeline, ~4 min
python pipeline/build_animations.py  # render play GIFs
python tests/test_engine.py          # invariant test suite
python tests/test_playanalysis.py    # play-analysis test suite

quarto render quarto/                # the R + Python book
```

## Built twice — R and Python

Every analysis component exists in **both languages**, with a Quarto chapter
showing them side by side:

| # | Component | R | Python | Chapter |
|---|---|---|---|---|
| 1 | Play-by-play from tracking | `R/R01_play_by_play.R` | `components/c01_play_by_play.py` | `quarto/01-play-by-play.qmd` |
| 2 | WPA & Leverage Index | `R/R02_wpa_leverage.R` | `components/c02_wpa_leverage.py` | `quarto/02-wpa-leverage.qmd` |
| 3 | Tracking features | `R/R03_tracking_features.R` | `components/c03_tracking_features.py` | — |
| 4 | Speed & baserunning | `R/R04_speed_baserunning.R` | `components/c04_speed_baserunning.py` | `quarto/04-…` |
| 5 | Power & hitting | `R/R05_power_hitting.R` | `components/c05_power_hitting.py` | `quarto/05-…` |
| 6 | Pitching | `R/R06_pitching.R` | `components/c06_pitching.py` | `quarto/06-…` |
| 7 | Defense & fielding | `R/R07_defense.R` | `components/c07_defense.py` | `quarto/07-…` |
| 8 | Fan-interactive games | `R/R08_fan_interactive.R` | `components/c08_fan_interactive.py` | `quarto/08-…` |
| 9 | Composite & storytelling | `R/R09_composite.R` | `components/c09_composite.py` | `quarto/09-…` |
| 10 | Play animation | `R/R10_animation.R` | `components/c10_animation.py` | `quarto/03-animation.qmd` |

The R side extends the organizers' `SMT_Data_Starter.R` directly — its Arrow
datasets, `animate_play()` and `create_play_by_play()` are reused, not rebuilt.

### Validation status of each language

- **Python** — executed against all 246 games; two test suites pass.
- **R** — executed end to end on macOS (R 4.6.0): 250 games, 19,139 plate
  appearances, 96.8 s. Results match Python closely (PA/game 76.6 vs 76.6,
  WP base rate 0.517 vs 0.517, leverage mean 1.000 vs 1.000, catch-model
  accuracy 0.959 vs 0.955). Full parity table in `R/README.md`.
- **Quarto** — `tools/check_quarto.py` validates YAML, chunk fences, unique
  labels, image paths, and **compiles every Python chunk** (10 documents,
  90 chunks, 0 problems).

**Two independent implementations agreeing** is the strongest evidence in this
submission: the R and Python engines were written separately from the same
documented algorithms, and both produce a strictly monotonic run-expectancy
matrix and independently identify the same turning point in the showcase game
(a walk-off three-run homer in the bottom of the 11th, WPA ≈ +0.81).

---

## What's here

### Round 1 — the original submission (unchanged, still builds)

| File | What it is |
|---|---|
| `Abstract.docx` | Required abstract. |
| `Narrative_Paper.docx` | Required narrative paper with embedded figures. |
| `SMT_Analysis.qmd` | Required Quarto analysis. |
| `SMT_Master_Idea_List.docx` | ~30 ideas plus the Top-10 selection. |
| `code/` | Original extractors, catch model, and figure scripts. |

### Round 2 — the storytelling engine

| Path | What it is |
|---|---|
| **`ARCHITECTURE.md`** | **Start here** — design, methodology, validation, honest limits. |
| `smtstory/` | The modular engine (see below). |
| `pipeline/` | Nine runnable stages plus `run_all.py`. |
| `tests/` | Two invariant test suites (no pytest needed). |
| **`outputs/play_explorer.html`** | **Click any at-bat and watch it.** Field replay, pitch tunnels, adaptive analysis. |
| `outputs/scoreboard_dashboard.html` | Game-flow scoreboard with live win probability. |
| `outputs/engine_figures/` | Broadcast PNG graphics. |
| `outputs/engine/` | Tables, fitted models, playbook, highlight packages. |

### The Play Explorer

Open `outputs/play_explorer.html` and click any at-bat. What you get depends on
how the play ended:

| If the at-bat ended in… | You see |
|---|---|
| a **strikeout** | every pitch drawn from the catcher's angle and in profile, with the commit-point line, induced break, tunnel ratio, extension, and a verdict: *nasty pitch* or *bad swing* |
| a **ground out** | the fielder's route and ground covered, time to the ball, transfer time, throw velocity, and the race to first with a SAFE/OUT margin |
| a **fly out** | route distance, hang time, closing speed, route efficiency, and the catch-probability odds |
| a **base hit** | where it went, which fielder had a chance, and the runner's sprint speed against every runner in the league |

All of it animates: the ball and all nine fielders move from the real 20 Hz
tracking, with the ball growing as it rises so fly balls read as airborne.

### The engine, layer by layer

```
smtstory/
  config.py       constants, theme, paths (also bootstraps the original smt_utils)
  dataio/         table loading                    ← wraps existing smt_utils
  tracking/       geometry + kinematics            ← wraps existing smt_utils
  state/          GAME STATE RECONSTRUCTION (outs, runs, score) + validation
  analytics/      run expectancy · win probability · leverage · WPA · highlight
                  · pitch tunneling · league baselines
  probability/    zone · contact · catch (Robbery Meter) · baserunning
  playanatomy/    per-play fielding, baserunning, close plays, double plays
  playback/       compact tracking frames for animation
  cards/          52 story cards in 6 categories
  narrative/      broadcast sentence generation
  highlights/     automatic highlight packages
  viz/            broadcast PNG layer
  web/            scoreboard dashboard + Play Explorer
```

Each layer depends only on the ones above it, so components are swappable and
separately testable.

---

## The key technical problem

The SMT data has base occupancy but **no outs, no count, and no score** — so
win probability, leverage and run expectancy cannot be computed at all until
game state is recovered. `smtstory/state/` reconstructs it from occupancy
transitions and the event stream using an accounting identity closed by the
three-out constraint, with a baseball-physics plausibility bound.

**Validation against real baseball:**

| Quantity | Reconstructed | Real MiLB |
|---|---|---|
| Runs per game | **10.12** | ≈ 9.5 |
| Hits per game | **19.7** | ≈ 18 |
| Half-innings balancing to 3 outs | **99.8 %** | 100 % |
| State anomalies (flagged & quarantined) | 0.27 % | — |

An independent check in `state/validate.py` counts runners crossing home plate
in the 20 Hz tracking, giving a lower bound of 7.7 runs/game. The truth sits
between the two.

---

## Model performance

| Model | Metric |
|---|---|
| Win probability | accuracy 0.774, Brier 0.144 (n = 18,834) |
| Leverage index | mean 1.000, p95 2.62, max 8.23 |
| Catch (Robbery Meter) | accuracy 0.955, **AUC 0.954** |
| Home run \| contact | accuracy 0.951, **AUC 0.942** |
| Extra-base hit \| contact | accuracy 0.877, AUC 0.855 |
| Ball in play \| location | accuracy 0.873, Brier 0.099 |

Run expectancy is monotonic in outs for all 8 base states
(0.585 bases-empty/0-out → 2.087 loaded/0-out).

**Sanity check that matters:** the engine's highest-scoring moments of the
season are walk-off home runs in extra innings and game-ending outs at leverage
4.8–8.2 — the same plays a human editor would pick.

---

## What is deliberately *not* modeled

Honesty about scope was treated as a feature:

- **Called strike probability** — the data contains no umpire calls, so there is
  nothing to supervise. A calibrated geometric `in_zone` flag and a genuinely
  supervised P(ball in play | location) are provided instead.
- **Stolen base / pickoff probability** — no steal or pickoff outcome labels
  exist. Those cards use *measured* lead distance from tracking.
- **Spin rate** — not recoverable from positional tracking. Pitch *movement*
  (deviation from a straight-line path) is used instead.

---

## Example output

The engine independently selected this as the season's showcase game:

> **VAS beat IOL 6–4.** VAS-5976 homers, a 3-run shot that carried 382 feet at
> 121 mph off the bat. That increased their win probability by 83%.

Bottom of the 11th, runners on first and second, two outs — leverage 4.5.
Cards that fired automatically: `TURNING POINT`, `STATCAST SMASH`,
`CLUTCH CONTACT`.
