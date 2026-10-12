"""
generator.py — turning numbers into sentences a fan understands.

Design rules, learned from how broadcasts actually sound:

1. **One idea per sentence.** A scoreboard line is read in about two seconds.
2. **Lead with the number that surprised you**, not the setup.
3. **Never print a raw metric name.** "Leverage index 5.8" means nothing to a
   family in section 112; "this at-bat matters almost six times more than
   normal" means everything.
4. **Compare, don't just state.** A number becomes a story when it is measured
   against the league, the game, or the season.

The generator is template-based rather than a language model: it must be
deterministic, instant, and incapable of saying something false about the game.
"""
import numpy as np

from ..state.reconstruct import BASE_STATES

ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
            7: "7th", 8: "8th", 9: "9th"}


def ordinal(n):
    n = int(n)
    if n in ORDINALS:
        return ORDINALS[n]
    return f"{n}th"


def describe_state(base_state, outs):
    """'runners on the corners, one out'"""
    b = int(base_state)
    on1, on2, on3 = bool(b & 1), bool(b & 2), bool(b & 4)
    if not (on1 or on2 or on3):
        bases = "bases empty"
    elif on1 and on2 and on3:
        bases = "bases loaded"
    elif on1 and on3:
        bases = "runners on the corners"
    elif on1 and on2:
        bases = "runners on first and second"
    elif on2 and on3:
        bases = "runners on second and third"
    elif on1:
        bases = "a runner on first"
    elif on2:
        bases = "a runner on second"
    else:
        bases = "a runner on third"
    o = {0: "nobody out", 1: "one out", 2: "two outs"}.get(int(outs), "")
    return f"{bases}, {o}" if o else bases


class NarrativeGenerator:
    """Produces short broadcast lines for plays, cards, and recaps."""

    def __init__(self, league_context=None):
        # league_context carries season-wide reference values so the generator
        # can say "hardest hit ball of the season" and mean it.
        self.ctx = league_context or {}

    # ------------------------------------------------------------ play level
    def play_line(self, play):
        """The single best sentence describing a play."""
        g = play.get
        bits = []

        outcome = g("outcome")
        batter = g("batter") or "The batter"
        runs = int(g("runs") or 0)

        if outcome == "home_run":
            dist = g("hit_distance_ft")
            ev = g("exit_velo_mph")
            s = f"{batter} homers"
            if runs > 1:
                s += f", a {runs}-run shot"
            if dist and np.isfinite(dist):
                s += f" that carried {dist:.0f} feet"
            if ev and np.isfinite(ev):
                s += f" at {ev:.0f} mph off the bat"
            bits.append(s + ".")
        elif outcome in ("single", "double", "triple"):
            word = {"single": "singles", "double": "doubles", "triple": "triples"}[outcome]
            s = f"{batter} {word}"
            if runs:
                s += f", driving in {runs}"
            bits.append(s + ".")
        elif outcome == "walk_hbp":
            bits.append(f"{batter} reaches without swinging the bat.")
        else:
            bits.append(f"{batter} is retired.")

        # The impact sentence.
        wpa = g("wpa")
        if wpa is not None and np.isfinite(wpa) and abs(wpa) >= 0.08:
            direction = "increased" if wpa > 0 else "cut"
            bits.append(f"That {direction} their win probability by "
                        f"{abs(wpa)*100:.0f}%.")

        return " ".join(bits)

    # ---------------------------------------------------------- situational
    def situation_line(self, play):
        g = play.get
        half = "Top" if g("half_inning") == "Top" else "Bottom"
        return (f"{half} of the {ordinal(g('inning') or 1)}, "
                f"{describe_state(g('base_state_before') or 0, g('outs_before') or 0)}.")

    # ------------------------------------------------------------- insights
    def insight_lines(self, play, limit=3):
        """The short, punchy facts that make good scoreboard copy."""
        g = play.get
        out = []

        cp = g("catch_prob")
        if cp is not None and np.isfinite(cp) and g("catch_made") == 1:
            out.append(f"This catch had only a {cp*100:.0f}% chance of being made.")

        wpa = g("wpa")
        if wpa is not None and np.isfinite(wpa) and abs(wpa) >= 0.10:
            out.append(f"That swing changed win probability by "
                       f"{abs(wpa)*100:.0f} percentage points.")

        sp = g("sprint_mph")
        if sp is not None and np.isfinite(sp) and sp >= 19.5:
            out.append(f"The runner reached {sp:.1f} mph.")

        ev = g("exit_velo_mph")
        if ev is not None and np.isfinite(ev):
            hardest = self.ctx.get("max_exit_velo_game")
            if hardest is not None and ev >= hardest - 1e-6:
                out.append(f"That is the hardest-hit ball of tonight's game at "
                           f"{ev:.1f} mph.")
            elif ev >= 105:
                out.append(f"Scorched — {ev:.1f} mph off the bat.")

        pv = g("pitch_velo_mph")
        if pv is not None and np.isfinite(pv):
            fastest = self.ctx.get("max_pitch_velo_game")
            if fastest is not None and pv >= fastest - 1e-6:
                out.append(f"That is the fastest pitch recorded today at "
                           f"{pv:.0f} mph.")

        li = g("leverage_index")
        if li is not None and np.isfinite(li) and li >= 2.5:
            out.append(f"The leverage index for this at-bat was {li:.1f} — "
                       f"one of the biggest moments of the night.")

        dist = g("hit_distance_ft")
        if dist is not None and np.isfinite(dist) and dist >= 400:
            out.append(f"That ball travelled {dist:.0f} feet.")

        return out[:limit]

    # --------------------------------------------------------------- recaps
    def inning_recap(self, inning, half, plays):
        runs = int(sum(int(p.get("runs") or 0) for p in plays))
        hits = sum(1 for p in plays
                   if p.get("outcome") in ("single", "double", "triple", "home_run"))
        half_word = "top" if half == "Top" else "bottom"
        if runs == 0:
            return f"A scoreless {half_word} of the {ordinal(inning)}."
        return (f"{runs} run{'s' if runs != 1 else ''} on {hits} "
                f"hit{'s' if hits != 1 else ''} in the {half_word} of the "
                f"{ordinal(inning)}.")

    def game_recap(self, summary, top_play=None):
        home, away = summary.get("home_team", "Home"), summary.get("away_team", "Away")
        hs, as_ = summary.get("home_final", 0), summary.get("away_final", 0)
        winner, loser = (home, away) if hs >= as_ else (away, home)
        ws, ls = (hs, as_) if hs >= as_ else (as_, hs)
        line = f"{winner} beat {loser} {ws}-{ls}."
        if top_play is not None:
            line += " " + self.play_line(top_play)
        return line
