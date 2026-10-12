#' R09_composite.R -- COMPONENT 9: Composite & Storytelling.
#'
#' Mirrors components/c09_composite.py.
#'
#' Scoreboard products in this file
#'   Five-Tool Scoreboard   percentile blend of speed, power and arm
#'   Player of the Game     weighted contribution score for a single game
#'   Rivalry Radar          team-vs-team tale of the tape
#'   Prospect Spotlight     a player's tool grades, ready to animate

### Five-Tool Scoreboard ----

#' Blend speed, power and arm into one number every fan understands.
#'
#' Each tool is converted to a league percentile first, so quantities in
#' different units (mph off the bat, mph on the run, mph on the throw) can be
#' averaged honestly. Players missing a tool are scored on what we measured,
#' with the count reported so nobody is silently flattered.
#'
#' IMPORTANT: pass the FULL leaderboards (`top = Inf`), not the top-15 views.
#' Percentiles are computed within whatever is handed in, so truncated inputs
#' rank a player against a handful of rivals instead of the league.
five_tool_scoreboard <- function(burner, smash, cannons, min_tools = 2, top = 15) {
  spd <- burner %>% dplyr::select(player, speed = top_speed_mph)
  pwr <- smash %>% dplyr::select(player, power = max_exit_velo)
  arm <- cannons %>% dplyr::select(player, arm = max_throw_mph)

  spd %>%
    dplyr::full_join(pwr, by = "player") %>%
    dplyr::full_join(arm, by = "player") %>%
    dplyr::mutate(
      speed_pct = round(100 * dplyr::percent_rank(speed), 1),
      power_pct = round(100 * dplyr::percent_rank(power), 1),
      arm_pct   = round(100 * dplyr::percent_rank(arm), 1),
      tools_measured = as.integer(!is.na(speed_pct)) +
        as.integer(!is.na(power_pct)) + as.integer(!is.na(arm_pct)),
      five_tool_score = round(rowMeans(
        cbind(speed_pct, power_pct, arm_pct), na.rm = TRUE), 1),
      grade = grade_for(five_tool_score),
      team = stringr::str_split_i(player, "-", 1)) %>%
    dplyr::filter(tools_measured >= min_tools) %>%
    dplyr::arrange(dplyr::desc(five_tool_score)) %>%
    utils::head(top)
}

#' The five-tool radar, drawn as a bar profile (readable at scoreboard scale).
plot_five_tool <- function(five_tool, player) {
  d <- five_tool %>%
    dplyr::filter(player == !!player) %>%
    dplyr::select(speed_pct, power_pct, arm_pct) %>%
    tidyr::pivot_longer(dplyr::everything(), names_to = "tool",
                        values_to = "percentile") %>%
    dplyr::mutate(tool = stringr::str_remove(tool, "_pct"))

  ggplot2::ggplot(d, ggplot2::aes(x = tool, y = percentile, fill = percentile)) +
    ggplot2::geom_col(width = 0.65) +
    ggplot2::geom_text(ggplot2::aes(label = round(percentile)),
                       vjust = -0.5, colour = SMT_THEME$text) +
    ggplot2::scale_fill_viridis_c(option = "plasma", limits = c(0, 100)) +
    ggplot2::ylim(0, 105) +
    ggplot2::labs(title = "FIVE-TOOL SCOREBOARD", subtitle = player,
                  x = NULL, y = "League percentile") +
    theme_scoreboard() +
    ggplot2::theme(legend.position = "none")
}

### Player of the Game ----

#' Who did the most to win it, measured in win probability added.
player_of_the_game <- function(pbp, game_string, top = 5) {
  g <- pbp %>% dplyr::filter(game_string == !!game_string)
  if (nrow(g) == 0) return(tibble::tibble())

  batting <- g %>%
    dplyr::group_by(player = batter) %>%
    dplyr::summarise(plate_appearances = dplyr::n(),
                     wpa = round(sum(wpa, na.rm = TRUE), 3),
                     hits = sum(outcome %in% c("single", "double", "triple",
                                               "home_run")),
                     home_runs = sum(outcome == "home_run"),
                     rbi = sum(runs), .groups = "drop") %>%
    dplyr::mutate(role = "batting")

  pitching <- g %>%
    dplyr::group_by(player = pitcher) %>%
    dplyr::summarise(batters_faced = dplyr::n(),
                     #' A pitcher gains when the batting team loses ground.
                     wpa = round(-sum(wpa, na.rm = TRUE), 3), .groups = "drop") %>%
    dplyr::mutate(role = "pitching")

  dplyr::bind_rows(batting, pitching) %>%
    dplyr::mutate(potg_score = round(100 * wpa, 1)) %>%
    dplyr::arrange(dplyr::desc(wpa)) %>%
    utils::head(top)
}

### Rivalry Radar ----

#' Team-vs-team tale of the tape built from tracking aggregates.
rivalry_radar <- function(pbp, team_a, team_b) {
  purrr::map_dfr(c(team_a, team_b), function(tm) {
    sub <- pbp %>% dplyr::filter(batting_team == tm)
    tibble::tibble(
      team = tm,
      plate_appearances = nrow(sub),
      runs = sum(sub$runs, na.rm = TRUE),
      home_runs = sum(sub$outcome == "home_run", na.rm = TRUE),
      avg_exit_velo = if ("exit_velo_mph" %in% names(sub)) {
        round(mean(sub$exit_velo_mph, na.rm = TRUE), 1)
      } else NA_real_,
      avg_wpa_per_pa = round(mean(sub$wpa, na.rm = TRUE), 4),
      high_leverage_pa = sum(sub$leverage_index >= 2, na.rm = TRUE))
  })
}

### Prospect Spotlight ----

#' One player's tool grades, in the shape a scoreboard animates.
prospect_spotlight <- function(player, burner, smash, cannons,
                               baselines = NULL) {
  pick <- function(df, col) {
    r <- df %>% dplyr::filter(player == !!player)
    if (nrow(r) == 0) return(NA_real_)
    as.numeric(r[[col]][1])
  }
  tools <- c(speed = pick(burner, "top_speed_mph"),
             power = pick(smash, "max_exit_velo"),
             arm   = pick(cannons, "max_throw_mph"))
  metric_for <- c(speed = "sprint_mph", power = "exit_velo_mph",
                  arm = "throw_velo_mph")

  purrr::imap_dfr(tools, function(value, tool) {
    ref <- if (!is.null(baselines)) baselines[[metric_for[[tool]]]] else NULL
    pct <- if (!is.null(ref) && is.finite(value)) {
      percentile_of(value, ref)
    } else NA_real_
    tibble::tibble(tool = tool, value = round(value, 1),
                   league_percentile = pct, grade = grade_for(pct))
  })
}

### Game headline ----

#' The one-line story of a game: final score and its biggest swing.
game_headline <- function(pbp, game_string) {
  g <- pbp %>% dplyr::filter(game_string == !!game_string)
  if (nrow(g) == 0) return(list())
  top <- g %>% dplyr::slice_max(abs(wpa), n = 1, with_ties = FALSE)
  list(game = game_string,
       final_home = max(g$home_score_after, na.rm = TRUE),
       final_away = max(g$away_score_after, na.rm = TRUE),
       turning_point_batter = top$batter,
       turning_point_outcome = top$outcome,
       turning_point_wpa = round(top$wpa, 3),
       turning_point_leverage = round(top$leverage_index, 2))
}
