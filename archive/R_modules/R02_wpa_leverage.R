#' R02_wpa_leverage.R -- COMPONENT 2: Run Expectancy, Win Probability,
#' Leverage Index and WPA.
#'
#' Mirrors components/c02_wpa_leverage.py.
#'
#' Everything here is a function of the play-by-play table from component 1.
#' Nothing is imported from another league: the run-expectancy matrix and the
#' win-probability model are both estimated from THIS season.
#'
#' Usage:
#'   source("R/smt_setup.R"); source("R/R01_play_by_play.R")
#'   source("R/R02_wpa_leverage.R")
#'   re  <- fit_run_expectancy(pbp)
#'   wp  <- fit_win_probability(pbp, re)
#'   pbp <- add_wpa(pbp, wp, re)
#'   pbp <- add_leverage(pbp, wp, re)

### Run Expectancy ----

#' Empirical 24-state run expectancy: average runs scored from a base/out state
#' to the end of the half-inning.
#'
#' Only half-innings whose out accounting balanced are used, because a
#' half-inning with unresolved outs has an unreliable "runs to end of inning".
fit_run_expectancy <- function(pbp) {
  pbp %>%
    dplyr::filter(half_balanced) %>%
    dplyr::arrange(game_string, inning, half_inning, at_bat) %>%
    dplyr::group_by(game_string, inning, half_inning) %>%
    #' Runs from this at-bat to the end of the inning = reverse cumulative sum.
    dplyr::mutate(runs_rest_of_inning = rev(cumsum(rev(runs)))) %>%
    dplyr::ungroup() %>%
    dplyr::filter(outs_before < OUTS_PER_HALF) %>%
    dplyr::group_by(base_state_before, outs_before) %>%
    dplyr::summarise(run_expectancy = mean(runs_rest_of_inning),
                     n = dplyr::n(), .groups = "drop")
}

#' The familiar 8 x 3 matrix, ready to print.
run_expectancy_table <- function(re_tbl) {
  re_tbl %>%
    dplyr::mutate(bases = BASE_STATES[base_state_before + 1],
                  outs = paste0(outs_before, ifelse(outs_before == 1,
                                                    " out", " outs"))) %>%
    dplyr::select(bases, outs, run_expectancy) %>%
    tidyr::pivot_wider(names_from = outs, values_from = run_expectancy) %>%
    dplyr::mutate(dplyr::across(where(is.numeric), ~ round(.x, 3)))
}

#' Look up RE for a state; a state with three outs is worth zero.
re_lookup <- function(re_tbl, base_state, outs) {
  if (is.na(outs) || outs >= OUTS_PER_HALF) return(0)
  hit <- re_tbl %>%
    dplyr::filter(base_state_before == base_state, outs_before == outs)
  if (nrow(hit) == 0) return(mean(re_tbl$run_expectancy, na.rm = TRUE))
  hit$run_expectancy[1]
}

#' Vectorised RE lookup, used to build model features.
re_vector <- function(re_tbl, base_state, outs) {
  key <- paste(base_state, outs)
  ref <- stats::setNames(re_tbl$run_expectancy,
                         paste(re_tbl$base_state_before, re_tbl$outs_before))
  out <- unname(ref[key])
  out[is.na(out) | outs >= OUTS_PER_HALF] <- 0
  out
}

### Win Probability ----

#' Build the design frame for the win-probability model.
#'
#' Feature choices, and why:
#'   score_diff                   the value of a lead
#'   innings_left                 how much time remains to change it
#'   score_diff x innings_left    a lead is worth more as innings run out
#'   re_state                     the run potential of the current state
#'   is_bottom                    the home team bats last
wp_features <- function(pbp, re_tbl) {
  pbp %>%
    dplyr::mutate(
      innings_left = pmax(0, 9 - inning + ifelse(half_inning == "Top", 0.5, 0)),
      is_bottom = as.integer(half_inning == "Bottom"),
      runners_on = as.integer(bitwAnd(base_state_before, 1L) > 0) +
        as.integer(bitwAnd(base_state_before, 2L) > 0) +
        as.integer(bitwAnd(base_state_before, 4L) > 0),
      in_scoring_position = as.integer(bitwAnd(base_state_before, 6L) > 0),
      re_state = re_vector(re_tbl, base_state_before, outs_before),
      score_diff = score_diff_before,
      score_diff_x_innings_left = score_diff_before * innings_left,
      score_diff_per_inning_left = score_diff_before / (innings_left + 1),
      outs = outs_before
    )
}

