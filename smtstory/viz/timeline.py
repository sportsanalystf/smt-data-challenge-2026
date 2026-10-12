"""
timeline.py — game-flow graphics.

The win probability chart is the single most valuable storytelling graphic in
baseball: it shows, in one line, where a game was won and lost. These render it
in a form that survives being displayed on a scoreboard — thick lines, few
labels, and the turning point called out explicitly rather than left for the
viewer to find.
"""
import numpy as np
import matplotlib.pyplot as plt

from .. import config
from .theme import apply_theme, title_bar, brand

T = config.THEME


def _x_axis(game):
    """Continuous play index with inning boundaries for gridlines."""
    x = np.arange(len(game))
    bounds, labels = [], []
    prev = None
    for i, (inn, half) in enumerate(zip(game.inning, game.half_inning)):
        key = (inn, half)
        if key != prev:
            if half == "Top":
                bounds.append(i)
                labels.append(str(int(inn)))
            prev = key
    return x, bounds, labels


def win_probability_chart(game, home_team="HOME", away_team="AWAY",
                          out_path=None, annotate_top=True, figsize=(11, 5.2)):
    """The game-flow chart: home team's win probability across the game."""
    apply_theme()
    g = game.reset_index(drop=True)

    # Convert "batting team win probability" to a single home-team series.
    wp_home = np.where(g.half_inning.eq("Bottom"), g.wp_after, 1.0 - g.wp_after)
    x, bounds, labels = _x_axis(g)

    fig, ax = plt.subplots(figsize=figsize)
    ax.axhline(0.5, color=T["muted"], lw=1, ls="--", alpha=.5)
    ax.fill_between(x, 0.5, wp_home, where=(wp_home >= 0.5),
                    color=T["home"], alpha=.35, interpolate=True)
    ax.fill_between(x, 0.5, wp_home, where=(wp_home < 0.5),
                    color=T["away"], alpha=.35, interpolate=True)
    ax.plot(x, wp_home, color=T["text"], lw=2.6)

    for b in bounds:
        ax.axvline(b, color=T["panel_light"], lw=1, alpha=.8)

    if annotate_top and "wpa" in g.columns and g.wpa.notna().any():
        i = int(g.wpa.abs().idxmax())
        ax.scatter([i], [wp_home[i]], s=190, color=T["gold"], zorder=6,
                   edgecolor=T["ink"], lw=1.5, marker="*")
        ax.annotate(f"TURNING POINT\n{g.wpa.iloc[i]*100:+.0f}% win prob",
                    xy=(i, wp_home[i]),
                    xytext=(i + max(3, len(g) * 0.04),
                            min(0.92, wp_home[i] + 0.22)),
                    color=T["gold"], fontsize=11, fontweight="bold",
                    arrowprops=dict(color=T["gold"], arrowstyle="->", lw=1.6))

    ax.set_ylim(0, 1)
    ax.set_xlim(0, max(1, len(g) - 1))
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xticks(bounds)
    ax.set_xticklabels(labels)
    ax.set_xlabel("INNING", fontweight="bold", color=T["muted"])
    ax.grid(axis="y", alpha=.25)
    ax.text(0.01, 0.96, f"{home_team} WINNING", transform=ax.transAxes,
            color=T["home"], fontweight="bold", fontsize=12, va="top")
    ax.text(0.01, 0.04, f"{away_team} WINNING", transform=ax.transAxes,
            color=T["away"], fontweight="bold", fontsize=12, va="bottom")

    title_bar(fig, "WIN PROBABILITY", f"{away_team} at {home_team}")
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.90])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig


def leverage_timeline(game, out_path=None, figsize=(11, 3.6)):
    """Where the pressure was."""
    apply_theme()
    g = game.reset_index(drop=True)
    x, bounds, labels = _x_axis(g)
    li = g.leverage_index.to_numpy(float)

    fig, ax = plt.subplots(figsize=figsize)
    colors = [T["accent"] if v >= 2.0 else T["panel_light"] for v in li]
    ax.bar(x, li, color=colors, width=1.0)
    ax.axhline(1.0, color=T["muted"], ls="--", lw=1)
    ax.text(len(g) * 0.995, 1.06, "average pressure", ha="right",
            color=T["muted"], fontsize=10)
    ax.set_xticks(bounds)
    ax.set_xticklabels(labels)
    ax.set_xlabel("INNING", fontweight="bold", color=T["muted"])
    ax.set_ylabel("LEVERAGE")
    ax.set_xlim(-0.5, len(g) - 0.5)
    title_bar(fig, "LEVERAGE INDEX", "How much each moment mattered")
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.86])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig


def momentum_timeline(game, window=6, out_path=None, figsize=(11, 3.6)):
    """Rolling momentum: which side has been winning the last few innings."""
    apply_theme()
    g = game.reset_index(drop=True)
    # Signed WPA in favor of the home team.
    home_wpa = np.where(g.half_inning.eq("Bottom"), g.wpa, -g.wpa)
    mom = np.convolve(home_wpa, np.ones(window) / window, mode="same")
    x, bounds, labels = _x_axis(g)

    fig, ax = plt.subplots(figsize=figsize)
    ax.fill_between(x, 0, mom, where=(mom >= 0), color=T["home"], alpha=.6,
                    interpolate=True)
    ax.fill_between(x, 0, mom, where=(mom < 0), color=T["away"], alpha=.6,
                    interpolate=True)
    ax.axhline(0, color=T["muted"], lw=1)
    ax.set_xticks(bounds)
    ax.set_xticklabels(labels)
    ax.set_xlabel("INNING", fontweight="bold", color=T["muted"])
    ax.set_ylabel("MOMENTUM")
    ax.set_xlim(0, max(1, len(g) - 1))
    title_bar(fig, "MOMENTUM METER", f"Rolling {window}-play win-probability swing")
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.86])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig
