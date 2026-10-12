#' R04_speed_baserunning.R -- COMPONENT 4: Speed & Baserunning.
#'
#' Mirrors components/c04_speed_baserunning.py.
#'
#' Scoreboard products in this file
#'   Burner Board           peak sprint speed to first, ranked across the league
#'   Home-to-First Dash     contact to the bag, as a beat-the-clock graphic
#'   Fastest Out of the Box acceleration in the first 1.5 seconds
#'   Extra-Base Instinct    speed and path efficiency taking an extra base
#'   Pickoff Jump           secondary lead distance and burst

### Burner Board ----

#' Peak sprint speed on the way to first, ranked across the league.
burner_board <- function(sprints, lineups_tbl = lineups, min_runs = 3, top = 15) {
  attach_player(sprints, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(
      top_speed_mph = max(sprint_mph, na.rm = TRUE),
      avg_speed_mph = round(mean(sprint_mph, na.rm = TRUE), 2),
      runs = dplyr::n(),
      team = dplyr::first(team),
      .groups = "drop") %>%
    dplyr::filter(runs >= min_runs) %>%
    dplyr::mutate(league_percentile = round(100 * dplyr::percent_rank(top_speed_mph), 1)) %>%
    dplyr::arrange(dplyr::desc(top_speed_mph)) %>%
    utils::head(top)
}

#' The Burner Board as a scoreboard bar chart.
plot_burner_board <- function(board, n = 12) {
  d <- board %>% utils::head(n) %>%
    dplyr::mutate(player = forcats::fct_reorder(player, top_speed_mph))
  ggplot2::ggplot(d, ggplot2::aes(x = top_speed_mph, y = player)) +
    ggplot2::geom_col(fill = SMT_THEME$grass) +
    ggplot2::geom_text(ggplot2::aes(label = sprintf("%.1f", top_speed_mph)),
                       hjust = -0.15, colour = SMT_THEME$text, size = 3.4) +
    ggplot2::coord_cartesian(xlim = c(min(d$top_speed_mph) - 1,
                                      max(d$top_speed_mph) + 1)) +
    ggplot2::labs(title = "BURNER BOARD",
                  subtitle = "Peak sprint speed on the way to first",
                  x = "mph", y = NULL) +
    theme_scoreboard()
}

### Home-to-First Dash ----

#' Elapsed time from contact to the first-base bag.
#'
#' `runs_tbl` needs columns batter and time_to_base_s, produced by the play
#' anatomy step (the moment the runner enters the bag radius).
home_to_first <- function(runs_tbl, top = 15) {
  runs_tbl %>%
    dplyr::filter(is.finite(time_to_base_s),
                  time_to_base_s > 3, time_to_base_s < 7.5) %>%
    dplyr::group_by(batter) %>%
    dplyr::summarise(best_time_s = min(time_to_base_s),
                     avg_time_s = round(mean(time_to_base_s), 2),
                     tries = dplyr::n(), .groups = "drop") %>%
    dplyr::mutate(grade = dplyr::case_when(
      best_time_s < 4.2 ~ "ELITE",
      best_time_s < 4.5 ~ "PLUS",
      TRUE ~ "AVERAGE")) %>%
    dplyr::arrange(best_time_s) %>%
    utils::head(top)
}

### Fastest Out of the Box ----

#' Acceleration in the first stride and a half after contact.
#'
#' Measured as the speed gained over the first 1.5 seconds, which is the window
#' in which a hitter's reaction and first step actually show up.
out_of_the_box <- function(runs_tbl, top = 15) {
  runs_tbl %>%
    dplyr::filter(is.finite(burst_ft_s2), burst_ft_s2 > 0) %>%
    dplyr::group_by(batter) %>%
    dplyr::summarise(best_burst = max(burst_ft_s2),
                     avg_burst = round(mean(burst_ft_s2), 1),
                     n = dplyr::n(), .groups = "drop") %>%
    dplyr::arrange(dplyr::desc(best_burst)) %>%
    utils::head(top)
}

#' Compute burst for one runner directly from tracking.
compute_burst <- function(track, t_hit, window_ms = 1500) {
  w <- track %>%
    dplyr::filter(timestamp >= t_hit, timestamp <= t_hit + window_ms)
  if (nrow(w) < 3) return(NA_real_)
  sp <- frame_speed(w$field_x, w$field_y, w$timestamp)
  sp <- sp[is.finite(sp)]
  if (length(sp) < 2) return(NA_real_)
  (max(sp) - sp[1]) / (window_ms / 1000)
}

### Extra-Base Instinct ----

#' Top speed and path efficiency when a runner takes an extra base.
extra_base_instinct <- function(pbp, sprints, top = 15) {
  key <- pbp %>%
    dplyr::filter(outcome %in% c("double", "triple")) %>%
    dplyr::select(game_string, play = last_play, batter, outcome)

  sprints %>%
    dplyr::inner_join(key, by = c("game_string", "play")) %>%
    dplyr::group_by(batter) %>%
    dplyr::summarise(
      top_speed_mph = max(sprint_mph, na.rm = TRUE),
      avg_speed_mph = round(mean(sprint_mph, na.rm = TRUE), 2),
      extra_bases = dplyr::n(),
      triples = sum(outcome == "triple"),
      .groups = "drop") %>%
    dplyr::arrange(dplyr::desc(extra_bases), dplyr::desc(top_speed_mph)) %>%
    utils::head(top)
}

### Pickoff Jump ----

#' Secondary lead distance and burst on pickoff plays.
#'
#' SCOPE NOTE: the data flags pickoff attempts (`is_pickoff`) but records no
#' outcome, and there are no stolen-base or caught-stealing labels anywhere. So
#' this reports the MEASURED lead and burst rather than a modelled steal
#' probability -- an honest number beats an invented one.
pickoff_jump <- function(game_string, lineups_tbl = lineups, top = 15) {
  picks <- lineups_tbl %>%
    dplyr::filter(game_string == !!game_string,
                  dplyr::coalesce(is_pickoff, FALSE))
  if (nrow(picks) == 0) {
    return(tibble::tibble(play = integer(0), runner_id = integer(0),
                          lead_ft = numeric(0), burst_mph = numeric(0)))
  }

  bags <- list("11" = BASE_XY$first, "12" = BASE_XY$second, "13" = BASE_XY$third)

  purrr::map_dfr(unique(picks$play_per_game), function(play) {
    purrr::map_dfr(names(bags), function(rid) {
      trk <- get_player_track(game_string, play, as.numeric(rid))
      if (nrow(trk) < 3) return(NULL)
      bag <- bags[[rid]]
      lead <- dist_2d(trk$field_x[1], trk$field_y[1], bag[1], bag[2])
      sp <- frame_speed(trk$field_x, trk$field_y, trk$timestamp)
      burst <- top_speed(sp, 0.95) * FT_S_TO_MPH
      if (!is.finite(lead) || lead <= 0 || lead >= 30) return(NULL)
      tibble::tibble(play = as.integer(play), runner_id = as.integer(rid),
                     lead_ft = round(lead, 1),
                     burst_mph = round(burst, 1))
    })
  }) %>%
    dplyr::arrange(dplyr::desc(lead_ft)) %>%
    utils::head(top)
}
