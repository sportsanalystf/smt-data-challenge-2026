"""
exporter.py — turn tracking into something the browser can animate.

DESIGN CONSTRAINT
-----------------
A full game of player tracking is ~350,000 rows. Serialized naively as JSON
objects that is well over 30 MB, which no self-contained HTML file should carry.
Three decisions keep it small enough to embed while staying smooth on screen:

1. **Arrays, not objects.** Every frame is `[x, y]`, not `{"x": .., "y": ..}`.
   That alone is roughly a 4x saving.
2. **One decimal foot.** Tracking precision beyond a tenth of a foot is
   invisible at scoreboard scale.
3. **Trim to the live ball.** Frames are kept from just before the pitch to
   shortly after the play ends — not the dead time between pitches.

The browser linearly interpolates between the 20 Hz samples, so playback looks
continuous at 60 fps without shipping more data.

Ball height (z) is carried too, so the replay can show the arc of a fly ball
and the pitch's approach to the plate, not just a dot sliding around a map.
"""
import numpy as np
import pandas as pd

from .. import config

EV = config.EVENT

# Players worth drawing. Umpires and coaches are tracked but add clutter.
DRAW_IDS = list(range(1, 14))   # pitcher..runner on 3rd

# Padding around the live-ball window, in milliseconds.
PRE_ROLL_MS = 400
POST_ROLL_MS = 800


def _round_pairs(xs, ys, nd=1):
    return [[round(float(a), nd), round(float(b), nd)] for a, b in zip(xs, ys)]


def export_play(game, play, max_frames=260, include_players=True):
    """Compact replay payload for a single play.

    Returns None when the play has no usable tracking.
    """
    ball = game.ball[game.ball.play_per_game == play].sort_values("timestamp")
    if ball.empty:
        return None

    ev = game.events[game.events.play_per_game == play].sort_values("timestamp")
    t_start = int(ball.timestamp.iloc[0])
    t_end = int(ball.timestamp.iloc[-1])

    # Trim to the live-ball window when the event stream defines one.
    pitch = ev[ev.ball_eventcode == EV["PITCH"]]
    end_ev = ev[ev.ball_eventcode == EV["END_OF_PLAY"]]
    if not pitch.empty:
        t_start = max(t_start, int(pitch.timestamp.iloc[0]) - PRE_ROLL_MS)
    if not end_ev.empty:
        t_end = min(t_end, int(end_ev.timestamp.iloc[-1]) + POST_ROLL_MS)
    if t_end <= t_start:
        t_end = int(ball.timestamp.iloc[-1])

    b = ball[(ball.timestamp >= t_start) & (ball.timestamp <= t_end)]
    if len(b) < 2:
        b = ball
    # Guard against pathological windows (ball retrieved long after the play).
    if len(b) > max_frames:
        step = int(np.ceil(len(b) / max_frames))
        b = b.iloc[::step]

    times = b.timestamp.to_numpy(int)
    payload = {
        "play": int(play),
        "t0": int(times[0]),
        "times": [int(t - times[0]) for t in times],
        "ball": [[round(float(x), 1), round(float(y), 1), round(float(z), 2)]
                 for x, y, z in zip(b.ball_position_x, b.ball_position_y,
                                    b.ball_position_z)],
    }

    # Event markers, so the animation can flash "CONTACT" / "CAUGHT".
    marks = []
    for _, r in ev.iterrows():
        code = int(r.ball_eventcode)
        if code in (EV["PITCH"], EV["HIT_INTO_PLAY"], EV["ACQUIRED"],
                    EV["THROW"], EV["END_OF_PLAY"], EV["HOME_RUN"],
                    EV["BOUNCE"], EV["DEFLECTION_WALL"]):
            marks.append({"t": int(r.timestamp - times[0]), "code": code,
                          "player_id": int(r.player_id)
                          if np.isfinite(r.player_id) else None})
    payload["events"] = marks

    if include_players and game.player is not None and not game.player.empty:
        pp = game.player[(game.player.play_per_game == play) &
                         (game.player.player_id.isin(DRAW_IDS)) &
                         (game.player.timestamp >= times[0]) &
                         (game.player.timestamp <= times[-1])]
        players = {}
        for pid, trk in pp.groupby("player_id"):
            trk = trk.sort_values("timestamp")
            # Resample onto the ball's clock so the browser animates one series.
            xs = np.interp(times, trk.timestamp.to_numpy(float),
                           trk.field_x.to_numpy(float))
            ys = np.interp(times, trk.timestamp.to_numpy(float),
                           trk.field_y.to_numpy(float))
            players[str(int(pid))] = _round_pairs(xs, ys)
        payload["players"] = players
    return payload


class PlaybackExporter:
    """Builds replay payloads for a whole game."""

    def __init__(self, include_players=True):
        self.include_players = include_players

    def game(self, game, plays=None):
        out = {}
        wanted = plays if plays is not None else sorted(
            game.ball.play_per_game.unique().tolist())
        for p in wanted:
            try:
                pay = export_play(game, int(p),
                                  include_players=self.include_players)
            except Exception:
                pay = None
            if pay:
                out[str(int(p))] = pay
        return out


def export_game_playback(game, plays=None, include_players=True):
    return PlaybackExporter(include_players).game(game, plays)
