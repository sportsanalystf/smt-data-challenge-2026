"""
analyze.py
----------
Turns the extracted play-level features into the Top-10 scoreboard products:
attributes each play to a real player via lineups, builds season leaderboards,
fits the catch-probability model (the flagship "Robbery Meter"), and writes
leaderboard CSVs + figures.

Run:  python analyze.py <data_root> <features_dir> <out_dir>
"""
import sys
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = sys.argv[1]
FEAT = sys.argv[2]
OUT = sys.argv[3]
LB = os.path.join(OUT, "leaderboards")
FIG = os.path.join(OUT, "figures")
os.makedirs(LB, exist_ok=True)
os.makedirs(FIG, exist_ok=True)

GREEN = "#0b6b3a"
ACCENT = "#c8102e"
plt.rcParams.update({"figure.dpi": 130, "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False})

POS_COL = {1: "pitcher", 2: "catcher", 3: "first_baseman", 4: "second_baseman",
           5: "third_baseman", 6: "shortstop", 7: "left_fielder",
           8: "center_fielder", 9: "right_fielder", 10: "batter"}

# ---------------------------------------------------------------- lineups
lu = pd.read_csv(os.path.join(DATA, "lineups.csv"))
lu = lu.drop_duplicates(subset=["game_string", "play_per_game"])
lu_key = lu.set_index(["game_string", "play_per_game"])


def attach_player(df, pos_col_name, play_col="play"):
    """Merge a player code onto df using (game_string, play) -> lineup column."""
    m = lu[["game_string", "play_per_game", pos_col_name]].rename(
        columns={"play_per_game": play_col, pos_col_name: "player"})
    out = df.merge(m, on=["game_string", play_col], how="left")
    out["team"] = out["player"].str.split("-").str[0]
    return out


def save_lb(df, name):
    df.to_csv(os.path.join(LB, name), index=False)
    return df


# ---------------------------------------------------------------- load features
hits = pd.read_csv(os.path.join(FEAT, "hits_v2.csv"))
hits = hits.rename(columns={"carry_ft": "hit_distance_ft"})
pitches = pd.read_csv(os.path.join(FEAT, "pitches.csv"))
throws = pd.read_csv(os.path.join(FEAT, "throws.csv"))
sprints = pd.read_csv(os.path.join(FEAT, "sprints.csv"))
catches = pd.read_csv(os.path.join(FEAT, "catches.csv"))
print("loaded", {k: len(v) for k, v in
                 dict(hits=hits, pitches=pitches, throws=throws,
                      sprints=sprints, catches=catches).items()})

# ======================================================================
# IDEA 1 - BURNER BOARD (sprint speed to first)
# ======================================================================
s = attach_player(sprints, "batter")
s = s.dropna(subset=["player"])
burner = (s.groupby("player")
          .agg(top_sprint_mph=("sprint_mph", "max"),
               avg_sprint_mph=("sprint_mph", "mean"),
               runs=("sprint_mph", "size"), team=("team", "first"))
          .reset_index())
burner = burner[burner.runs >= 3].sort_values("top_sprint_mph", ascending=False)
burner["avg_sprint_mph"] = burner.avg_sprint_mph.round(2)
save_lb(burner.head(50), "01_burner_board_sprint_speed.csv")

# ======================================================================
# IDEA 2 - STATCAST SMASH (exit velocity)
# ======================================================================
h = attach_player(hits, "batter").dropna(subset=["player"])
smash = (h.groupby("player")
         .agg(max_exit_velo=("exit_velo_mph", "max"),
              p90_exit_velo=("exit_velo_mph", lambda x: round(np.percentile(x, 90), 1)),
              balls=("exit_velo_mph", "size"), team=("team", "first"))
         .reset_index())
smash = smash[smash.balls >= 5].sort_values(
    ["p90_exit_velo", "max_exit_velo"], ascending=False)
save_lb(smash.head(50), "02_statcast_smash_exit_velo.csv")

# ======================================================================
# IDEA 3 - MOONSHOT METER (hit distance, fly balls)
# ======================================================================
fly = h[(h.launch_deg >= 10) & (h.hit_distance_ft >= 150)]
moon = (fly.groupby("player")
        .agg(max_distance_ft=("hit_distance_ft", "max"),
             flies=("hit_distance_ft", "size"), team=("team", "first"))
        .reset_index())
moon = moon[moon.flies >= 3].sort_values("max_distance_ft", ascending=False)
save_lb(moon.head(50), "03_moonshot_meter_distance.csv")
# top single moonshots (fly already carries player/team from attach_player)
top_shots = fly.sort_values("hit_distance_ft", ascending=False).head(30)
save_lb(top_shots[["game_string", "play", "player", "team", "exit_velo_mph",
                   "launch_deg", "hit_distance_ft"]], "03b_top_single_moonshots.csv")

# ======================================================================
# IDEA 4 - BARREL ZONE (EV x launch sweet spot)
# ======================================================================
# "Barrel": EV >= 95 mph and launch angle 20-35 deg (classic sweet spot)
h["is_barrel"] = ((h.exit_velo_mph >= 95) &
                  (h.launch_deg.between(20, 35))).astype(int)
barrel = (h.groupby("player")
          .agg(barrels=("is_barrel", "sum"), balls=("is_barrel", "size"),
               team=("team", "first")).reset_index())
barrel["barrel_rate_pct"] = (100 * barrel.barrels / barrel.balls).round(1)
barrel = barrel[barrel.balls >= 8].sort_values(
    ["barrels", "barrel_rate_pct"], ascending=False)
save_lb(barrel.head(50), "04_barrel_zone.csv")

# ======================================================================
# IDEA 5 - RADAR GUN LIVE (pitch velocity)
# ======================================================================
# drop implausible single-frame spikes (elite MiLB fastballs top out ~103 mph)
pitches = pitches[pitches.pitch_velo_mph <= 103]
p = attach_player(pitches, "pitcher").dropna(subset=["player"])
radar = (p.groupby("player")
         .agg(max_pitch_velo=("pitch_velo_mph", "max"),
              avg_pitch_velo=("pitch_velo_mph", "mean"),
              pitches=("pitch_velo_mph", "size"), team=("team", "first"))
         .reset_index())
radar = radar[radar.pitches >= 30].sort_values("max_pitch_velo", ascending=False)
radar["avg_pitch_velo"] = radar.avg_pitch_velo.round(1)
save_lb(radar.head(50), "05_radar_gun_pitch_velo.csv")

# ======================================================================
# IDEA 6 & 5b - OUTFIELD CANNONS (arm strength) -> use throws
# ======================================================================
def throw_player(row):
    key = (row.game_string, row.play)
    col = POS_COL.get(int(row.fielder_id))
    if key in lu_key.index and col:
        return lu_key.loc[key, col]
    return None

throws["player"] = throws.apply(throw_player, axis=1)
throws["team"] = throws.player.str.split("-").str[0]
throws["pos"] = throws.fielder_id.map(POS_COL)
cannon = (throws.dropna(subset=["player"]).groupby(["player"])
          .agg(max_throw_velo=("throw_velo_mph", "max"),
               avg_throw_velo=("throw_velo_mph", "mean"),
               throws=("throw_velo_mph", "size"),
               pos=("pos", "first"), team=("team", "first")).reset_index())
cannon = cannon[cannon.throws >= 3].sort_values("max_throw_velo", ascending=False)
cannon["avg_throw_velo"] = cannon.avg_throw_velo.round(1)
save_lb(cannon.head(50), "06_outfield_cannons_arm_strength.csv")

# ======================================================================
# IDEA 7 - THE ROBBERY METER (catch probability model)  [FLAGSHIP]
# ======================================================================
c = catches.copy()
c = c[(c.hang_s > 0.4) & (c.route_ft >= 0) & (c.route_ft < 160)].copy()
c["req_speed"] = (c.route_ft / c.hang_s).clip(0, 45)   # ft/s needed to arrive
# Features
X = c[["route_ft", "hang_s", "req_speed"]].to_numpy(float)
y = c["catch_made"].to_numpy(float)
mu, sd = X.mean(0), X.std(0)
Xs = (X - mu) / sd
Xd = np.hstack([np.ones((len(Xs), 1)), Xs])


def fit_logistic(Xd, y, l2=1.0, iters=500, lr=0.3):
    w = np.zeros(Xd.shape[1])
    n = len(y)
    for _ in range(iters):
        z = Xd @ w
        pr = 1 / (1 + np.exp(-z))
        grad = Xd.T @ (pr - y) / n + l2 * np.r_[0, w[1:]] / n
        w -= lr * grad
    return w


w = fit_logistic(Xd, y)
c["catch_prob"] = 1 / (1 + np.exp(-(Xd @ w)))
# in-sample accuracy / calibration
pred = (c.catch_prob >= 0.5).astype(int)
acc = (pred == c.catch_made).mean()
brier = np.mean((c.catch_prob - c.catch_made) ** 2)
base = c.catch_made.mean()
print(f"catch model: n={len(c)} base_catch_rate={base:.3f} acc={acc:.3f} brier={brier:.3f}")
with open(os.path.join(LB, "_model_summary.txt"), "w") as f:
    f.write(f"Catch Probability Model (logistic regression, numpy)\n")
    f.write(f"features: route_ft, hang_s, req_speed (standardized)\n")
    f.write(f"n_opportunities={len(c)}  base_catch_rate={base:.3f}\n")
    f.write(f"accuracy={acc:.3f}  brier_score={brier:.3f}\n")
    f.write(f"weights(bias,route,hang,req)={np.round(w,3).tolist()}\n")

# attach fielder identity
def catch_player(row):
    key = (row.game_string, row.play)
    col = POS_COL.get(int(row.fielder_id))
    if key in lu_key.index and col:
        return lu_key.loc[key, col]
    return None

c["player"] = c.apply(catch_player, axis=1)
c["team"] = c.player.str.split("-").str[0]
c["pos"] = c.fielder_id.map(POS_COL)
c["oae"] = c.catch_made - c.catch_prob   # outs above expected per play
c.to_csv(os.path.join(LB, "_catch_opportunities_scored.csv"), index=False)

# Fielder Outs Above Expected leaderboard
oae = (c.dropna(subset=["player"]).groupby("player")
       .agg(opportunities=("oae", "size"),
            catches_made=("catch_made", "sum"),
            expected=("catch_prob", "sum"),
            oae=("oae", "sum"), pos=("pos", "first"),
            team=("team", "first")).reset_index())
oae = oae[oae.opportunities >= 12]
oae["expected"] = oae.expected.round(1)
oae["oae"] = oae.oae.round(2)
oae = oae.sort_values("oae", ascending=False)
save_lb(oae, "07_robbery_meter_outs_above_expected.csv")

# Web Gems: catches MADE with the lowest catch probability (unlikeliest plays)
gems = c[c.catch_made == 1].copy()
gems["robbery_score"] = (100 * (1 - gems.catch_prob)).round(1)
gems = gems.sort_values("catch_prob").head(40)
save_lb(gems[["game_string", "play", "player", "team", "pos", "route_ft",
              "hang_s", "req_speed", "catch_prob", "robbery_score"]],
        "07b_web_gems_unlikeliest_catches.csv")

# ======================================================================
# IDEA 8 - CATCH OR NO CATCH? (fan-vote suspense plays: prob ~ 0.5)
# ======================================================================
c["suspense"] = 1 - (2 * (c.catch_prob - 0.5)).abs()   # 1 at p=.5
vote = c.dropna(subset=["player"]).sort_values("suspense", ascending=False).head(40)
save_lb(vote[["game_string", "play", "player", "team", "pos", "route_ft",
              "hang_s", "catch_prob", "catch_made", "suspense"]],
        "08_catch_or_no_catch_game.csv")

# ======================================================================
# IDEA 9 - GROUND CREW RANGE (ground covered on catches)
# ======================================================================
made = c[c.catch_made == 1]
range_lb = (made.dropna(subset=["player"]).groupby("player")
            .agg(avg_route_ft=("route_ft", "mean"),
                 max_route_ft=("route_ft", "max"),
                 top_closing_ftps=("close_ftps", "max"),
                 catches=("route_ft", "size"),
                 pos=("pos", "first"), team=("team", "first")).reset_index())
range_lb = range_lb[range_lb.catches >= 8]
range_lb["avg_route_ft"] = range_lb.avg_route_ft.round(1)
range_lb["top_closing_mph"] = (range_lb.top_closing_ftps * 0.681818).round(1)
range_lb = range_lb.sort_values("avg_route_ft", ascending=False)
save_lb(range_lb, "09_ground_crew_range.csv")

# ======================================================================
# IDEA 10 - FIVE-TOOL SCORE (composite percentile: speed, power, arm)
# ======================================================================
def pctile_map(series):
    r = series.rank(pct=True) * 100
    return r

spd = burner[["player", "top_sprint_mph"]].copy()
pwr = smash[["player", "max_exit_velo"]].copy()
arm = cannon[["player", "max_throw_velo"]].copy()
five = spd.merge(pwr, on="player", how="outer").merge(arm, on="player", how="outer")
five["speed_pct"] = pctile_map(five.top_sprint_mph)
five["power_pct"] = pctile_map(five.max_exit_velo)
five["arm_pct"] = pctile_map(five.max_throw_velo)
tools = five[["speed_pct", "power_pct", "arm_pct"]]
five["tools_available"] = tools.notna().sum(1)
five["five_tool_score"] = tools.mean(axis=1).round(1)
five["team"] = five.player.str.split("-").str[0]
five = five[five.tools_available >= 2].sort_values("five_tool_score", ascending=False)
save_lb(five.head(50), "10_five_tool_score.csv")

# ======================================================================
# FIGURES
# ======================================================================
# Fig A: catch probability surface (prob vs route for several hang times)
fig, ax = plt.subplots(figsize=(7, 4.4))
routes = np.linspace(0, 130, 120)
for hang in [2.0, 3.0, 4.0, 5.0]:
    req = np.clip(routes / hang, 0, 45)
    Xg = np.column_stack([routes, np.full_like(routes, hang), req])
    Xg = (Xg - mu) / sd
    Xg = np.hstack([np.ones((len(Xg), 1)), Xg])
    pr = 1 / (1 + np.exp(-(Xg @ w)))
    ax.plot(routes, pr, lw=2.4, label=f"{hang:.0f} s hang time")
ax.set_xlabel("Route distance to the ball (ft)")
ax.set_ylabel("Catch probability")
ax.set_title("The Robbery Meter — Catch Probability Model", fontweight="bold", color=GREEN)
ax.legend(title="Hang time", frameon=False)
ax.set_ylim(0, 1.02)
ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_catch_probability_model.png")); plt.close(fig)

# Fig B: Burner board top 15
top = burner.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 5))
ax.barh(top.player, top.top_sprint_mph, color=GREEN)
for yi, (v) in enumerate(top.top_sprint_mph):
    ax.text(v + .05, yi, f"{v:.1f}", va="center", fontsize=9)
