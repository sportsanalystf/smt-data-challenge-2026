#' R01_play_by_play.R -- COMPONENT 1: tracking data -> play-by-play.
#'
#' Mirrors components/c01_play_by_play.py.
#'
#' WHY THIS COMPONENT EXISTS
#' The SMT tables record base occupancy but NOT outs, runs, or the score. Win
#' probability, leverage and run expectancy are all functions of
#' (inning, half, outs, base state, score differential), so none of them can be
#' computed until a proper play-by-play table is reconstructed. This file does
#' that reconstruction.
#'
#' THE METHOD
#' For each half-inning we walk the at-bats and apply an accounting identity.
#' Everyone on base before the play, plus the batter, must finish in exactly one
#' of three places -- still on base, across the plate, or retired:
#'
#'     |B| + 1 = |A| + runs + outs
#'
#' |B| and |A| are read from `lineups`; whether the batter reached is read from
#' the NEXT at-bat's occupancy. The half-inning must total three outs, which
#' closes the system.
#'
#' THREE CORRECTIONS THAT MATTER (each found by checking against real rates)
#'   1. Do not count the batter twice in the identity.
#'   2. Do not apply the identity to the LAST at-bat of a half-inning -- there is
#'      no observed "after" state, so runners left on base would be
#'      indistinguishable from runs.
#'   3. Only the TERMINAL play decides the outcome. A foul ball shares event
#'      code 4 with a live batted ball, so a walk that followed a foul would
#'      otherwise be recorded as a single.
#'
#' Usage:
#'   source("R/smt_setup.R"); source("R/R01_play_by_play.R")
#'   pbp <- build_play_by_play("y1_d122_IOL_VAS")

### Terminal-play helpers ----

#' Events belonging to the last play of an at-bat.
terminal_play_events <- function(events_tbl, plays) {
  if (length(plays) == 0) return(events_tbl[0, ])
  last_play <- max(plays)
  events_tbl %>%
    dplyr::filter(play_per_game == last_play) %>%
    dplyr::arrange(timestamp)
}

#' TRUE if the terminal play was a batted ball that stayed live.
#' A foul registers as contact followed immediately by end-of-play with nobody
#' touching the ball; a live ball is fielded, bounces, or leaves the yard.
is_live_contact <- function(term_events) {
  codes <- term_events$ball_eventcode
  if (length(codes) == 0) return(FALSE)
  if (EVENT[["HOME_RUN"]] %in% codes) return(TRUE)
  if (!(EVENT[["HIT_INTO_PLAY"]] %in% codes)) return(FALSE)
  hit_idx <- which(codes == EVENT[["HIT_INTO_PLAY"]])[1]
  after <- codes[seq_len(length(codes))[-seq_len(hit_idx)]]
  any(after %in% LIVE_BALL_CODES)
}

#' Upper bound on how many runners can score, given what the batter did.
#' Occupancy alone cannot tell a runner who scored from one replaced by a
#' pinch-runner; baseball physics can. A runner on first cannot score on an
#' infield out, and a retired batter cannot drive in a runner from first.
max_plausible_runs <- function(kind, on1, on2, on3) {
  n1 <- as.integer(!is.na(on1)); n2 <- as.integer(!is.na(on2))
  n3 <- as.integer(!is.na(on3))
  on_base <- n1 + n2 + n3
  switch(kind,
         "home_run" = on_base + 1L,
         "triple"   = on_base,
         "double"   = n1 + n2 + n3,
         "single"   = n2 + n3,
         "walk_hbp" = if (n1 & n2 & n3) 1L else 0L,
         "out"      = n3,
         "fielders_choice" = n3,
         on_base)
}

### Outcome classification ----

#' Infer the outcome of one at-bat from occupancy + the terminal play.
classify_at_bat <- function(events_tbl, plays, dest_base, next_batter_seen) {
  term <- terminal_play_events(events_tbl, plays)
  codes <- term$ball_eventcode
  live  <- is_live_contact(term)

  if (EVENT[["HOME_RUN"]] %in% codes) {
    return(list(kind = "home_run", dest = 4L, live = TRUE, confidence = "high"))
  }
  if (!is.na(dest_base) && dest_base > 0) {
    if (!live) {
      return(list(kind = "walk_hbp", dest = dest_base, live = FALSE,
                  confidence = if (dest_base == 1) "high" else "medium"))
    }
    kind <- switch(as.character(dest_base),
                   "1" = "single", "2" = "double", "3" = "triple", "single")
    return(list(kind = kind, dest = dest_base, live = TRUE, confidence = "high"))
  }
  list(kind = "out", dest = 0L, live = live,
       confidence = if (next_batter_seen) "high" else "medium")
}

