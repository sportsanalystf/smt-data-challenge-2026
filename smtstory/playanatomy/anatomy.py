"""
anatomy.py — the measured story of a single play.

The dashboard needs to answer a different question depending on how the play
ended, so this module dissects each play into the quantities that make that
particular story tellable:

  strikeout      -> handled by analytics/tunneling.py (nothing happens on field)
  ground out     -> who fielded it, how far they moved, how quickly they
                    transferred and threw, and how close the play was at first
  fly out        -> route distance, hang time, closing speed, catch difficulty
  base hit       -> where it landed, which fielder had the best chance,
                    how fast the batter ran
  close play     -> the ball's arrival time vs the runner's arrival time

Every quantity is measured from 20 Hz tracking, never assumed.

REUSE NOTE: kinematics (speeds, route distance, route efficiency) come from
`smtstory.tracking`, which itself wraps the original project's smt_utils.
"""
import numpy as np
import pandas as pd

from .. import config
from ..tracking import kinematics as K
from ..tracking.geometry import HOME, FIRST, SECOND, THIRD

EV = config.EVENT

PLAY_TYPES = ["strikeout_or_walk", "ground_out", "fly_out", "line_out",
              "base_hit", "home_run", "fielders_choice", "unknown"]

BASE_XY = {1: FIRST, 2: SECOND, 3: THIRD, 0: HOME}

# A runner is "at the bag" within this radius (feet).
BAG_RADIUS_FT = 4.0
# The longest plausible time from contact to a fielder gloving a live ball.
MAX_FIELD_TIME_S = 12.0


