"""
c10_animation.py — COMPONENT 10: play animation.

Mirrors R/R10_animation.R (which uses gganimate + sportyR).

Renders a play as an animated GIF: the ball and all tracked players moving on a
field diagram, with the ball's marker growing as it rises so a fly ball reads as
airborne rather than as a dot sliding across a map. A second renderer animates
the pitch sequence of an at-bat from the catcher's angle, which is what turns a
strikeout — where nothing happens on the field — into something watchable.

Output is a file on disk (GIF or MP4), so it embeds directly in Quarto, a Word
paper, or a scoreboard playlist.
"""
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Arc, Rectangle

from smtstory import config
from smtstory.tracking.geometry import HOME, FIRST, SECOND, THIRD

T = config.THEME

TYPE_COLOR = {"defense": "#ffd54a", "offense": "#ff7a90", "battery": "#ffffff"}
POS_LABEL = config.POS_ABBR


def _player_type(pid):
    if pid in (1, 2):
        return "battery"
    if pid <= 9:
        return "defense"
    return "offense"


def draw_field(ax, max_depth=420):
    """A MiLB-proportioned field in SMT coordinates."""
    ax.set_facecolor(T["field_green"])
    pts = np.array([HOME, FIRST, SECOND, THIRD, HOME])
    ax.plot(pts[:, 0], pts[:, 1], color="white", lw=2, zorder=3)
    for base in (FIRST, THIRD):
        v = np.array(base) / np.linalg.norm(base)
        ax.plot([0, v[0] * max_depth * 0.82], [0, v[1] * max_depth * 0.82],
                color="white", lw=1.4, zorder=2)
    ax.add_patch(Arc((0, 0), max_depth * 2, max_depth * 2, theta1=45,
                     theta2=135, color="white", lw=1.4, zorder=2))
    for b in (FIRST, SECOND, THIRD):
        ax.scatter(*b, s=48, color="white", edgecolor="black", zorder=4)
    ax.scatter(*HOME, s=58, marker="D", color="white", edgecolor="black", zorder=4)
    ax.add_patch(plt.Circle((0, 60.5), 9, color="#8a5a2b", alpha=.75, zorder=1))
    ax.set_aspect("equal")
    ax.set_xlim(-max_depth * 0.78, max_depth * 0.78)
    ax.set_ylim(-30, max_depth * 1.02)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return ax


def animate_play(game, play, out_path, fps=12, title=None, subtitle=None,
                 trail=True, max_frames=140):
    """Render one play as an animated GIF.

    Parameters
    ----------
    game : GameData      loaded with player tracking
    play : int           play_per_game
    out_path : str       .gif destination
    """
    ball = game.ball[game.ball.play_per_game == play].sort_values("timestamp")
    if ball.empty:
        raise ValueError(f"no ball tracking for play {play}")

    ev = game.events[game.events.play_per_game == play].sort_values("timestamp")
    pitch = ev[ev.ball_eventcode == config.EVENT["PITCH"]]
    t0 = int(pitch.timestamp.iloc[0]) if len(pitch) else int(ball.timestamp.iloc[0])
    end = ev[ev.ball_eventcode == config.EVENT["END_OF_PLAY"]]
    t1 = int(end.timestamp.iloc[-1]) if len(end) else int(ball.timestamp.iloc[-1])

    b = ball[(ball.timestamp >= t0) & (ball.timestamp <= t1)]
    if len(b) < 2:
        b = ball
    times = b.timestamp.to_numpy(int)
    if len(times) > max_frames:
        step = int(np.ceil(len(times) / max_frames))
        b = b.iloc[::step]
        times = b.timestamp.to_numpy(int)

    bx = b.ball_position_x.to_numpy(float)
    by = b.ball_position_y.to_numpy(float)
    bz = b.ball_position_z.to_numpy(float)

    # Resample each player onto the ball's clock.
    tracks = {}
    pp = game.player[(game.player.play_per_game == play) &
                     (game.player.player_id <= 13)]
    for pid, trk in pp.groupby("player_id"):
        trk = trk.sort_values("timestamp")
        tracks[int(pid)] = (
            np.interp(times, trk.timestamp.to_numpy(float),
                      trk.field_x.to_numpy(float)),
            np.interp(times, trk.timestamp.to_numpy(float),
                      trk.field_y.to_numpy(float)))

    # Event captions keyed to frame index.
    captions = {}
    labels = {1: "PITCH", 4: "CONTACT", 2: "FIELDED", 3: "THROW",
              11: "HOME RUN", 10: "OFF THE WALL", 16: "BOUNCE", 5: "END OF PLAY"}
    for _, r in ev.iterrows():
        lab = labels.get(int(r.ball_eventcode))
        if lab is None:
            continue
        idx = int(np.argmin(np.abs(times - int(r.timestamp))))
        captions[idx] = lab

    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    fig.patch.set_facecolor(T["ink"])
    # Leave room for the title band; fill the rest with the field.
    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.02)
    draw_field(ax)

    if title:
        # Title and subtitle live on the FIGURE, not the axes, so an equal-aspect
        # field cannot push them into each other.
        fig.text(0.5, 0.965, title, ha="center", va="top", color="white",
                 fontweight="bold", fontsize=14)
    if subtitle:
        fig.text(0.5, 0.925, subtitle, ha="center", va="top",
                 color=T["muted"], fontsize=9)

    trail_line, = ax.plot([], [], color="white", lw=1.3, ls="--", alpha=.6, zorder=5)
    ball_dot = ax.scatter([], [], s=60, color="white", edgecolor=T["accent"],
                          lw=1.4, zorder=9)
    player_dots, player_texts = {}, {}
    for pid in tracks:
        c = TYPE_COLOR[_player_type(pid)]
        player_dots[pid] = ax.scatter([], [], s=70, color=c, edgecolor="black",
                                      lw=.8, zorder=7)
        player_texts[pid] = ax.text(0, 0, POS_LABEL.get(pid, str(pid)),
                                    color=c, fontsize=7.5, fontweight="bold",
                                    ha="center", va="bottom", zorder=8)
    caption = ax.text(0.5, 0.955, "", transform=ax.transAxes, ha="center",
                      color=T["gold"], fontsize=15, fontweight="bold", zorder=10)
    clock = ax.text(0.02, 0.02, "", transform=ax.transAxes, color=T["muted"],
                    fontsize=9, zorder=10)

    def update(i):
        if trail:
            trail_line.set_data(bx[:i + 1], by[:i + 1])
        ball_dot.set_offsets([[bx[i], by[i]]])
        # Marker area grows with height so a fly ball reads as airborne, but the
        # growth is capped — an uncapped scale turns a towering popup into a
        # circle that swallows the infield.
        ball_dot.set_sizes([45 + 9 * float(np.clip(bz[i], 0, 14))])
        for pid, (xs, ys) in tracks.items():
            player_dots[pid].set_offsets([[xs[i], ys[i]]])
            player_texts[pid].set_position((xs[i], ys[i] + 7))
        # Hold a caption briefly after its event.
        text = ""
        for idx in sorted(captions):
            if idx <= i <= idx + 5:
                text = captions[idx]
        caption.set_text(text)
        clock.set_text(f"{(times[i]-times[0])/1000:.1f}s")
        return ()

    anim = FuncAnimation(fig, update, frames=len(times), blit=False)
    anim.save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return out_path


