"""
outcomes.py — classify what happened in a single at-bat.

The SMT data does not label plate-appearance outcomes, so we infer them from
two independent signals:

  1. Base-occupancy transitions in `lineups` (where did the batter end up?)
  2. The ball-event stream (was the ball hit? did it leave the yard? who
     fielded it, and where?)

Using both is what makes the inference robust: occupancy tells us the result,
events tell us the manner. Each outcome carries a `confidence` flag so any
downstream metric can filter on well-identified plays.
"""
from dataclasses import dataclass, field

from .. import config

EV = config.EVENT


@dataclass
class Outcome:
    """The inferred result of one at-bat."""
    kind: str                  # 'home_run','triple','double','single','walk_hbp',
                               # 'out','fielders_choice','unknown'
    batter_dest: int           # 0 = out/not on base, 1..3 = base reached, 4 = scored
    bases_gained: int = 0      # for the batter
    ball_in_play: bool = False
    outs_recorded: int = 0     # filled in by the reconstructor (needs constraints)
    runs_scored: int = 0       # filled in by the reconstructor
    confidence: str = "high"   # 'high' | 'medium' | 'low'
    detail: dict = field(default_factory=dict)

    @property
    def is_hit(self):
        return self.kind in ("single", "double", "triple", "home_run")

    @property
    def on_base(self):
        return self.batter_dest > 0


def _events_for_atbat(events, plays):
    return events[events.play_per_game.isin(plays)]


# Events that indicate the ball was actually fielded / stayed live after contact.
LIVE_BALL_CODES = {EV["ACQUIRED"], EV["THROW"], EV["ACQUIRED_UNK"],
                   EV["THROW_UNK"], EV["DEFLECTION"], EV["DEFLECTION_WALL"],
                   EV["BOUNCE"]}


def terminal_play_events(events, plays):
    """Events belonging to the LAST play of the at-bat.

    This matters: a foul ball shares event code 4 ("hit into play") with a live
    batted ball, so an at-bat containing any foul would otherwise look like a
    ball in play. Only the final play determines the outcome.
    """
    if not plays:
        return events.iloc[0:0]
    last = max(plays)
    return events[events.play_per_game == last].sort_values("timestamp")


def is_live_contact(term_events):
    """True if the terminal play was a batted ball that stayed live.

    A foul ball registers as contact followed immediately by end-of-play with no
    fielder ever touching it; a live ball is fielded, bounces, or leaves the yard.
    """
    codes = term_events.ball_eventcode.astype(int).tolist()
    if EV["HOME_RUN"] in codes:
        return True
    if EV["HIT_INTO_PLAY"] not in codes:
        return False
    hit_idx = codes.index(EV["HIT_INTO_PLAY"])
    after = codes[hit_idx + 1:]
    return any(c in LIVE_BALL_CODES for c in after)


def classify_atbat(events, plays, batter, dest_base, next_batter_seen):
    """Infer the outcome of one at-bat.

    Parameters
    ----------
    events : DataFrame        ball-events for the whole game
    plays  : list[int]        play_per_game values belonging to this at-bat
    batter : str              batter player code
    dest_base : int or None   base the batter occupies at the next at-bat
                              (None = not on base afterwards)
    next_batter_seen : bool   whether a subsequent at-bat exists in this half
    """
    term = terminal_play_events(events, plays)
    codes = set(term.ball_eventcode.astype(int).tolist())

    # Only the terminal play decides the outcome (see is_live_contact).
    ball_in_play = is_live_contact(term)
    is_hr = EV["HOME_RUN"] in codes

    # Home run: explicit event code, or the batter vanished after putting a ball
    # in play with no fielder ever acquiring it.
    if is_hr:
        return Outcome(kind="home_run", batter_dest=4, bases_gained=4,
                       ball_in_play=True, confidence="high",
                       detail={"event": "home_run_code"})

    if dest_base is not None and dest_base > 0:
        if not ball_in_play:
            # Reached without putting the ball in play -> walk or hit-by-pitch.
            return Outcome(kind="walk_hbp", batter_dest=dest_base,
                           bases_gained=dest_base, ball_in_play=False,
                           confidence="high" if dest_base == 1 else "medium")
        kind = {1: "single", 2: "double", 3: "triple"}.get(dest_base, "single")
        return Outcome(kind=kind, batter_dest=dest_base, bases_gained=dest_base,
                       ball_in_play=True, confidence="high")

    # Batter is not on base at the next at-bat.
    if not next_batter_seen:
        # Half-inning ended on this at-bat: almost always the third out, but the
        # batter could also have reached on a play that ended the inning
        # elsewhere. Treated as an out with medium confidence.
        return Outcome(kind="out", batter_dest=0, ball_in_play=ball_in_play,
                       confidence="medium", detail={"reason": "inning_ended"})

    return Outcome(kind="out", batter_dest=0, ball_in_play=ball_in_play,
                   confidence="high")