#' Fit win probability with glm(). A logistic model is used rather than an
#' empirical lookup because 250 games cannot fill an
#' (inning x base-out x score-margin) grid; a lookup would produce jagged,
#' non-monotonic probabilities that look broken on a scoreboard.
fit_win_probability <- function(pbp, re_tbl) {
  d <- wp_features(pbp, re_tbl)
  stats::glm(
    batting_team_won ~ score_diff + innings_left +
      score_diff_x_innings_left + score_diff_per_inning_left +
      outs + re_state + is_bottom + runners_on + in_scoring_position,
    family = stats::binomial(link = "logit"), data = d
  )
}

#' Predict win probability for the batting team.
predict_wp <- function(model, pbp, re_tbl) {
  d <- wp_features(pbp, re_tbl)
  as.numeric(stats::predict(model, newdata = d, type = "response"))
}

#' Fit quality, reported the same way as the Python implementation.
wp_metrics <- function(model, pbp, re_tbl) {
  p <- predict_wp(model, pbp, re_tbl)
  y <- pbp$batting_team_won
  tibble::tibble(
    metric = c("plate appearances", "accuracy", "Brier score", "log loss",
               "base rate"),
    value = c(length(y),
              round(mean((p >= 0.5) == (y == 1)), 4),
              round(mean((p - y)^2), 4),
              round(-mean(y * log(pmax(p, 1e-9)) +
                            (1 - y) * log(pmax(1 - p, 1e-9))), 4),
              round(mean(y), 4))
  )
}

### WPA ----

#' Attach win probability before/after and WPA to every plate appearance.
#'
#' The subtlety is the half-inning flip: after the third out the other team
#' bats, so "the batting team" changes. When the sides change we take the
#' complement of the next state's win probability.
add_wpa <- function(pbp, model, re_tbl) {
  #' Win probability is predicted for the WHOLE frame in one call, before any
  #' grouping. (An earlier version predicted inside a grouped mutate via
  #' `cur_data_all()`, which is deprecated in dplyr 1.1+ and also meant one
  #' model call per game.)
  out <- pbp %>%
    dplyr::arrange(game_string, inning,
                   as.integer(half_inning == "Bottom"), at_bat)
  out$wp_before <- predict_wp(model, out, re_tbl)

  out %>%
    dplyr::group_by(game_string) %>%
    dplyr::mutate(
      .next_wp = dplyr::lead(wp_before),
      .same_side = dplyr::lead(half_inning) == half_inning &
        dplyr::lead(inning) == inning,
      wp_after = dplyr::case_when(
        is.na(.next_wp) ~ as.numeric(batting_team_won),
        .same_side      ~ .next_wp,
        TRUE            ~ 1 - .next_wp
      ),
      wpa = wp_after - wp_before
    ) %>%
    dplyr::select(-.next_wp, -.same_side) %>%
    dplyr::ungroup()
}

#' Expected Runs Added: the run value of a play.
add_re24 <- function(pbp, re_tbl) {
  pbp %>%
    dplyr::group_by(game_string, inning, half_inning) %>%
    dplyr::mutate(
      re_before = re_vector(re_tbl, base_state_before, outs_before),
      re_after = dplyr::coalesce(
        re_vector(re_tbl, dplyr::lead(base_state_before),
                  dplyr::lead(outs_before)), 0),
      re24 = re_after - re_before + runs
    ) %>%
    dplyr::ungroup()
}

### Leverage Index ----

