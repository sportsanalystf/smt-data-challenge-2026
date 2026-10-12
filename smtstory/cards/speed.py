"""Speed & baserunning cards."""
from .base import StoryCard

MPH = "MPH"


class BurnerBoard(StoryCard):
    """Top sprint speed, framed against the league."""
    card_id, title, category, viz_hint = "burner_board", "BURNER BOARD", "speed", "gauge"
    base_priority = 2.0

    def applies(self, ctx):
        return ctx.has("sprint_mph") and ctx.sprint_mph >= 17.0

    def build(self, ctx):
        pct = ctx.get("sprint_percentile")
        sub = ctx.get("batter", "")
        narr = f"{sub} hit {ctx.sprint_mph:.1f} mph on that run."
        if pct is not None:
            narr += f" That is faster than {pct:.0f}% of the league."
        pri = self.base_priority + max(0.0, (ctx.sprint_mph - 19.0))
        return self._payload(f"{ctx.sprint_mph:.1f}", MPH, sub, narr,
                             {"sprint_mph": ctx.sprint_mph, "percentile": pct},
                             priority=pri)


class HomeToFirst(StoryCard):
    """Time from contact to reaching first base."""
    card_id, title, category = "home_to_first", "HOME-TO-FIRST DASH", "speed"
    base_priority = 1.8

    def applies(self, ctx):
        return ctx.has("home_to_first_s") and 3.0 < ctx.home_to_first_s < 7.0

    def build(self, ctx):
        t = ctx.home_to_first_s
        tag = "elite" if t < 4.2 else ("above average" if t < 4.5 else "average")
        return self._payload(f"{t:.2f}", "SEC", ctx.get("batter", ""),
                             f"{ctx.get('batter','The runner')} got down the line in "
                             f"{t:.2f} seconds — {tag}.",
                             {"seconds": t, "grade": tag})


class FastestOutOfBox(StoryCard):
    """Acceleration in the first moments after contact."""
    card_id, title, category = "out_of_box", "FASTEST OUT OF THE BOX", "speed"
    base_priority = 1.4

    def applies(self, ctx):
        return ctx.has("burst_ft_s2") and ctx.burst_ft_s2 > 8.0

    def build(self, ctx):
        return self._payload(f"{ctx.burst_ft_s2:.1f}", "FT/S²", ctx.get("batter", ""),
                             f"{ctx.get('batter','The batter')} exploded out of the box, "
                             f"accelerating at {ctx.burst_ft_s2:.1f} ft/s².",
                             {"burst": ctx.burst_ft_s2})


class ExtraBaseInstinct(StoryCard):
    """Taking the extra base."""
    card_id, title, category = "extra_base", "EXTRA-BASE INSTINCT", "speed"
    base_priority = 1.9

    def applies(self, ctx):
        return ctx.outcome in ("double", "triple") and ctx.has("sprint_mph")

    def build(self, ctx):
        name = {"double": "a double", "triple": "a triple"}[ctx.outcome]
        return self._payload(f"{ctx.sprint_mph:.1f}", MPH, ctx.get("batter", ""),
                             f"{ctx.get('batter','The runner')} turned that into {name}, "
                             f"topping out at {ctx.sprint_mph:.1f} mph.",
                             {"outcome": ctx.outcome, "sprint_mph": ctx.sprint_mph},
                             priority=self.base_priority +
                             (0.5 if ctx.outcome == "triple" else 0.0))


class SprintEfficiency(StoryCard):
    """How direct the baserunning path was."""
    card_id, title, category = "sprint_efficiency", "SPRINT EFFICIENCY", "speed"
    base_priority = 1.1

    def applies(self, ctx):
        return ctx.has("run_efficiency")

    def build(self, ctx):
        pct = 100.0 * ctx.run_efficiency
        return self._payload(f"{pct:.0f}", "%", ctx.get("batter", ""),
                             f"That baserunning path was {pct:.0f}% efficient "
                             f"against a perfectly straight line.",
                             {"efficiency": ctx.run_efficiency})


class LeadDistance(StoryCard):
    """Measured secondary lead off the bag."""
    card_id, title, category = "lead_distance", "LEAD DISTANCE", "speed"
    base_priority = 1.2

    def applies(self, ctx):
        return ctx.has("lead_ft") and ctx.lead_ft > 6.0

    def build(self, ctx):
        return self._payload(f"{ctx.lead_ft:.1f}", "FT", ctx.get("runner", ""),
                             f"The runner is {ctx.lead_ft:.1f} feet off the bag.",
                             {"lead_ft": ctx.lead_ft})


CARDS = [BurnerBoard(), HomeToFirst(), FastestOutOfBox(), ExtraBaseInstinct(),
         SprintEfficiency(), LeadDistance()]
