"""
tunneling.py — pitch trajectories, tunneling, and "how nasty was that pitch?"

WHY THIS EXISTS
---------------
When an at-bat ends in a strikeout there is nothing to see on the field, so the
scoreboard has nothing to show. But the most interesting question in baseball
just got answered: *was that unhittable pitching, or a bad swing?* This module
answers it from the ball tracking.

THE PHYSICS
-----------
A pitch is tracked at 20 Hz, giving ~10-12 points between release (y ≈ 55 ft)
and the plate (y = 0). Rather than work with those raw samples, we fit a smooth
quadratic to x(y) and z(y). A quadratic is exactly right here: under constant
acceleration (gravity plus a roughly constant aerodynamic force) position is
quadratic in flight distance. Fitting lets us evaluate the trajectory at ANY
distance from the plate, which is what tunneling requires.

THE TUNNEL
----------
A hitter must decide to swing roughly 175 ms before the ball arrives — about
**23.8 feet** in front of the plate, the "commit point". Two pitches that are
close together at the commit point but far apart at the plate are, from the
hitter's chair, indistinguishable until it is too late. That is a tunnel.

    tunnel_distance  = separation of two pitches at the commit point (inches)
    plate_distance   = separation of the same two pitches at the plate (inches)
    tunnel_ratio     = plate_distance / tunnel_distance

A high ratio is deception: same tunnel, different destination.

LATE BREAK
----------
We extrapolate the trajectory linearly from the release using its initial
direction, then measure how far the real pitch ends up from that straight line
at the plate. That deviation is the movement the hitter could not have
accounted for early — "late life".

EXTENSION AND EFFECTIVE VELOCITY
--------------------------------
Release distance is measured directly (the rubber is 60.5 ft from the plate), so
extension = 60.5 − release_y. A pitcher who releases a foot closer to the plate
gives the hitter less time, and the ball plays faster than the gun says.
Effective velocity rescales the measured speed by the distance actually
travelled relative to league-average extension.
"""
import numpy as np
import pandas as pd

from .. import config

# A hitter commits roughly 175 ms out; at ~135 ft/s that is ~23.8 feet.
COMMIT_POINT_FT = 23.8
PLATE_Y = 0.0
RUBBER_TO_PLATE_FT = 60.5
FT_TO_IN = 12.0


def fit_trajectory(ball_frames, t_pitch, min_frames=5):
    """Fit x(y) and z(y) as quadratics over the pitch's flight.

    Returns a dict of coefficients and endpoints, or None if the pitch cannot
    be fit (too few tracked frames).
    """
    b = ball_frames[ball_frames.timestamp >= t_pitch].sort_values("timestamp")
    if len(b) < min_frames:
        return None
    y = b.ball_position_y.to_numpy(float)
    x = b.ball_position_x.to_numpy(float)
    z = b.ball_position_z.to_numpy(float)

    # Keep the portion travelling toward the plate, from release to just past it.
    keep = y <= y.max()
    y, x, z = y[keep], x[keep], z[keep]
    if len(y) < min_frames or (y.max() - y.min()) < 20:
        return None

    try:
        cx = np.polyfit(y, x, 2)
        cz = np.polyfit(y, z, 2)
    except Exception:
        return None

    release_y = float(y.max())
    return {
        "cx": cx, "cz": cz,
        "release_y": release_y,
        "release_x": float(np.polyval(cx, release_y)),
        "release_z": float(np.polyval(cz, release_y)),
        "extension_ft": float(RUBBER_TO_PLATE_FT - release_y),
        "plate_x": float(np.polyval(cx, PLATE_Y)),
        "plate_z": float(np.polyval(cz, PLATE_Y)),
        "n_frames": int(len(y)),
    }


def at_distance(traj, y):
    """(x, z) of the fitted pitch at a given distance from the plate."""
    return (float(np.polyval(traj["cx"], y)), float(np.polyval(traj["cz"], y)))


