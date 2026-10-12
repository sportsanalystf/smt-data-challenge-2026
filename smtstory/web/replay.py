"""
replay.py — the interactive Play Explorer.

Generates ONE self-contained HTML file in which every at-bat of a real game can
be clicked and watched: the ball and all nine fielders animate from the tracking
data, and the analysis panel adapts to what actually happened.

  strikeout  -> pitch tunnel view: every pitch of the at-bat drawn from the
                catcher's angle and from above, with break, tunnel ratio and a
                verdict on whether it was nasty pitching or a bad swing
  fly / line -> the fielder's route, ground covered, closing speed, catch odds
  ground out -> route, transfer, throw velocity, and the race to first
  base hit   -> where it landed, who had a chance, how fast the runner went
                vs. every runner in the league

No server, no build step, no network.
"""
import json
import os


HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#0e141b;--panel:#161f2b;--panel2:#22303f;--line:#2d3f52;--text:#fff;
--muted:#93a5b6;--home:#2f80ed;--away:#f2994a;--gold:#ffc72c;--accent:#c8102e;
--good:#22c55e;--purple:#a855f7;--grass:#0b6b3a;--dirt:#8a5a2b}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--text);font:14px/1.45 -apple-system,
BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:16px}
h1{font-size:19px;margin:0}
.sub{color:var(--muted);font-size:12px;margin:2px 0 12px}
.top{display:flex;gap:16px;align-items:center;background:var(--panel);
border-radius:12px;padding:12px 16px;margin-bottom:12px;flex-wrap:wrap}
.sc{font-size:30px;font-weight:800}.sc.a{color:var(--away)}.sc.h{color:var(--home)}
.tn{font-weight:700;font-size:15px}
.grid{display:grid;grid-template-columns:300px 1fr 340px;gap:12px}
@media(max-width:1250px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border-radius:12px;padding:12px}
.panel h2{font-size:11px;letter-spacing:1.3px;color:var(--muted);text-transform:uppercase;
margin:0 0 8px}
#list{max-height:660px;overflow-y:auto}
.ab{padding:7px 9px;border-radius:8px;cursor:pointer;border-left:3px solid transparent;
margin-bottom:3px;font-size:12.5px}
.ab:hover{background:var(--panel2)}
.ab.sel{background:var(--panel2);border-left-color:var(--gold)}
.ab .r1{display:flex;justify-content:space-between;gap:6px}
.ab .who{font-weight:700}
.ab .meta{color:var(--muted);font-size:11px}
.tag{font-size:9.5px;padding:1px 5px;border-radius:4px;font-weight:700;letter-spacing:.4px}
.t-strikeout_or_walk{background:#3b2f5e;color:#cbb6ff}
.t-ground_out{background:#4a3a1e;color:#ffd88a}
.t-fly_out{background:#1e3a4a;color:#8fd4ff}
.t-line_out{background:#1e4a3a;color:#8fffc4}
.t-base_hit{background:#4a1e2a;color:#ff9ab0}
.t-home_run{background:#5e2f2f;color:#ffb3b3}
.t-unknown{background:#333;color:#aaa}
.wpa{font-weight:700}.pos{color:var(--good)}.neg{color:var(--accent)}
.stage{position:relative;background:#0a1017;border-radius:10px;overflow:hidden}
svg{display:block;width:100%;height:auto}
.ctrl{display:flex;gap:7px;align-items:center;margin-top:9px;flex-wrap:wrap}
button{background:var(--panel2);color:var(--text);border:0;border-radius:7px;
padding:7px 12px;font-weight:700;font-size:12px;cursor:pointer}
button:hover{background:#2f4257}button.p{background:var(--gold);color:#000}
button.sm{padding:5px 9px;font-size:11px}
input[type=range]{flex:1;min-width:120px;accent-color:var(--gold)}
.narr{font-size:14px;margin:6px 0}
.ins{color:var(--gold);font-size:12px;margin:3px 0}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}
.stat{background:var(--panel2);border-radius:8px;padding:8px}
.stat .k{font-size:9.5px;color:var(--muted);letter-spacing:.6px;text-transform:uppercase}
.stat .v{font-size:19px;font-weight:800;margin-top:2px}
.stat .c{font-size:10.5px;color:var(--muted);margin-top:1px}
.bar{height:5px;background:var(--line);border-radius:3px;margin-top:5px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--gold);border-radius:3px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.card{background:var(--panel2);border-radius:9px;padding:9px;text-align:center}
.card .t{font-size:9.5px;font-weight:800;letter-spacing:.5px;color:var(--gold)}
.card .v{font-size:23px;font-weight:800;margin:3px 0 0}
.card .u{font-size:9.5px;color:var(--muted);font-weight:700}
.card .n{font-size:10px;color:#c9d6e2;margin-top:5px;line-height:1.3}
.card.defense .t{color:var(--accent)}.card.speed .t{color:var(--good)}
.card.fan .t{color:var(--purple)}.card.pitching .t{color:var(--home)}
.card.story .t{color:#fff}.card.power .t{color:var(--gold)}
.verdict{padding:9px;border-radius:9px;margin-bottom:8px;font-weight:700}
.v-nasty{background:#3d1f2a;color:#ff9ab0}.v-miss{background:#1f3d2a;color:#9affc4}
.v-ok{background:#1f2f3d;color:#9ad0ff}
.pt{display:flex;gap:4px;flex-wrap:wrap;margin:7px 0}
.pt b{background:var(--panel2);border-radius:6px;padding:3px 7px;font-size:11px;cursor:pointer}
.pt b.on{background:var(--gold);color:#000}
.legend{font-size:10.5px;color:var(--muted);margin-top:5px}
.tabs{display:flex;gap:5px;margin-bottom:8px}
.tabs b{padding:5px 10px;border-radius:7px;background:var(--panel2);font-size:11px;cursor:pointer}
.tabs b.on{background:var(--gold);color:#000}
.foot{color:var(--muted);font-size:11px;text-align:center;margin-top:14px}
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">Play Explorer — click any at-bat to watch it and see why it mattered ·
SMT Data Challenge 2026 · "On the Big Screen!"</div>

<div class="top">
  <span class="sc a" id="ar">0</span><span class="tn" id="an">AWAY</span>
  <span style="color:var(--muted)">at</span>
  <span class="tn" id="hn">HOME</span><span class="sc h" id="hr">0</span>
  <span style="margin-left:auto;color:var(--muted)" id="sit">—</span>
</div>

<div class="grid">
  <div class="panel"><h2>At-Bats</h2><div id="list"></div></div>

  <div>
    <div class="panel">
      <div class="tabs">
        <b class="on" data-v="field">Field Replay</b>
        <b data-v="tunnel">Pitch Tunnel</b>
        <b data-v="wp">Win Probability</b>
      </div>
      <div class="stage" id="stage"><svg id="view" viewBox="0 0 640 460"></svg></div>
      <div class="ctrl">
        <button class="p" id="play">▶ Play</button>
        <button class="sm" id="slow">0.5x</button>
        <input type="range" id="scrub" min="0" max="100" value="0">
        <span id="clock" style="color:var(--muted);font-size:11px;min-width:52px"></span>
      </div>
      <div class="legend" id="legend"></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h2>What Happened</h2>
      <div class="narr" id="narr">Select an at-bat.</div>
      <div id="ins"></div>
      <div class="stats" id="stats"></div>
    </div>
  </div>

  <div>
    <div class="panel"><h2>Analysis</h2><div id="analysis"></div></div>
    <div class="panel" style="margin-top:12px"><h2>Story Cards</h2>
      <div class="cards" id="cards"></div></div>
  </div>
</div>
<div class="foot">Every number is measured from SMT 20 Hz player and ball tracking.</div>
</div>
<script>
const B = __DATA__;
const ABS = B.at_bats, PB = B.playback, META = B.meta, ZONE = B.zone;
const $ = i => document.getElementById(i);
let sel = 0, view = "field", t = 0, timer = null, speed = 1, seq = [], pitchSel = -1;

/* ---------------- field geometry: SMT feet -> svg px ---------------- */
const VW = 640, VH = 460, MAXD = 420;
function fx(x){ return VW/2 + (x / MAXD) * (VW/2 - 12); }
function fy(y){ return VH - 22 - (y / MAXD) * (VH - 46); }

function fieldBase(){
  const H=[0,0],F=[63.64,63.64],S=[0,127.28],T=[-63.64,63.64];
  const P=p=>`${fx(p[0])},${fy(p[1])}`;
  let s=`<rect x="0" y="0" width="${VW}" height="${VH}" fill="#0b6b3a"/>`;
  s+=`<path d="M ${P(H)} L ${fx(-MAXD*0.72)},${fy(MAXD*0.72)} A ${VW/2} ${VW/2} 0 0 1 ${fx(MAXD*0.72)},${fy(MAXD*0.72)} Z" fill="#0d7a42"/>`;
  s+=`<polygon points="${P(H)} ${P(F)} ${P(S)} ${P(T)}" fill="#8a5a2b" opacity=".55"/>`;
  s+=`<polyline points="${P(H)} ${P(F)} ${P(S)} ${P(T)} ${P(H)}" fill="none" stroke="#fff" stroke-width="1.6"/>`;
  [F,T].forEach(b=>{ const n=Math.hypot(b[0],b[1]); const v=[b[0]/n*MAXD*0.8,b[1]/n*MAXD*0.8];
    s+=`<line x1="${fx(0)}" y1="${fy(0)}" x2="${fx(v[0])}" y2="${fy(v[1])}" stroke="#fff" stroke-width="1.2"/>`;});
  [F,S,T].forEach(b=>s+=`<rect x="${fx(b[0])-3}" y="${fy(b[1])-3}" width="6" height="6" fill="#fff"/>`);
  s+=`<circle cx="${fx(0)}" cy="${fy(60.5)}" r="7" fill="#8a5a2b" stroke="#fff" stroke-width="1"/>`;
  s+=`<polygon points="${fx(0)},${fy(0)-4} ${fx(0)+4},${fy(0)} ${fx(0)},${fy(0)+4} ${fx(0)-4},${fy(0)}" fill="#fff"/>`;
  return s;
}

const POSCOL={1:"#fff",2:"#fff",3:"#8fd4ff",4:"#8fd4ff",5:"#8fd4ff",6:"#8fd4ff",
7:"#ffd88a",8:"#ffd88a",9:"#ffd88a",10:"#ff9ab0",11:"#ff9ab0",12:"#ff9ab0",13:"#ff9ab0"};
const POSLBL={1:"P",2:"C",3:"1B",4:"2B",5:"3B",6:"SS",7:"LF",8:"CF",9:"RF",10:"B",11:"R1",12:"R2",13:"R3"};

function curPlay(){ const ab=ABS[sel]; return PB[String(ab.key_play)]||null; }
function frameAt(p,ms){
  const T=p.times; if(!T.length) return 0;
  let i=0; while(i<T.length-1 && T[i+1]<=ms) i++;
  return i;
}
function lerp(a,b,f){ return a+(b-a)*f; }

function drawField(){
  const ab=ABS[sel], p=curPlay();
  let s=fieldBase();
  if(!p){ $("view").innerHTML=s+`<text x="16" y="26" fill="#fff" font-size="13">No tracking for this play</text>`; return; }
  const T=p.times, dur=T[T.length-1]||1, ms=Math.min(t,dur);
  const i=frameAt(p,ms), j=Math.min(i+1,T.length-1);
  const span=(T[j]-T[i])||1, f=Math.max(0,Math.min(1,(ms-T[i])/span));

  // ball trail
  let tr="";
  for(let k=0;k<=i;k++){ const b=p.ball[k]; if(!b) continue; tr+=(k?"L":"M")+fx(b[0])+","+fy(b[1]); }
  if(tr) s+=`<path d="${tr}" fill="none" stroke="#fff" stroke-width="1.6" opacity=".55" stroke-dasharray="3 3"/>`;

  // players
  if(p.players){
    for(const pid in p.players){
      const arr=p.players[pid]; const a=arr[i],b=arr[j]; if(!a) continue;
      const x=lerp(a[0],(b||a)[0],f), y=lerp(a[1],(b||a)[1],f);
      const c=POSCOL[pid]||"#fff";
      s+=`<circle cx="${fx(x)}" cy="${fy(y)}" r="5" fill="${c}" stroke="#0a1017" stroke-width="1.2"/>`;
      s+=`<text x="${fx(x)}" y="${fy(y)-8}" fill="${c}" font-size="8.5" text-anchor="middle" font-weight="700">${POSLBL[pid]||pid}</text>`;
    }
  }
  // ball (size grows with height so fly balls read as airborne)
  const b1=p.ball[i], b2=p.ball[j]||p.ball[i];
  if(b1){
    const bx=lerp(b1[0],b2[0],f), by=lerp(b1[1],b2[1],f), bz=lerp(b1[2],b2[2],f);
    const r=3+Math.max(0,Math.min(6,bz/9));
    s+=`<circle cx="${fx(bx)}" cy="${fy(by)}" r="${r+2}" fill="#000" opacity=".28"/>`;
    s+=`<circle cx="${fx(bx)}" cy="${fy(by)}" r="${r}" fill="#fff" stroke="#c8102e" stroke-width="1.2"/>`;
  }
  // event flashes
  (p.events||[]).forEach(e=>{
    if(Math.abs(e.t-ms)<220){
      const lbl={1:"PITCH",4:"CONTACT",2:"FIELDED",3:"THROW",5:"END",11:"HOME RUN",16:"BOUNCE",10:"OFF THE WALL"}[e.code];
      if(lbl) s+=`<text x="${VW/2}" y="34" fill="#ffc72c" font-size="17" font-weight="800" text-anchor="middle">${lbl}</text>`;
    }
  });
  s+=`<text x="10" y="20" fill="#93a5b6" font-size="11">${ab.situation}</text>`;
  $("view").innerHTML=s;
  $("clock").textContent=(ms/1000).toFixed(1)+"s";
  $("scrub").value=Math.round(1000*ms/dur);
  $("legend").innerHTML='<span style="color:#8fd4ff">■</span> infield &nbsp; <span style="color:#ffd88a">■</span> outfield &nbsp; <span style="color:#ff9ab0">■</span> batter/runners &nbsp; ball grows with height';
}

/* ---------------- pitch tunnel view ---------------- */
function drawTunnel(){
  const ab=ABS[sel], ps=ab.pitches||[];
  if(!ps.length){ $("view").innerHTML=`<rect width="${VW}" height="${VH}" fill="#0a1017"/><text x="16" y="28" fill="#93a5b6" font-size="13">No pitch tracking for this at-bat</text>`; return; }
  const COL=["#ffc72c","#2f80ed","#22c55e","#c8102e","#a855f7","#f2994a","#8fd4ff","#ff9ab0"];
  let s=`<rect width="${VW}" height="${VH}" fill="#0a1017"/>`;

  // LEFT: catcher's view (x vs z at the plate) with the strike zone
  const cx0=30,cy0=40,cw=250,ch=250;
  const zx=v=>cx0+cw/2+(v/2.4)*(cw/2), zz=v=>cy0+ch-((v-0.4)/3.6)*ch;
  s+=`<text x="${cx0}" y="${cy0-12}" fill="#93a5b6" font-size="11">CATCHER'S VIEW — where each pitch crossed</text>`;
  s+=`<rect x="${zx(-ZONE.half_width)}" y="${zz(ZONE.top)}" width="${zx(ZONE.half_width)-zx(-ZONE.half_width)}" height="${zz(ZONE.bottom)-zz(ZONE.top)}" fill="none" stroke="#fff" stroke-width="1.6"/>`;
  ps.forEach((p,k)=>{ if(p.plate_x==null) return;
    const on=(pitchSel<0||pitchSel===k);
    s+=`<circle cx="${zx(p.plate_x)}" cy="${zz(p.plate_z)}" r="${on?9:5}" fill="${COL[k%8]}" opacity="${on?1:.25}" stroke="#0a1017" stroke-width="1.5"/>`;
    s+=`<text x="${zx(p.plate_x)}" y="${zz(p.plate_z)+4}" font-size="10" font-weight="800" text-anchor="middle" fill="#0a1017" opacity="${on?1:.3}">${k+1}</text>`;
  });

  // RIGHT: side view (distance from plate vs height) showing the tunnel
  const sx0=310,sy0=40,sw=310,sh=250;
  const px=y=>sx0+sw-(y/58)*sw, pz=v=>sy0+sh-((v-0.4)/6.2)*sh;
  s+=`<text x="${sx0}" y="${sy0-12}" fill="#93a5b6" font-size="11">SIDE VIEW — release to plate</text>`;
  s+=`<line x1="${px(0)}" y1="${sy0}" x2="${px(0)}" y2="${sy0+sh}" stroke="#fff" stroke-width="1.4"/>`;
  s+=`<text x="${px(0)-4}" y="${sy0+sh+13}" fill="#93a5b6" font-size="9" text-anchor="end">plate</text>`;
  const CP=23.8;
  s+=`<line x1="${px(CP)}" y1="${sy0}" x2="${px(CP)}" y2="${sy0+sh}" stroke="#ffc72c" stroke-dasharray="4 4" stroke-width="1.2"/>`;
  s+=`<text x="${px(CP)}" y="${sy0-2}" fill="#ffc72c" font-size="9" text-anchor="middle">commit point</text>`;
  ps.forEach((p,k)=>{ const poly=p.polyline; if(!poly) return;
    const on=(pitchSel<0||pitchSel===k);
    let d=""; poly.forEach((q,n)=>{ d+=(n?"L":"M")+px(q[0])+","+pz(q[2]); });
    s+=`<path d="${d}" fill="none" stroke="${COL[k%8]}" stroke-width="${on?2.6:1.2}" opacity="${on?1:.28}"/>`;
  });
  $("view").innerHTML=s;
  $("legend").innerHTML='Pitches that stay together at the yellow line but separate at the plate are <b>tunneled</b> — the hitter cannot tell them apart in time.';
}

/* ---------------- win probability view ---------------- */
function drawWP(){
  const n=ABS.length, W=VW,H=VH;
  const x=k=>16+(k/(n-1))*(W-32), y=p=>H-30-(p*(H-60));
  let s=`<rect width="${W}" height="${H}" fill="#0a1017"/>`;
  s+=`<line x1="16" y1="${y(.5)}" x2="${W-16}" y2="${y(.5)}" stroke="#93a5b6" stroke-dasharray="4 4" opacity=".5"/>`;
  let d="",prev=null;
  ABS.forEach((a,k)=>{ if(a.wp_home==null) return; d+=(d?"L":"M")+x(k)+","+y(a.wp_home);
    const key=a.inning+a.half; if(key!==prev&&a.half==="Top"){
      s+=`<line x1="${x(k)}" y1="20" x2="${x(k)}" y2="${H-30}" stroke="#22303f"/>`;
      s+=`<text x="${x(k)+3}" y="${H-16}" fill="#93a5b6" font-size="9">${a.inning}</text>`;} prev=key;});
  s+=`<path d="${d}" fill="none" stroke="#fff" stroke-width="2.4"/>`;
  const a=ABS[sel];
  if(a.wp_home!=null) s+=`<circle cx="${x(sel)}" cy="${y(a.wp_home)}" r="6" fill="#ffc72c" stroke="#0a1017" stroke-width="2"/>`;
  s+=`<text x="20" y="30" fill="#2f80ed" font-size="11" font-weight="700">${META.home} winning</text>`;
  s+=`<text x="20" y="${H-38}" fill="#f2994a" font-size="11" font-weight="700">${META.away} winning</text>`;
  $("view").innerHTML=s;
  $("legend").innerHTML="Click any at-bat on the left to jump to that moment.";
}

function draw(){ if(view==="field") drawField(); else if(view==="tunnel") drawTunnel(); else drawWP(); }

/* ---------------- analysis panel ---------------- */
function statBox(k,v,c,pct){
  return `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div>
  ${c?`<div class="c">${c}</div>`:""}
  ${pct!=null?`<div class="bar"><i style="width:${Math.max(2,Math.min(100,pct))}%"></i></div>`:""}</div>`;
}

function renderAnalysis(){
  const a=ABS[sel], an=a.anatomy||{}, cmp=a.comparisons||{}, out=[];
  const f=an.fielding, r=an.running, cp=an.close_play, sv=a.strikeout_verdict;

  if(sv){
    const cls=sv.verdict==="NASTY PITCH"?"v-nasty":(sv.verdict==="HITTER MISSED IT"?"v-miss":"v-ok");
    out.push(`<div class="verdict ${cls}">${sv.verdict} · ${Math.round(sv.nastiness)}/100 nasty<div style="font-weight:400;margin-top:4px;font-size:12.5px">${sv.narrative}</div></div>`);
  }
  if(a.pitches&&a.pitches.length){
    out.push(`<div class="pt">`+a.pitches.map((p,k)=>`<b class="${pitchSel===k?'on':''}" onclick="selPitch(${k})">#${k+1} ${p.velo_mph?Math.round(p.velo_mph):"?"}</b>`).join("")+`</div>`);
    const p=a.pitches[pitchSel<0?a.pitches.length-1:pitchSel];
    let g="";
    if(p.velo_mph!=null) g+=statBox("Velocity",p.velo_mph.toFixed(0)+" mph",p.effective_velo_mph?("plays like "+p.effective_velo_mph.toFixed(0)):"");
    if(p.break_vertical_in!=null) g+=statBox("Induced Break",(p.break_vertical_in>0?"+":"")+p.break_vertical_in.toFixed(0)+'"',"gravity removed");
    if(p.break_horizontal_in!=null) g+=statBox("Horizontal",(p.break_horizontal_in).toFixed(0)+'"',"run");
    if(p.tunnel_ratio!=null) g+=statBox("Tunnel",p.tunnel_ratio.toFixed(1)+"x","vs previous pitch");
    if(p.extension_ft!=null) g+=statBox("Extension",p.extension_ft.toFixed(1)+" ft","toward the plate");
    if(p.nastiness!=null) g+=statBox("Nastiness",Math.round(p.nastiness),"0-100",p.nastiness);
    out.push(`<div class="stats">${g}</div>`);
  }
  if(f){
    let g=statBox("Fielded by",f.fielder_pos,"");
    if(f.route_ft!=null) g+=statBox("Ground Covered",f.route_ft.toFixed(0)+" ft",
      cmp.route?`more than ${Math.round(cmp.route.percentile)}% of plays`:"",cmp.route?cmp.route.percentile:null);
    if(f.time_to_ball_s!=null) g+=statBox("Time to Ball",f.time_to_ball_s.toFixed(2)+"s","");
    if(f.closing_speed_mph!=null) g+=statBox("Closing Speed",f.closing_speed_mph.toFixed(1)+" mph","");
    if(f.route_efficiency!=null) g+=statBox("Route Efficiency",(100*f.route_efficiency).toFixed(0)+"%","1.0 = perfect line");
    if(f.transfer_s!=null) g+=statBox("Transfer",f.transfer_s.toFixed(2)+"s","glove to release");
    if(f.throw_velo_mph!=null) g+=statBox("Throw",f.throw_velo_mph.toFixed(0)+" mph",
      cmp.throw?`stronger than ${Math.round(cmp.throw.percentile)}%`:"",cmp.throw?cmp.throw.percentile:null);
    if(f.catch_prob!=null) g+=statBox("Catch Odds",(100*f.catch_prob).toFixed(0)+"%",f.catch_difficulty||"");
    out.push(`<h2 style="margin-top:10px">Defense</h2><div class="stats">${g}</div>`);
  }
  if(r){
    let g="";
    if(r.top_speed_mph!=null) g+=statBox("Sprint Speed",r.top_speed_mph.toFixed(1)+" mph",
      cmp.sprint?`${cmp.sprint.grade} · faster than ${Math.round(cmp.sprint.percentile)}%`:"",cmp.sprint?cmp.sprint.percentile:null);
    if(r.time_to_base_s!=null) g+=statBox("To the Bag",r.time_to_base_s.toFixed(2)+"s","from contact");
    if(r.burst_ft_s2!=null) g+=statBox("Burst",r.burst_ft_s2.toFixed(0)+" ft/s²","out of the box");
    if(r.run_efficiency!=null) g+=statBox("Path",(100*r.run_efficiency).toFixed(0)+"%","directness");
    if(g) out.push(`<h2 style="margin-top:10px">Baserunning</h2><div class="stats">${g}</div>`);
  }
  if(cp){
    const cls=cp.verdict==="SAFE"?"v-miss":"v-nasty";
    out.push(`<div class="verdict ${cls}" style="margin-top:10px">${cp.verdict} by ${Math.abs(cp.margin_s).toFixed(2)}s
    <div style="font-weight:400;font-size:12px;margin-top:3px">Throw ${cp.throw_distance_ft.toFixed(0)} ft${cp.bang_bang?" · bang-bang play":""}</div></div>`);
  }
  if(!out.length) out.push(`<div style="color:var(--muted);font-size:12.5px">No tracking detail for this at-bat.</div>`);
  $("analysis").innerHTML=out.join("");
}

function renderCards(){
  const a=ABS[sel];
  $("cards").innerHTML=(a.cards||[]).map(c=>`<div class="card ${c.category}">
    <div class="t">${c.title}</div><div class="v">${c.headline}</div>
    <div class="u">${c.unit||""}</div><div class="n">${c.narrative||""}</div></div>`).join("")
    ||`<div style="color:var(--muted);font-size:12px">No cards.</div>`;
}

function renderList(){
  $("list").innerHTML=ABS.map((a,k)=>{
    const w=(a.wpa||0)*100;
    return `<div class="ab ${k===sel?'sel':''}" onclick="pick(${k})">
      <div class="r1"><span class="who">${a.batter||""}</span>
      <span class="wpa ${w>=0?'pos':'neg'}">${w>=0?"+":""}${w.toFixed(0)}%</span></div>
      <div class="r1"><span class="meta">${a.half==="Top"?"▲":"▼"}${a.inning} · ${a.outcome||""}</span>
      <span class="tag t-${a.play_type}">${(a.play_type||"").replace(/_/g," ")}</span></div></div>`;
  }).join("");
  const el=$("list").children[sel]; if(el) el.scrollIntoView({block:"nearest"});
}

function renderMeta(){
  const a=ABS[sel];
  $("ar").textContent=a.away_score??0; $("hr").textContent=a.home_score??0;
  $("an").textContent=META.away; $("hn").textContent=META.home;
  $("sit").textContent=a.situation||"";
  $("narr").textContent=a.narrative||"";
  $("ins").innerHTML=(a.insights||[]).map(s=>`<div class="ins">▸ ${s}</div>`).join("");
  let g="";
  if(a.wpa!=null) g+=statBox("Win Probability Added",((a.wpa*100)>=0?"+":"")+(a.wpa*100).toFixed(0)+"%","");
  if(a.leverage!=null) g+=statBox("Leverage",a.leverage.toFixed(1)+"x","1.0 = average");
  if(a.highlight!=null) g+=statBox("Highlight Score",Math.round(a.highlight),"0-100",a.highlight);
  const ev=(a.comparisons||{}).exit_velo;
  if(ev) g+=statBox("Exit Velocity",ev.value.toFixed(0)+" mph",`harder than ${Math.round(ev.percentile)}%`,ev.percentile);
  $("stats").innerHTML=g;
}

function pick(k){ sel=k; pitchSel=-1; t=0; stop(); renderList(); renderMeta(); renderAnalysis(); renderCards();
  const a=ABS[sel];
  if(view==="field"&&!PB[String(a.key_play)]) view="tunnel";
  syncTabs(); draw(); }
function selPitch(k){ pitchSel=(pitchSel===k?-1:k); view="tunnel"; syncTabs(); renderAnalysis(); draw(); }
function syncTabs(){ document.querySelectorAll(".tabs b").forEach(b=>b.classList.toggle("on",b.dataset.v===view)); }
document.querySelectorAll(".tabs b").forEach(b=>b.onclick=()=>{ view=b.dataset.v; syncTabs(); draw(); });

function stop(){ if(timer){clearInterval(timer);timer=null;$("play").textContent="▶ Play";} }
$("play").onclick=()=>{
  if(timer){stop();return;}
  const p=curPlay(); if(!p||view!=="field"){ view="field"; syncTabs(); }
  const dur=(curPlay()?.times.slice(-1)[0])||0; if(!dur) return;
  if(t>=dur) t=0;
  $("play").textContent="⏸ Pause";
  timer=setInterval(()=>{ t+=33*speed; const d=(curPlay()?.times.slice(-1)[0])||0;
    if(t>=d){ t=d; draw(); stop(); return;} draw(); },33);
};
$("slow").onclick=()=>{ speed=(speed===1?0.5:(speed===0.5?0.25:1)); $("slow").textContent=speed+"x"; };
$("scrub").oninput=e=>{ const d=(curPlay()?.times.slice(-1)[0])||0; t=d*(+e.target.value/1000); draw(); };
document.addEventListener("keydown",e=>{
  if(e.key==="ArrowDown"){pick(Math.min(ABS.length-1,sel+1));e.preventDefault();}
  if(e.key==="ArrowUp"){pick(Math.max(0,sel-1));e.preventDefault();}
  if(e.key===" "){$("play").click();e.preventDefault();}
});
pick(0);
</script></body></html>"""


def build_replay_dashboard(playbook, out_path, title=None):
    """Write the self-contained Play Explorer from a playbook bundle."""
    meta = playbook.get("meta", {})
    title = title or (f"{meta.get('away','AWAY')} at {meta.get('home','HOME')} "
                      f"— Play Explorer")
    html = (HTML.replace("__DATA__", json.dumps(playbook, separators=(",", ":")))
                .replace("__TITLE__", title))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
