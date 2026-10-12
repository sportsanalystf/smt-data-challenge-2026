#' R03_tracking_features.R -- COMPONENT 3: physical measurements from tracking.
#'
#' Mirrors components/c03_tracking_features.py.
#'
#' Everything the scoreboard shows begins here: speeds differenced from 20 Hz
#' positions, batted-ball measurements from the ball's flight, pitch
#' trajectories fit as quadratics, and fielder routes. Each function is pure --
#' tracking frames in, numbers out -- so it can be reused by every component
#' downstream.

### Loading one play ----

#' Ball tracking for a single play, collected from Arrow.
get_ball_track <- function(game_string, play) {
  ball_positions %>%
    dplyr::filter(game_string == !!game_string, play_per_game == !!play) %>%
    dplyr::collect() %>%
    dplyr::mutate(dplyr::across(c(timestamp, ball_position_x, ball_position_y,
                                  ball_position_z), as.numeric)) %>%
    dplyr::arrange(timestamp)
}

#' Player tracking for a single play (optionally one player).
get_player_track <- function(game_string, play, player_id = NULL) {
  out <- player_positions %>%
    dplyr::filter(game_string == !!game_string, play_per_game == !!play)
  if (!is.null(player_id)) {
    out <- out %>% dplyr::filter(player_id == !!player_id)
  }
  out %>%
    dplyr::collect() %>%
    dplyr::mutate(dplyr::across(c(timestamp, field_x, field_y, player_id),
                                as.numeric)) %>%
    dplyr::arrange(timestamp)
}

#' Ball events for a play.
get_events <- function(game_string, play) {
  ball_events %>%
    dplyr::filter(game_string == !!game_string, play_per_game == !!play) %>%
    dplyr::collect() %>%
    dplyr::mutate(dplyr::across(c(timestamp, player_id, ball_eventcode),
                                as.numeric)) %>%
    dplyr::arrange(timestamp)
}

#' Timestamp of a given event code within a play (NA if absent).
event_time <- function(events_tbl, code) {
  hit <- events_tbl %>% dplyr::filter(ball_eventcode == code)
  if (nrow(hit) == 0) return(NA_real_)
  hit$timestamp[1]
}

### Speeds ----

#' Instantaneous player speed (ft/s) between consecutive frames.
player_speed_series <- function(track) {
  if (nrow(track) < 3) return(tibble::tibble(t_s = numeric(0),
                                             speed_ftps = numeric(0)))
  sp <- frame_speed(track$field_x, track$field_y, track$timestamp)
  tibble::tibble(
    t_s = (track$timestamp[-nrow(track)] - track$timestamp[1]) / 1000,
    speed_ftps = sp,
    speed_mph = sp * FT_S_TO_MPH
  )
}

#' Instantaneous 3-D ball speed (ft/s).
ball_speed_series <- function(ball_track) {
  if (nrow(ball_track) < 2) return(numeric(0))
  dt <- diff(ball_track$timestamp) / 1000
  d <- sqrt(diff(ball_track$ball_position_x)^2 +
              diff(ball_track$ball_position_y)^2 +
              diff(ball_track$ball_position_z)^2)
  ifelse(dt > 0, d / dt, NA_real_)
}

### Batted ball ----

#' Exit velocity (mph) from the ball's flight just after contact.
exit_velocity <- function(ball_track, t_hit, window_ms = 400, probs = 0.95) {
  w <- ball_track %>%
    dplyr::filter(timestamp >= t_hit, timestamp <= t_hit + window_ms)
  if (nrow(w) < 3) return(NA_real_)
  top_speed(ball_speed_series(w), probs) * FT_S_TO_MPH
}

#' Launch angle (degrees) from the initial velocity vector after contact.
launch_angle <- function(ball_track, t_hit, frames = 4) {
  w <- ball_track %>% dplyr::filter(timestamp >= t_hit)
  if (nrow(w) < 2) return(NA_real_)
  n <- min(frames, nrow(w) - 1)
  horiz <- sqrt((w$ball_position_x[n + 1] - w$ball_position_x[1])^2 +
                  (w$ball_position_y[n + 1] - w$ball_position_y[1])^2)
  if (horiz <= 0) return(NA_real_)
  vert <- w$ball_position_z[n + 1] - w$ball_position_z[1]
  atan2(vert, horiz) * 180 / pi
}

#' Carry distance: where the ball first lands.
#'
#' Uses the first recorded bounce when available, otherwise the point after the
#' apex where the ball returns to roughly its contact height. This avoids the
#' common error of taking the ball's maximum distance over the whole play, which
#' is inflated by relay throws.
carry_distance <- function(ball_track, t_hit, bounce_ts = NA_real_) {
  b <- ball_track %>% dplyr::filter(timestamp >= t_hit)
  if (nrow(b) < 3) return(NA_real_)
  if (!is.na(bounce_ts)) {
    idx <- which.min(abs(b$timestamp - bounce_ts))
    return(sqrt(b$ball_position_x[idx]^2 + b$ball_position_y[idx]^2))
  }
  z <- b$ball_position_z
  apex <- which.max(z)
  after <- z[apex:length(z)]
  idx <- apex + which.min(abs(after - z[1])) - 1
  idx <- min(idx, nrow(b))
  sqrt(b$ball_position_x[idx]^2 + b$ball_position_y[idx]^2)
}

### Pitching ----

#' Pitch velocity (mph) over the flight to the plate.
pitch_velocity <- function(ball_track, t_pitch, window_ms = 800, probs = 0.90) {
  w <- ball_track %>%
    dplyr::filter(timestamp >= t_pitch, timestamp <= t_pitch + window_ms)
  if (nrow(w) < 3) return(NA_real_)
  top_speed(ball_speed_series(w), probs) * FT_S_TO_MPH
}

#' Fit a pitch trajectory: x(y) and z(y) as quadratics.
#'
#' A quadratic is exactly right here -- under constant acceleration (gravity
#' plus a roughly constant aerodynamic force) position is quadratic in flight
#' distance. Fitting lets us evaluate the pitch at ANY distance from the plate,
#' which is what tunneling requires.
fit_pitch_trajectory <- function(ball_track, t_pitch, min_frames = 5) {
  b <- ball_track %>% dplyr::filter(timestamp >= t_pitch)
  if (nrow(b) < min_frames) return(NULL)
  y <- b$ball_position_y
  if ((max(y) - min(y)) < 20) return(NULL)
  fx <- stats::lm(ball_position_x ~ poly(ball_position_y, 2, raw = TRUE), data = b)
  fz <- stats::lm(ball_position_z ~ poly(ball_position_y, 2, raw = TRUE), data = b)
  release_y <- max(y)
  at_y <- function(model, yy) {
    as.numeric(stats::predict(model,
                              newdata = data.frame(ball_position_y = yy)))
  }
  list(
    fx = fx, fz = fz, release_y = release_y,
    release_x = at_y(fx, release_y), release_z = at_y(fz, release_y),
    extension_ft = RUBBER_TO_PLATE_FT - release_y,
    plate_x = at_y(fx, 0), plate_z = at_y(fz, 0),
    at_y = at_y
  )
}

#' (x, z) of the fitted pitch at a given distance from the plate.
pitch_at_distance <- function(traj, y) {
  c(x = traj$at_y(traj$fx, y), z = traj$at_y(traj$fz, y))
}

#' Approximate flight time from release to the plate.
flight_time_s <- function(release_y, velo_mph) {
  if (!is.finite(velo_mph) || velo_mph <= 0) return(NA_real_)
  v_fts <- (velo_mph / FT_S_TO_MPH) * AVG_SPEED_FACTOR
  release_y / v_fts
}

#' Movement at the plate, in inches: horizontal, INDUCED vertical, and the
#' gravity component that was removed.
#'
#' Deviation from the straight line a hitter would naively extrapolate has two
#' causes, and only one is interesting. Gravity drops a 90 mph pitch about 39
#' inches; reporting that as "movement" would make every pitch look filthy and
#' tell a fan nothing. Subtracting it leaves the aerodynamic (spin) component,
#' which is what separates a four-seamer from a curveball.
late_break_in <- function(traj, velo_mph = NA_real_) {
  ry <- traj$release_y
  eps <- 0.5
  dx_dy <- (traj$at_y(traj$fx, ry) - traj$at_y(traj$fx, ry - eps)) / eps
  dz_dy <- (traj$at_y(traj$fz, ry) - traj$at_y(traj$fz, ry - eps)) / eps
  dy <- 0 - ry
  lin_x <- traj$release_x + dx_dy * dy
  lin_z <- traj$release_z + dz_dy * dy

  horiz_in <- (traj$plate_x - lin_x) * 12
  raw_vert_in <- (traj$plate_z - lin_z) * 12

  t <- flight_time_s(ry, velo_mph)
  gravity_drop_in <- if (is.finite(t)) 0.5 * GRAVITY_FT_S2 * t^2 * 12 else NA_real_
  induced_in <- if (is.finite(gravity_drop_in)) raw_vert_in + gravity_drop_in else NA_real_

  list(horizontal_in = horiz_in, induced_vertical_in = induced_in,
       gravity_drop_in = gravity_drop_in)
}

