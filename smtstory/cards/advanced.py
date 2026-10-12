"""
advanced.py — cards that depend on the deeper per-play analysis.

These fire off the pitch-sequence analyzer (`analytics/tunneling.py`), the play
anatomy engine (`playanatomy/`), and the league baselines
(`analytics/baselines.py`). They are what turn "the at-bat ended in a
strikeout" into an explanation, and "he was safe" into a measured race.

They live in their own module because they require enriched context that the
basic cards do not, while still declaring their own category so the registry
and the scoreboard treat them like any other card.
"""
import numpy as np

from .base import StoryCard


# ============================================================== PITCHING
class PutawayPitch(StoryCard):
    """Was the strikeout earned, or given away? The headline card for a K."""
    card_id, title, category, viz_hint = ("putaway", "PUTAWAY PITCH",
                                          "pitching", "tunnel")
    base_priority = 2.6

    def applies(self, ctx):
        v = ctx.get("strikeout_verdict")
        return bool(v and v.get("verdict"))

    def build(self, ctx):
        v = ctx.strikeout_verdict
        nasty = float(v.get("nastiness") or 0.0)
        return self._payload(f"{nasty:.0f}", "/100 NASTY",
                             ctx.get("pitcher", ""), v.get("narrative", ""),
                             {"verdict": v.get("verdict"), "why": v.get("why"),
                              "detail": v.get("detail", []),
                              "nastiness": nasty},
                             priority=self.base_priority + nasty / 40.0)


class PitchTunnel(StoryCard):
    """How well the putaway pitch hid behind the previous one."""
    card_id, title, category, viz_hint = ("pitch_tunnel", "PITCH TUNNEL",
                                          "pitching", "tunnel")
    base_priority = 2.0

    def applies(self, ctx):
        return ctx.has("tunnel_ratio") and ctx.tunnel_ratio >= 1.5

    def build(self, ctx):
        r = ctx.tunnel_ratio
        td = ctx.get("tunnel_distance_in")
        pd_ = ctx.get("plate_distance_in")
        narr = (f"Those two pitches were {td:.0f} inches apart when the hitter "
                f"had to decide, and {pd_:.0f} inches apart at the plate — "
                f"a {r:.1f}x tunnel.") if td and pd_ else \
               f"A {r:.1f}x tunnel off the previous pitch."
        return self._payload(f"{r:.1f}", "x TUNNEL", ctx.get("pitcher", ""),
                             narr,
                             {"tunnel_ratio": r, "tunnel_distance_in": td,
                              "plate_distance_in": pd_},
                             priority=self.base_priority + min(3.0, r / 2.0))


class EffectiveVelocity(StoryCard):
    """Perceived speed, adjusted for how far down the mound he releases."""
    card_id, title, category, viz_hint = ("effective_velo", "EFFECTIVE VELO",
                                          "pitching", "gauge")
    base_priority = 1.5

    def applies(self, ctx):
        return (ctx.has("effective_velo_mph", "velo_mph") and
                abs(ctx.effective_velo_mph - ctx.velo_mph) >= 0.8)

    def build(self, ctx):
        eff, raw = ctx.effective_velo_mph, ctx.velo_mph
        ext = ctx.get("extension_ft")
        diff = eff - raw
        word = "plays faster" if diff > 0 else "plays slower"
        narr = (f"{raw:.0f} on the gun, but with {ext:.1f} feet of extension it "
                f"{word} — like {eff:.0f}.") if ext else \
               f"{raw:.0f} mph {word} — like {eff:.0f}."
        return self._payload(f"{eff:.0f}", "MPH PERCEIVED",
                             ctx.get("pitcher", ""), narr,
                             {"effective_velo": eff, "actual_velo": raw,
                              "extension_ft": ext})


class LateLifeCard(StoryCard):
    """Induced movement — gravity removed."""
    card_id, title, category, viz_hint = ("late_life_v2", "LATE LIFE",
                                          "pitching", "tunnel")
    base_priority = 1.6

    def applies(self, ctx):
        return ctx.has("break_vertical_in") and abs(ctx.break_vertical_in) >= 8

    def build(self, ctx):
        ivb = ctx.break_vertical_in
        hb = ctx.get("break_horizontal_in") or 0.0
        if ivb > 0:
            desc = f"carried {ivb:.0f} inches more than gravity says it should"
        else:
            desc = f"dropped {abs(ivb):.0f} inches beyond gravity"
        return self._payload(f"{abs(ivb):.0f}", "IN MOVEMENT",
                             ctx.get("pitcher", ""),
                             f"That pitch {desc}, with {abs(hb):.0f} inches of "
                             f"horizontal run.",
                             {"induced_vertical_break_in": ivb,
                              "horizontal_break_in": hb})