### The reconstruction ----

#' Reconstruct the at-bat sequence for one game.
#'
#' @param game_string e.g. "y1_d122_IOL_VAS"
#' @param lineups_tbl the `lineups` table (from the starter file)
#' @param events_tbl  ball events for this game, already collected
#' @return tibble, one row per plate appearance
reconstruct_at_bats <- function(game_string, lineups_tbl = lineups,
                                events_tbl = NULL) {

  lu <- lineups_tbl %>% dplyr::filter(game_string == !!game_string)
  if (nrow(lu) == 0) stop("no lineup rows for ", game_string)

  if (is.null(events_tbl)) {
    events_tbl <- ball_events %>%
      dplyr::filter(game_string == !!game_string) %>%
      dplyr::collect() %>%
      dplyr::mutate(dplyr::across(c(play_per_game, timestamp,
                                    player_id, ball_eventcode), as.numeric))
  }

  #' Plate appearances only -- a pickoff is not an at-bat.
  pa <- lu %>% dplyr::filter(!dplyr::coalesce(is_pickoff, FALSE))

  #' Collapse plays to at-bats; state is taken at the FIRST play of the at-bat.
  ab <- pa %>%
    dplyr::group_by(inning, half_inning, at_bat) %>%
    dplyr::summarise(
      first_play = min(play_per_game),
      last_play  = max(play_per_game),
      n_pitches  = dplyr::n(),
      batter = dplyr::first(batter), pitcher = dplyr::first(pitcher),
      on_1b = dplyr::first(on_1b), on_2b = dplyr::first(on_2b),
      on_3b = dplyr::first(on_3b),
      home_team = dplyr::first(home_team), away_team = dplyr::first(away_team),
      .groups = "drop"
    ) %>%
    dplyr::mutate(half_order = as.integer(half_inning == "Bottom")) %>%
    dplyr::arrange(inning, half_order, at_bat)

  plays_by_ab <- pa %>%
    dplyr::group_by(inning, half_inning, at_bat) %>%
    dplyr::summarise(plays = list(play_per_game), .groups = "drop")

  out_rows <- list()

  for (half_key in unique(paste(ab$inning, ab$half_order))) {
    grp <- ab %>%
      dplyr::filter(paste(inning, half_order) == half_key) %>%
      dplyr::arrange(at_bat)
    n <- nrow(grp)
    if (n == 0) next

    recs <- vector("list", n)

    ## ---- pass 1: batter outcomes and departures
    for (i in seq_len(n)) {
      r   <- grp[i, ]
      nxt <- if (i < n) grp[i + 1, ] else NULL

      before <- c(r$on_1b, r$on_2b, r$on_3b)
      before <- before[!is.na(before)]
      after  <- if (!is.null(nxt)) {
        a <- c(nxt$on_1b, nxt$on_2b, nxt$on_3b); a[!is.na(a)]
      } else character(0)

      #' Which base does the batter occupy at the NEXT at-bat? That is what
      #' tells us whether he reached, and how far.
      dest <- NA_integer_
      if (!is.null(nxt)) {
        dest <- 0L
        if (!is.na(nxt$on_1b) && nxt$on_1b == r$batter) {
          dest <- 1L
        } else if (!is.na(nxt$on_2b) && nxt$on_2b == r$batter) {
          dest <- 2L
        } else if (!is.na(nxt$on_3b) && nxt$on_3b == r$batter) {
          dest <- 3L
        }
      }

      plays <- plays_by_ab %>%
        dplyr::filter(inning == r$inning, half_inning == r$half_inning,
                      at_bat == r$at_bat) %>%
        dplyr::pull(plays) %>% unlist()

      oc <- classify_at_bat(events_tbl, plays, dest, next_batter_seen = !is.null(nxt))

      is_last <- is.null(nxt)
      #' The identity is NOT applied to the last at-bat: with no observed
      #' "after" state, stranded runners would be counted as runs.
      gone <- if (is_last) 0L else max(0L, length(before) + 1L - length(after))
      batter_out <- if (oc$dest == 0) 1L else 0L
      runner_gone <- max(0L, gone - batter_out)

      #' NOTE: the team columns must be carried through here -- the final
      #' mutate needs them to work out which side was batting, and the score.
      #' Player codes are coerced to character explicitly: if a base is empty
      #' for an entire half-inning the column arrives as logical NA, and
      #' bind_rows() refuses to combine logical with character.
      recs[[i]] <- list(
        inning = as.integer(r$inning), half_inning = as.character(r$half_inning),
        at_bat = as.integer(r$at_bat),
        first_play = as.numeric(r$first_play),
        last_play = as.numeric(r$last_play),
        n_pitches = as.integer(r$n_pitches),
        batter = as.character(r$batter), pitcher = as.character(r$pitcher),
        home_team = as.character(r$home_team),
        away_team = as.character(r$away_team),
        on_1b = as.character(r$on_1b), on_2b = as.character(r$on_2b),
        on_3b = as.character(r$on_3b),
        outcome = oc$kind, batter_dest = as.integer(oc$dest),
        ball_in_play = oc$live,
        confidence = oc$confidence, n_before = length(before),
        gone = gone, batter_out = batter_out, runner_gone = runner_gone,
        is_last = is_last
      )
    }

    ## ---- pass 2: allocate departures between runs and outs
    batter_outs <- vapply(recs, function(x) x$batter_out, integer(1))
    known_outs  <- sum(batter_outs)
    avail       <- sum(vapply(recs, function(x) x$runner_gone, integer(1)))
    needed      <- min(max(0L, OUTS_PER_HALF - known_outs), avail)

    #' Charge runner outs first where the batter was ALSO retired -- the
    #' double-play signature -- then to other balls in play.
    ord <- order(batter_outs == 0,
                 !vapply(recs, function(x) x$ball_in_play, logical(1)))
    runner_outs <- integer(n)
    remaining <- needed
    for (i in ord) {
      if (remaining <= 0) break
      if (recs[[i]]$outcome == "home_run") next
      take <- min(recs[[i]]$runner_gone, remaining)
      runner_outs[i] <- take
      remaining <- remaining - take
    }

    for (i in seq_len(n)) {
      rec <- recs[[i]]
      if (rec$outcome == "home_run") {
        recs[[i]]$runs <- rec$n_before + 1L
        recs[[i]]$outs_on_play <- 0L
      } else if (rec$is_last) {
        used <- sum(vapply(recs[seq_len(i - 1)],
                           function(x) x$outs_on_play, integer(1)))
        recs[[i]]$outs_on_play <- max(0L, OUTS_PER_HALF - used)
        recs[[i]]$runs <- 0L
      } else {
        recs[[i]]$outs_on_play <- batter_outs[i] + runner_outs[i]
        raw <- max(0L, rec$runner_gone - runner_outs[i])
        cap <- max_plausible_runs(rec$outcome, rec$on_1b, rec$on_2b, rec$on_3b)
        recs[[i]]$runs <- as.integer(min(raw, cap))
        if (raw > cap) recs[[i]]$confidence <- "medium"
      }
    }

    half_outs <- sum(vapply(recs, function(x) x$outs_on_play, integer(1)))
    balanced <- (half_outs == OUTS_PER_HALF)

    ## ---- pass 3: running outs, clamped so the state can never be illegal
    outs_before <- 0L
    for (i in seq_len(n)) {
      allowance <- OUTS_PER_HALF - outs_before
      anomaly <- recs[[i]]$outs_on_play > allowance || outs_before >= OUTS_PER_HALF
      recs[[i]]$outs_on_play <- max(0L, min(recs[[i]]$outs_on_play, allowance))
      recs[[i]]$state_anomaly <- anomaly
      recs[[i]]$half_balanced <- balanced && !anomaly
      if (anomaly) recs[[i]]$confidence <- "low"
      recs[[i]]$outs_before <- min(outs_before, OUTS_PER_HALF - 1L)
      recs[[i]]$outs_after  <- min(OUTS_PER_HALF,
                                   outs_before + recs[[i]]$outs_on_play)
      recs[[i]]$base_state_before <- base_state_code(recs[[i]]$on_1b,
                                                     recs[[i]]$on_2b,
                                                     recs[[i]]$on_3b)
      outs_before <- recs[[i]]$outs_after
    }

    out_rows <- c(out_rows, recs)
  }

  df <- dplyr::bind_rows(lapply(out_rows, function(x) {
    x$is_last <- NULL; x$gone <- NULL; x$batter_out <- NULL
    x$runner_gone <- NULL
    tibble::as_tibble(x)
  }))

  ## ---- game-level score progression
  df %>%
    dplyr::arrange(inning, as.integer(half_inning == "Bottom"), at_bat) %>%
    dplyr::mutate(
      game_string = !!game_string,
      batting_team = ifelse(half_inning == "Top", away_team, home_team),
      home_runs_scored = ifelse(half_inning == "Bottom", runs, 0L),
      away_runs_scored = ifelse(half_inning == "Top", runs, 0L),
      home_score_after = cumsum(home_runs_scored),
      away_score_after = cumsum(away_runs_scored),
      home_score_before = home_score_after - home_runs_scored,
      away_score_before = away_score_after - away_runs_scored,
      score_diff_before = ifelse(half_inning == "Top",
                                 away_score_before - home_score_before,
                                 home_score_before - away_score_before),
      situation = paste0(ifelse(half_inning == "Top", "Top ", "Bot "), inning,
                         ", ", describe_state(base_state_before, outs_before))
    )
}

