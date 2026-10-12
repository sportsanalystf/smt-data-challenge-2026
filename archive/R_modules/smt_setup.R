#' smt_setup.R -- shared configuration and helpers for the R implementation.
#'
#' This file is sourced by every other R module. It sources the challenge's own
#' `SMT_Data_Starter.R` (so `ball_positions`, `ball_events`, `player_positions`,
#' `lineups`, `game_info`, `animate_play()` and `create_play_by_play()` are all
#' available exactly as the organizers provided them) and then adds the
#' constants and small utilities the components share.
#'
#' Usage:
#'   source("R/smt_setup.R")

### Packages ----
library(tidyverse)
library(arrow)

### Data directory ----
#' Point this at the folder containing ball-events/, ball-positions/,
#' player-positions/, lineups.csv and game-info.csv. The environment variable
#' lets the Quarto documents run without editing this file.
smt_data_dir <- function() {
  d <- Sys.getenv("SMT_DATA_ROOT", unset = "")
  if (d != "") return(normalizePath(d, mustWork = FALSE))

  #' Otherwise find the folder that actually contains the data. `submission/`
  #' normally sits inside the challenge folder, but don't assume the depth --
  #' look for `ball-events` and stop at the first hit.
  candidates <- c(getwd(),
                  file.path(getwd(), ".."),
                  file.path(getwd(), "..", ".."))
  for (cand in candidates) {
    if (dir.exists(file.path(cand, "ball-events"))) {
      return(normalizePath(cand, mustWork = FALSE))
    }
  }
  normalizePath(file.path(getwd(), ".."), mustWork = FALSE)
}

#' Source the organizers' starter file, which opens the Arrow datasets and
#' defines animate_play() and create_play_by_play().
#'
#' IMPORTANT: the starter contains a hard-coded Windows path,
#'
#'     data_directory <- "C:/Users/b.fryer/Desktop/Organizer-SMT-Data-Challenge-2026"
#'
#' and it assigns that value as it is sourced. Setting `data_directory`
#' beforehand does NOT work -- sourcing simply overwrites it, and Arrow then
#' fails with "Cannot list directory 'C:/Users/b.fryer/...'".
#'
#' So we read the starter as text, rewrite that one assignment to point at this
#' machine's data folder, and evaluate the result. The organizers' file is left
#' untouched on disk.
source_smt_starter <- function(starter_path = NULL, data_dir = NULL) {
  if (is.null(starter_path)) {
    candidates <- c(
      file.path(smt_data_dir(), "SMT_Data_Starter.R"),
      file.path("..", "SMT_Data_Starter.R"),
      "SMT_Data_Starter.R"
    )
    hit <- candidates[file.exists(candidates)]
    starter_path <- if (length(hit) > 0) hit[1] else NA_character_
  }
  if (is.na(starter_path) || !file.exists(starter_path)) {
    stop("Could not find SMT_Data_Starter.R -- pass starter_path explicitly.")
  }

  root <- if (is.null(data_dir)) smt_data_dir() else normalizePath(data_dir,
                                                                   mustWork = FALSE)
  if (!dir.exists(file.path(root, "ball-events"))) {
    stop("No 'ball-events' folder under: ", root,
         "\n  Set the data root explicitly, e.g.\n",
         '  Sys.setenv(SMT_DATA_ROOT = "/path/to/SMT-Data-Challenge-2026")')
  }
  #' Arrow wants forward slashes on every platform.
  root <- gsub("\\\\", "/", root)

  lines <- readLines(starter_path, warn = FALSE)
  idx <- grep("^\\s*data_directory\\s*<-", lines)
  replacement <- sprintf('data_directory <- "%s"', root)
  if (length(idx) > 0) {
    lines[idx] <- replacement
  } else {
    lines <- c(replacement, lines)
  }

  eval(parse(text = paste(lines, collapse = "\n")), envir = globalenv())
  message("SMT starter loaded against: ", root)
  invisible(root)
}

### Constants ----

FT_S_TO_MPH <- 0.681818          # 1 ft/s in mph
FRAME_HZ    <- 20                # tracking sample rate
OUTS_PER_HALF <- 3L
RUBBER_TO_PLATE_FT <- 60.5
COMMIT_POINT_FT <- 23.8          # where a hitter must decide (~175 ms out)
GRAVITY_FT_S2 <- 32.174
AVG_SPEED_FACTOR <- 0.93         # a pitch loses ~8% of its speed en route
MAX_PLAUSIBLE_PITCH_MPH <- 103   # above this is a tracking spike at this level

#' Base bag centres in the SMT coordinate system (90 ft basepaths).
BASE_XY <- list(
  home   = c(0, 0),
  first  = c(63.64, 63.64),
  second = c(0, 127.28),
  third  = c(-63.64, 63.64),
  mound  = c(0, 60.5)
)

#' player_id lookup (matches the Data Description glossary).
PLAYER_IDS <- c(
  pitcher = 1, catcher = 2, first_baseman = 3, second_baseman = 4,
  third_baseman = 5, shortstop = 6, left_fielder = 7, center_fielder = 8,
  right_fielder = 9, batter = 10, runner_1b = 11, runner_2b = 12, runner_3b = 13
)

POS_ABBR <- c("1" = "P", "2" = "C", "3" = "1B", "4" = "2B", "5" = "3B",
              "6" = "SS", "7" = "LF", "8" = "CF", "9" = "RF", "10" = "BAT")

#' The lineup column that corresponds to each fielding player_id.
POS_COLUMN <- c("1" = "pitcher", "2" = "catcher", "3" = "first_baseman",
                "4" = "second_baseman", "5" = "third_baseman",
                "6" = "shortstop", "7" = "left_fielder",
                "8" = "center_fielder", "9" = "right_fielder",
                "10" = "batter")

OUTFIELD_IDS <- c(7, 8, 9)
INFIELD_IDS  <- c(3, 4, 5, 6)

#' ball_eventcode lookup.
EVENT <- c(PITCH = 1, ACQUIRED = 2, THROW = 3, HIT_INTO_PLAY = 4,
           END_OF_PLAY = 5, PICKOFF = 6, ACQUIRED_UNK = 7, THROW_UNK = 8,
           DEFLECTION = 9, DEFLECTION_WALL = 10, HOME_RUN = 11, BOUNCE = 16)

#' Codes that mean the ball stayed live after contact. A foul ball shares
#' code 4 with a live batted ball, so this set is how we tell them apart.
LIVE_BALL_CODES <- c(EVENT[["ACQUIRED"]], EVENT[["THROW"]],
                     EVENT[["ACQUIRED_UNK"]], EVENT[["THROW_UNK"]],
                     EVENT[["DEFLECTION"]], EVENT[["DEFLECTION_WALL"]],
                     EVENT[["BOUNCE"]])

#' The eight base states, indexed by (1B, 2B, 3B) occupancy bits + 1.
BASE_STATES <- c("___", "1__", "_2_", "12_", "__3", "1_3", "_23", "123")

### Small helpers ----

#' Encode base occupancy as an integer 0-7.
base_state_code <- function(on1, on2, on3) {
  as.integer(!is.na(on1)) + 2L * as.integer(!is.na(on2)) +
    4L * as.integer(!is.na(on3))
}

#' Human-readable base/out state, e.g. "runners on the corners, one out".
describe_state <- function(base_state, outs) {
  on1 <- bitwAnd(base_state, 1L) > 0
  on2 <- bitwAnd(base_state, 2L) > 0
  on3 <- bitwAnd(base_state, 4L) > 0
  bases <- dplyr::case_when(
    !on1 & !on2 & !on3 ~ "bases empty",
    on1 & on2 & on3    ~ "bases loaded",
    on1 & on3          ~ "runners on the corners",
    on1 & on2          ~ "runners on first and second",
    on2 & on3          ~ "runners on second and third",
    on1                ~ "a runner on first",
    on2                ~ "a runner on second",
    TRUE               ~ "a runner on third"
  )
  out_txt <- dplyr::case_when(outs == 0 ~ "nobody out",
                              outs == 1 ~ "one out",
                              TRUE      ~ "two outs")
  paste0(bases, ", ", out_txt)
}

#' 'y1_d061_VKA_PHD' -> team codes and day, useful for joins and titles.
parse_game_string <- function(game_string) {
  parts <- stringr::str_split(game_string, "_", simplify = TRUE)
  list(year = parts[1], day = parts[2], away = parts[3], home = parts[4])
}

#' Euclidean distance between two (x, y) points.
dist_2d <- function(x1, y1, x2, y2) sqrt((x1 - x2)^2 + (y1 - y2)^2)

#' Robust peak of a numeric vector: a high percentile resists single-frame
#' tracking spikes far better than max().
top_speed <- function(x, probs = 0.90) {
  x <- x[is.finite(x)]
  if (length(x) == 0) return(NA_real_)
  unname(stats::quantile(x, probs = probs, na.rm = TRUE))
}

#' Speed (ft/s) between consecutive tracking frames.
frame_speed <- function(x, y, timestamp) {
  dt <- diff(timestamp) / 1000
  d  <- sqrt(diff(x)^2 + diff(y)^2)
  ifelse(dt > 0, d / dt, NA_real_)
}

#' Trailing rolling mean, in base R.
#'
#' Used by the Velocity Heartbeat. Written by hand so the project does not
#' hard-depend on `zoo` for one small thing -- if `zoo` is installed it is used,
#' otherwise this fallback runs.
rolling_mean <- function(x, width = 10, min_obs = 3) {
  n <- length(x)
  out <- rep(NA_real_, n)
  for (i in seq_len(n)) {
    lo <- max(1L, i - width + 1L)
    w <- x[lo:i]
    w <- w[is.finite(w)]
    if (length(w) >= min_obs) out[i] <- mean(w)
  }
  out
}

#' Convert a season distribution + value into a league percentile (0-100).
percentile_of <- function(value, reference, lower_is_better = FALSE) {
  reference <- reference[is.finite(reference)]
  if (!is.finite(value) || length(reference) == 0) return(NA_real_)
  p <- 100 * mean(reference <= value)
  if (lower_is_better) p <- 100 - p
  round(p, 1)
}

#' Scouting-style grade from a percentile.
grade_for <- function(pct) {
  dplyr::case_when(
    is.na(pct)  ~ NA_character_,
    pct >= 97   ~ "ELITE",
    pct >= 85   ~ "PLUS-PLUS",
    pct >= 70   ~ "PLUS",
    pct >= 45   ~ "AVERAGE",
    pct >= 25   ~ "BELOW AVG",
    TRUE        ~ "WELL BELOW"
  )
}

#' Attach the player code for a lineup position onto a play-keyed table.
attach_player <- function(df, lineups_tbl, position_column, play_col = "play") {
  key <- lineups_tbl %>%
    dplyr::distinct(game_string, play_per_game, .keep_all = TRUE) %>%
    dplyr::select(game_string, play_per_game,
                  player = dplyr::all_of(position_column))
  df %>%
    dplyr::left_join(key,
                     by = stats::setNames(c("game_string", "play_per_game"),
                                          c("game_string", play_col))) %>%
    dplyr::mutate(team = stringr::str_split_i(player, "-", 1))
}

### Theme ----
#' High-contrast palette chosen for legibility on a stadium scoreboard.
SMT_THEME <- list(
  ink = "#12181f", panel = "#161f2b", panel_light = "#22303f",
  text = "#ffffff", muted = "#9fb0c0", grass = "#0b6b3a",
  gold = "#ffc72c", accent = "#c8102e", home = "#2f80ed", away = "#f2994a"
)

theme_scoreboard <- function(base_size = 13) {
  ggplot2::theme_minimal(base_size = base_size) +
    ggplot2::theme(
      plot.background  = ggplot2::element_rect(fill = SMT_THEME$ink, colour = NA),
      panel.background = ggplot2::element_rect(fill = SMT_THEME$panel, colour = NA),
      panel.grid.major = ggplot2::element_line(colour = SMT_THEME$panel_light),
      panel.grid.minor = ggplot2::element_blank(),
      text             = ggplot2::element_text(colour = SMT_THEME$text),
      axis.text        = ggplot2::element_text(colour = SMT_THEME$muted),
      plot.title       = ggplot2::element_text(face = "bold", size = base_size + 5),
      plot.subtitle    = ggplot2::element_text(colour = SMT_THEME$muted),
      legend.position  = "bottom"
    )
}