class PlayAnatomy:
    """Dissects one play into measured components."""

    def __init__(self, catch_model=None, baselines=None):
        self.catch_model = catch_model
        self.baselines = baselines or {}

    # ------------------------------------------------------------- helpers
    def _track(self, player_df, play, pid):
        d = player_df[(player_df.play_per_game == play) &
                      (player_df.player_id == pid)]
        return d.sort_values("timestamp")

    def _pos_at(self, trk, t):
        if trk.empty:
            return None
        d = trk[trk.timestamp <= t]
        if d.empty:
            d = trk
        return d.iloc[-1][["field_x", "field_y"]].to_numpy(float)

    # -------------------------------------------------------- classification
    def classify(self, events_play, outcome, launch_deg=None):
        """What kind of play was this?

        Uses `is_live_contact` rather than merely checking for event code 4:
        a foul ball shares that code with a live batted ball, and a caught foul
        tip for strike three would otherwise be dissected as a ground out (with
        the catcher retrieving the ball three minutes later).
        """
        from ..state.outcomes import is_live_contact

        codes = events_play.ball_eventcode.astype(int).tolist()
        if EV["HOME_RUN"] in codes or outcome == "home_run":
            return "home_run"
        if not is_live_contact(events_play.sort_values("timestamp")):
            return "strikeout_or_walk"
        if outcome in ("single", "double", "triple"):
            return "base_hit"
        if outcome == "fielders_choice":
            return "fielders_choice"
        # An out on a ball in play: ground or air, decided by launch angle when
        # available, otherwise by which fielder recorded the out.
        if launch_deg is not None and np.isfinite(launch_deg):
            if launch_deg < 10:
                return "ground_out"
            if launch_deg < 25:
                return "line_out"
            return "fly_out"
        acq = events_play[events_play.ball_eventcode == EV["ACQUIRED"]]
        if not acq.empty and int(acq.player_id.iloc[0]) in config.OUTFIELD_IDS:
            return "fly_out"
        return "ground_out"

    # ------------------------------------------------------------- fielding
    def fielding(self, game, play, t_hit):
        """Who fielded it, how far they went, and how fast they turned it around."""
        ev = game.events[game.events.play_per_game == play]
        ball = game.ball[game.ball.play_per_game == play].sort_values("timestamp")
        pp = game.player

        acq = ev[(ev.ball_eventcode.isin([EV["ACQUIRED"], EV["ACQUIRED_UNK"]])) &
                 (ev.timestamp >= t_hit) & (ev.player_id.between(1, 9))]
        if acq.empty:
            return None

        first = acq.iloc[0]
        fid = int(first.player_id)
        t_acq = int(first.timestamp)

        # A live ball is fielded within a few seconds. Anything longer is the
        # ball being retrieved after the play was already dead (a foul, or a
        # ball rolling to the backstop), which must not be reported as a play.
        if (t_acq - t_hit) / 1000.0 > MAX_FIELD_TIME_S:
            return None

        trk = self._track(pp, play, fid)
        start = self._pos_at(trk, t_hit)
        end = self._pos_at(trk, t_acq)
        if start is None or end is None:
            return None

        route_ft = float(np.hypot(*(end - start)))
        time_s = (t_acq - t_hit) / 1000.0
        sp = K.player_speed(trk[(trk.timestamp >= t_hit) &
                                (trk.timestamp <= t_acq)])
        top_close = K.top_speed(sp, 90) if len(sp) else np.nan
        eff = K.route_efficiency(trk, t_hit, t_acq)

        out = {
            "fielder_id": fid,
            "fielder_pos": config.POS_ABBR.get(fid, str(fid)),
            "fielder_start": [round(float(start[0]), 1), round(float(start[1]), 1)],
            "fielder_end": [round(float(end[0]), 1), round(float(end[1]), 1)],
            "route_ft": round(route_ft, 1),
            "time_to_ball_s": round(time_s, 2),
            "closing_speed_ftps": round(float(top_close), 1)
            if np.isfinite(top_close) else None,
            "closing_speed_mph": round(float(top_close) * config.FT_S_TO_MPH, 1)
            if np.isfinite(top_close) else None,
            "route_efficiency": round(float(eff), 3) if np.isfinite(eff) else None,
            "t_acquired": t_acq,
        }

        # Transfer and throw: how quickly did the ball leave the glove?
        thr = ev[(ev.ball_eventcode.isin([EV["THROW"], EV["THROW_UNK"]])) &
                 (ev.timestamp >= t_acq) & (ev.player_id == fid)]
        if not thr.empty:
            t_thr = int(thr.iloc[0].timestamp)
            out["transfer_s"] = round((t_thr - t_acq) / 1000.0, 2)
            w = ball[(ball.timestamp >= t_thr) & (ball.timestamp <= t_thr + 500)]
            if len(w) >= 3:
                v = K.top_speed(K.ball_speed_3d(w), 90) * config.FT_S_TO_MPH
                if 30 < v < 110:
                    out["throw_velo_mph"] = round(float(v), 1)
            out["t_thrown"] = t_thr

        # Catch difficulty, if this was an air out to the outfield.
        if self.catch_model is not None and fid in config.OUTFIELD_IDS:
            hang = time_s
            if 0.4 < hang < 8 and route_ft < 160:
                p = float(self.catch_model.predict([route_ft], [hang])[0])
                out["catch_prob"] = round(p, 3)
                out["catch_difficulty"] = self.catch_model.difficulty_label(p)
        return out

    # ---------------------------------------------------------- baserunning
    def baserunning(self, game, play, t_hit, target_base=1):
        """How fast did the batter get down the line?"""
        pp = game.player
        trk = self._track(pp, play, config.PLAYER_IDS["batter"])
        if trk.empty:
            return None
        run = trk[trk.timestamp >= t_hit]
        if len(run) < 4:
            return None

        sp = K.player_speed(run)
        top = K.top_speed(sp, 95)
        bag = np.array(BASE_XY[target_base], dtype=float)
        d = np.hypot(run.field_x.to_numpy(float) - bag[0],
                     run.field_y.to_numpy(float) - bag[1])

        out = {
            "top_speed_ftps": round(float(top), 1) if np.isfinite(top) else None,
            "top_speed_mph": round(float(top) * config.FT_S_TO_MPH, 1)
            if np.isfinite(top) else None,
            "distance_covered_ft": round(float(K.path_length(
                run, run.timestamp.iloc[0], run.timestamp.iloc[-1]) or 0), 1),
            "closest_to_bag_ft": round(float(d.min()), 1),
        }

        # Time to the bag: first frame inside the bag radius.
        reach = np.where(d <= BAG_RADIUS_FT)[0]
        if len(reach):
            t_reach = int(run.timestamp.iloc[int(reach[0])])
            out["time_to_base_s"] = round((t_reach - t_hit) / 1000.0, 2)
            out["t_reached"] = t_reach

        # Acceleration out of the box: speed gained in the first 1.5 seconds.
        early = run[run.timestamp <= t_hit + 1500]
        if len(early) >= 3:
            esp = K.player_speed(early)
            esp = esp[np.isfinite(esp)]
            if len(esp) >= 2:
                out["burst_ft_s2"] = round(
                    float((esp.max() - esp[0]) / 1.5), 1)
        eff = K.route_efficiency(run, run.timestamp.iloc[0], run.timestamp.iloc[-1])
        out["run_efficiency"] = round(float(eff), 3) if np.isfinite(eff) else None
        return out

    # ------------------------------------------------------- the close play
    def close_play(self, fielding, running):
        """How close was it at the bag?

        Compares when the throw would arrive against when the runner arrived.
        Positive margin means the runner beat the ball.
        """
        if not fielding or not running:
            return None
        t_reach = running.get("t_reached")
        t_thrown = fielding.get("t_thrown")
        if t_reach is None or t_thrown is None:
            return None
        throw_velo = fielding.get("throw_velo_mph")
        end = fielding.get("fielder_end")
        if throw_velo is None or end is None:
            return None
        dist = float(np.hypot(end[0] - FIRST[0], end[1] - FIRST[1]))
        v_fts = throw_velo / config.FT_S_TO_MPH
        t_ball_arrives = t_thrown + 1000.0 * dist / max(v_fts, 1e-6)
        margin_s = (t_ball_arrives - t_reach) / 1000.0
        return {
            "throw_distance_ft": round(dist, 1),
            "ball_arrival_ms": int(t_ball_arrives),
            "runner_arrival_ms": int(t_reach),
            "margin_s": round(margin_s, 3),
            "verdict": "SAFE" if margin_s > 0 else "OUT",
            "bang_bang": bool(abs(margin_s) < 0.15),
        }

    # --------------------------------------------------------- double play
    def double_play(self, game, play, t_hit):
        """Pivot time: acquire-to-release for the middle infielder on a relay."""
        ev = game.events[game.events.play_per_game == play]
        seq = ev[(ev.timestamp >= t_hit) &
                 (ev.ball_eventcode.isin([EV["ACQUIRED"], EV["THROW"]]))]
        pivots = []
        for pid in (config.PLAYER_IDS["second_baseman"],
                    config.PLAYER_IDS["shortstop"]):
            a = seq[(seq.player_id == pid) & (seq.ball_eventcode == EV["ACQUIRED"])]
            t = seq[(seq.player_id == pid) & (seq.ball_eventcode == EV["THROW"])]
            if not a.empty and not t.empty:
                dt = (int(t.iloc[0].timestamp) - int(a.iloc[0].timestamp)) / 1000.0
                if 0 <= dt < 2.0:
                    pivots.append({"player_id": int(pid),
                                   "pos": config.POS_ABBR.get(int(pid)),
                                   "pivot_s": round(dt, 2)})
        return pivots or None

    # ------------------------------------------------------------ pop time
    def pop_time(self, game, play):
        """Catcher exchange-and-throw time on a stolen-base attempt."""
        ev = game.events[game.events.play_per_game == play]
        c = config.PLAYER_IDS["catcher"]
        a = ev[(ev.player_id == c) & (ev.ball_eventcode == EV["ACQUIRED"])]
        t = ev[(ev.player_id == c) & (ev.ball_eventcode.isin([EV["THROW"],
                                                              EV["THROW_UNK"]]))]
        if a.empty or t.empty:
            return None
        dt = (int(t.iloc[0].timestamp) - int(a.iloc[0].timestamp)) / 1000.0
        if not (0 <= dt < 3.0):
            return None
        ball = game.ball[game.ball.play_per_game == play]
        w = ball[(ball.timestamp >= int(t.iloc[0].timestamp)) &
                 (ball.timestamp <= int(t.iloc[0].timestamp) + 600)]
        velo = None
        if len(w) >= 3:
            v = K.top_speed(K.ball_speed_3d(w), 90) * config.FT_S_TO_MPH
            if 30 < v < 100:
                velo = round(float(v), 1)
        return {"exchange_s": round(dt, 2), "throw_velo_mph": velo}

    # ------------------------------------------------------------- assemble
    def analyze(self, game, atbat_row, launch_deg=None):
        """Full anatomy of the deciding play of an at-bat."""
        play = int(atbat_row["last_play"])
        ev = game.events[game.events.play_per_game == play]
        if ev.empty:
            return None

        hit = ev[ev.ball_eventcode == EV["HIT_INTO_PLAY"]]
        outcome = atbat_row.get("outcome")
        ptype = self.classify(ev, outcome, launch_deg)

        out = {"play": play, "play_type": ptype, "outcome": outcome}

        if hit.empty:
            return out  # strikeout / walk: the story is in the pitch sequence

        t_hit = int(hit.iloc[0].timestamp)
        out["t_hit"] = t_hit
        out["fielding"] = self.fielding(game, play, t_hit)
        out["running"] = self.baserunning(game, play, t_hit)
        out["close_play"] = self.close_play(out["fielding"], out["running"])
        dp = self.double_play(game, play, t_hit)
        if dp:
            out["double_play"] = dp
        return out