class VelocityHoldCard(StoryCard):
    """Radar Gun Live with a league comparison."""
    card_id, title, category, viz_hint = ("radar_compare", "RADAR GUN",
                                          "pitching", "gauge")
    base_priority = 1.7

    def applies(self, ctx):
        return ctx.has("pitch_velo_mph", "pitch_velo_percentile")

    def build(self, ctx):
        v, p = ctx.pitch_velo_mph, ctx.pitch_velo_percentile
        return self._payload(f"{v:.0f}", "MPH", ctx.get("pitcher", ""),
                             f"{v:.0f} mph — harder than {p:.0f}% of pitches "
                             f"thrown in this league.",
                             {"velo": v, "percentile": p},
                             priority=self.base_priority + p / 100.0)


# ============================================================== DEFENSE
class GroundCovered(StoryCard):
    """The fielding play, measured."""
    card_id, title, category, viz_hint = ("ground_covered", "GROUND COVERED",
                                          "defense", "fieldplay")
    base_priority = 2.1

    def applies(self, ctx):
        f = ctx.get("fielding")
        return bool(f and f.get("route_ft") is not None and f["route_ft"] >= 8)

    def build(self, ctx):
        f = ctx.fielding
        pos, route = f["fielder_pos"], f["route_ft"]
        t = f.get("time_to_ball_s")
        spd = f.get("closing_speed_mph")
        pct = ctx.get("route_percentile")
        narr = f"The {pos} covered {route:.0f} feet"
        if t:
            narr += f" in {t:.1f} seconds"
        if spd:
            narr += f", closing at {spd:.1f} mph"
        narr += "."
        if pct is not None:
            narr += f" That is more ground than {pct:.0f}% of plays."
        return self._payload(f"{route:.0f}", "FT COVERED", pos, narr,
                             {**f, "route_percentile": pct},
                             priority=self.base_priority + route / 60.0)


class QuickHands(StoryCard):
    """Glove-to-hand transfer speed."""
    card_id, title, category, viz_hint = ("quick_hands", "QUICK HANDS",
                                          "defense", "fieldplay")
    base_priority = 1.7

    def applies(self, ctx):
        f = ctx.get("fielding")
        return bool(f and f.get("transfer_s") is not None and f["transfer_s"] <= 1.5)

    def build(self, ctx):
        f = ctx.fielding
        tr = f["transfer_s"]
        v = f.get("throw_velo_mph")
        narr = f"Glove to hand in {tr:.2f} seconds"
        if v:
            narr += f", then {v:.0f} mph across the diamond"
        narr += "."
        return self._payload(f"{tr:.2f}", "SEC TRANSFER", f["fielder_pos"], narr,
                             {"transfer_s": tr, "throw_velo_mph": v},
                             priority=self.base_priority + (1.5 - tr))


class CannonCompare(StoryCard):
    """Arm strength against the league."""
    card_id, title, category, viz_hint = ("cannon_compare", "OUTFIELD CANNON",
                                          "defense", "gauge")
    base_priority = 1.9

    def applies(self, ctx):
        f = ctx.get("fielding")
        return bool(f and f.get("throw_velo_mph") and ctx.get("throw_percentile"))

    def build(self, ctx):
        f, p = ctx.fielding, ctx.throw_percentile
        v = f["throw_velo_mph"]
        return self._payload(f"{v:.0f}", "MPH ARM", f["fielder_pos"],
                             f"{v:.0f} mph on the throw — a stronger arm than "
                             f"{p:.0f}% of throws we have measured.",
                             {"throw_velo": v, "percentile": p},
                             priority=self.base_priority + p / 100.0)


class DoublePlayBallet(StoryCard):
    """Pivot time on the turn."""
    card_id, title, category, viz_hint = ("dp_ballet", "DOUBLE-PLAY BALLET",
                                          "defense", "fieldplay")
    base_priority = 2.3

    def applies(self, ctx):
        dp = ctx.get("double_play")
        return bool(dp)

    def build(self, ctx):
        dp = ctx.double_play
        best = min(dp, key=lambda d: d["pivot_s"])
        return self._payload(f"{best['pivot_s']:.2f}", "SEC PIVOT",
                             best["pos"],
                             f"Turned in {best['pivot_s']:.2f} seconds — "
                             f"glove to release on the pivot.",
                             {"pivots": dp})


class PopTimePipeline(StoryCard):
    """Catcher exchange and throw."""
    card_id, title, category, viz_hint = ("pop_time", "POP-TIME PIPELINE",
                                          "defense", "fieldplay")
    base_priority = 2.0

    def applies(self, ctx):
        return bool(ctx.get("pop_time"))

    def build(self, ctx):
        pt = ctx.pop_time
        v = pt.get("throw_velo_mph")
        narr = f"Exchange to release in {pt['exchange_s']:.2f} seconds"
        if v:
            narr += f", {v:.0f} mph down to second"
        narr += "."
        return self._payload(f"{pt['exchange_s']:.2f}", "SEC POP", "CATCHER",
                             narr, dict(pt))


# ============================================================== SPEED
class SafeAtBase(StoryCard):
    """The race: runner vs the throw."""
    card_id, title, category, viz_hint = ("safe_race", "BEAT THE THROW",
                                          "speed", "race")
    base_priority = 2.4

    def applies(self, ctx):
        cp = ctx.get("close_play")
        return bool(cp and cp.get("margin_s") is not None)

    def build(self, ctx):
        cp = ctx.close_play
        m = cp["margin_s"]
        word = "beat the throw by" if m > 0 else "was retired by"
        return self._payload(f"{abs(m):.2f}", "SEC", ctx.get("batter", ""),
                             f"{'Safe' if m > 0 else 'Out'} — the runner {word} "
                             f"{abs(m):.2f} seconds.",
                             dict(cp),
                             priority=self.base_priority +
                             (1.5 if cp.get("bang_bang") else 0.0))


class SprintCompare(StoryCard):
    """Sprint speed against every runner in the league."""
    card_id, title, category, viz_hint = ("sprint_compare", "BURNER BOARD",
                                          "speed", "gauge")
    base_priority = 2.1

    def applies(self, ctx):
        r = ctx.get("running")
        return bool(r and r.get("top_speed_mph") and ctx.get("sprint_percentile"))

    def build(self, ctx):
        r, p = ctx.running, ctx.sprint_percentile
        v = r["top_speed_mph"]
        grade = ctx.get("sprint_grade") or ""
        return self._payload(f"{v:.1f}", "MPH", ctx.get("batter", ""),
                             f"Topped out at {v:.1f} mph — faster than "
                             f"{p:.0f}% of the league. {grade}".strip(),
                             {"top_speed_mph": v, "percentile": p,
                              "grade": grade},
                             priority=self.base_priority + p / 100.0)


class HomeToFirstCompare(StoryCard):
    """Time down the line with a league comparison."""
    card_id, title, category, viz_hint = ("h2f_compare", "HOME-TO-FIRST DASH",
                                          "speed", "race")
    base_priority = 2.0

    def applies(self, ctx):
        r = ctx.get("running")
        return bool(r and r.get("time_to_base_s") and
                    3.0 < r["time_to_base_s"] < 7.5)

    def build(self, ctx):
        t = ctx.running["time_to_base_s"]
        pct = ctx.get("h2f_percentile")
        narr = f"Down the line in {t:.2f} seconds."
        if pct is not None:
            narr += f" Quicker than {pct:.0f}% of the league."
        return self._payload(f"{t:.2f}", "SEC", ctx.get("batter", ""), narr,
                             {"seconds": t, "percentile": pct})


class OutOfTheBox(StoryCard):
    """Acceleration in the first step and a half."""
    card_id, title, category = "box_burst", "FASTEST OUT OF THE BOX", "speed"
    base_priority = 1.5

    def applies(self, ctx):
        r = ctx.get("running")
        return bool(r and r.get("burst_ft_s2") and r["burst_ft_s2"] > 10)

    def build(self, ctx):
        b = ctx.running["burst_ft_s2"]
        return self._payload(f"{b:.0f}", "FT/S² BURST", ctx.get("batter", ""),
                             f"Out of the box hard — accelerating at "
                             f"{b:.0f} ft/s² in the first stride.",
                             {"burst": b})


# ============================================================== FAN
class OutOrSafe(StoryCard):
    """A bang-bang play, put to the crowd."""
    card_id, title, category, viz_hint = ("out_or_safe", "OUT OR SAFE?",
                                          "fan", "vote")
    base_priority = 2.9

    def applies(self, ctx):
        cp = ctx.get("close_play")
        return bool(cp and cp.get("bang_bang"))

    def build(self, ctx):
        cp = ctx.close_play
        return self._payload("VOTE", "", ctx.get("batter", ""),
                             "Too close to call — what did you see?",
                             {"vote_options": ["SAFE", "OUT"],
                              "actual": cp["verdict"],
                              "margin_s": cp["margin_s"],
                              "model_answer": cp["verdict"]},
                             priority=self.base_priority)


class GuessTheTunnel(StoryCard):
    """Fan game on a strikeout: was that nasty, or a bad swing?"""
    card_id, title, category, viz_hint = ("guess_nasty", "NASTY OR NOT?",
                                          "fan", "vote")
    base_priority = 2.2

    def applies(self, ctx):
        v = ctx.get("strikeout_verdict")
        return bool(v and 40 <= v.get("nastiness", 0) <= 70)

    def build(self, ctx):
        v = ctx.strikeout_verdict
        return self._payload("VOTE", "", ctx.get("pitcher", ""),
                             "Filthy pitch, or should he have hit that?",
                             {"vote_options": ["NASTY PITCH", "BAD SWING"],
                              "actual": v["verdict"],
                              "nastiness": v["nastiness"]})


# ============================================================== STORY
class SprayChartCard(StoryCard):
    """Where this hitter has put the ball tonight."""
    card_id, title, category, viz_hint = ("spray", "SPRAY CHART", "story",
                                          "spray")
    base_priority = 1.2

    def applies(self, ctx):
        return bool(ctx.get("spray_points"))

    def build(self, ctx):
        pts = ctx.spray_points
        return self._payload(f"{len(pts)}", "BALLS IN PLAY",
                             ctx.get("batter", ""),
                             f"Where {ctx.get('batter','this hitter')} has put "
                             f"the ball in play tonight.",
                             {"points": pts})


class RivalryRadar(StoryCard):
    """Team vs team, tale of the tape."""
    card_id, title, category, viz_hint = ("rivalry", "RIVALRY RADAR", "story",
                                          "compare")
    base_priority = 1.4

    def applies(self, ctx):
        return bool(ctx.get("rivalry"))

    def build(self, ctx):
        r = ctx.rivalry
        return self._payload(r.get("headline", "VS"), "", "",
                             r.get("narrative", "Tale of the tape."),
                             dict(r))


class ProspectSpotlight(StoryCard):
    """A young player's tool grades."""
    card_id, title, category, viz_hint = ("prospect", "PROSPECT SPOTLIGHT",
                                          "story", "compare")
    base_priority = 1.5

    def applies(self, ctx):
        return bool(ctx.get("tool_grades"))

    def build(self, ctx):
        g = ctx.tool_grades
        best = max(g.items(), key=lambda kv: kv[1] or 0)
        return self._payload(f"{best[1]:.0f}", f"{best[0].upper()} PCTL",
                             ctx.get("player", ""),
                             f"Best tool: {best[0]} at the "
                             f"{best[1]:.0f}th percentile.",
                             {"grades": g})


CARDS = [
    # pitching
    PutawayPitch(), PitchTunnel(), EffectiveVelocity(), LateLifeCard(),
    VelocityHoldCard(),
    # defense
    GroundCovered(), QuickHands(), CannonCompare(), DoublePlayBallet(),
    PopTimePipeline(),
    # speed
    SafeAtBase(), SprintCompare(), HomeToFirstCompare(), OutOfTheBox(),
    # fan
    OutOrSafe(), GuessTheTunnel(),
    # story
    SprayChartCard(), RivalryRadar(), ProspectSpotlight(),
]
