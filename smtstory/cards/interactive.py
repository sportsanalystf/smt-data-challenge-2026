"""
Fan-interactive cards.

These are the cards that ASK the crowd something. Each one carries a
`vote_options` list and the model's answer, so the scoreboard can show the
question, collect the vote, then reveal the truth. The design rule is that a
question is only worth asking when the answer is genuinely uncertain — a
prompt the crowd gets right 95% of the time is not a game, it is a formality.
That is why each card gates on the model's own uncertainty.
"""
from .base import StoryCard


class CatchOrNoCatch(StoryCard):
    card_id, title, category, viz_hint = ("catch_or_not", "CATCH OR NO CATCH?",
                                          "fan", "vote")
    base_priority = 2.7

    def applies(self, ctx):
        # Only ask when the model is genuinely torn.
        return ctx.has("catch_prob") and 0.25 <= ctx.catch_prob <= 0.75

    def build(self, ctx):
        p = ctx.catch_prob
        return self._payload("VOTE", "", ctx.get("fielder", ""),
                             "Does he come up with it?",
                             {"vote_options": ["CAUGHT", "DROPS"],
                              "model_answer": "CAUGHT" if p >= 0.5 else "DROPS",
                              "model_confidence": max(p, 1 - p),
                              "actual": ("CAUGHT" if ctx.get("catch_made") == 1
                                         else "DROPS"),
                              "catch_prob": p,
                              "suspense": 1.0 - abs(2 * (p - 0.5))},
                             priority=self.base_priority + (1.0 - abs(2 * (p - 0.5))))


class GuessTheGun(StoryCard):
    card_id, title, category, viz_hint = ("guess_gun", "GUESS THE GUN", "fan", "vote")
    base_priority = 1.5

    def applies(self, ctx):
        return ctx.has("pitch_velo_mph") and ctx.pitch_velo_mph >= 90.0

    def build(self, ctx):
        v = ctx.pitch_velo_mph
        lo = int(v // 3 * 3) - 3
        opts = [f"{lo}-{lo+2}", f"{lo+3}-{lo+5}", f"{lo+6}-{lo+8}"]
        idx = min(2, max(0, int((v - lo) // 3)))
        return self._payload("VOTE", "", ctx.get("pitcher", ""),
                             "How hard was that one?",
                             {"vote_options": opts, "actual": f"{v:.0f} MPH",
                              "correct_option": opts[idx]})


class HowFarDidItGo(StoryCard):
    card_id, title, category, viz_hint = ("how_far", "HOW FAR DID IT GO?",
                                          "fan", "vote")
    base_priority = 2.0

    def applies(self, ctx):
        return ctx.has("hit_distance_ft") and ctx.hit_distance_ft >= 330.0

    def build(self, ctx):
        d = ctx.hit_distance_ft
        base = int(d // 25 * 25) - 25
        opts = [f"{base}-{base+24} ft", f"{base+25}-{base+49} ft",
                f"{base+50}+ ft"]
        idx = min(2, max(0, int((d - base) // 25)))
        return self._payload("VOTE", "", ctx.get("batter", ""),
                             "How far did that ball travel?",
                             {"vote_options": opts, "actual": f"{d:.0f} FT",
                              "correct_option": opts[idx]})


class GuessExitVelocity(StoryCard):
    card_id, title, category, viz_hint = ("guess_ev", "GUESS THE EXIT VELO",
                                          "fan", "vote")
    base_priority = 1.6

    def applies(self, ctx):
        return ctx.has("exit_velo_mph") and ctx.exit_velo_mph >= 98.0

    def build(self, ctx):
        v = ctx.exit_velo_mph
        base = int(v // 5 * 5) - 5
        opts = [f"{base}-{base+4}", f"{base+5}-{base+9}", f"{base+10}+"]
        idx = min(2, max(0, int((v - base) // 5)))
        return self._payload("VOTE", "", ctx.get("batter", ""),
                             "How hard was that hit?",
                             {"vote_options": opts, "actual": f"{v:.0f} MPH",
                              "correct_option": opts[idx]})


class BeatTheBurner(StoryCard):
    """Race a fan's reaction against the runner's real sprint."""
    card_id, title, category, viz_hint = ("beat_burner", "BEAT THE BURNER",
                                          "fan", "vote")
    base_priority = 1.4

    def applies(self, ctx):
        return ctx.has("home_to_first_s")

    def build(self, ctx):
        t = ctx.home_to_first_s
        return self._payload(f"{t:.2f}", "SEC", ctx.get("batter", ""),
                             f"Think you're quick? He made it in {t:.2f} seconds. "
                             f"Tap when the pitch is released and see how you compare.",
                             {"target_seconds": t, "interactive": True})


CARDS = [CatchOrNoCatch(), GuessTheGun(), HowFarDidItGo(), GuessExitVelocity(),
         BeatTheBurner()]
