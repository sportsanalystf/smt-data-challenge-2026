"""
field.py — field diagrams, spray charts, and play overlays.

REUSE NOTE: the field-drawing approach here is the one proven in the original
project's `plot_webgem.py` (diamond, foul lines, outfield arc drawn in the SMT
coordinate system), generalized into a reusable axes builder so every defensive
and batted-ball graphic shares one visual language.
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Arc

from .. import config
from ..tracking.geometry import HOME, FIRST, SECOND, THIRD
from .theme import apply_theme, title_bar, brand

T = config.THEME


def field_axes(ax, max_depth=420, grass=None):
    """Draw a baseball field in SMT coordinates onto `ax`."""
    grass = grass or T["field_green"]
    ax.set_facecolor(grass)

    pts = np.array([HOME, FIRST, SECOND, THIRD, HOME])
    ax.plot(pts[:, 0], pts[:, 1], color="white", lw=2, zorder=3)
    for base in (FIRST, THIRD):
        v = np.array(base) / np.linalg.norm(base)
        ax.plot([0, v[0] * max_depth * 0.82], [0, v[1] * max_depth * 0.82],
                color="white", lw=1.5, zorder=2)
    ax.add_patch(Arc((0, 0), max_depth * 2, max_depth * 2, theta1=45, theta2=135,
                     color="white", lw=1.5, zorder=2))
    for b in (FIRST, SECOND, THIRD):
        ax.scatter(*b, s=55, color="white", edgecolor="black", zorder=4)
    ax.scatter(*HOME, s=65, marker="D", color="white", edgecolor="black", zorder=4)

    ax.set_aspect("equal")
    ax.set_xlim(-max_depth * 0.78, max_depth * 0.78)
    ax.set_ylim(-30, max_depth * 1.06)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return ax


def spray_chart(batted, out_path=None, title="SPRAY CHART", subtitle="",
                color_by="exit_velo_mph", figsize=(7.6, 6.6)):
    """Where batted balls landed, colored by how hard they were hit.

    `batted` needs land_x / land_y (or hit_distance_ft + bearing) columns.
    """
    apply_theme()
    fig, ax = plt.subplots(figsize=figsize)
    field_axes(ax)

    df = batted.dropna(subset=["land_x", "land_y"])
    if len(df):
        c = df[color_by] if color_by in df.columns else None
        sc = ax.scatter(df.land_x, df.land_y, c=c, cmap="plasma", s=42,
                        edgecolor="black", lw=.4, zorder=6, alpha=.9)
        if c is not None:
            cb = fig.colorbar(sc, ax=ax, fraction=.035, pad=.02)
            cb.set_label(color_by.replace("_", " ").title(), color=T["text"])
            cb.ax.tick_params(colors=T["muted"])

    title_bar(fig, title, subtitle)
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.90])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig


def play_overlay(ball_frames, fielder_frames=None, runner_frames=None,
                 out_path=None, title="THE PLAY", subtitle="",
                 annotation=None, figsize=(7.8, 6.8)):
    """The signature defensive graphic: ball flight plus tracked routes.

    This is what turns a number into a story — the fan sees exactly how far the
    fielder had to run and how long the ball hung.
    """
    apply_theme()
    fig, ax = plt.subplots(figsize=figsize)
    field_axes(ax)

    if ball_frames is not None and len(ball_frames):
        ax.plot(ball_frames.ball_position_x, ball_frames.ball_position_y,
                color="white", lw=1.4, ls="--", alpha=.85, zorder=5,
                label="Ball flight")

    if fielder_frames is not None and len(fielder_frames):
        ax.plot(fielder_frames.field_x, fielder_frames.field_y,
                color=T["accent"], lw=3.2, zorder=6, label="Fielder route")
        ax.scatter(fielder_frames.field_x.iloc[0], fielder_frames.field_y.iloc[0],
                   s=95, color="white", edgecolor=T["accent"], lw=2, zorder=7)
        ax.scatter(fielder_frames.field_x.iloc[-1], fielder_frames.field_y.iloc[-1],
                   s=210, marker="*", color=T["gold"], edgecolor="black", zorder=8)

    if runner_frames is not None and len(runner_frames):
        ax.plot(runner_frames.field_x, runner_frames.field_y,
                color=T["gold"], lw=2.4, zorder=6, label="Runner")

    if annotation:
        ax.text(0.03, 0.97, annotation, transform=ax.transAxes, va="top",
                fontsize=12, color="white", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", fc=T["ink"], ec="white",
                          alpha=.75))

    ax.legend(loc="lower right", facecolor=T["ink"], labelcolor=T["text"],
              framealpha=.6, fontsize=10)
    title_bar(fig, title, subtitle)
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.90])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig
