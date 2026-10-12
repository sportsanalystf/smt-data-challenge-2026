#' R08_fan_interactive.R -- COMPONENT 8: Fan-interactive games.
#'
#' Mirrors components/c08_fan_interactive.py.
#'
#' Scoreboard products in this file
#'   Catch or No Catch?   freeze at contact, crowd votes, model reveals the odds
#'   Out or Safe?         a bang-bang play at first, put to the crowd
#'   Guess the Gun        fans guess the pitch speed
#'   How Far Did It Go?   fans estimate carry distance
#'   Beat the Burner      a fan's reaction time raced against a real sprint
#'
#' DESIGN RULE: a question is only worth asking when the answer is genuinely
#' uncertain. A prompt the crowd gets right 95% of the time is a formality, not
#' a game -- so every selector below ranks candidates by SUSPENSE, not by size.

#' Build multiple-choice ranges around a true value.
bucket_options <- function(value, step, n = 3) {
  base <- floor(value / step) * step - step
  opts <- vapply(seq_len(n) - 1,
                 function(i) sprintf("%g-%g", base + i * step,
                                     base + (i + 1) * step - 1),
                 character(1))
  idx <- min(max(floor((value - base) / step) + 1, 1), n)
  list(options = opts, answer = opts[idx])
}

### Catch or No Catch? ----

#' Fly balls where the model is closest to a coin flip.
catch_or_no_catch <- function(scored, top = 10) {
  scored %>%
    dplyr::mutate(suspense = 1 - abs(2 * (catch_prob - 0.5))) %>%
    dplyr::filter(catch_prob >= 0.25, catch_prob <= 0.75) %>%
    dplyr::arrange(dplyr::desc(suspense)) %>%
    dplyr::transmute(game_string, play,
                     route_ft = round(route_ft, 1),
                     hang_s = round(hang_s, 2),
                     catch_prob = round(catch_prob, 3),
                     catch_made,
                     suspense = round(suspense, 3),
                     prompt = "Does he come up with it?",
                     answer = ifelse(catch_made == 1, "CAUGHT", "DROPS")) %>%
    utils::head(top)
}

### Out or Safe? ----

#' Bang-bang plays at first: the throw and the runner arrive together.
#'
#' `close_plays` comes from the play anatomy step and carries the margin between
#' the ball's arrival and the runner's.
out_or_safe <- function(close_plays, max_margin_s = 0.15, top = 10) {
  close_plays %>%
    dplyr::filter(is.finite(margin_s), abs(margin_s) <= max_margin_s) %>%
    dplyr::arrange(abs(margin_s)) %>%
    dplyr::mutate(prompt = "Too close to call -- what did you see?",
                  margin_s = round(margin_s, 3)) %>%
    utils::head(top)
}

### Guess the Gun ----

#' Fans guess the radar reading. Fast pitches make the best prompts.
guess_the_gun <- function(pitches, min_velo = 90, top = 10, step = 3) {
  d <- pitches %>%
    dplyr::filter(is.finite(pitch_velo_mph), pitch_velo_mph >= min_velo,
                  pitch_velo_mph <= MAX_PLAUSIBLE_PITCH_MPH) %>%
    dplyr::arrange(dplyr::desc(pitch_velo_mph)) %>%
    utils::head(top)
  if (nrow(d) == 0) return(d)
  buckets <- lapply(d$pitch_velo_mph, bucket_options, step = step)
  d %>%
    dplyr::mutate(
      prompt = "How hard was that one?",
      options = vapply(buckets, function(b) paste(b$options, collapse = " | "),
                       character(1)),
      answer = vapply(buckets, function(b) b$answer, character(1)))
}

### How Far Did It Go? ----

#' Fans estimate carry on a long fly ball.
how_far_did_it_go <- function(hits, min_distance = 330, top = 10, step = 25) {
  d <- hits %>%
    dplyr::filter(is.finite(carry_ft), carry_ft >= min_distance) %>%
    dplyr::arrange(dplyr::desc(carry_ft)) %>%
    utils::head(top)
  if (nrow(d) == 0) return(d)
  buckets <- lapply(d$carry_ft, bucket_options, step = step)
  d %>%
    dplyr::mutate(
      prompt = "How far did that ball travel?",
      options = vapply(buckets, function(b)
        paste(paste0(b$options, " ft"), collapse = " | "), character(1)),
      answer = vapply(buckets, function(b) paste0(b$answer, " ft"), character(1)))
}

### Beat the Burner ----

#' Race a fan's phone tap against a real sprint.
#'
#' The target time is how long the runner would need to cover 90 feet at his
#' peak speed -- the number the crowd is actually chasing.
beat_the_burner <- function(sprints, baselines = NULL, top = 10) {
  d <- sprints %>%
    dplyr::filter(is.finite(sprint_mph)) %>%
    dplyr::arrange(dplyr::desc(sprint_mph)) %>%
    utils::head(top) %>%
    dplyr::mutate(
      target_time_s = round(90 / (sprint_mph / FT_S_TO_MPH), 2),
      prompt = "Tap when the pitch is released -- can you beat him to the bag?")
  if (!is.null(baselines) && !is.null(baselines$sprint_mph)) {
    d <- d %>%
      dplyr::mutate(league_percentile = vapply(
        sprint_mph, percentile_of, numeric(1),
        reference = baselines$sprint_mph))
  }
  d
}

### Slate ----

#' One night's interactive slate, ready for the control room.
game_night_slate <- function(catch_df, gun_df, far_df, burner_df,
                             safe_df = NULL) {
  rows <- tibble::tibble(
    game = c("Catch or No Catch?", "Guess the Gun", "How Far Did It Go?",
             "Beat the Burner"),
    prompts_available = c(nrow(catch_df), nrow(gun_df), nrow(far_df),
                          nrow(burner_df)))
  if (!is.null(safe_df)) {
    rows <- dplyr::bind_rows(
      rows, tibble::tibble(game = "Out or Safe?",
                           prompts_available = nrow(safe_df)))
  }
  rows
}
