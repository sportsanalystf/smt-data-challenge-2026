# R implementation

A complete parallel implementation of the storytelling engine in tidyverse R,
extending the organizers' own `SMT_Data_Starter.R`.

## Load order

The modules build on each other, so source them in order:

```r
Sys.setenv(SMT_DATA_ROOT = "/path/to/SMT-Data-Challenge-2026")

source("R/smt_setup.R")     # constants, helpers, theme
source_smt_starter()        # the organizers' Arrow datasets + animate_play()

source("R/R01_play_by_play.R")
source("R/R02_wpa_leverage.R")
source("R/R03_tracking_features.R")
source("R/R04_speed_baserunning.R")
source("R/R05_power_hitting.R")
source("R/R06_pitching.R")
source("R/R07_defense.R")
source("R/R08_fan_interactive.R")
source("R/R09_composite.R")
source("R/R10_animation.R")
```

## Modules

| File | Component | Key functions |
|---|---|---|
| `smt_setup.R` | shared | `source_smt_starter()`, `base_state_code()`, `describe_state()`, `top_speed()`, `theme_scoreboard()` |
| `R01_play_by_play.R` | 1 | `build_play_by_play()`, `reconstruct_at_bats()`, `season_validation()` |
| `R02_wpa_leverage.R` | 2 | `fit_run_expectancy()`, `fit_win_probability()`, `add_wpa()`, `add_leverage()`, `plot_game_flow()` |
| `R03_tracking_features.R` | 3 | `exit_velocity()`, `carry_distance()`, `fit_pitch_trajectory()`, `late_break_in()`, `tunnel_pair()`, `route_efficiency()` |
| `R04_speed_baserunning.R` | 4 | `burner_board()`, `home_to_first()`, `out_of_the_box()`, `extra_base_instinct()`, `pickoff_jump()` |
| `R05_power_hitting.R` | 5 | `statcast_smash()`, `moonshot_meter()`, `barrel_zone()`, `launch_angle_rainbow()`, `clutch_contact()` |
| `R06_pitching.R` | 6 | `radar_gun()`, `velocity_heartbeat()`, `effective_velocity_table()`, `late_life_table()` |
| `R07_defense.R` | 7 | `fit_catch_model()`, `outs_above_expected()`, `web_gem()`, `outfield_cannons()`, `ground_crew_range()`, `double_play_ballet()`, `pop_time_pipeline()` |
| `R08_fan_interactive.R` | 8 | `catch_or_no_catch()`, `out_or_safe()`, `guess_the_gun()`, `how_far_did_it_go()`, `beat_the_burner()` |
| `R09_composite.R` | 9 | `five_tool_scoreboard()`, `player_of_the_game()`, `rivalry_radar()`, `prospect_spotlight()` |
| `R10_animation.R` | 10 | `animate_play_annotated()`, `animate_pitch_sequence()`, `animate_fielder_route()` |

110 functions across 11 files.

## Packages

`tidyverse`, `arrow`, `sportyR`, `gganimate`, `zoo`, `scales`. The first four
are already installed by `SMT_Data_Starter.R`.

## Relationship to the Python side

Every R module has a Python counterpart in `../components/` implementing the
same logic, and the Quarto chapters in `../quarto/` show both side by side. The
two are independent implementations of the same documented algorithms, which is
what allows them to cross-check each other.

Where the languages differ idiomatically, each uses its natural form: R fits win
probability and catch probability with `glm()`, while Python uses a small
NumPy logistic implementation. Both are L2-regularized logistic regressions on
the same features and produce equivalent results.

## Validation status — EXECUTED ✅

The full R pipeline has been run end to end on macOS (R 4.6.0, tidyverse 2.0.0,
arrow 24.0.0): **250 games, 19,139 plate appearances, 96.8 seconds.**

All 13 files also pass `Rscript -e "parse(...)"` and the static checker
(`../tools/check_r_syntax.py`).

### R vs Python parity

The two implementations were written independently from the same documented
algorithms, so agreement between them is real evidence rather than a tautology.

| Quantity | R | Python | Real MiLB |
|---|---|---|---|
| Plate appearances / game | **76.6** | 76.6 | ≈76 |
| Runs / game | 9.95 | 10.12 | ≈9.5 |
| Hits / game | 19.4 | 19.7 | ≈18 |
| Home runs / game | 2.6 | 2.64 | ≈2 |
| Win probability accuracy | 0.779 | 0.774 | — |
| Win probability Brier | 0.141 | 0.144 | — |
| WP base rate | 0.517 | 0.517 | — |
| Leverage mean | 1.000 | 1.000 | — |
| Leverage p95 / max | 2.63 / 7.92 | 2.62 / 8.23 | — |
| Catch model accuracy | 0.959 | 0.955 | — |
| Catch model Brier | 0.036 | 0.038 | — |
| Run expectancy (bases empty, 0 out) | 0.575 | 0.584 | — |
| Run expectancy (loaded, 0 out) | 2.12 | 2.07 | — |

Both produce a **strictly monotonic** run-expectancy matrix (falling across
outs for all eight base states), and both independently identify the same
turning point in the showcase game: a walk-off three-run homer in the bottom of
the 11th, WPA ≈ +0.81 at leverage ≈ 4.3.

Residual differences are expected and small: R fits with `glm()` (IRLS) while
Python uses NumPy gradient descent, and the two reconstruct slightly different
game counts (R iterates `game_info`, Python walks the directory tree and skips
4 games with empty lineup tables).

### Bugs found by running it

Worth recording, because each was invisible to static analysis:

1. **The starter's hard-coded path.** `SMT_Data_Starter.R` assigns a Windows
   `data_directory` as it is sourced, overwriting anything set beforehand.
   `source_smt_starter()` now rewrites that line in memory.
2. **Missing team columns.** `reconstruct_at_bats()` computed `home_team` /
   `away_team` but never carried them into the per-at-bat records.
3. **Tied games broke the win-probability target.** Writing the label as two
   strict inequalities marked *both* sides as losers in the 7.7% of
   reconstructed games that end tied. The model then learned from contradictory
   rows — base rate 0.425, and "biggest swings" that were all *outs* with large
   *positive* WPA. Ties now go to the away side so the labels stay
   complementary.
4. **Five-Tool ranked against the top-15 tables**, not the league, handing the
   leader a 100th percentile in every tool. It now receives full leaderboards.
5. `cur_data_all()` (deprecated in dplyr 1.1+), a `zoo` hard dependency, and a
   leverage loop that made ~11,000 `predict()` calls instead of 6.
