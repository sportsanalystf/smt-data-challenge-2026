#' R05_power_hitting.R -- COMPONENT 5: Power & Hitting.
#'
#' Mirrors components/c05_power_hitting.py.
#'
#' Scoreboard products in this file
#'   Statcast Smash        exit velocity leaderboard
#'   Moonshot Meter        estimated carry distance of flies and home runs
#'   Barrel Zone           the sweet-spot exit-velo x launch-angle combination
#'   Launch Angle Rainbow  a hitter's spray of launch angles and outcomes
#'   Clutch Contact        hardest contact weighted by leverage

BARREL_MIN_EV <- 95
BARREL_LA_MIN <- 20
BARREL_LA_MAX <- 35

### Statcast Smash ----

#' Hardest-hit balls, ranked by 90th-percentile exit velocity.
#'
#' The 90th percentile is used rather than the maximum because a single
#' mis-tracked frame can inflate one reading; a high percentile rewards hitters
#' who do it repeatedly.
statcast_smash <- function(hits, lineups_tbl = lineups, min_balls = 5, top = 15) {
  attach_player(hits, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(
      max_exit_velo = max(exit_velo_mph, na.rm = TRUE),
      p90_exit_velo = round(stats::quantile(exit_velo_mph, 0.90, na.rm = TRUE), 1),
      avg_exit_velo = round(mean(exit_velo_mph, na.rm = TRUE), 1),
      balls = dplyr::n(), team = dplyr::first(team), .groups = "drop") %>%
    dplyr::filter(balls >= min_balls) %>%
    dplyr::arrange(dplyr::desc(p90_exit_velo), dplyr::desc(max_exit_velo)) %>%
    utils::head(top)
}

#' The single hardest-hit balls of the night.
hardest_hit_balls <- function(hits, lineups_tbl = lineups, top = 10) {
  attach_player(hits, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::arrange(dplyr::desc(exit_velo_mph)) %>%
    dplyr::select(game_string, play, player, team, exit_velo_mph,
                  launch_deg, hit_distance_ft = carry_ft) %>%
    utils::head(top)
}

### Moonshot Meter ----

#' Estimated carry distance on balls hit in the air.
moonshot_meter <- function(hits, lineups_tbl = lineups, min_flies = 3, top = 15) {
  attach_player(hits, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player), launch_deg >= 10, carry_ft >= 150) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(longest_ft = max(carry_ft, na.rm = TRUE),
                     avg_ft = round(mean(carry_ft, na.rm = TRUE), 1),
                     flies = dplyr::n(), team = dplyr::first(team),
                     .groups = "drop") %>%
    dplyr::filter(flies >= min_flies) %>%
    dplyr::arrange(dplyr::desc(longest_ft)) %>%
    utils::head(top)
}

### Barrel Zone ----

#' Barrels: hit hard, in the sweet-spot launch window.
barrel_zone <- function(hits, lineups_tbl = lineups, min_balls = 8, top = 15) {
  attach_player(hits, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::mutate(is_barrel = as.integer(
      exit_velo_mph >= BARREL_MIN_EV &
        launch_deg >= BARREL_LA_MIN & launch_deg <= BARREL_LA_MAX)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(barrels = sum(is_barrel, na.rm = TRUE),
                     balls = dplyr::n(), team = dplyr::first(team),
                     .groups = "drop") %>%
    dplyr::mutate(barrel_rate_pct = round(100 * barrels / balls, 1)) %>%
    dplyr::filter(balls >= min_balls) %>%
    dplyr::arrange(dplyr::desc(barrels), dplyr::desc(barrel_rate_pct)) %>%
    utils::head(top)
}

#' The classic sweet-spot heat map: outcome rate across exit velo x launch angle.
plot_barrel_zone <- function(hits) {
  d <- hits %>%
    dplyr::filter(is.finite(exit_velo_mph), is.finite(launch_deg),
                  launch_deg > -30, launch_deg < 70) %>%
    dplyr::mutate(is_barrel = exit_velo_mph >= BARREL_MIN_EV &
                    launch_deg >= BARREL_LA_MIN & launch_deg <= BARREL_LA_MAX)
  ggplot2::ggplot(d, ggplot2::aes(x = exit_velo_mph, y = launch_deg)) +
    ggplot2::geom_hex(bins = 34) +
    ggplot2::scale_fill_viridis_c(option = "inferno", trans = "log10") +
    ggplot2::annotate("rect", xmin = BARREL_MIN_EV, xmax = max(d$exit_velo_mph),
                      ymin = BARREL_LA_MIN, ymax = BARREL_LA_MAX,
                      fill = NA, colour = SMT_THEME$gold, linewidth = 1.1) +
    ggplot2::annotate("text", x = BARREL_MIN_EV + 12, y = BARREL_LA_MAX + 6,
                      label = "BARREL ZONE", colour = SMT_THEME$gold,
                      fontface = "bold", size = 4) +
    ggplot2::labs(title = "BARREL ZONE",
                  subtitle = "Every batted ball, by exit velocity and launch angle",
                  x = "Exit velocity (mph)", y = "Launch angle (degrees)",
                  fill = "Batted balls") +
    theme_scoreboard()
}

### Launch Angle Rainbow ----

#' A hitter's distribution of launch angles and what each type produced.
launch_angle_rainbow <- function(hits, lineups_tbl = lineups, player = NULL) {
  d <- attach_player(hits, lineups_tbl, "batter", play_col = "play") %>%
    dplyr::filter(!is.na(player), is.finite(launch_deg))
  if (!is.null(player)) d <- d %>% dplyr::filter(player == !!player)

  d <- d %>%
    dplyr::mutate(batted_ball_type = cut(
      launch_deg, breaks = c(-90, 10, 25, 50, 90),
      labels = c("ground ball", "line drive", "fly ball", "pop up")))

  summary <- d %>%
    dplyr::group_by(batted_ball_type) %>%
    dplyr::summarise(n = dplyr::n(),
                     avg_exit_velo = round(mean(exit_velo_mph, na.rm = TRUE), 1),
                     avg_distance = round(mean(carry_ft, na.rm = TRUE), 1),
                     .groups = "drop")
  list(data = d, summary = summary)
}

#' The rainbow itself: launch angle against distance, coloured by exit velocity.
plot_launch_rainbow <- function(rainbow) {
  ggplot2::ggplot(rainbow$data,
                  ggplot2::aes(x = launch_deg, y = carry_ft,
                               colour = exit_velo_mph)) +
    ggplot2::geom_point(alpha = 0.7, size = 1.8) +
    ggplot2::scale_colour_viridis_c(option = "plasma") +
    ggplot2::labs(title = "LAUNCH ANGLE RAINBOW",
                  subtitle = "How launch angle turns into distance",
                  x = "Launch angle (degrees)", y = "Carry (feet)",
                  colour = "Exit velo") +
    theme_scoreboard()
}

### Clutch Contact ----

#' Hardest contact when it mattered most: exit velocity weighted by leverage.
clutch_contact <- function(pbp_with_tracking, top = 15) {
  pbp_with_tracking %>%
    dplyr::filter(is.finite(exit_velo_mph), is.finite(leverage_index)) %>%
    dplyr::mutate(clutch_contact_score = round(
      pmax(exit_velo_mph, 60) / 100 * sqrt(leverage_index), 3)) %>%
    dplyr::arrange(dplyr::desc(clutch_contact_score)) %>%
    dplyr::select(game_string, inning, half = half_inning, batter, outcome,
                  exit_velo_mph, leverage_index, wpa, clutch_contact_score) %>%
    utils::head(top)
}