GRAVITY_FT_S2 = 32.174
# A pitch loses roughly 8% of its speed on the way in; use the average.
AVG_SPEED_FACTOR = 0.93


def flight_time_s(release_y, velo_mph):
    """Approximate time from release to the plate."""
    if velo_mph is None or not np.isfinite(velo_mph) or velo_mph <= 0:
        return np.nan
    v_fts = (velo_mph / config.FT_S_TO_MPH) * AVG_SPEED_FACTOR
    return float(release_y / v_fts)


def late_break_in(traj, velo_mph=None):
    """Pitch movement at the plate, in inches.

    Returns (horizontal_break, induced_vertical_break, gravity_drop).

    The baseline is the straight line a hitter would naively extrapolate from
    the ball's initial direction at release. Deviation from that line has two
    causes, and only one of them is interesting:

      * **gravity**, which pulls every pitch down by 0.5*g*t^2 — around 39
        inches on a 90 mph fastball. Reporting this as "movement" would make
        every pitch look filthy and tell a fan nothing.
      * **aerodynamic force** (spin), which is what actually separates a
        four-seamer from a curveball.

    So we subtract the gravity component to get INDUCED vertical break: positive
    means the ball resisted gravity (carry/"rise"), negative means it fell more
    than gravity alone (a breaking ball).
    """
    ry = traj["release_y"]
    # Derivative of the quadratic at release gives the initial direction.
    dx_dy = 2 * traj["cx"][0] * ry + traj["cx"][1]
    dz_dy = 2 * traj["cz"][0] * ry + traj["cz"][1]
    dy = PLATE_Y - ry
    lin_x = traj["release_x"] + dx_dy * dy
    lin_z = traj["release_z"] + dz_dy * dy

    horiz_in = float((traj["plate_x"] - lin_x) * FT_TO_IN)
    raw_vert_in = float((traj["plate_z"] - lin_z) * FT_TO_IN)

    t = flight_time_s(ry, velo_mph)
    if np.isfinite(t):
        gravity_drop_in = float(0.5 * GRAVITY_FT_S2 * t * t * FT_TO_IN)
    else:
        gravity_drop_in = np.nan

    induced_in = (raw_vert_in + gravity_drop_in
                  if np.isfinite(gravity_drop_in) else np.nan)
    return horiz_in, induced_in, gravity_drop_in


def effective_velocity(velo_mph, extension_ft, league_extension_ft):
    """Speed as the hitter experiences it, adjusted for release extension.

    Travel distance is (60.5 − extension). Releasing closer shortens the flight
    and buys less reaction time, so the ball plays faster than the gun reading.
    """
    if not np.isfinite(velo_mph) or not np.isfinite(extension_ft):
        return np.nan
    d_actual = max(1.0, RUBBER_TO_PLATE_FT - extension_ft)
    d_league = max(1.0, RUBBER_TO_PLATE_FT - league_extension_ft)
    return float(velo_mph * d_league / d_actual)


def tunnel_pair(traj_a, traj_b, commit=COMMIT_POINT_FT):
    """Tunnel metrics between two consecutive pitches."""
    ax, az = at_distance(traj_a, commit)
    bx, bz = at_distance(traj_b, commit)
    tunnel = float(np.hypot(ax - bx, az - bz) * FT_TO_IN)
    plate = float(np.hypot(traj_a["plate_x"] - traj_b["plate_x"],
                           traj_a["plate_z"] - traj_b["plate_z"]) * FT_TO_IN)
    ratio = plate / tunnel if tunnel > 1e-6 else np.nan
    return {"tunnel_distance_in": tunnel, "plate_distance_in": plate,
            "tunnel_ratio": ratio}


