"""
Pitching cards.

SCOPE NOTE: spin rate is not present in the SMT data and cannot be recovered
from positional tracking alone, so no spin card is offered. Pitch MOVEMENT,
however, is measurable — it is the deviation of the ball's path from the
straight line it would follow without aerodynamic forces — so "Late Life" is
built from that real quantity instead.
"""
import numpy as np

from .base import StoryCard


class RadarGunLive(StoryCard):
    card_id, title, category, viz_hint = "radar_gun", "RADAR GUN", "pitching", "gauge"
    base_priority = 1.7

    def applies(self, ctx):
        return ctx.has("pitch_velo_mph") and ctx.pitch_velo_mph >= 88.0

    def build(self, ctx):
        v = ctx.pitch_velo_mph
        fastest = ctx.get("is_fastest_of_game")
        narr = (f"{v:.0f} on the gun." if not fastest else
                f"Season heat — {v:.0f} mph, the fastest pitch of the night.")
        return self._payload(f"{v:.0f}", "MPH", ctx.get("pitcher", ""), narr,
                             {"pitch_velo": v, "fastest_of_game": bool(fastest)},
                             priority=self.base_priority + max(0.0, (v - 95.0) / 5.0)
                             + (1.0 if fastest else 0.0))


class VelocityHeartbeat(StoryCard):
    """How a starter's velocity is holding across the outing."""
    card_id, title, category, viz_hint = ("velocity_heartbeat", "VELOCITY HEARTBEAT",
                                          "pitching", "timeline")
    base_priority = 1.3

    def applies(self, ctx):
        return ctx.has("pitcher_velo_trend") and (ctx.get("pitcher_pitch_count") or 0) >= 40

    def build(self, ctx):
        trend = ctx.pitcher_velo_trend
        word = "holding strong" if trend > -0.5 else "starting to fade"
        return self._payload(f"{trend:+.1f}", "MPH", ctx.get("pitcher", ""),
                             f"{ctx.get('pitcher','He')} is {word} — "
                             f"{trend:+.1f} mph from his first inning.",
                             {"trend": trend,
                              "pitch_count": ctx.get("pitcher_pitch_count")})


class LateLife(StoryCard):
    """Measured movement: deviation from a straight-line path."""
    card_id, title, category = "late_life", "LATE LIFE", "pitching"
    base_priority = 1.4

    def applies(self, ctx):
        return ctx.has("pitch_break_in") and abs(ctx.pitch_break_in) > 4.0

    def build(self, ctx):
        b = abs(ctx.pitch_break_in)
        return self._payload(f"{b:.0f}", "IN", ctx.get("pitcher", ""),
                             f"That pitch moved {b:.0f} inches off a straight line "
                             f"on its way to the plate.",
                             {"break_in": ctx.pitch_break_in})


class CommandMap(StoryCard):
    """Where the pitch crossed the zone."""
    card_id, title, category, viz_hint = ("command_map", "COMMAND MAP",
                                          "pitching", "zone")
    base_priority = 1.1

    def applies(self, ctx):
        return ctx.has("plate_x", "plate_z")

    def build(self, ctx):
        loc = "in the zone" if ctx.get("in_zone") else "off the plate"
        return self._payload("SPOT", "", ctx.get("pitcher", ""),
                             f"Painted {loc}.",
                             {"plate_x": ctx.plate_x, "plate_z": ctx.plate_z,
                              "in_zone": bool(ctx.get("in_zone"))})


class PitchingEscape(StoryCard):
    """A pitcher escaping a high-leverage jam."""
    card_id, title, category = "escape", "ESCAPE ARTIST", "pitching"
    base_priority = 2.3

    def applies(self, ctx):
        return (ctx.has("leverage_index", "wpa") and ctx.leverage_index >= 2.0
                and ctx.wpa < -0.06 and ctx.get("outcome") in ("out", "fielders_choice"))

    def build(self, ctx):
        return self._payload(f"{abs(ctx.wpa)*100:.0f}", "% WIN", ctx.get("pitcher", ""),
                             f"{ctx.get('pitcher','The pitcher')} works out of it — "
                             f"swinging the game {abs(ctx.wpa)*100:.0f}% back "
                             f"toward his side.",
                             {"leverage": ctx.leverage_index, "wpa": ctx.wpa},
                             priority=self.base_priority + ctx.leverage_index / 3.0)


CARDS = [RadarGunLive(), VelocityHeartbeat(), LateLife(), CommandMap(),
         PitchingEscape()]
