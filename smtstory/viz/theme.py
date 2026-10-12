"""
theme.py — the broadcast look.

Scoreboard graphics are read from 300 feet away, often in daylight, in about
seven seconds. That drives every choice here: dark panels for contrast, one
enormous number per graphic, heavy weights, minimal chrome, and no thin gridlines
or small tick labels that vanish at distance.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .. import config

T = config.THEME


def apply_theme():
    plt.rcParams.update({
        "figure.facecolor": T["ink"],
        "axes.facecolor": T["panel"],
        "savefig.facecolor": T["ink"],
        "text.color": T["text"],
        "axes.labelcolor": T["text"],
        "xtick.color": T["muted"],
        "ytick.color": T["muted"],
        "axes.edgecolor": T["panel_light"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 13,
        "font.family": "DejaVu Sans",
        "axes.titlesize": 18,
        "axes.titleweight": "bold",
        "figure.dpi": 140,
        "grid.color": T["panel_light"],
        "grid.alpha": 0.6,
        "legend.frameon": False,
    })


def big_number(ax, value, unit="", label="", color=None, value_size=76):
    """The signature scoreboard element: one huge number."""
    color = color or T["gold"]
    ax.axis("off")
    ax.text(0.5, 0.56, str(value), ha="center", va="center",
            fontsize=value_size, fontweight="bold", color=color,
            transform=ax.transAxes)
    if unit:
        ax.text(0.5, 0.30, unit, ha="center", va="center", fontsize=20,
                color=T["muted"], fontweight="bold", transform=ax.transAxes)
    if label:
        ax.text(0.5, 0.88, label, ha="center", va="center", fontsize=17,
                color=T["text"], fontweight="bold", transform=ax.transAxes)


def title_bar(fig, title, subtitle=""):
    fig.text(0.02, 0.965, title, fontsize=21, fontweight="bold", color=T["text"],
             va="top")
    if subtitle:
        fig.text(0.02, 0.915, subtitle, fontsize=13, color=T["muted"], va="top")


def brand(fig, text="SMT DATA CHALLENGE 2026  ·  ON THE BIG SCREEN!"):
    fig.text(0.98, 0.015, text, fontsize=9, color=T["muted"], ha="right")


def team_color(is_home):
    return T["home"] if is_home else T["away"]
