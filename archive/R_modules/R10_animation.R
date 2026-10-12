#' R10_animation.R -- COMPONENT 10: play animation.
#'
#' Mirrors components/c10_animation.py.
#'
#' The challenge's own `SMT_Data_Starter.R` already provides `animate_play()`,
#' which draws a play on a sportyR field with gganimate. This module EXTENDS it
#' rather than replacing it:
#'
#'   animate_play_annotated()   the starter's animation plus the story --
#'                              WPA, leverage, and what the play was
#'   animate_pitch_sequence()   the catcher's-eye view of an at-bat's pitches,
#'                              which is how a strikeout (where nothing happens
#'                              on the field) becomes watchable
#'   animate_fielder_route()    the defensive story: route, ground covered and
#'                              closing speed, traced as it happens
#'
#' All three return gganimate objects; save with `anim_save()`.

### Shared frame builder ----

#' Assemble one play's tracking into the long frame gganimate wants.
#'
#' Player and ball tracking are combined into a single table with a `type`
#' column, timestamps are aligned to the stadium's true frame interval, and a
#' `frame_id` is created so gganimate has an integer to transition over.
build_tracking_frames <- function(game_string, play, start_at_pitch = TRUE) {

  players <- get_player_track(game_string, play) %>%
    dplyr::mutate(
      type = dplyr::case_when(
        player_id <= 9 ~ "defense",
        player_id >= 10 & player_id <= 13 ~ "offense",
        player_id >= 14 & player_id <= 17 ~ "umpire",
        TRUE ~ "coach"),
      position_x = field_x, position_y = field_y, position_z = NA_real_) %>%
    dplyr::select(timestamp, player_id, type, position_x, position_y, position_z)

  ball <- get_ball_track(game_string, play) %>%
    dplyr::mutate(player_id = NA_real_, type = "ball",
                  position_x = ball_position_x, position_y = ball_position_y,
                  position_z = ball_position_z) %>%
    dplyr::select(timestamp, player_id, type, position_x, position_y, position_z)

  trk <- dplyr::bind_rows(players, ball) %>% dplyr::arrange(timestamp)

  if (start_at_pitch) {
    ev <- get_events(game_string, play)
    t_pitch <- event_time(ev, EVENT[["PITCH"]])
    if (!is.na(t_pitch)) trk <- trk %>% dplyr::filter(timestamp >= t_pitch)
  }

  #' Frame interval can vary by stadium (30 vs 50 fps sources), so derive it
  #' from the data instead of assuming.
  step <- trk %>%
    dplyr::filter(type != "ball") %>%
    dplyr::group_by(player_id) %>%
    dplyr::mutate(gap = timestamp - dplyr::lag(timestamp)) %>%
    dplyr::ungroup() %>%
    dplyr::count(gap) %>%
    dplyr::filter(!is.na(gap)) %>%
    dplyr::slice_max(n, n = 1) %>%
    dplyr::pull(gap)
  if (length(step) == 0 || !is.finite(step[1])) step <- 1000 / FRAME_HZ

  trk %>%
    dplyr::mutate(timestamp_adj = round(timestamp / step[1]) * step[1],
                  frame_id = match(timestamp_adj, sort(unique(timestamp_adj))))
}

### Annotated play animation ----

#' The starter's field animation, plus the story of the play.
#'
#' @param pbp_row a single row of the play-by-play table (component 1/2), used
#'   for the caption -- outcome, WPA and leverage.
animate_play_annotated <- function(game_string, play, pbp_row = NULL,
                                   fps = 12, width = 5, height = 5) {

  options(gganimate.dev_args = list(width = width, height = height,
                                    units = "in", res = 120))
  trk <- build_tracking_frames(game_string, play)

  caption <- paste("Game:", game_string, "| Play:", play)
  title <- "PLAY REPLAY"
  if (!is.null(pbp_row) && nrow(pbp_row) > 0) {
    title <- toupper(gsub("_", " ", pbp_row$outcome[1]))
    caption <- sprintf("%s | WPA %+.0f%% | Leverage %.1fx",
                       pbp_row$batter[1],
                       100 * pbp_row$wpa[1],
                       pbp_row$leverage_index[1])
  }

  p <- sportyR::geom_baseball(league = "MiLB") +
    ggplot2::geom_point(
      data = dplyr::filter(trk, type != "ball"),
      ggplot2::aes(x = position_x, y = position_y, fill = type),
      shape = 21, size = 4, show.legend = FALSE) +
    ggplot2::geom_text(
      data = dplyr::filter(trk, type == "defense"),
      ggplot2::aes(x = position_x, y = position_y,
                   label = POS_ABBR[as.character(player_id)]),
      colour = "black", size = 2.2, show.legend = FALSE) +
    #' The ball's marker grows with height, so a fly ball reads as airborne
    #' instead of as a dot sliding across a map.
    ggplot2::geom_point(
      data = dplyr::filter(trk, type == "ball"),
      ggplot2::aes(x = position_x, y = position_y, size = position_z),
      fill = "white", shape = 21, show.legend = FALSE) +
    ggplot2::scale_size_continuous(range = c(2, 6)) +
    ggplot2::scale_fill_manual(values = c("offense" = "#ff7a90",
                                          "defense" = "#ffd54a",
                                          "coach" = "#1A85FF",
                                          "umpire" = "black")) +
    ggplot2::labs(title = title, subtitle = caption) +
    gganimate::transition_time(frame_id) +
    gganimate::shadow_wake(0.12, exclude_layer = c(1:16))

  gganimate::animate(p, fps = fps, nframes = max(trk$frame_id))
}

