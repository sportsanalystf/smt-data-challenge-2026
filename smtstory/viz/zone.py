"""zone.py — strike-zone heat maps (the 'attack zone')."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .. import config
from .theme import apply_theme, title_bar, brand

T = config.THEME


def zone_heatmap(zone_model, out_path=None, title="ATTACK ZONE",
                 subtitle="Probability a pitch is put in play, by location",
                 figsize=(6.2, 6.4)):
    """Contact probability across the plate, with the calibrated zone drawn on."""
    apply_theme()
    xs, zs, P = zone_model.zone_grid(n=60)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.pcolormesh(xs, zs, P, cmap="inferno", shading="auto")
    cb = fig.colorbar(im, ax=ax, fraction=.04, pad=.02)
    cb.set_label("P(ball in play)", color=T["text"])
    cb.ax.tick_params(colors=T["muted"])

    hw = zone_model.half_width
    ax.add_patch(Rectangle((-hw, zone_model.bottom), 2 * hw,
                           zone_model.top - zone_model.bottom,
                           fill=False, edgecolor="white", lw=2.4, zorder=5))
    ax.set_xlabel("Horizontal location (ft)  ·  catcher's view")
    ax.set_ylabel("Height (ft)")
    ax.set_aspect("equal")
    title_bar(fig, title, subtitle)
    brand(fig)
    fig.tight_layout(rect=[0, 0.02, 1, 0.90])
    if out_path:
        fig.savefig(out_path)
        plt.close(fig)
        return out_path
    return fig
