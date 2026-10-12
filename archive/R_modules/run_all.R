#' run_all.R -- the R pipeline, end to end.
#'
#' Runs every R component in dependency order and writes results to
#' `outputs/R/`. This is the R equivalent of `pipeline/run_all.py`.
#'
#' Usage, from the `submission/` folder:
#'   Rscript R/run_all.R
#'   Rscript R/run_all.R y1_d122_IOL_VAS      # a specific showcase game
#'   Rscript R/run_all.R y1_d122_IOL_VAS 30   # ...and reconstruct 30 games
#'
#' Inside RStudio:
#'   setwd("~/Desktop/SMT-Data-Challenge-2026/submission")
#'   source("R/run_all.R")

args <- commandArgs(trailingOnly = TRUE)
SHOWCASE  <- if (length(args) >= 1) args[1] else "y1_d122_IOL_VAS"
#' Default to the WHOLE season. A small sample produces a run-expectancy matrix
#' that is not monotonic in outs (thin cells) and an unstable win-probability
#' model, so 25 games is only useful for a quick smoke test.
N_GAMES   <- if (length(args) >= 2) as.integer(args[2]) else 250L

step <- function(n, label) {
  cat("\n", strrep("=", 70), "\n", sep = "")
  cat(sprintf("STAGE %s: %s\n", n, label))
  cat(strrep("=", 70), "\n", sep = "")
}

t_start <- Sys.time()

### Setup -------------------------------------------------------------------
step(0, "Setup")
source("R/smt_setup.R")
source_smt_starter()
cat("starter loaded; data root:", smt_data_dir(), "\n")

for (f in c("R01_play_by_play.R", "R02_wpa_leverage.R", "R03_tracking_features.R",
            "R04_speed_baserunning.R", "R05_power_hitting.R", "R06_pitching.R",
            "R07_defense.R", "R08_fan_interactive.R", "R09_composite.R")) {
  source(file.path("R", f))
}
cat("all component modules sourced\n")

out_dir <- file.path("outputs", "R")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
save_tbl <- function(x, name) {
  if (is.null(x) || nrow(x) == 0) {
    cat("  (empty)", name, "\n"); return(invisible(NULL))
  }
  readr::write_csv(x, file.path(out_dir, paste0(name, ".csv")))
  cat("  wrote", name, sprintf("(%d rows)", nrow(x)), "\n")
}

### Component 1 -------------------------------------------------------------
step(1, "Play-by-play (game state reconstruction)")
pbp_game <- build_play_by_play(SHOWCASE)
cat("showcase game:", SHOWCASE, "--", nrow(pbp_game), "plate appearances\n\n")
print(pbp_table(pbp_game, n = 8))
save_tbl(pbp_game, "01_play_by_play_showcase")

#' A season sample: the win-probability model needs many games to fit.
all_games <- game_info %>% dplyr::pull(game_string) %>% unique()
#' The showcase game MUST be in the sample -- Player of the Game and the game
#' headline filter the season table for it, and silently return nothing if it
#' was never reconstructed.
sample_games <- unique(c(SHOWCASE, utils::head(all_games, N_GAMES)))
cat("\nreconstructing", length(sample_games), "games for model fitting...\n")
pbp <- build_play_by_play_season(sample_games)
cat("season sample:", nrow(pbp), "plate appearances from",
    dplyr::n_distinct(pbp$game_string), "games\n\n")
print(season_validation(pbp))
save_tbl(pbp, "01_play_by_play_season")

### Component 2 -------------------------------------------------------------
step(2, "Run Expectancy, Win Probability, Leverage, WPA")
re_tbl <- fit_run_expectancy(pbp)
cat("\nRUN EXPECTANCY MATRIX\n")
print(run_expectancy_table(re_tbl))
save_tbl(run_expectancy_table(re_tbl), "02_run_expectancy")

wp_model <- fit_win_probability(pbp, re_tbl)
cat("\nWIN PROBABILITY MODEL\n")
print(wp_metrics(wp_model, pbp, re_tbl))

pbp <- add_wpa(pbp, wp_model, re_tbl)
pbp <- add_re24(pbp, re_tbl)
cat("\nattaching leverage (this is the slow step)...\n")
pbp <- add_leverage(pbp, wp_model, re_tbl)

cat("\nLEVERAGE PROFILE\n")
print(leverage_profile(pbp))
cat("\nBIGGEST SWINGS\n")
print(biggest_swings(pbp, n = 8))
save_tbl(biggest_swings(pbp, n = 50), "02_biggest_swings")
save_tbl(pbp, "02_play_by_play_enriched")

### Component 3 -------------------------------------------------------------
step(3, "Tracking features and league baselines")
feat_dir <- file.path("outputs", "feat")
eng_dir  <- file.path("outputs", "engine")

read_if <- function(path) {
  if (file.exists(path)) readr::read_csv(path, show_col_types = FALSE) else NULL
}
sprints <- read_if(file.path(feat_dir, "sprints.csv"))
hits    <- read_if(file.path(feat_dir, "hits_v2.csv"))
catches <- read_if(file.path(feat_dir, "catches.csv"))
throws  <- read_if(file.path(feat_dir, "throws.csv"))
pitches <- read_if(file.path(eng_dir,  "pitch_locations.csv"))

have_features <- !any(sapply(list(sprints, hits, catches, throws, pitches),
                             is.null))
