#' R07_defense.R -- COMPONENT 7: Defense & Fielding.
#'
#' Mirrors components/c07_defense.py.
#'
#' Scoreboard products in this file
#'   The Robbery Meter    catch probability and Outs Above Expected
#'   Outfield Cannons     throw (arm) velocity leaderboard
#'   Ground Crew Range    distance covered and closing speed chasing fly balls
#'   Web Gem of the Game  the single most improbable completed catch
#'   Double-Play Ballet   pivot time on the turn
#'   Pop-Time Pipeline    catcher exchange and throw to second

### Helper: which player was the fielder? ----

#' Map fielder_id + play to the actual player code via the lineup.
#'
#' De-duplicating the lineup first matters: a play can appear more than once,
#' and a join that returns two rows per fielding play silently doubles every
#' leaderboard built from it.
attach_fielder <- function(df, lineups_tbl = lineups) {
  key <- lineups_tbl %>%
    dplyr::distinct(game_string, play_per_game, .keep_all = TRUE) %>%
    dplyr::select(game_string, play_per_game, dplyr::all_of(unname(POS_COLUMN)))

  df %>%
    dplyr::left_join(key, by = c("game_string", "play" = "play_per_game")) %>%
    dplyr::mutate(
      pos = POS_ABBR[as.character(fielder_id)],
      player = purrr::pmap_chr(
        list(fielder_id, pitcher, catcher, first_baseman, second_baseman,
             third_baseman, shortstop, left_fielder, center_fielder,
             right_fielder),
        function(fid, p, c, b1, b2, b3, ss, lf, cf, rf) {
          vals <- as.character(c(p, c, b1, b2, b3, ss, lf, cf, rf))
          idx <- suppressWarnings(as.integer(fid))
          if (is.na(idx) || idx < 1 || idx > 9) return(NA_character_)
          #' as.character() above matters: a lineup column that is entirely
          #' empty arrives as logical NA, and pmap_chr() rejects a non-character
          #' return value.
          as.character(vals[idx])
        }),
      team = stringr::str_split_i(player, "-", 1))
}

### The Robbery Meter ----

#' Fit catch probability from route distance, hang time and required speed.
#'
#' Three physically meaningful features: route and hang are the physics, and
#' their ratio -- the speed a fielder would have to sustain to arrive -- is what
#' separates a routine fly from a highlight.
fit_catch_model <- function(catches, max_route_ft = 160, min_hang_s = 0.4,
                            max_req_speed = 45) {
  d <- catches %>%
    dplyr::filter(hang_s > min_hang_s, route_ft >= 0, route_ft < max_route_ft) %>%
    dplyr::mutate(req_speed = pmin(route_ft / hang_s, max_req_speed))
  model <- stats::glm(catch_made ~ route_ft + hang_s + req_speed,
                      family = stats::binomial(link = "logit"), data = d)
  list(model = model, data = d)
}

#' Fit quality.
catch_model_metrics <- function(fit) {
  p <- as.numeric(stats::predict(fit$model, type = "response"))
  y <- fit$data$catch_made
  tibble::tibble(
    metric = c("opportunities", "base catch rate", "accuracy", "Brier score"),
    value = c(length(y), round(mean(y), 3),
              round(mean((p >= 0.5) == (y == 1)), 3),
              round(mean((p - y)^2), 3))
  )
}

#' Score every catch opportunity.
score_catches <- function(fit) {
  fit$data %>%
    dplyr::mutate(
      catch_prob = as.numeric(stats::predict(fit$model, type = "response")),
      oae = catch_made - catch_prob,
      robbery_score = ifelse(catch_made == 1, 100 * (1 - catch_prob), 0),
      #' A play is most fun to vote on when the model is least certain.
      suspense = 1 - abs(2 * (catch_prob - 0.5)))
}

#' Outs Above Expected: catches made beyond what an average defender makes.
outs_above_expected <- function(scored, lineups_tbl = lineups,
                                min_opps = 12, top = 15) {
  attach_fielder(scored, lineups_tbl) %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(opportunities = dplyr::n(),
                     catches_made = sum(catch_made),
                     expected = round(sum(catch_prob), 1),
                     oae = round(sum(oae), 2),
                     pos = dplyr::first(pos), team = dplyr::first(team),
                     .groups = "drop") %>%
    dplyr::filter(opportunities >= min_opps) %>%
    dplyr::arrange(dplyr::desc(oae)) %>%
    utils::head(top)
}

#' The most improbable completed catches -- auto-selected highlights.
web_gem <- function(scored, lineups_tbl = lineups, top = 10) {
  attach_fielder(scored, lineups_tbl) %>%
    dplyr::filter(catch_made == 1) %>%
    dplyr::arrange(catch_prob) %>%
    dplyr::transmute(game_string, play, player, pos,
                     route_ft = round(route_ft, 1), hang_s = round(hang_s, 2),
                     catch_prob = round(catch_prob, 3),
                     robbery_score = round(robbery_score, 1)) %>%
    utils::head(top)
}