class PitchSequenceAnalyzer:
    """Builds the pitch-by-pitch story of an at-bat."""

    def __init__(self, zone_model=None, league_extension_ft=5.5,
                 league_velo_mph=88.0):
        self.zone = zone_model
        self.league_extension = league_extension_ft
        self.league_velo = league_velo_mph

    # ------------------------------------------------------------ per pitch
    def analyze_pitch(self, ball_frames, t_pitch, velo_mph=None):
        traj = fit_trajectory(ball_frames, t_pitch)
        if traj is None:
            return None
        bx_in, bz_in, grav_in = late_break_in(traj, velo_mph)
        total = (float(np.hypot(bx_in, bz_in)) if np.isfinite(bz_in)
                 else float(abs(bx_in)))
        out = {
            "release_x": traj["release_x"], "release_z": traj["release_z"],
            "release_y": traj["release_y"],
            "extension_ft": traj["extension_ft"],
            "plate_x": traj["plate_x"], "plate_z": traj["plate_z"],
            "break_horizontal_in": bx_in,
            "break_vertical_in": bz_in,          # induced (gravity removed)
            "gravity_drop_in": grav_in,
            "total_break_in": total,
            "flight_time_s": flight_time_s(traj["release_y"], velo_mph),
            "velo_mph": velo_mph,
            "effective_velo_mph": effective_velocity(
                velo_mph if velo_mph is not None else np.nan,
                traj["extension_ft"], self.league_extension),
            "_traj": traj,
        }
        if self.zone is not None:
            out["in_zone"] = bool(self.zone.in_zone(traj["plate_x"],
                                                    traj["plate_z"]))
            out["zone_edge_distance_in"] = self._edge_distance(
                traj["plate_x"], traj["plate_z"])
        return out

    def _edge_distance(self, x, z):
        """Inches from the nearest edge of the strike zone.

        Negative means inside the zone (distance to the nearest edge from
        within); positive means outside. Pitches near zero are on the black.
        """
        if self.zone is None:
            return np.nan
        hw = self.zone.half_width
        dx = abs(x) - hw
        dz = max(self.zone.bottom - z, z - self.zone.top)
        outside = max(dx, dz)
        return float(outside * FT_TO_IN)

    # ---------------------------------------------------------- per at-bat
    def analyze_at_bat(self, ball, events, plays, velos=None):
        """Analyze every pitch of an at-bat plus the tunnels between them."""
        EV = config.EVENT
        pitches = []
        for p in sorted(plays):
            e = events[(events.play_per_game == p) &
                       (events.ball_eventcode == EV["PITCH"])]
            if e.empty:
                continue
            t = int(e.timestamp.iloc[0])
            b = ball[ball.play_per_game == p]
            velo = None
            if velos is not None:
                v = velos.get(p)
                velo = float(v) if v is not None and np.isfinite(v) else None
            info = self.analyze_pitch(b, t, velo)
            if info is None:
                continue
            info["play"] = int(p)
            info["pitch_number"] = len(pitches) + 1
            pitches.append(info)

        # Tunnels between consecutive pitches.
        for i in range(1, len(pitches)):
            tp = tunnel_pair(pitches[i - 1]["_traj"], pitches[i]["_traj"])
            pitches[i].update(tp)

        for p in pitches:
            p["nastiness"] = self.nastiness(p)
        return pitches

    # --------------------------------------------------------- nastiness
    def nastiness(self, pitch):
        """0-100: how hard was this pitch to hit?

        Four ingredients, each scaled to 0-1 and averaged with weights:
          velocity        raw speed relative to the league
          late break      movement the hitter could not read early
          location        pitches on or just off the edges are hardest
          deception       tunnel ratio against the previous pitch
        """
        parts, weights = [], []

        v = pitch.get("effective_velo_mph") or pitch.get("velo_mph")
        if v is not None and np.isfinite(v):
            parts.append(np.clip((v - 84.0) / 16.0, 0, 1))
            weights.append(2.0)

        br = pitch.get("total_break_in")
        if br is not None and np.isfinite(br):
            parts.append(np.clip(br / 18.0, 0, 1))
            weights.append(2.0)

        ed = pitch.get("zone_edge_distance_in")
        if ed is not None and np.isfinite(ed):
            # Best (hardest to hit) right on the edge: |edge distance| small.
            # Middle-middle and way-off-the-plate are both easy to take/hit.
            parts.append(np.clip(1.0 - abs(ed) / 9.0, 0, 1))
            weights.append(1.6)

        tr = pitch.get("tunnel_ratio")
        if tr is not None and np.isfinite(tr):
            parts.append(np.clip((tr - 1.0) / 5.0, 0, 1))
            weights.append(1.4)

        if not parts:
            return np.nan
        return float(100.0 * np.average(parts, weights=weights))

    # ------------------------------------------------------- the verdict
    def strikeout_verdict(self, pitches):
        """Was the strikeout earned by the pitcher, or given away by the hitter?

        Judged on the PUTAWAY pitch: a nasty pitch on the edge with late movement
        and a good tunnel is pitching; a straight pitch over the middle that the
        hitter missed is not.
        """
        if not pitches:
            return None
        put = pitches[-1]
        nasty = put.get("nastiness")
        edge = put.get("zone_edge_distance_in")
        brk = put.get("total_break_in")
        ratio = put.get("tunnel_ratio")

        if nasty is None or not np.isfinite(nasty):
            return None

        if nasty >= 62:
            verdict = "NASTY PITCH"
            why = "the pitcher earned this one"
        elif nasty <= 40:
            verdict = "HITTER MISSED IT"
            why = "that was a pitch to handle"
        else:
            verdict = "WELL EXECUTED"
            why = "good pitch, tough at-bat"

        # Only cite evidence that supports the verdict, so the sentence cannot
        # contradict itself (e.g. praising movement while calling it hittable).
        bits = []
        if verdict == "HITTER MISSED IT":
            if edge is not None and np.isfinite(edge) and edge < -4:
                bits.append("over the heart of the plate")
            elif brk is not None and np.isfinite(brk) and brk < 8:
                bits.append("with little movement")
        else:
            if brk is not None and np.isfinite(brk) and brk >= 6:
                bits.append(f"{brk:.0f} inches of late movement")
            if edge is not None and np.isfinite(edge) and abs(edge) <= 4:
                bits.append("right on the black")
            if ratio is not None and np.isfinite(ratio) and ratio >= 2.0:
                bits.append(f"tunneled {ratio:.1f}x off the previous pitch")

        return {
            "verdict": verdict,
            "why": why,
            "nastiness": float(nasty),
            "detail": bits,
            "putaway_pitch": {k: v for k, v in put.items() if k != "_traj"},
            "narrative": self._verdict_line(verdict, put, bits),
        }

    @staticmethod
    def _verdict_line(verdict, put, bits):
        v = put.get("velo_mph")
        head = f"{v:.0f} mph" if v and np.isfinite(v) else "That pitch"
        if verdict == "NASTY PITCH":
            tail = ", ".join(bits) if bits else "perfectly located"
            return f"Unhittable — {head} with {tail}."
        if verdict == "HITTER MISSED IT":
            tail = f" {bits[0]}" if bits else ""
            return (f"{head}{tail} — that was a pitch to handle, and the hitter "
                    f"missed it.")
        tail = ", ".join(bits) if bits else "well located"
        return f"{head}, {tail}."


def trajectory_polyline(traj, n=24):
    """Sample the fitted pitch for drawing: list of (y, x, z) from release to plate."""
    ys = np.linspace(traj["release_y"], PLATE_Y, n)
    xs = np.polyval(traj["cx"], ys)
    zs = np.polyval(traj["cz"], ys)
    return [[round(float(y), 2), round(float(x), 3), round(float(z), 3)]
            for y, x, z in zip(ys, xs, zs)]
