# Architecture — Real-Time Baseball Storytelling Engine

SMT Data Challenge 2026 · *On the Big Screen!*

This document explains how the system is put together, why each layer exists,
and what was reused from the original project rather than rewritten.

---

## 1. Design principle

The engine is built as a **one-directional stack**. Every layer depends only on
the layers above it, and never the reverse:

```
   dataio      read the SMT tables
      ↓
   tracking    geometry + kinematics from 20 Hz positions
      ↓
   state       reconstruct outs / runs / score  ← the foundation
      ↓
   analytics   run expectancy, win probability, leverage, WPA, highlight score
      ↓
   probability zone, contact, catch, baserunning models
      ↓
   cards       fan-facing story cards (pure data, no drawing)
      ↓
   narrative   broadcast sentences        highlights   auto-generated reels
      ↓                                        ↓
   viz (PNG)                              web (interactive HTML)
```

Why it matters: `state` knows nothing about visualization, and a story card
knows nothing about how it will be drawn. That is what allows the *same* card
to appear as a PNG in the written paper, a panel on a stadium scoreboard, and a
tile in the HTML dashboard — and it is what makes each piece independently
testable.

---

## 2. What was reused from the original project

The extension deliberately **wraps** the existing code rather than replacing it:

| Original file | How it is reused now |
|---|---|
| `code/smt_utils.py` | Still the single source of truth for base coordinates, game listing/loading, and speed differencing. `smtstory/config.py` puts it on the path; `tracking/` and `dataio/` delegate to it. |
| `code/extract_features.py` | Its outputs (`hits`, `sprints`, `catches`, `throws`) are consumed directly by the probability stage — no re-extraction. |
| `code/analyze.py` (catch model) | Re-expressed as `probability/catch.py` with identical features and methodology, now behind the shared model interface. |
| `code/plot_webgem.py` | Its field-drawing approach became `viz/field.py::field_axes`, reused by every field graphic. |

Nothing from the original submission was deleted; the first-round deliverables
still build and run.

---

## 3. The foundation: game state reconstruction

**The problem.** The SMT data has base occupancy, but **no outs, no count, and
no score**. Win Probability, Leverage, Run Expectancy and WPA are all functions
of `(inning, half, outs, base state, score differential)`. Without state, none
of them exist. This was the blocking gap, and solving it is the core technical
contribution of the extension.

**The method.** For each half-inning we walk the at-bats and apply an accounting
identity. Everyone on base before the play, plus the batter, must end up in
exactly one of three places — still on base, across the plate, or retired:

```
|B| + 1  =  |A|  +  runs  +  outs
```

`|B|` and `|A|` are observed from the lineup table. Whether the batter reached is
inferred from the next at-bat's occupancy. The half-inning must total three
outs, which closes the system.

**Three corrections that mattered**, each found by validating against real
baseball rates:

1. **Do not double-count the batter.** The first implementation subtracted the
   batter twice and produced a 31–28 final score.
2. **Do not apply the identity to the last at-bat of a half-inning.** There is
   no observed "after" state, so runners left on base would be
   indistinguishable from runs. Stranded runners were being scored.
3. **Only the terminal play decides the outcome.** A foul ball shares event
   code 4 with a live batted ball, so any walk that followed a foul was being
   recorded as a single. Fixing this moved walks from 5.4/game to 9.3/game.

Additionally, a **physical plausibility constraint** (`max_plausible_runs`)
prevents phantom runs from player substitutions: a runner on first cannot score
on an infield out, and a batter who was retired cannot drive in a runner from
first.

**Validation.** Two independent estimates bracket the truth:

| Quantity | Value | Real MiLB reference |
|---|---|---|
| Runs per game (reconstruction) | **10.12** | ≈ 9.5 |
| Hits per game | **19.7** | ≈ 18 |
| Walks per game | 9.3 | ≈ 7 |
| Half-innings balancing to 3 outs | **99.8 %** | 100 % |
| State anomalies (quarantined) | 0.27 % | — |