#' The catch-probability curve: the model, as a fan would read it.
plot_catch_model <- function(fit, hang_times = c(2, 3, 4, 5)) {
  grid <- tidyr::expand_grid(route_ft = seq(0, 130, by = 2),
                             hang_s = hang_times) %>%
    dplyr::mutate(req_speed = pmin(route_ft / hang_s, 45))
  grid$catch_prob <- as.numeric(stats::predict(fit$model, newdata = grid,
                                               type = "response"))
  ggplot2::ggplot(grid, ggplot2::aes(x = route_ft, y = catch_prob,
                                     colour = factor(hang_s))) +
    ggplot2::geom_line(linewidth = 1.3) +
    ggplot2::scale_y_continuous(labels = scales::percent, limits = c(0, 1)) +
    ggplot2::labs(title = "THE ROBBERY METER",
                  subtitle = "Catch probability by route distance and hang time",
                  x = "Route distance (feet)", y = "Catch probability",
                  colour = "Hang time (s)") +
    theme_scoreboard()
}

### Outfield Cannons ----

#' Arm strength leaderboard.
outfield_cannons <- function(throws, lineups_tbl = lineups,
                             min_throws = 3, top = 15) {
  attach_fielder(throws, lineups_tbl) %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(max_throw_mph = max(throw_velo_mph, na.rm = TRUE),
                     avg_throw_mph = round(mean(throw_velo_mph, na.rm = TRUE), 1),
                     throws = dplyr::n(),
                     pos = dplyr::first(pos), team = dplyr::first(team),
                     .groups = "drop") %>%
    dplyr::filter(throws >= min_throws) %>%
    dplyr::arrange(dplyr::desc(max_throw_mph)) %>%
    utils::head(top)
}

### Ground Crew Range ----

#' Ground covered and top closing speed on balls caught.
ground_crew_range <- function(catches, lineups_tbl = lineups,
                              min_catches = 8, top = 15) {
  catches %>%
    dplyr::filter(catch_made == 1) %>%
    attach_fielder(lineups_tbl) %>%
    dplyr::filter(!is.na(player)) %>%
    dplyr::group_by(player) %>%
    dplyr::summarise(avg_route_ft = round(mean(route_ft, na.rm = TRUE), 1),
                     max_route_ft = max(route_ft, na.rm = TRUE),
                     top_closing_mph = round(max(close_ftps, na.rm = TRUE) *
                                               FT_S_TO_MPH, 1),
                     catches = dplyr::n(),
                     pos = dplyr::first(pos), team = dplyr::first(team),
                     .groups = "drop") %>%
    dplyr::filter(catches >= min_catches) %>%
    dplyr::arrange(dplyr::desc(avg_route_ft)) %>%
    utils::head(top)
}

### Double-Play Ballet ----

#' Pivot time: glove-to-release for the middle infielders on a relay.
double_play_ballet <- function(game_string, plays, top = 10) {
  purrr::map_dfr(plays, function(play) {
    ev <- get_events(game_string, play)
    purrr::map_dfr(c(PLAYER_IDS[["second_baseman"]], PLAYER_IDS[["shortstop"]]),
                   function(pid) {
                     a <- ev %>% dplyr::filter(player_id == pid,
                                               ball_eventcode == EVENT[["ACQUIRED"]])
                     t <- ev %>% dplyr::filter(player_id == pid,
                                               ball_eventcode == EVENT[["THROW"]])
                     if (nrow(a) == 0 || nrow(t) == 0) return(NULL)
                     dt <- (t$timestamp[1] - a$timestamp[1]) / 1000
                     if (dt < 0 || dt >= 2) return(NULL)
                     tibble::tibble(play = as.integer(play),
                                    pos = POS_ABBR[as.character(pid)],
                                    pivot_s = round(dt, 2))
                   })
  }) %>%
    dplyr::arrange(pivot_s) %>%
    utils::head(top)
}

### Pop-Time Pipeline ----

#' Catcher exchange time and throw velocity to second base.
pop_time_pipeline <- function(game_string, plays, top = 10) {
  cid <- PLAYER_IDS[["catcher"]]
  purrr::map_dfr(plays, function(play) {
    ev <- get_events(game_string, play)
    a <- ev %>% dplyr::filter(player_id == cid,
                              ball_eventcode == EVENT[["ACQUIRED"]])
    t <- ev %>% dplyr::filter(player_id == cid,
                              ball_eventcode %in% c(EVENT[["THROW"]],
                                                    EVENT[["THROW_UNK"]]))
    if (nrow(a) == 0 || nrow(t) == 0) return(NULL)
    dt <- (t$timestamp[1] - a$timestamp[1]) / 1000
    if (dt < 0 || dt >= 3) return(NULL)
    ball <- get_ball_track(game_string, play) %>%
      dplyr::filter(timestamp >= t$timestamp[1],
                    timestamp <= t$timestamp[1] + 600)
    velo <- if (nrow(ball) >= 3) {
      round(top_speed(ball_speed_series(ball), 0.90) * FT_S_TO_MPH, 1)
    } else NA_real_
    tibble::tibble(play = as.integer(play), exchange_s = round(dt, 2),
                   throw_velo_mph = velo)
  }) %>%
    dplyr::arrange(exchange_s) %>%
    utils::head(top)
}
