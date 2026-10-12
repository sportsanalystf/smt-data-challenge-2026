"""Power & hitting cards."""
from .base import StoryCard


class StatcastSmash(StoryCard):
    """Exit velocity."""
    card_id, title, category, viz_hint = "smash", "STATCAST SMASH", "power", "gauge"
    base_priority = 2.0

    def applies(self, ctx):
        return ctx.has("exit_velo_mph") and ctx.exit_velo_mph >= 95.0

    def build(self, ctx):
        ev = ctx.exit_velo_mph
        hardest = ctx.get("is_hardest_of_game")
        narr = f"{ctx.get('batter','That')} left the bat at {ev:.1f} mph."
        if hardest:
            narr = f"Hardest-hit ball of the night — {ev:.1f} mph off the bat."
        return self._payload(f"{ev:.1f}", "MPH", ctx.get("batter", ""), narr,
                             {"exit_velo": ev, "hardest_of_game": bool(hardest)},
                             priority=self.base_priority + (ev - 95.0) / 10.0
                             + (1.0 if hardest else 0.0))


class MoonshotMeter(StoryCard):
    """Carry distance on a fly ball or home run."""
    card_id, title, category, viz_hint = "moonshot", "MOONSHOT METER", "power", "field"
    base_priority = 2.2

    def applies(self, ctx):
        return ctx.has("hit_distance_ft") and ctx.hit_distance_ft >= 300.0

    def build(self, ctx):
        d = ctx.hit_distance_ft
        hr = ctx.outcome == "home_run"
        narr = (f"That ball travelled {d:.0f} feet." if not hr else
                f"Gone! A {d:.0f}-foot home run off the bat of "
                f"{ctx.get('batter','the hitter')}.")
        return self._payload(f"{d:.0f}", "FT", ctx.get("batter", ""), narr,
                             {"distance_ft": d, "home_run": bool(hr)},
                             priority=self.base_priority + (1.2 if hr else 0.0)
                             + max(0.0, (d - 380.0) / 50.0))


class BarrelZone(StoryCard):
    """The sweet spot: hit hard at the right angle."""
    card_id, title, category = "barrel", "BARREL ZONE", "power"
    base_priority = 1.8

    def applies(self, ctx):
        return (ctx.has("exit_velo_mph", "launch_deg") and
                ctx.exit_velo_mph >= 95.0 and 20.0 <= ctx.launch_deg <= 35.0)

    def build(self, ctx):
        return self._payload("BARREL", "", ctx.get("batter", ""),
                             f"Barreled — {ctx.exit_velo_mph:.0f} mph at "
                             f"{ctx.launch_deg:.0f} degrees, the sweet spot.",
                             {"exit_velo": ctx.exit_velo_mph,
                              "launch": ctx.launch_deg})


class LaunchAngleRainbow(StoryCard):
    """Launch angle of the batted ball."""
    card_id, title, category, viz_hint = "launch_angle", "LAUNCH ANGLE", "power", "field"
    base_priority = 1.2

    def applies(self, ctx):
        return ctx.has("launch_deg", "exit_velo_mph")

    def build(self, ctx):
        la = ctx.launch_deg
        kind = ("a line drive" if 10 <= la < 25 else
                "a fly ball" if la >= 25 else
                "a ground ball" if la < 10 else "a batted ball")
        return self._payload(f"{la:.0f}", "DEG", ctx.get("batter", ""),
                             f"Off the bat at {la:.0f} degrees — {kind}.",
                             {"launch": la, "type": kind})


class ClutchContact(StoryCard):
    """A big hit in a big spot."""
    card_id, title, category = "clutch_contact", "CLUTCH CONTACT", "power"
    base_priority = 2.4

    def applies(self, ctx):
        return (ctx.has("leverage_index") and ctx.leverage_index >= 2.0 and
                ctx.get("outcome") in ("single", "double", "triple", "home_run"))

    def build(self, ctx):
        li = ctx.leverage_index
        wpa = ctx.get("wpa") or 0.0
        return self._payload(f"{wpa*100:+.0f}", "% WIN", ctx.get("batter", ""),
                             f"In a spot {li:.1f} times more important than average, "
                             f"that swing moved the needle {abs(wpa)*100:.0f}%.",
                             {"leverage": li, "wpa": wpa},
                             priority=self.base_priority + li / 2.0)


class HomeRunProbability(StoryCard):
    """Live home run probability the instant the ball is hit."""
    card_id, title, category, viz_hint = "hr_prob", "HOME RUN?", "power", "gauge"
    base_priority = 2.1

    def applies(self, ctx):
        return ctx.has("p_home_run") and ctx.p_home_run >= 0.25

    def build(self, ctx):
        p = 100.0 * ctx.p_home_run
        return self._payload(f"{p:.0f}", "%", ctx.get("batter", ""),
                             f"Off the bat, that had a {p:.0f}% chance of leaving the yard.",
                             {"p_home_run": ctx.p_home_run})


CARDS = [StatcastSmash(), MoonshotMeter(), BarrelZone(), LaunchAngleRainbow(),
         ClutchContact(), HomeRunProbability()]
