"""
cards_render.py — turning a CardPayload into a scoreboard graphic.

One renderer handles every card, driven by the card's `viz_hint`. That is the
payoff of the payload design: adding a new card gets a graphic for free.
"""
import numpy as np
import matplotlib.pyplot as plt

from .. import config
from .theme import apply_theme, big_number, brand

T = config.THEME

CATEGORY_COLOR = {
    "speed": T["good"], "power": T["gold"], "pitching": T["home"],
    "defense": T["accent"], "fan": "#a855f7", "story": T["text"],
    "general": T["muted"],
}


def _gauge(ax, frac, color):
    """A semicircular gauge — reads instantly at distance."""
    frac = float(np.clip(frac, 0, 1))
    theta = np.linspace(np.pi, 0, 200)
    ax.plot(np.cos(theta), np.sin(theta), color=T["panel_light"], lw=13,
            solid_capstyle="round")
    k = max(2, int(200 * frac))
    ax.plot(np.cos(theta[:k]), np.sin(theta[:k]), color=color, lw=13,
            solid_capstyle="round")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.28, 1.25)
    ax.set_aspect("equal")
    ax.axis("off")


def render_card(payload, out_path=None, figsize=(5.4, 4.2), gauge_fraction=None):
    """Render one story card as a standalone PNG."""
    apply_theme()
    color = CATEGORY_COLOR.get(payload.category, T["gold"])

    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(T["ink"])

    # Header band
    fig.text(0.5, 0.93, payload.title, ha="center", va="top", fontsize=17,
             fontweight="bold", color=color)
    if payload.subtitle:
        fig.text(0.5, 0.855, str(payload.subtitle), ha="center", va="top",
                 fontsize=12, color=T["muted"])

    if payload.viz_hint == "gauge" and gauge_fraction is not None:
        ax = fig.add_axes([0.16, 0.34, 0.68, 0.42])
        _gauge(ax, gauge_fraction, color)
        fig.text(0.5, 0.44, payload.headline, ha="center", va="center",
                 fontsize=46, fontweight="bold", color=color)
        fig.text(0.5, 0.35, payload.unit, ha="center", va="center",
                 fontsize=14, color=T["muted"], fontweight="bold")
    else:
        ax = fig.add_axes([0.05, 0.32, 0.90, 0.46])
        big_number(ax, payload.headline, payload.unit, "", color=color,
                   value_size=64)

    if payload.narrative:
        wrapped = _wrap(payload.narrative, 46)
        fig.text(0.5, 0.20, wrapped, ha="center", va="top", fontsize=12,
                 color=T["text"])

    brand(fig)
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig


def render_card_strip(payloads, out_path=None, figsize=None):
    """A row of cards, as they would appear across a scoreboard ribbon."""
    apply_theme()
    n = max(1, len(payloads))
    figsize = figsize or (4.6 * n, 4.0)
    fig, axes = plt.subplots(1, n, figsize=figsize)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor(T["ink"])

    for ax, p in zip(axes, payloads):
        color = CATEGORY_COLOR.get(p.category, T["gold"])
        ax.set_facecolor(T["panel"])
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(T["panel_light"])
        ax.text(0.5, 0.90, p.title, ha="center", va="top", fontsize=13,
                fontweight="bold", color=color, transform=ax.transAxes)
        ax.text(0.5, 0.55, p.headline, ha="center", va="center", fontsize=44,
                fontweight="bold", color=color, transform=ax.transAxes)
        ax.text(0.5, 0.37, p.unit, ha="center", va="center", fontsize=13,
                color=T["muted"], fontweight="bold", transform=ax.transAxes)
        if p.narrative:
            ax.text(0.5, 0.22, _wrap(p.narrative, 34), ha="center", va="top",
                    fontsize=9.5, color=T["text"], transform=ax.transAxes)

    brand(fig)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig


def _wrap(text, width):
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines[:4])