#' Perceived speed once release extension is accounted for.
#'
#' Travel distance is (60.5 - extension). Releasing closer to the plate
#' shortens the flight and buys the hitter less time, so the ball plays faster
#' than the gun says.
effective_velocity <- function(velo_mph, extension_ft, league_extension_ft = 5.5) {
  if (!is.finite(velo_mph) || !is.finite(extension_ft)) return(NA_real_)
  d_actual <- max(1, RUBBER_TO_PLATE_FT - extension_ft)
  d_league <- max(1, RUBBER_TO_PLATE_FT - league_extension_ft)
  velo_mph * d_league / d_actual
}

#' Tunneling between two consecutive pitches.
#'
#' A hitter commits about 175 ms before the ball arrives -- roughly 23.8 feet
#' out. Two pitches close together there but far apart at the plate are, from
#' the hitter's chair, indistinguishable until it is too late.
tunnel_pair <- function(traj_a, traj_b, commit = COMMIT_POINT_FT) {
  a <- pitch_at_distance(traj_a, commit)
  b <- pitch_at_distance(traj_b, commit)
  tunnel_in <- sqrt((a[["x"]] - b[["x"]])^2 + (a[["z"]] - b[["z"]])^2) * 12
  plate_in <- sqrt((traj_a$plate_x - traj_b$plate_x)^2 +
                     (traj_a$plate_z - traj_b$plate_z)^2) * 12
  list(tunnel_distance_in = tunnel_in, plate_distance_in = plate_in,
       tunnel_ratio = if (tunnel_in > 1e-6) plate_in / tunnel_in else NA_real_)
}

### Fielding ----

#' Straight-line distance a fielder covered between two timestamps.
route_distance <- function(track, t_start, t_end) {
  a <- track %>% dplyr::filter(timestamp <= t_start)
  b <- track %>% dplyr::filter(timestamp <= t_end)
  if (nrow(a) == 0 || nrow(b) == 0) return(NA_real_)
  dist_2d(dplyr::last(a$field_x), dplyr::last(a$field_y),
          dplyr::last(b$field_x), dplyr::last(b$field_y))
}

#' Actual distance travelled along the path.
path_length <- function(track, t_start, t_end) {
  w <- track %>%
    dplyr::filter(timestamp >= t_start, timestamp <= t_end)
  if (nrow(w) < 2) return(NA_real_)
  sum(sqrt(diff(w$field_x)^2 + diff(w$field_y)^2))
}

#' Straight-line distance / actual path length. 1.0 = a perfect route.
route_efficiency <- function(track, t_start, t_end) {
  direct <- route_distance(track, t_start, t_end)
  actual <- path_length(track, t_start, t_end)
  if (!is.finite(direct) || !is.finite(actual) || actual <= 0) return(NA_real_)
  min(1, direct / actual)
}

### League baselines ----

#' Season distributions, so any measurement can be turned into a percentile.
build_baselines <- function(hits = NULL, sprints = NULL, throws = NULL,
                            catches = NULL, pitches = NULL) {
  b <- list()
  if (!is.null(sprints)) b$sprint_mph <- sprints$sprint_mph
  if (!is.null(hits)) {
    b$exit_velo_mph <- hits$exit_velo_mph
    b$launch_deg <- hits$launch_deg
    b$carry_ft <- hits$carry_ft
  }
  if (!is.null(throws)) b$throw_velo_mph <- throws$throw_velo_mph
  if (!is.null(catches)) {
    b$route_ft <- catches$route_ft
    b$hang_s <- catches$hang_s
  }
  if (!is.null(pitches)) {
    v <- pitches$pitch_velo_mph
    #' Drop single-frame tracking spikes; 103 mph is the plausible ceiling at
    #' this level and an artifact would distort every percentile built from it.
    b$pitch_velo_mph <- v[v > 50 & v <= MAX_PLAUSIBLE_PITCH_MPH]
  }
  lapply(b, function(x) x[is.finite(x)])
}

#' Summary table of the baselines.
baseline_table <- function(baselines) {
  purrr::imap_dfr(baselines, function(x, nm) {
    tibble::tibble(
      metric = nm, n = length(x), mean = round(mean(x), 2),
      p10 = round(stats::quantile(x, 0.10), 2),
      median = round(stats::median(x), 2),
      p90 = round(stats::quantile(x, 0.90), 2),
      max = round(max(x), 2))
  })
}
