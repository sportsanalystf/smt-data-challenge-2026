"""
dashboard.py — generates a self-contained interactive scoreboard.

The output is ONE .html file with the game data embedded as JSON and all
styling and behaviour inline. No server, no build step, no network: a club can
drop it on a control-room laptop, or a judge can double-click it.

It replays a real game the way a scoreboard would experience it: play by play,
with win probability updating live, story cards surfacing automatically when
they apply, and a fan-vote prompt appearing on genuinely uncertain plays.
"""
import json
import os

import numpy as np
import pandas as pd

from .. import config
from ..cards import default_registry, PlayContext
from ..narrative import NarrativeGenerator


def _safe(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if not np.isfinite(f) else round(f, 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return v


def build_play_feed(game, registry=None, narrator=None, max_cards=3):
    """Turn a scored game into the JSON feed the dashboard consumes."""
    registry = registry or default_registry()
    narrator = narrator or NarrativeGenerator({
        "max_exit_velo_game": game.exit_velo_mph.max()
        if "exit_velo_mph" in game.columns else None,
        "max_pitch_velo_game": game.pitch_velo_mph.max()
        if "pitch_velo_mph" in game.columns else None,
    })

    feed = []
    for row in game.to_dict("records"):
        clean = {k: _safe(v) for k, v in row.items()}
        ctx = PlayContext(clean)
        cards = [c.to_dict() for c in registry.surface(ctx, limit=max_cards)]
        wp_home = (clean.get("wp_after") if clean.get("half_inning") == "Bottom"
                   else (1.0 - clean.get("wp_after"))
                   if clean.get("wp_after") is not None else None)
        feed.append({
            "inning": clean.get("inning"),
            "half": clean.get("half_inning"),
            "batter": clean.get("batter"),
            "pitcher": clean.get("pitcher"),
            "outcome": clean.get("outcome"),
            "runs": clean.get("runs") or 0,
            "outs_before": clean.get("outs_before"),
            "base_state": clean.get("base_state_before"),
            "home_score": clean.get("home_score_after"),
            "away_score": clean.get("away_score_after"),
            "wp_home": _safe(wp_home),
            "wpa": clean.get("wpa"),
            "leverage": clean.get("leverage_index"),
            "highlight": clean.get("highlight_score"),
            "situation": narrator.situation_line(clean),
            "narrative": narrator.play_line(clean),
            "insights": narrator.insight_lines(clean),
            "cards": cards,
            "metrics": {k: clean.get(k) for k in
                        ("exit_velo_mph", "launch_deg", "hit_distance_ft",
                         "pitch_velo_mph", "sprint_mph", "catch_prob", "route_ft",
                         "hang_s") if clean.get(k) is not None},
        })
    return feed


HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --ink:#12181f; --panel:#161f2b; --panel2:#22303f; --text:#fff; --muted:#9fb0c0;
  --home:#2f80ed; --away:#f2994a; --gold:#ffc72c; --accent:#c8102e; --good:#22c55e;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:18px}
h1{font-size:20px;margin:0 0 2px;letter-spacing:.5px}
.sub{color:var(--muted);font-size:13px;margin-bottom:14px}
.score{display:flex;align-items:center;gap:18px;background:var(--panel);
  border-radius:12px;padding:14px 18px;margin-bottom:14px;flex-wrap:wrap}
.team{display:flex;align-items:center;gap:10px}
.team .name{font-weight:700;font-size:17px}
.team .runs{font-size:34px;font-weight:800;min-width:46px;text-align:center}
.away .runs{color:var(--away)} .home .runs{color:var(--home)}
.state{margin-left:auto;text-align:right;color:var(--muted);font-size:13px}
.state b{color:var(--text);font-size:15px;display:block}
.grid{display:grid;grid-template-columns:1.55fr 1fr;gap:14px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border-radius:12px;padding:14px}
.panel h2{font-size:12px;letter-spacing:1.4px;color:var(--muted);
  text-transform:uppercase;margin:0 0 10px}
.controls{display:flex;gap:8px;align-items:center;margin:12px 0;flex-wrap:wrap}
button{background:var(--panel2);color:var(--text);border:0;border-radius:8px;
  padding:9px 14px;font-weight:700;cursor:pointer;font-size:13px}
button:hover{background:#2c3d50}
button.primary{background:var(--gold);color:#000}
input[type=range]{flex:1;min-width:180px;accent-color:var(--gold)}
.narr{font-size:15px;line-height:1.5;margin:8px 0 4px}
.insight{color:var(--gold);font-size:13px;margin:4px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--panel2);border-radius:10px;padding:12px;text-align:center;
  animation:pop .35s ease}
@keyframes pop{from{transform:scale(.9);opacity:0}to{transform:scale(1);opacity:1}}
.card .t{font-size:11px;font-weight:800;letter-spacing:.8px;color:var(--gold)}
.card .v{font-size:30px;font-weight:800;margin:6px 0 0}
.card .u{font-size:11px;color:var(--muted);font-weight:700}
.card .n{font-size:11px;color:#cdd8e3;margin-top:7px;line-height:1.35}
.card.defense .t{color:var(--accent)} .card.speed .t{color:var(--good)}
.card.fan .t{color:#a855f7} .card.story .t{color:#fff} .card.pitching .t{color:var(--home)}
.bases{display:grid;grid-template-columns:repeat(3,14px);gap:3px;justify-content:center}
.b{width:14px;height:14px;transform:rotate(45deg);background:#2c3d50;border-radius:2px}
.b.on{background:var(--gold)}
.vote{margin-top:10px;padding:10px;background:#2a1f3d;border-radius:10px}
.vote .q{font-weight:700;margin-bottom:8px}
.vote button{margin-right:8px;background:#a855f7}
.reveal{margin-top:8px;font-weight:700;color:var(--gold)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td{padding:5px 4px;border-bottom:1px solid var(--panel2)}
td.n{color:var(--muted);width:52px}
td.w{text-align:right;font-weight:700;width:62px}
.pos{color:var(--good)} .neg{color:var(--accent)}
.foot{color:var(--muted);font-size:11px;margin-top:16px;text-align:center}
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">Real-Time Baseball Storytelling Engine · SMT Data Challenge 2026 · "On the Big Screen!"</div>

<div class="score">
  <div class="team away"><span class="runs" id="ar">0</span><span class="name" id="an">AWAY</span></div>
  <div class="team home"><span class="name" id="hn">HOME</span><span class="runs" id="hr">0</span></div>
  <div class="state">
    <b id="inn">Top 1</b>
    <span id="outs">0 out</span>
    <div class="bases" style="margin-top:6px">
      <div class="b" id="b3"></div><div class="b" id="b2"></div><div class="b" id="b1"></div>
    </div>
  </div>
</div>

<div class="controls">
  <button class="primary" id="play">▶ Play</button>
  <button id="prev">◀ Prev</button>
  <button id="next">Next ▶</button>
  <button id="big">★ Biggest moment</button>
  <input type="range" id="scrub" min="0" value="0">
  <span id="counter" style="color:var(--muted);font-size:12px"></span>
</div>

<div class="grid">
  <div>
    <div class="panel">
      <h2>Win Probability</h2>
      <svg id="wp" viewBox="0 0 700 220" style="width:100%;height:auto"></svg>
    </div>
    <div class="panel" style="margin-top:14px">
      <h2>Leverage</h2>
      <svg id="lev" viewBox="0 0 700 90" style="width:100%;height:auto"></svg>
    </div>
    <div class="panel" style="margin-top:14px">
      <h2>Biggest Swings</h2>
      <table id="top"></table>
    </div>
  </div>

  <div>
    <div class="panel">
      <h2>On The Call</h2>
      <div class="narr" id="narr">Press play to replay the game.</div>
      <div id="ins"></div>
      <div id="votebox"></div>
    </div>
    <div class="panel" style="margin-top:14px">
      <h2>Story Cards</h2>
      <div class="cards" id="cards"></div>
    </div>
  </div>
</div>
<div class="foot">Win probability, leverage and every story card are computed from SMT player and ball tracking.</div>
</div>
<script>
const DATA = __DATA__;
const META = __META__;
let i = 0, timer = null;

const $ = id => document.getElementById(id);
$("an").textContent = META.away; $("hn").textContent = META.home;
$("scrub").max = DATA.length - 1;

function wpPath(upTo){
  const W=700,H=220,n=DATA.length;
  const x=k=>(k/(n-1))*W, y=p=>H-(p*H);
  let d="";
  for(let k=0;k<=upTo;k++){
    const p=DATA[k].wp_home; if(p===null||p===undefined) continue;
    d += (d===""?"M":"L") + x(k).toFixed(1) + "," + y(p).toFixed(1);
  }
  return d;
}

function drawWP(){
  const svg=$("wp"), W=700,H=220,n=DATA.length;
  const x=k=>(k/(n-1))*W, y=p=>H-(p*H);
  let s = `<line x1="0" y1="${H/2}" x2="${W}" y2="${H/2}" stroke="#9fb0c0" stroke-dasharray="4 4" stroke-width="1" opacity=".5"/>`;
  // inning separators
  let prev=null;
  DATA.forEach((p,k)=>{ const key=p.inning+p.half;
    if(key!==prev && p.half==="Top"){ s+=`<line x1="${x(k)}" y1="0" x2="${x(k)}" y2="${H}" stroke="#22303f" stroke-width="1"/>`;
      s+=`<text x="${x(k)+3}" y="${H-4}" fill="#9fb0c0" font-size="10">${p.inning}</text>`; }
    prev=key; });
  s += `<path d="${wpPath(DATA.length-1)}" fill="none" stroke="#22303f" stroke-width="2"/>`;
  s += `<path id="wpline" d="${wpPath(i)}" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/>`;
  const p=DATA[i].wp_home;
  if(p!==null&&p!==undefined){
    s += `<circle cx="${x(i)}" cy="${y(p)}" r="5.5" fill="${p>=.5?'#2f80ed':'#f2994a'}" stroke="#fff" stroke-width="2"/>`;
  }
  s += `<text x="6" y="14" fill="#2f80ed" font-size="11" font-weight="700">${META.home} WINNING</text>`;
  s += `<text x="6" y="${H-10}" fill="#f2994a" font-size="11" font-weight="700">${META.away} WINNING</text>`;
  svg.innerHTML = s;
}

function drawLev(){
  const svg=$("lev"), W=700,H=90,n=DATA.length;
  const mx = Math.max(3, ...DATA.map(d=>d.leverage||0));
  let s="";
  DATA.forEach((d,k)=>{
    const h=((d.leverage||0)/mx)*H, w=W/n;
    const col = (d.leverage||0)>=2 ? "#c8102e" : (k<=i?"#2f80ed":"#22303f");
    s+=`<rect x="${(k*w).toFixed(1)}" y="${(H-h).toFixed(1)}" width="${Math.max(1,w-0.5).toFixed(1)}" height="${h.toFixed(1)}" fill="${col}" opacity="${k<=i?1:.45}"/>`;
  });
  s+=`<line x1="0" y1="${H-(1/mx)*H}" x2="${W}" y2="${H-(1/mx)*H}" stroke="#9fb0c0" stroke-dasharray="3 3" stroke-width="1"/>`;
  svg.innerHTML=s;
}

function drawTop(){
  const idx = DATA.map((d,k)=>k).sort((a,b)=>Math.abs(DATA[b].wpa||0)-Math.abs(DATA[a].wpa||0)).slice(0,6);
  $("top").innerHTML = idx.map(k=>{
    const d=DATA[k], w=(d.wpa||0)*100;
    return `<tr onclick="goto(${k})" style="cursor:pointer">
      <td class="n">${d.half==="Top"?"▲":"▼"}${d.inning}</td>
      <td>${d.batter||""} — ${d.outcome||""}</td>
      <td class="w ${w>=0?'pos':'neg'}">${w>=0?"+":""}${w.toFixed(0)}%</td></tr>`;
  }).join("");
}

function render(){
  const d = DATA[i];
  $("ar").textContent = d.away_score ?? 0;
  $("hr").textContent = d.home_score ?? 0;
  $("inn").textContent = (d.half==="Top"?"Top ":"Bot ") + d.inning;
  $("outs").textContent = (d.outs_before ?? 0) + " out";
  const bs = d.base_state||0;
  $("b1").className = "b" + ((bs&1)?" on":"");
  $("b2").className = "b" + ((bs&2)?" on":"");
  $("b3").className = "b" + ((bs&4)?" on":"");
  $("narr").innerHTML = "<b>"+(d.situation||"")+"</b><br>"+(d.narrative||"");
  $("ins").innerHTML = (d.insights||[]).map(t=>`<div class="insight">▸ ${t}</div>`).join("");
  $("counter").textContent = `play ${i+1} / ${DATA.length}`;
  $("scrub").value = i;

  $("cards").innerHTML = (d.cards||[]).map(c=>`
    <div class="card ${c.category}">
      <div class="t">${c.title}</div>
      <div class="v">${c.headline}</div>
      <div class="u">${c.unit||""}</div>
      <div class="n">${c.narrative||""}</div>
    </div>`).join("") || `<div style="color:var(--muted);font-size:13px">No cards for this play.</div>`;

  // Fan vote appears only when a vote-type card fired.
  const vote = (d.cards||[]).find(c=>c.viz_hint==="vote" && c.detail && c.detail.vote_options);
  $("votebox").innerHTML = vote ? `<div class="vote"><div class="q">${vote.narrative}</div>
      ${vote.detail.vote_options.map(o=>`<button onclick="reveal(this,'${String(vote.detail.actual||vote.detail.correct_option||"").replace(/'/g,"")}')">${o}</button>`).join("")}
      <div class="reveal" id="rv"></div></div>` : "";

  drawWP(); drawLev();
}

function reveal(btn, actual){ $("rv").textContent = "Actual: " + actual; }
function goto(k){ i = Math.max(0, Math.min(DATA.length-1, k)); render(); }
$("next").onclick = ()=>goto(i+1);
$("prev").onclick = ()=>goto(i-1);
$("scrub").oninput = e=>goto(+e.target.value);
$("big").onclick = ()=>{
  let best=0; DATA.forEach((d,k)=>{ if(Math.abs(d.wpa||0)>Math.abs(DATA[best].wpa||0)) best=k; });
  goto(best);
};
$("play").onclick = ()=>{
  if(timer){ clearInterval(timer); timer=null; $("play").textContent="▶ Play"; return; }
  $("play").textContent="⏸ Pause";
  timer = setInterval(()=>{ if(i>=DATA.length-1){ clearInterval(timer); timer=null; $("play").textContent="▶ Play"; return;} goto(i+1); }, 650);
};
drawTop(); render();
</script></body></html>"""


def build_dashboard(game, summary, out_path, title=None):
    """Write the self-contained dashboard for one game."""
    feed = build_play_feed(game)
    home = summary.get("home_team", "HOME")
    away = summary.get("away_team", "AWAY")
    title = title or f"{away} at {home} — Live Storytelling Scoreboard"
    meta = {"home": home, "away": away,
            "home_final": _safe(summary.get("home_final")),
            "away_final": _safe(summary.get("away_final")),
            "game_string": summary.get("game_string", "")}

    html = (HTML.replace("__DATA__", json.dumps(feed, default=str))
                .replace("__META__", json.dumps(meta, default=str))
                .replace("__TITLE__", title))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