ax.set_xlabel("Top sprint speed (mph)")
ax.set_title("Burner Board — Fastest to First", fontweight="bold", color=GREEN)
ax.set_xlim(top.top_sprint_mph.min() - 1, top.top_sprint_mph.max() + 1)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_burner_board.png")); plt.close(fig)

# Fig C: exit velo distribution with top marked
fig, ax = plt.subplots(figsize=(7, 4.2))
ax.hist(hits.exit_velo_mph, bins=40, color=GREEN, alpha=.8)
ax.axvline(hits.exit_velo_mph.quantile(.99), color=ACCENT, lw=2,
           label=f"99th pct = {hits.exit_velo_mph.quantile(.99):.0f} mph")
ax.set_xlabel("Exit velocity (mph)"); ax.set_ylabel("Batted balls")
ax.set_title("Statcast Smash — Exit Velocity Distribution", fontweight="bold", color=GREEN)
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_exit_velo_dist.png")); plt.close(fig)

# Fig D: OAE leaderboard
o = oae.head(12).iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 5))
colors = [GREEN if v >= 0 else ACCENT for v in o.oae]
ax.barh(o.player + "  (" + o.pos.str[:2].str.upper() + ")", o.oae, color=colors)
ax.axvline(0, color="k", lw=.8)
ax.set_xlabel("Outs Above Expected (season)")
ax.set_title("Robbery Meter — Best Defenders (OAE)", fontweight="bold", color=GREEN)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_oae_leaderboard.png")); plt.close(fig)

# Fig E: pitch velo distribution
fig, ax = plt.subplots(figsize=(7, 4.2))
ax.hist(pitches.pitch_velo_mph, bins=40, color="#1f4e79", alpha=.85)
ax.set_xlabel("Pitch velocity (mph)"); ax.set_ylabel("Pitches")
ax.set_title("Radar Gun Live — Pitch Velocity Distribution", fontweight="bold", color=GREEN)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig_pitch_velo_dist.png")); plt.close(fig)

print("DONE. leaderboards + figures written to", OUT)
print("web gem #1:", gems.iloc[0][["game_string","play","player","catch_prob","route_ft","hang_s"]].to_dict())
