"""Storytelling cards — the game-level narrative layer."""
from .base import StoryCard


class MomentumMeter(StoryCard):
    card_id, title, category, viz_hint = ("momentum", "MOMENTUM METER",
                                          "story", "timeline")
    base_priority = 1.5

    def applies(self, ctx):
        return ctx.has("momentum")

    def build(self, ctx):
        m = ctx.momentum
        team = ctx.get("momentum_team", "")
        return self._payload(f"{abs(m)*100:.0f}", "%", team,
                             f"Momentum has swung {abs(m)*100:.0f}% toward {team} "
                             f"over the last three innings.",
                             {"momentum": m, "team": team})


class ClutchMeter(StoryCard):
    card_id, title, category, viz_hint = ("clutch_meter", "CLUTCH METER",
                                          "story", "gauge")
    base_priority = 2.2

    def applies(self, ctx):
        return ctx.has("leverage_index") and ctx.leverage_index >= 2.5

    def build(self, ctx):
        li = ctx.leverage_index
        return self._payload(f"{li:.1f}", "x", ctx.get("batter", ""),
                             f"This at-bat matters {li:.1f} times more than an "
                             f"average trip to the plate.",
                             {"leverage": li},
                             priority=self.base_priority + li / 3.0)


class TurningPoint(StoryCard):
    """The single biggest swing of the game so far."""
    card_id, title, category, viz_hint = ("turning_point", "TURNING POINT",
                                          "story", "timeline")
    base_priority = 2.8

    def applies(self, ctx):
        return ctx.has("wpa") and abs(ctx.wpa) >= 0.20

    def build(self, ctx):
        w = ctx.wpa
        who = ctx.get("batter", "That play")
        return self._payload(f"{w*100:+.0f}", "% WIN", who,
                             f"That swung win probability by "
                             f"{abs(w)*100:.0f} percentage points — the game may "
                             f"have just turned.",
                             {"wpa": w, "wp_before": ctx.get("wp_before"),
                              "wp_after": ctx.get("wp_after")},
                             priority=self.base_priority + abs(w) * 4.0)


class WinProbabilitySwing(StoryCard):
    card_id, title, category, viz_hint = ("wp_swing", "WIN PROBABILITY",
                                          "story", "timeline")
    base_priority = 1.9

    def applies(self, ctx):
        return ctx.has("wp_before", "wp_after") and abs(ctx.get("wpa") or 0) >= 0.08

    def build(self, ctx):
        return self._payload(f"{ctx.wp_after*100:.0f}", "%", ctx.get("batting_team", ""),
                             f"Win probability moves from {ctx.wp_before*100:.0f}% "
                             f"to {ctx.wp_after*100:.0f}%.",
                             {"wp_before": ctx.wp_before, "wp_after": ctx.wp_after,
                              "wpa": ctx.get("wpa")})


class FiveToolScore(StoryCard):
    card_id, title, category, viz_hint = ("five_tool", "FIVE-TOOL SCORE",
                                          "story", "gauge")
    base_priority = 1.3

    def applies(self, ctx):
        return ctx.has("five_tool_score")

    def build(self, ctx):
        return self._payload(f"{ctx.five_tool_score:.0f}", "/100",
                             ctx.get("player", ""),
                             f"Blending speed, power and arm strength, that grades "
                             f"out at {ctx.five_tool_score:.0f} out of 100.",
                             {"five_tool_score": ctx.five_tool_score})


class PlayerOfTheGame(StoryCard):
    card_id, title, category = "potg", "PLAYER OF THE GAME", "story"
    base_priority = 2.5

    def applies(self, ctx):
        return ctx.has("potg_player")

    def build(self, ctx):
        return self._payload(f"{ctx.get('potg_wpa',0)*100:+.0f}", "% WIN",
                             ctx.potg_player,
                             f"{ctx.potg_player} did the most to win this one, "
                             f"adding {ctx.get('potg_wpa',0)*100:+.0f}% of win "
                             f"probability.",
                             {"player": ctx.potg_player,
                              "wpa": ctx.get("potg_wpa")})


CARDS = [MomentumMeter(), ClutchMeter(), TurningPoint(), WinProbabilitySwing(),
         FiveToolScore(), PlayerOfTheGame()]