if (!have_features) {
  cat("\nNOTE: season feature tables are missing, so components 4-9 are\n")
  cat("      skipped. Build them once with the Python extractors:\n")
  cat("         python3 pipeline/build_state.py 0 250\n")
  cat("         python3 pipeline/build_pitch_locations.py 0 250\n")
} else {
  baselines <- build_baselines(hits, sprints, throws, catches, pitches)
  cat("\nLEAGUE BASELINES\n")
  print(baseline_table(baselines))
  save_tbl(baseline_table(baselines), "03_league_baselines")

  ### Component 4 -----------------------------------------------------------
  step(4, "Speed & Baserunning")
  board <- burner_board(sprints, lineups, min_runs = 3, top = 15)
  cat("\nBURNER BOARD\n"); print(utils::head(board, 5))
  save_tbl(board, "04_burner_board")
  save_tbl(extra_base_instinct(pbp, sprints, top = 15), "04_extra_base_instinct")

  ### Component 5 -----------------------------------------------------------
  step(5, "Power & Hitting")
  smash <- statcast_smash(hits, lineups, min_balls = 5, top = 15)
  cat("\nSTATCAST SMASH\n"); print(utils::head(smash, 5))
  save_tbl(smash, "05_statcast_smash")
  save_tbl(moonshot_meter(hits, lineups, top = 15), "05_moonshot_meter")
  save_tbl(barrel_zone(hits, lineups, top = 15), "05_barrel_zone")
  save_tbl(hardest_hit_balls(hits, lineups, top = 20), "05_hardest_hit")

  ### Component 6 -----------------------------------------------------------
  step(6, "Pitching")
  radar <- radar_gun(pitches, lineups, min_pitches = 30, top = 15)
  cat("\nRADAR GUN LIVE\n"); print(utils::head(radar, 5))
  save_tbl(radar, "06_radar_gun")

  hb <- velocity_heartbeat(pitches, SHOWCASE)
  if (length(hb$summary) > 0) {
    cat("\nVELOCITY HEARTBEAT\n"); print(unlist(hb$summary))
    save_tbl(hb$data, "06_velocity_heartbeat")
  }

  ### Component 7 -----------------------------------------------------------
  step(7, "Defense & Fielding")
  fit <- fit_catch_model(catches)
  cat("\nROBBERY METER\n"); print(catch_model_metrics(fit))
  scored <- score_catches(fit)
  save_tbl(outs_above_expected(scored, lineups, top = 20), "07_outs_above_expected")
  save_tbl(web_gem(scored, lineups, top = 20), "07_web_gems")
  save_tbl(outfield_cannons(throws, lineups, top = 20), "07_outfield_cannons")
  save_tbl(ground_crew_range(catches, lineups, top = 20), "07_ground_crew_range")
  cat("\nOUTS ABOVE EXPECTED\n")
  print(utils::head(outs_above_expected(scored, lineups, top = 5), 5))

  ### Component 8 -----------------------------------------------------------
  step(8, "Fan-interactive games")
  catch_df  <- catch_or_no_catch(scored, top = 20)
  gun_df    <- guess_the_gun(pitches, top = 20)
  far_df    <- how_far_did_it_go(hits, top = 20)
  burner_df <- beat_the_burner(sprints, baselines, top = 20)
  save_tbl(catch_df, "08_catch_or_no_catch")
  save_tbl(gun_df, "08_guess_the_gun")
  save_tbl(far_df, "08_how_far")
  save_tbl(burner_df, "08_beat_the_burner")
  cat("\nTONIGHT'S SLATE\n")
  print(game_night_slate(catch_df, gun_df, far_df, burner_df))

  ### Component 9 -----------------------------------------------------------
  step(9, "Composite & Storytelling")
  #' Five-Tool ranks each tool as a LEAGUE percentile, so it must be fed the
  #' full leaderboards. Passing the top-15 tables would rank players against
  #' fourteen rivals and hand the leader a 100th percentile in every tool.
  board_full   <- burner_board(sprints, lineups, min_runs = 3, top = Inf)
  smash_full   <- statcast_smash(hits, lineups, min_balls = 5, top = Inf)
  cannons_full <- outfield_cannons(throws, lineups, min_throws = 3, top = Inf)
  five <- five_tool_scoreboard(board_full, smash_full, cannons_full, top = 25)
  cat("\nFIVE-TOOL SCOREBOARD\n"); print(utils::head(five, 5))
  save_tbl(five, "09_five_tool")
  save_tbl(player_of_the_game(pbp, SHOWCASE, top = 10), "09_player_of_the_game")
  cat("\nGAME HEADLINE\n"); print(unlist(game_headline(pbp, SHOWCASE)))
}

### Done --------------------------------------------------------------------
elapsed <- round(as.numeric(difftime(Sys.time(), t_start, units = "secs")), 1)
cat("\n", strrep("=", 70), "\n", sep = "")
cat("R PIPELINE COMPLETE in", elapsed, "seconds\n")
cat("results written to", normalizePath(out_dir, mustWork = FALSE), "\n")
cat("\nFor animations (needs sportyR + gganimate):\n")
cat('   source("R/R10_animation.R")\n')
cat(sprintf('   anim <- animate_play_annotated("%s", 246,\n', SHOWCASE))
cat('              dplyr::filter(pbp_game, last_play == 246))\n')
cat('   save_animation(anim, "outputs/R/play.gif")\n')