`state/validate.py` provides the second, physically independent estimate: it
watches 20 Hz player tracking and counts runners whose closest approach to home
plate falls inside 8 feet. That detector is a **lower bound** (tracking stops at
end-of-play, so runners who score after the whistle are missed), and it returns
~7.7 runs/game. The truth sits between the two, close to the reconstruction.

**Honest limits.** Reaching on an error and a fielder's choice are not
distinguishable from a single by occupancy alone, which is why hits run ~10 %
high. Every at-bat carries a `confidence` flag and a `state_anomaly` flag, and
downstream models filter on them.

---

## 4. Core analytics

| Component | Method | Result |
|---|---|---|
| **Run Expectancy** | Empirical 24-state matrix (8 base states × 3 out states), fit on balanced half-innings only | 0.585 runs bases-empty/0-out → 2.087 loaded/0-out; strictly monotonic in outs |
| **Win Probability** | Logistic model on score differential, innings remaining, their interaction, outs, state run expectancy, and home-half indicator | accuracy **0.774**, Brier **0.144**, log-loss 0.433 (n = 18,834) |
| **WPA** | `WP(after) − WP(before)`, with the half-inning flip handled explicitly (when sides change, win probability becomes its complement) | mean \|WPA\| = 0.034; largest swings are walk-off home runs (+0.84) |
| **Leverage Index** | Expected \|ΔWP\| over the league outcome mix, normalized so the average plate appearance = 1.0 | mean **1.000**, p95 2.62, max 8.23 |
| **Clutch Score** | Leverage-weighted \|WPA\|, compressed with `tanh` so one enormous play doesn't flatten the leaderboard | 0–100 |

A logistic model was chosen over an empirical lookup because 250 games cannot
fill an (inning × base-out × score-margin) grid; a lookup produces jagged,
non-monotonic probabilities that look broken on a scoreboard.

**Performance note.** Leverage requires one win-probability evaluation per
possible outcome per plate appearance — ~113k model calls per season. Row-wise
with pandas this took minutes; the vectorized NumPy path
(`predict_array`) reduced the whole analytics stage to **~5 seconds**, which is
what makes the metric viable for a live feed.

---

## 5. The Highlight Score

The component that decides what goes on the big screen. It fuses game
importance with physical spectacle, because fans respond to both:

```
HighlightScore = 100 × Σ(wᵢ · sᵢ) / Σ(wᵢ)
```

Every component is mapped to a common 0–1 excitement scale before combining, so
mph, feet and probabilities can be weighed honestly. **Components missing for a
play are dropped and the weights renormalize** — a play is never penalized for
lacking a measurement. Weights live in one dictionary
(`HIGHLIGHT_WEIGHTS`) so a club can retune its scoreboard's personality without
touching code.

Validation: the season's top-scoring moments are walk-off home runs in extra
innings and game-ending outs at leverage 4.8–8.2 — exactly what a human editor
would choose.

---

## 6. Live probability engine

All four models share one dependency-free logistic implementation
(`probability/base.py`), so every probability in the system is fit, regularized
and reported identically.

| Model | Labels | Quality |
|---|---|---|
| Catch (Robbery Meter) | catch made / not made | acc 0.955, **AUC 0.954** |
| Home run \| contact | reconstructed outcome | acc 0.951, **AUC 0.942** |
| Extra-base hit \| contact | reconstructed outcome | acc 0.877, AUC 0.855 |
| Hit \| contact | reconstructed outcome | acc 0.683, AUC 0.734 |
| Ball in play \| location | event stream | acc 0.873, AUC 0.687 |

**Scope honesty.** Two requested probabilities are *not* offered as models,
because the data cannot supervise them and inventing them would be dishonest:

- **Called strike probability** — there are no umpire calls in the data. Instead
  the engine reports a geometric `in_zone` flag with the zone's vertical bounds
  **calibrated from the data** (z = 0 is a datum, not the ground), plus a
  genuinely supervised P(ball in play | location).
- **Stolen base / pickoff probability** — no steal, caught-stealing, or pickoff
  outcome labels exist. The Pickoff Jump and Lead Distance cards therefore use
  *measured* lead distance from tracking instead of a fabricated probability.
- **Spin rate** — not recoverable from positional tracking. Pitch *movement*
  (deviation from a straight-line path) is measurable and is used instead.

---

## 7. Story cards

A card is the atomic unit of the fan experience: one idea, one number, one
sentence, one graphic. Each implements two methods:

```python
applies(ctx) -> bool          # should this fire for this play?
build(ctx)   -> CardPayload   # the numbers and words to show
```

The **registry auto-surfaces** cards: given a play it asks every card whether it
applies and returns those that do, ranked by priority. That is the mechanism
behind "the right graphic appears at the right moment". A card that raises an
exception is skipped — a single bad card can never take down the scoreboard.

30 cards ship across six categories: `speed`, `power`, `pitching`, `defense`,
`fan`, `story`. Fan-vote cards gate on **model uncertainty** — a question the
crowd gets right 95 % of the time is not a game, so "Catch or No Catch?" only
fires when catch probability is between 0.25 and 0.75.

---

## 8. Narrative generation

Template-based, not a language model: it must be deterministic, instant, and
incapable of saying something false about the game. Four rules, taken from how
broadcasts actually sound:

1. One idea per sentence.
2. Lead with the number that surprised you.
3. Never print a raw metric name — "leverage index 5.8" means nothing in
   section 112; "this at-bat matters almost six times more than normal" means
   everything.
4. Compare, don't just state.

---

## 8b. Making every play watchable

The scoreboard's job is not only to say *what* happened but to let a fan *see*
it. Three modules turn each at-bat into something you can click and watch, with
the analysis matched to how the play actually ended.

### Pitch tunneling (`analytics/tunneling.py`)

When an at-bat ends in a strikeout there is nothing to see on the field — but
the most interesting question just got answered: *was that unhittable pitching,
or a bad swing?*

Each pitch has ~10–12 tracked frames between release (y ≈ 55 ft) and the plate.
We fit **quadratics** to x(y) and z(y) — exactly right, since under constant
acceleration position is quadratic in flight distance — which lets us evaluate
the trajectory at any distance.

| Quantity | How it is derived |
|---|---|
| **Extension** | 60.5 − release_y, measured directly (release varied 3.3–8.9 ft in the sample at-bat) |
| **Effective velocity** | speed rescaled by actual flight distance vs league-average extension |
| **Tunnel ratio** | separation at the plate ÷ separation at the **commit point** (23.8 ft, ~175 ms out, where a hitter must decide) |
| **Induced vertical break** | deviation from the naive straight line **minus the gravity component** |

That last row matters. Gravity alone drops a 90 mph pitch ~39 inches; reporting
it as "movement" would make every pitch look filthy and tell a fan nothing. The
first implementation did exactly that and produced 22–46 inch "breaks" on every
pitch. After subtracting gravity, the numbers separate pitch types cleanly:

```
 velo   extension   induced VB   horiz   flight
 91.9      5.67       +19.3      -13.6   0.437   <- riding fastball
 77.7      6.82        +4.1       -4.9   0.507   <- breaking ball
```

A **nastiness** score (velocity, late break, edge proximity, tunnel ratio)
drives a three-way verdict: `NASTY PITCH` / `WELL EXECUTED` / `HITTER MISSED IT`.
The narration only cites evidence consistent with its verdict, so it can never
praise a pitch's movement while calling it hittable.

### Play anatomy (`playanatomy/anatomy.py`)

For balls in play, the anatomy engine measures who fielded it, how far they
went, how quickly they transferred and threw, and how close the play was:

| Play type | Sample season values |
|---|---|
| ground out | 16 ft route, 2.5 s to the ball |
| line out | 26 ft, 2.6 s |
| fly out | 67 ft, 5.1 s |
| base hit | 49 ft, 4.3 s |

plus transfer time (1.25 s average), throw velocity (66 mph average, 91 max),
route efficiency, double-play pivot time, and catcher pop time. A **close-play**
calculator compares when the throw would arrive against when the runner did,
producing a SAFE/OUT margin and a `bang_bang` flag that triggers the crowd vote.

A bug worth recording: foul balls share event code 4 with live batted balls, so
a caught foul tip was initially dissected as a ground out in which the catcher
"fielded" the ball 180 seconds after contact. Classification now runs through
`is_live_contact`, and a 12-second guard rejects any ball retrieved after the
play was already dead.

### Replay export (`playback/exporter.py`)

A full game of player tracking is ~350,000 rows — over 30 MB as naive JSON.
Three decisions bring the whole game down to **1.4 MB**: frames as arrays rather
than objects, one-decimal precision (finer is invisible at scoreboard scale),
and trimming to the live-ball window. The browser interpolates between 20 Hz
samples for smooth 60 fps playback, and ball height is carried so a fly ball
reads as airborne rather than as a dot sliding across a map.

### League baselines (`analytics/baselines.py`)

A number becomes a story only when compared. Season distributions for sprint
speed, exit velocity, pitch and throw velocity, and route distance convert any
measurement into a percentile and a scouting grade, so the panel can say
"faster than 84% of the league" instead of "20.1 mph".

---

## 9. Output layers

- **`viz/` (PNG)** — dark panels, one enormous number per graphic, no thin
  gridlines; designed to be read from 300 feet in daylight in about seven
  seconds. Includes win probability, leverage, momentum, spray charts, field
  overlays, attack-zone heat maps, and rendered story cards.
- **`web/dashboard.py` (HTML)** — one self-contained file with the game embedded
  as JSON and all CSS/JS inline. No server, no build step, no network. It
  replays a real game play-by-play with live win probability, auto-surfacing
  cards, and fan votes.
- **`web/replay.py` — the Play Explorer.** The same idea taken further: every
  at-bat is clickable and *watchable*. Three views share one stage —
  **Field Replay** (ball and all nine fielders animating from tracking, ball
  size scaling with height, event flashes for CONTACT / FIELDED / THROW),
  **Pitch Tunnel** (every pitch of the at-bat drawn from the catcher's angle and
  in profile, with the commit-point line that makes tunneling visible), and
  **Win Probability**. The analysis panel adapts to the play type, and each
  measurement is shown against its league percentile.

---

## 10. Testing

`tests/test_engine.py` runs without pytest and asserts **invariants** rather
than golden values, so it survives model retuning while still catching real
bugs:

- a half-inning can never contain four outs; `outs_before ∈ [0, 2]`
- runs are non-negative; scores are non-decreasing within a game
- run expectancy strictly decreases as outs increase, for every base state
- all probabilities lie in [0, 1]; P(home run) ≤ P(hit); mean leverage ≈ 1.0
- the Web Gem card fires on an improbable catch and *not* on a routine one
- the card registry survives NaN/None input

This suite caught the illegal-out-count bug that occupancy ambiguity introduced;
those at-bats are now clamped and quarantined (0.27 % of the season).

---

## 11. Running it

```bash
export SMT_DATA_ROOT=/path/to/SMT-Data-Challenge-2026
python pipeline/run_all.py                      # everything, ~4 minutes
python pipeline/run_all.py --skip-pitch-locations   # ~30 seconds if cached
python tests/test_engine.py
```

Stage outputs land in `outputs/engine/` (tables, models, JSON),
`outputs/engine_figures/` (PNG), and `outputs/scoreboard_dashboard.html`.