def animate_pitch_sequence(pitch_rows, zone, out_path, fps=2, title=None):
    """Animate an at-bat's pitches arriving one by one, catcher's view.

    `pitch_rows` is the DataFrame from c03.pitch_sequence (needs plate_x,
    plate_z, velo_mph and optionally polyline).
    """
    df = pitch_rows.dropna(subset=["plate_x", "plate_z"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("no pitches with plate locations")

    colors = ["#ffc72c", "#2f80ed", "#22c55e", "#c8102e", "#a855f7",
              "#f2994a", "#8fd4ff", "#ff9ab0"]

    fig, ax = plt.subplots(figsize=(5.0, 5.6))
    fig.patch.set_facecolor(T["ink"])
    ax.set_facecolor(T["panel"])
    hw = zone["half_width"] if isinstance(zone, dict) else zone.half_width
    zb = zone["bottom"] if isinstance(zone, dict) else zone.bottom
    zt = zone["top"] if isinstance(zone, dict) else zone.top
    ax.add_patch(Rectangle((-hw, zb), 2 * hw, zt - zb, fill=False,
                           edgecolor="white", lw=2.2, zorder=4))
    ax.set_xlim(-1.9, 1.9)
    ax.set_ylim(0.2, 4.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title or "PITCH SEQUENCE", color="white", fontweight="bold",
                 fontsize=12)
    info = ax.text(0.5, -0.06, "", transform=ax.transAxes, ha="center",
                   color=T["muted"], fontsize=10)

    dots = ax.scatter([], [], s=[], c=[], zorder=6, edgecolor="black", lw=1.2)

    def update(i):
        sub = df.iloc[:i + 1]
        ax.collections[-1].remove() if False else None
        dots.set_offsets(sub[["plate_x", "plate_z"]].to_numpy())
        dots.set_sizes([120] * len(sub))
        dots.set_color([colors[k % len(colors)] for k in range(len(sub))])
        r = df.iloc[i]
        bits = [f"Pitch {i+1}"]
        if pd.notna(r.get("velo_mph")):
            bits.append(f"{r['velo_mph']:.0f} mph")
        if "break_vertical_in" in df.columns and pd.notna(r.get("break_vertical_in")):
            bits.append(f"IVB {r['break_vertical_in']:+.0f} in")
        if "tunnel_ratio" in df.columns and pd.notna(r.get("tunnel_ratio")):
            bits.append(f"tunnel {r['tunnel_ratio']:.1f}x")
        info.set_text("   ·   ".join(bits))
        return ()

    anim = FuncAnimation(fig, update, frames=len(df), blit=False)
    anim.save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return out_path


def animation_index(paths):
    """Small table listing the rendered animations (for Quarto)."""
    return pd.DataFrame({
        "animation": [os.path.basename(p) for p in paths],
        "size_kb": [round(os.path.getsize(p) / 1024, 1) for p in paths],
        "path": paths,
    })
