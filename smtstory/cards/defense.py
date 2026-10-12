"""Defense cards — built on the Robbery Meter catch-probability model."""
from .base import StoryCard


class RobberyMeter(StoryCard):
    """The flagship: how unlikely was that catch?"""
    card_id, title, category, viz_hint = ("robbery_meter", "ROBBERY METER",
                                          "defense", "field")
    base_priority = 2.6

    def applies(self, ctx):
        return ctx.has("catch_prob") and ctx.get("catch_made") == 1

    def build(self, ctx):
        p = ctx.catch_prob
        score = 100.0 * (1.0 - p)
        return self._payload(f"{score:.0f}", "/100", ctx.get("fielder", ""),
                             f"That catch had only a {p*100:.0f}% chance of being made.",
                             {"catch_prob": p, "robbery_score": score,
                              "route_ft": ctx.get("route_ft"),
                              "hang_s": ctx.get("hang_s")},
                             priority=self.base_priority + (1.0 - p) * 3.0)


class WebGem(StoryCard):
    """Reserved for the truly improbable."""
    card_id, title, category, viz_hint = ("web_gem", "WEB GEM", "defense", "field")
    base_priority = 3.0

    def applies(self, ctx):
        return (ctx.has("catch_prob") and ctx.get("catch_made") == 1
                and ctx.catch_prob < 0.35)

    def build(self, ctx):
        p = ctx.catch_prob
        return self._payload(f"{(1-p)*100:.0f}", "/100", ctx.get("fielder", ""),
                             f"Web gem! {ctx.get('fielder','He')} covered "
                             f"{ctx.get('route_ft',0):.0f} feet in "
                             f"{ctx.get('hang_s',0):.1f} seconds on a play made only "
                             f"{p*100:.0f}% of the time.",
                             {"catch_prob": p, "route_ft": ctx.get("route_ft"),
                              "hang_s": ctx.get("hang_s")},
                             priority=self.base_priority + (1.0 - p) * 3.0)


class OutfieldCannon(StoryCard):
    card_id, title, category, viz_hint = ("cannon", "OUTFIELD CANNON",
                                          "defense", "gauge")
    base_priority = 1.8

    def applies(self, ctx):
        return ctx.has("throw_velo_mph") and ctx.throw_velo_mph >= 85.0

    def build(self, ctx):
        v = ctx.throw_velo_mph
        return self._payload(f"{v:.0f}", "MPH", ctx.get("fielder", ""),
                             f"What an arm — {v:.0f} mph on the throw.",
                             {"throw_velo": v},
                             priority=self.base_priority + max(0.0, (v - 90.0) / 5.0))


class GroundCrewRange(StoryCard):
    card_id, title, category, viz_hint = ("range", "GROUND CREW RANGE",
                                          "defense", "field")
    base_priority = 1.6

    def applies(self, ctx):
        return ctx.has("route_ft") and ctx.route_ft >= 60.0 and ctx.get("catch_made") == 1

    def build(self, ctx):
        return self._payload(f"{ctx.route_ft:.0f}", "FT", ctx.get("fielder", ""),
                             f"{ctx.get('fielder','He')} covered "
                             f"{ctx.route_ft:.0f} feet to run that down.",
                             {"route_ft": ctx.route_ft, "hang_s": ctx.get("hang_s")},
                             priority=self.base_priority + ctx.route_ft / 100.0)


class RouteEfficiency(StoryCard):
    card_id, title, category = "route_efficiency", "ROUTE EFFICIENCY", "defense"
    base_priority = 1.2

    def applies(self, ctx):
        return ctx.has("route_efficiency")

    def build(self, ctx):
        pct = 100.0 * ctx.route_efficiency
        grade = "a perfect read" if pct >= 95 else (
            "a strong route" if pct >= 88 else "a scenic route")
        return self._payload(f"{pct:.0f}", "%", ctx.get("fielder", ""),
                             f"{grade.capitalize()} — {pct:.0f}% efficient to the ball.",
                             {"route_efficiency": ctx.route_efficiency})


CARDS = [RobberyMeter(), WebGem(), OutfieldCannon(), GroundCrewRange(),
         RouteEfficiency()]