### Pitch sequence animation ----

#' The catcher's-eye view of an at-bat, one pitch at a time.
#'
#' This is what makes a strikeout watchable: nothing happens on the field, but
#' the sequence shows exactly how the pitcher set the hitter up. Pitches that
#' stay together at the commit point and separate at the plate are tunneled.
animate_pitch_sequence <- function(game_string, plays, velos = NULL,
                                   zone = list(bottom = 1.5, top = 3.4,
                                               half_width = 0.83),
                                   fps = 2) {

  seq_tbl <- purrr::imap_dfr(plays, function(play, i) {
    ev <- get_events(game_string, play)
    t_pitch <- event_time(ev, EVENT[["PITCH"]])
    if (is.na(t_pitch)) return(NULL)
    traj <- fit_pitch_trajectory(get_ball_track(game_string, play), t_pitch)
    if (is.null(traj)) return(NULL)
    v <- if (!is.null(velos)) velos[[as.character(play)]] else NA_real_
    if (is.null(v)) v <- NA_real_
    br <- late_break_in(traj, v)
    tibble::tibble(pitch_number = i, play = as.integer(play),
                   plate_x = traj$plate_x, plate_z = traj$plate_z,
                   velo_mph = round(v, 1),
                   induced_break_in = round(br$induced_vertical_in, 1))
  })

  if (nrow(seq_tbl) == 0) stop("no pitches with usable trajectories")

  #' Each pitch stays on screen once thrown, so the sequence accumulates.
  cumulative <- purrr::map_dfr(seq_len(nrow(seq_tbl)), function(k) {
    seq_tbl %>% utils::head(k) %>% dplyr::mutate(reveal = k)
  })

  p <- ggplot2::ggplot(cumulative,
                       ggplot2::aes(x = plate_x, y = plate_z,
                                    fill = factor(pitch_number))) +
    ggplot2::annotate("rect",
                      xmin = -zone$half_width, xmax = zone$half_width,
                      ymin = zone$bottom, ymax = zone$top,
                      fill = NA, colour = "white", linewidth = 1.2) +
    ggplot2::geom_point(shape = 21, size = 8, colour = "black") +
    ggplot2::geom_text(ggplot2::aes(label = pitch_number), size = 3.2) +
    ggplot2::coord_fixed(xlim = c(-1.9, 1.9), ylim = c(0.2, 4.6)) +
    ggplot2::scale_fill_viridis_d(option = "plasma") +
    ggplot2::labs(title = "PITCH SEQUENCE",
                  subtitle = "Catcher's view -- where each pitch crossed",
                  x = NULL, y = NULL) +
    theme_scoreboard() +
    ggplot2::theme(legend.position = "none",
                   axis.text = ggplot2::element_blank()) +
    gganimate::transition_manual(reveal)

  gganimate::animate(p, fps = fps, nframes = nrow(seq_tbl))
}

### Fielder route animation ----

#' Trace a fielder's route to the ball as it happens.
animate_fielder_route <- function(game_string, play, fielder_id, fps = 12) {
  ev <- get_events(game_string, play)
  t_hit <- event_time(ev, EVENT[["HIT_INTO_PLAY"]])
  if (is.na(t_hit)) stop("no ball-in-play event on this play")

  trk <- get_player_track(game_string, play, fielder_id) %>%
    dplyr::filter(timestamp >= t_hit) %>%
    dplyr::mutate(frame_id = dplyr::row_number())
  ball <- get_ball_track(game_string, play) %>%
    dplyr::filter(timestamp >= t_hit)

  route <- round(route_distance(trk, min(trk$timestamp), max(trk$timestamp)), 1)
  eff <- round(100 * route_efficiency(trk, min(trk$timestamp),
                                      max(trk$timestamp)))

  p <- sportyR::geom_baseball(league = "MiLB") +
    ggplot2::geom_path(data = ball,
                       ggplot2::aes(x = ball_position_x, y = ball_position_y),
                       colour = "white", linetype = "dashed", alpha = 0.8) +
    ggplot2::geom_path(data = trk,
                       ggplot2::aes(x = field_x, y = field_y),
                       colour = SMT_THEME$accent, linewidth = 1.4) +
    ggplot2::geom_point(data = trk,
                        ggplot2::aes(x = field_x, y = field_y),
                        colour = SMT_THEME$accent, size = 4) +
    ggplot2::labs(
      title = paste("GROUND COVERED --", POS_ABBR[as.character(fielder_id)]),
      subtitle = paste0(route, " ft covered | ", eff, "% route efficiency")) +
    gganimate::transition_reveal(trk$frame_id)

  gganimate::animate(p, fps = fps, nframes = nrow(trk))
}

### Saving ----

#' Save any of the animations above to disk.
save_animation <- function(anim, path, ...) {
  gganimate::anim_save(filename = path, animation = anim, ...)
  path
}
