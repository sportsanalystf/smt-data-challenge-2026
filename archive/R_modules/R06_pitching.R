#' R06_pitching.R -- COMPONENT 6: Pitching.
#'
#' Mirrors components/c06_pitching.py.
#'
#' Scoreboard products in this file
#'   Radar Gun Live      pitch velocity leaderboard and per-pitcher averages
#'   Velocity Heartbeat  a starter's velocity across an outing
#'   Effective Velocity  perceived speed adjusted for release extension
#'   Late Life           movement from release to the plate, gravity removed
#'
#' SCOPE NOTE: spin rate is not present in the SMT data and cannot be recovered
#' from positional tracking, so no spin product is offered. Movement, extension
#' and perceived velocity are all directly measurable and are used instead.

### Radar Gun Live ----

#' Pitch velocity leaderboard.
radar_gun <- function(pitches, lineups_tbl = lineups, min_pitches = 30, top = 15) {
  pitches %>%
    dplyr::filter(pitch_velo_mph <= MAX_PLAUSIBLE_PITCH_MPH) %>%
    attach_player(lineups_tbl, "pitcher", play_col = "play") %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(
      max_velo = max(pitch_velo_mph, na.rm = TRUE),
      avg_velo = round(mean(pitch_velo_mph, na.rm = TRUE), 1),
      p90_velo = round(stats::quantile(pitch_velo_mph, 0.90, na.rm = TRUE), 1),
      pitches = dplyr::n(), team = dplyr::first(team), .groups = "drop") %>%
    dplyr::filter(pitches >= min_pitches) %>%
    dplyr::arrange(dplyr::desc(max_velo)) %>%
    utils::head(top)
}

#' Velocity distribution across the league, with a pitcher highlighted.
plot_radar_distribution <- function(pitches, highlight_player = NULL,
                                    lineups_tbl = lineups) {
  d <- pitches %>%
    dplyr::filter(pitch_velo_mph > 50, pitch_velo_mph <= MAX_PLAUSIBLE_PITCH_MPH)
  p <- ggplot2::ggplot(d, ggplot2::aes(x = pitch_velo_mph)) +
    ggplot2::geom_histogram(bins = 45, fill = SMT_THEME$home, alpha = 0.85) +
    ggplot2::labs(title = "RADAR GUN LIVE",
                  subtitle = "Every tracked pitch this season",
                  x = "Pitch velocity (mph)", y = "Pitches") +
    theme_scoreboard()
  if (!is.null(highlight_player)) {
    hl <- d %>%
      attach_player(lineups_tbl, "pitcher", play_col = "play") %>%
      dplyr::filter(player == highlight_player)
    if (nrow(hl) > 0) {
      p <- p + ggplot2::geom_vline(xintercept = mean(hl$pitch_velo_mph),
                                   colour = SMT_THEME$gold, linewidth = 1.2)
    }
  }
  p
}

### Velocity Heartbeat ----

#' How a pitcher's velocity holds across an outing.
#'
#' Returns per-pitch velocity in sequence plus a rolling average -- the line the
#' scoreboard animates as a heartbeat.
velocity_heartbeat <- function(pitches, game_string, pitcher = NULL,
                               lineups_tbl = lineups) {
  d <- pitches %>%
    dplyr::filter(game_string == !!game_string,
                  pitch_velo_mph <= MAX_PLAUSIBLE_PITCH_MPH) %>%
    attach_player(lineups_tbl, "pitcher", play_col = "play") %>%
    dplyr::filter(!is.na(player))

  if (is.null(pitcher) && nrow(d) > 0) {
    pitcher <- d %>% dplyr::count(player, sort = TRUE) %>%
      dplyr::slice(1) %>% dplyr::pull(player)
  }

  d <- d %>%
    dplyr::filter(player == pitcher) %>%
    dplyr::arrange(play) %>%
    dplyr::mutate(pitch_number = dplyr::row_number(),
                  rolling_avg = round(rolling_mean(pitch_velo_mph, width = 10), 1))

  if (nrow(d) == 0) return(list(data = d, summary = list()))

  first10 <- mean(utils::head(d$pitch_velo_mph, 10))
  last10  <- mean(utils::tail(d$pitch_velo_mph, 10))
  list(
    data = d %>% dplyr::select(pitch_number, play, pitch_velo_mph, rolling_avg),
    summary = list(pitcher = pitcher, pitches = nrow(d),
                   avg_velo = round(mean(d$pitch_velo_mph), 1),
                   first_10_avg = round(first10, 1),
                   last_10_avg = round(last10, 1),
                   velo_held = round(last10 - first10, 1))
  )
}