#' A tiny state-transition model: what does the state become after an outcome?
#' It only has to be good enough to measure how far win probability can swing.
apply_outcome <- function(base_state, outs, kind) {
  on1 <- bitwAnd(base_state, 1L) > 0
  on2 <- bitwAnd(base_state, 2L) > 0
  on3 <- bitwAnd(base_state, 4L) > 0

  if (kind == "out") {
    return(list(base = base_state, outs = outs + 1L, runs = 0L))
  }
  if (kind == "walk_hbp") {
    if (!on1) return(list(base = base_state_code(TRUE, if (on2) TRUE else NA,
                                                 if (on3) TRUE else NA),
                          outs = outs, runs = 0L))
    if (!on2) return(list(base = base_state_code(TRUE, TRUE,
                                                 if (on3) TRUE else NA),
                          outs = outs, runs = 0L))
    if (!on3) return(list(base = 7L, outs = outs, runs = 0L))
    return(list(base = 7L, outs = outs, runs = 1L))
  }
  if (kind == "single") {
    return(list(base = base_state_code(TRUE, if (on1) TRUE else NA, NA),
                outs = outs, runs = as.integer(on2) + as.integer(on3)))
  }
  if (kind == "double") {
    return(list(base = 2L, outs = outs,
                runs = as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  if (kind == "triple") {
    return(list(base = 4L, outs = outs,
                runs = as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  if (kind == "home_run") {
    return(list(base = 0L, outs = outs,
                runs = 1L + as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  list(base = base_state, outs = outs, runs = 0L)
}

#' Encode base occupancy from three logical vectors (the vectorized twin of
#' `base_state_code()`, which takes player codes).
base_bits <- function(on1, on2, on3) {
  as.integer(on1) + 2L * as.integer(on2) + 4L * as.integer(on3)
}

#' Vectorized state transition: apply an outcome to MANY states at once.
apply_outcome_vec <- function(base_state, outs, kind) {
  n <- length(base_state)
  on1 <- bitwAnd(base_state, 1L) > 0
  on2 <- bitwAnd(base_state, 2L) > 0
  on3 <- bitwAnd(base_state, 4L) > 0
  zero <- rep(0L, n)
  falses <- rep(FALSE, n)

  if (kind %in% c("out", "fielders_choice")) {
    return(list(base = base_state, outs = outs + 1L, runs = zero))
  }
  if (kind == "walk_hbp") {
    newbase <- dplyr::case_when(
      !on1 ~ base_bits(TRUE, on2, on3),
      !on2 ~ base_bits(TRUE, TRUE, on3),
      TRUE ~ 7L)
    return(list(base = newbase, outs = outs,
                runs = as.integer(on1 & on2 & on3)))
  }
  if (kind == "single") {
    return(list(base = base_bits(TRUE, on1, falses), outs = outs,
                runs = as.integer(on2) + as.integer(on3)))
  }
  if (kind == "double") {
    return(list(base = rep(2L, n), outs = outs,
                runs = as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  if (kind == "triple") {
    return(list(base = rep(4L, n), outs = outs,
                runs = as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  if (kind == "home_run") {
    return(list(base = zero, outs = outs,
                runs = 1L + as.integer(on1) + as.integer(on2) + as.integer(on3)))
  }
  list(base = base_state, outs = outs, runs = zero)
}

#' Attach Leverage Index, normalized so an average plate appearance is 1.0.
#'
#' Leverage answers "how much can the game move from here?". We enumerate the
#' plausible outcomes of a plate appearance with their league frequencies, apply
#' each to the state, and average the resulting |dWP|.
#'
#' PERFORMANCE: this is done with ONE model prediction per outcome across the
#' whole season, not one per plate appearance. Row by row it is roughly six
#' `predict()` calls per at-bat -- tens of thousands of them, several minutes of
#' waiting. Vectorized it is six calls in total and finishes in seconds.
add_leverage <- function(pbp, model, re_tbl) {
  mix <- pbp %>%
    dplyr::count(outcome) %>%
    dplyr::mutate(p = n / sum(n))
  outcome_mix <- stats::setNames(mix$p, mix$outcome)

  innings <- pbp$inning
  halves  <- pbp$half_inning
  outs    <- pbp$outs_before
  bases   <- pbp$base_state_before
  diffs   <- pbp$score_diff_before

  wp0 <- predict_wp(model, pbp, re_tbl)
  total <- rep(0, nrow(pbp))

  for (kind in names(outcome_mix)) {
    st <- apply_outcome_vec(bases, outs, kind)
    ended <- st$outs >= OUTS_PER_HALF

    #' When the third out is made the other team bats, so the batting team's
    #' win probability becomes the complement of the new state's.
    nxt <- tibble::tibble(
      inning = ifelse(ended & halves == "Bottom", innings + 1L, innings),
      half_inning = ifelse(ended,
                           ifelse(halves == "Top", "Bottom", "Top"), halves),
      outs_before = ifelse(ended, 0L, st$outs),
      base_state_before = ifelse(ended, 0L, st$base),
      score_diff_before = ifelse(ended, -(diffs + st$runs), diffs + st$runs),
      batting_team_won = 0
    )
    wp1 <- predict_wp(model, nxt, re_tbl)
    wp1 <- ifelse(ended, 1 - wp1, wp1)
    total <- total + outcome_mix[[kind]] * abs(wp1 - wp0)
  }

  pbp %>%
    dplyr::mutate(
      expected_swing = total,
      leverage_index = total / mean(total, na.rm = TRUE),
      #' Clutch: win impact weighted by what was at stake, compressed so one
      #' enormous play does not flatten the leaderboard.
      clutch_score = 100 * tanh(3 * abs(wpa) * sqrt(pmax(leverage_index, 0)))
    )
}

### Presentation ----

#' The plays that moved the game most.
biggest_swings <- function(pbp, n = 10) {
  pbp %>%
    dplyr::arrange(dplyr::desc(abs(wpa))) %>%
    dplyr::transmute(game_string, inning, half = half_inning, batter, outcome,
                     runs, wp_before = round(wp_before, 3),
                     wp_after = round(wp_after, 3), wpa = round(wpa, 3),
                     leverage_index = round(leverage_index, 2)) %>%
    utils::head(n)
}

#' How leverage is distributed -- the check that it averages 1.0.
leverage_profile <- function(pbp) {
  li <- pbp$leverage_index[is.finite(pbp$leverage_index)]
  tibble::tibble(
    statistic = c("mean", "median", "p75", "p90", "p95", "max",
                  "share above 2.0 (high leverage)"),
    value = round(c(mean(li), stats::median(li),
                    stats::quantile(li, 0.75), stats::quantile(li, 0.90),
                    stats::quantile(li, 0.95), max(li), mean(li >= 2)), 3)
  )
}

#' The win-probability path through one game, ready for ggplot.
game_flow <- function(pbp, game_string) {
  pbp %>%
    dplyr::filter(game_string == !!game_string) %>%
    dplyr::mutate(
      wp_home = ifelse(half_inning == "Bottom", wp_after, 1 - wp_after),
      play_index = dplyr::row_number()
    ) %>%
    dplyr::select(play_index, inning, half_inning, batter, outcome,
                  wp_home, wpa, leverage_index)
}

#' The signature win-probability chart.
plot_game_flow <- function(flow, home_team = "HOME", away_team = "AWAY") {
  ggplot2::ggplot(flow, ggplot2::aes(x = play_index, y = wp_home)) +
    ggplot2::geom_hline(yintercept = 0.5, linetype = "dashed",
                        colour = SMT_THEME$muted) +
    ggplot2::geom_ribbon(ggplot2::aes(ymin = 0.5, ymax = pmax(wp_home, 0.5)),
                         fill = SMT_THEME$home, alpha = 0.35) +
    ggplot2::geom_ribbon(ggplot2::aes(ymin = pmin(wp_home, 0.5), ymax = 0.5),
                         fill = SMT_THEME$away, alpha = 0.35) +
    ggplot2::geom_line(colour = SMT_THEME$text, linewidth = 1.1) +
    ggplot2::scale_y_continuous(labels = scales::percent, limits = c(0, 1)) +
    ggplot2::labs(title = "WIN PROBABILITY",
                  subtitle = paste(away_team, "at", home_team),
                  x = "Plate appearance", y = NULL) +
    theme_scoreboard()
}
