"""
plot_webgem.py
--------------
Signature scoreboard graphic: overlays a fielder's tracked route and the ball
trajectory on a baseball field diagram for one catch, annotated with the
Robbery Meter catch probability. Demonstrates the "on the big screen" fan visual.

Run: python plot_webgem.py <data_root> <out_dir>
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc
import smt_utils as U

DATA, OUT = sys.argv[1], sys.argv[2]
FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)
GREEN, ACCENT, DIRT = "#0b6b3a", "#c8102e", "#b5793a"


def draw_field(ax):
    # infield diamond
    pts = np.array([U.HOME, U.FIRST, U.SECOND, U.THIRD, U.HOME])
    ax.plot(pts[:, 0], pts[:, 1], color="white", lw=2, zorder=3)
    # foul lines out to ~330 ft
    for base in (U.FIRST, U.THIRD):
        v = base / np.linalg.norm(base)
        ax.plot([0, v[0] * 330], [0, v[1] * 330], color="white", lw=1.5, zorder=2)
    # outfield arc
    arc = Arc((0, 0), 800, 800, theta1=45, theta2=135, color="white", lw=1.5, zorder=2)
    ax.add_patch(arc)
    for b, name in [(U.FIRST, "1B"), (U.SECOND, "2B"), (U.THIRD, "3B")]:
        ax.scatter(*b, s=60, color="white", edgecolor="k", zorder=4)
    ax.scatter(*U.HOME, s=70, marker="D", color="white", edgecolor="k", zorder=4)
    ax.set_facecolor(GREEN)
    ax.set_aspect("equal")
    ax.set_xlim(-300, 300); ax.set_ylim(-30, 430)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def plot_play(rel, play, fielder_id, prob, route, hang, player, out_png, title):
    ev = pd.read_csv(os.path.join(DATA, "ball-events", rel, "ball_events.csv"))
    bp = pd.read_csv(os.path.join(DATA, "ball-positions", rel, "ball-positions.csv"))
    pp = pd.read_csv(os.path.join(DATA, "player-positions", rel, "player-positions.csv"))
    for d in (ev, bp, pp):
        d.dropna(subset=["play_per_game"], inplace=True)
        d["play_per_game"] = d.play_per_game.astype(int)
    t_hit = int(ev[(ev.play_per_game == play) & (ev.ball_eventcode == 4)].timestamp.iloc[0])
    ftrk = pp[(pp.play_per_game == play) & (pp.player_id == fielder_id) &
              (pp.timestamp >= t_hit)].sort_values("timestamp")
    ball = bp[(bp.play_per_game == play) & (bp.timestamp >= t_hit)].sort_values("timestamp")

    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    draw_field(ax)
    # ball path
    ax.plot(ball.ball_position_x, ball.ball_position_y, color="white", lw=1.2,
            ls="--", alpha=.7, zorder=5)
    # fielder route
    ax.plot(ftrk.field_x, ftrk.field_y, color=ACCENT, lw=3, zorder=6)
    ax.scatter(ftrk.field_x.iloc[0], ftrk.field_y.iloc[0], s=90, color="white",
               edgecolor=ACCENT, lw=2, zorder=7, label="Fielder at contact")
    ax.scatter(ftrk.field_x.iloc[-1], ftrk.field_y.iloc[-1], s=170, marker="*",
               color="gold", edgecolor="k", zorder=8, label="Catch")
    ax.set_title(title, color="white", fontweight="bold", fontsize=13, pad=10)
    txt = (f"Catch probability: {prob*100:.0f}%\n"
           f"Route: {route:.0f} ft   Hang: {hang:.1f} s\n"
           f"Robbery Score: {(1-prob)*100:.0f}/100")
    ax.text(-290, 400, txt, color="white", fontsize=11, va="top",
            bbox=dict(boxstyle="round", fc="black", alpha=.55, ec="white"))
    ax.text(-290, 20, f"{player}", color="white", fontsize=10, alpha=.9)
    ax.legend(loc="lower right", frameon=True, facecolor="black", labelcolor="white",
              framealpha=.5, fontsize=9)
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    print("saved", out_png)


# Read the scored web gems and pick the hero play
gems = pd.read_csv(os.path.join(OUT, "leaderboards", "07b_web_gems_unlikeliest_catches.csv"))
g = gems.iloc[0]
# game_string y{yr}_d{day}_{away}_{home} -> dir home/away/yr/day
_, day, away, home = g.game_string.split("_")
rel = f"{home}/{away}/y1/{day}"
plot_play(rel, int(g.play), int({"left_fielder": 7, "center_fielder": 8,
          "right_fielder": 9}[g.pos]), float(g.catch_prob), float(g.route_ft),
          float(g.hang_s), g.player,
          os.path.join(FIG, "fig_webgem_hero.png"),
          "WEB GEM OF THE SEASON — The Robbery Meter")