#' The heartbeat chart.
plot_velocity_heartbeat <- function(hb) {
  ggplot2::ggplot(hb$data, ggplot2::aes(x = pitch_number)) +
    ggplot2::geom_point(ggplot2::aes(y = pitch_velo_mph),
                        colour = SMT_THEME$muted, size = 1.8, alpha = 0.8) +
    ggplot2::geom_line(ggplot2::aes(y = rolling_avg),
                       colour = SMT_THEME$gold, linewidth = 1.3, na.rm = TRUE) +
    ggplot2::labs(
      title = "VELOCITY HEARTBEAT",
      subtitle = paste0(hb$summary$pitcher, " -- ",
                        hb$summary$velo_held, " mph from first to last"),
      x = "Pitch number", y = "Velocity (mph)") +
    theme_scoreboard()
}

### Effective Velocity ----

#' Perceived speed once release extension is accounted for.
effective_velocity_table <- function(game_string, plays, velos,
                                     league_extension_ft = 5.5, top = NULL) {
  out <- purrr::map_dfr(plays, function(play) {
    ev <- get_events(game_string, play)
    t_pitch <- event_time(ev, EVENT[["PITCH"]])
    if (is.na(t_pitch)) return(NULL)
    traj <- fit_pitch_trajectory(get_ball_track(game_string, play), t_pitch)
    if (is.null(traj)) return(NULL)
    v <- velos[[as.character(play)]]
    if (is.null(v) || !is.finite(v) || v > MAX_PLAUSIBLE_PITCH_MPH) return(NULL)
    eff <- effective_velocity(v, traj$extension_ft, league_extension_ft)
    tibble::tibble(play = as.integer(play), velo_mph = round(v, 1),
                   extension_ft = round(traj$extension_ft, 2),
                   effective_velo_mph = round(eff, 1),
                   gain_mph = round(eff - v, 1))
  })
  if (nrow(out) == 0 || is.null(top)) return(out)
  out %>% dplyr::arrange(dplyr::desc(effective_velo_mph)) %>% utils::head(top)
}

### Late Life ----

#' Movement at the plate with the gravity component removed.
#'
#' Gravity drops a 90 mph pitch about 39 inches regardless of quality, so raw
#' deviation from a straight line makes every pitch look filthy. Induced break
#' is what actually separates a four-seamer from a curveball.
late_life_table <- function(game_string, plays, velos, top = NULL) {
  out <- purrr::map_dfr(plays, function(play) {
    ev <- get_events(game_string, play)
    t_pitch <- event_time(ev, EVENT[["PITCH"]])
    if (is.na(t_pitch)) return(NULL)
    traj <- fit_pitch_trajectory(get_ball_track(game_string, play), t_pitch)
    if (is.null(traj)) return(NULL)
    v <- velos[[as.character(play)]]
    if (is.null(v)) v <- NA_real_
    br <- late_break_in(traj, v)
    if (!is.finite(br$induced_vertical_in)) return(NULL)
    tibble::tibble(
      play = as.integer(play),
      velo_mph = round(v, 1),
      induced_vertical_break_in = round(br$induced_vertical_in, 1),
      horizontal_break_in = round(br$horizontal_in, 1),
      gravity_drop_in = round(br$gravity_drop_in, 1),
      total_movement_in = round(sqrt(br$horizontal_in^2 +
                                       br$induced_vertical_in^2), 1),
      pitch_shape = dplyr::case_when(
        br$induced_vertical_in > 12 ~ "riding fastball",
        br$induced_vertical_in > 6  ~ "fastball",
        br$induced_vertical_in > 0  ~ "changeup / cutter",
        TRUE ~ "breaking ball"))
  })
  if (nrow(out) == 0 || is.null(top)) return(out)
  out %>% dplyr::arrange(dplyr::desc(total_movement_in)) %>% utils::head(top)
}

#' Movement plot: horizontal against induced vertical break, the standard
#' "pitch shape" view.
plot_pitch_movement <- function(late_life) {
  ggplot2::ggplot(late_life,
                  ggplot2::aes(x = horizontal_break_in,
                               y = induced_vertical_break_in,
                               colour = pitch_shape, size = velo_mph)) +
    ggplot2::geom_hline(yintercept = 0, colour = SMT_THEME$muted) +
    ggplot2::geom_vline(xintercept = 0, colour = SMT_THEME$muted) +
    ggplot2::geom_point(alpha = 0.85) +
    ggplot2::scale_size_continuous(range = c(2, 6)) +
    ggplot2::labs(title = "LATE LIFE",
                  subtitle = "Movement at the plate, gravity removed",
                  x = "Horizontal break (inches)",
                  y = "Induced vertical break (inches)",
                  colour = NULL, size = "mph") +
    theme_scoreboard()
}
