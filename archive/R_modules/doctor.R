#' doctor.R -- preflight check for the R implementation. Run this first.
#'
#' Tells you whether this machine can run the R side: packages, data location,
#' the organizers' starter file, and the season feature tables the leaderboard
#' modules consume.
#'
#' Usage, from the `submission/` folder:
#'   Rscript R/doctor.R
#' or inside RStudio:
#'   source("R/doctor.R")

cat(strrep("=", 74), "\n")
cat("SMT STORYTELLING ENGINE -- R PREFLIGHT\n")
cat(strrep("=", 74), "\n")

problems <- character(0)
warnings_ <- character(0)

status_line <- function(ok, label, detail = "") {
  tag <- if (isTRUE(ok)) "  OK  " else if (identical(ok, "warn")) " WARN " else " MISS "
  cat(sprintf("[%s] %-34s %s\n", tag, label, detail))
}

### R version ----
cat("\nR\n")
ver_ok <- getRversion() >= "4.1.0"
status_line(ver_ok, "R version", as.character(getRversion()))
if (!ver_ok) {
  problems <- c(problems, "R 4.1+ recommended (needs the native |> pipe era)")
}

### Packages ----
cat("\nPACKAGES\n")
required <- c("tidyverse", "arrow", "dplyr", "tidyr", "purrr", "tibble",
              "stringr", "ggplot2", "readr")
optional <- c(sportyR = "field diagrams for animation",
              gganimate = "play animation",
              zoo = "rolling average in Velocity Heartbeat",
              scales = "percent axis labels",
              forcats = "ordered bars on the Burner Board",
              hexbin = "hex heat map in Barrel Zone",
              plyr = "used by the starter's own animate_play()")

for (p in required) {
  ok <- requireNamespace(p, quietly = TRUE)
  status_line(ok, p, if (ok) as.character(utils::packageVersion(p)) else "REQUIRED")
  if (!ok) problems <- c(problems, sprintf('install.packages("%s")', p))
}
for (p in names(optional)) {
  ok <- requireNamespace(p, quietly = TRUE)
  status_line(if (ok) TRUE else "warn", p,
              if (ok) as.character(utils::packageVersion(p)) else
                paste("optional --", optional[[p]]))
  if (!ok) warnings_ <- c(warnings_, sprintf('install.packages("%s")', p))
}

### Data ----
cat("\nDATA\n")
data_root <- Sys.getenv("SMT_DATA_ROOT", unset = "")
if (data_root == "") {
  #' The submission folder normally sits inside the challenge folder, so the
  #' parent directory is the data root.
  guess <- normalizePath(file.path(getwd(), ".."), mustWork = FALSE)
  if (dir.exists(file.path(guess, "ball-events"))) {
    data_root <- guess
    status_line("warn", "SMT_DATA_ROOT", "not set (auto-detected from layout)")
  } else {
    status_line(FALSE, "SMT_DATA_ROOT", "not set and could not auto-detect")
    problems <- c(problems,
                  'Sys.setenv(SMT_DATA_ROOT = "/path/to/SMT-Data-Challenge-2026")')
  }
} else {
  status_line(TRUE, "SMT_DATA_ROOT", data_root)
}

if (data_root != "") {
  status_line(TRUE, "data root", data_root)
  for (item in c("ball-events", "ball-positions", "player-positions")) {
    ok <- dir.exists(file.path(data_root, item))
    status_line(ok, item, if (ok) "found" else "NOT FOUND")
    if (!ok) problems <- c(problems, paste("missing", item))
  }
  for (item in c("lineups.csv", "game-info.csv", "SMT_Data_Starter.R")) {
    ok <- file.exists(file.path(data_root, item))
    status_line(ok, item, if (ok) "found" else "NOT FOUND")
    if (!ok) problems <- c(problems, paste("missing", item))
  }
}

### Feature tables ----
cat("\nSEASON FEATURE TABLES (needed by components 4-9)\n")
feat <- file.path(getwd(), "outputs", "feat")
eng  <- file.path(getwd(), "outputs", "engine")
tables <- list(
  "sprints.csv"        = file.path(feat, "sprints.csv"),
  "hits_v2.csv"        = file.path(feat, "hits_v2.csv"),
  "catches.csv"        = file.path(feat, "catches.csv"),
  "throws.csv"         = file.path(feat, "throws.csv"),
  "pitch_locations.csv" = file.path(eng, "pitch_locations.csv")
)
missing_tables <- character(0)
for (nm in names(tables)) {
  ok <- file.exists(tables[[nm]])
  size <- if (ok) sprintf("%.1f MB", file.size(tables[[nm]]) / 1e6) else "not built"
  status_line(if (ok) TRUE else "warn", nm, size)
  if (!ok) missing_tables <- c(missing_tables, nm)
}

### Verdict ----
cat("\n", strrep("=", 74), "\n", sep = "")
if (length(problems) > 0) {
  cat("NOT READY -- fix these first:\n")
  for (p in unique(problems)) cat("   *", p, "\n")
} else {
  cat("READY\n")
  if (length(warnings_) > 0) {
    cat("\nOptional packages you may want:\n")
    for (w in unique(warnings_)) cat("   ", w, "\n")
  }
  if (length(missing_tables) > 0) {
    cat("\nNOTE: these season feature tables are not built yet:\n")
    for (m in missing_tables) cat("   *", m, "\n")
    cat("\nThey are produced by the Python extractors (a one-time step):\n")
    cat("   python3 pipeline/build_state.py 0 250\n")
    cat("   python3 pipeline/build_pitch_locations.py 0 250\n")
    cat("\nComponents 1-3 (play-by-play, WPA/leverage, tracking features) run\n")
    cat("in pure R without them.\n")
  } else {
    cat("\nAll inputs present. Run the R pipeline:\n")
    cat("   Rscript R/run_all.R\n")
  }
}