#' Convenience wrapper: reconstruct and attach the final result of the game,
#' which win probability needs as its training target.
build_play_by_play <- function(game_string, lineups_tbl = lineups) {
  df <- reconstruct_at_bats(game_string, lineups_tbl)
  home_final <- max(df$home_score_after, na.rm = TRUE)
  away_final <- max(df$away_score_after, na.rm = TRUE)
  #' The win-probability target must be a clean complement: for every plate
  #' appearance exactly one side is the eventual winner. Writing this as two
  #' strict inequalities looks natural but is WRONG -- a reconstructed tie
  #' labels BOTH sides as losers, and the model then learns from contradictory
  #' rows (it drove the base rate to 0.425 and produced outs with +0.5 WPA).
  #' Ties are assigned to the away side so the labels stay complementary.
  df %>%
    dplyr::mutate(
      home_final = home_final, away_final = away_final,
      batting_team_won = ifelse(half_inning == "Bottom",
                                as.integer(home_final > away_final),
                                as.integer(away_final >= home_final))
    )
}

#' Reconstruct many games at once.
build_play_by_play_season <- function(game_strings, lineups_tbl = lineups) {
  purrr::map_dfr(game_strings, function(gs) {
    tryCatch(build_play_by_play(gs, lineups_tbl),
             error = function(e) {
               message("skipping ", gs, ": ", conditionMessage(e)); NULL
             })
  })
}

### Presentation ----

#' The columns a reader actually wants.
pbp_table <- function(df, n = 15) {
  df %>%
    dplyr::transmute(inning, half = half_inning, batter, pitcher,
                     outs = outs_before,
                     bases = BASE_STATES[base_state_before + 1],
                     outcome, runs, outs_made = outs_on_play,
                     away = away_score_after, home = home_score_after) %>%
    utils::head(n)
}

#' Validation view: how the reconstruction compares to real baseball rates.
season_validation <- function(df) {
  n_games <- dplyr::n_distinct(df$game_string)
  tibble::tibble(
    metric = c("runs_per_game", "hits_per_game", "walks_per_game",
               "home_runs_per_game", "plate_appearances_per_game"),
    reconstructed = round(c(
      sum(df$runs) / n_games,
      sum(df$outcome %in% c("single", "double", "triple", "home_run")) / n_games,
      sum(df$outcome == "walk_hbp") / n_games,
      sum(df$outcome == "home_run") / n_games,
      nrow(df) / n_games), 2),
    real_milb_reference = c(9.5, 18.0, 7.0, 2.0, 76.0)
  )
}
