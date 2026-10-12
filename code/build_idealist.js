// Builds "SMT_Master_Idea_List.docx"
const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, Header, Footer } = require("docx");

const GREEN = "0B6B3A", DARK = "1B1B1B", ACCENT = "C8102E", LIGHT = "E8F2EC";
const OUT = require("path").resolve(__dirname, "..");

const H = (t, lvl=HeadingLevel.HEADING_1) => new Paragraph({ heading: lvl, children:[new TextRun(t)] });
const P = (t, opts={}) => new Paragraph({ spacing:{after:120}, children:[new TextRun({text:t, ...opts})] });
const bullet = (t, ref="bul") => new Paragraph({ numbering:{reference:ref, level:0}, spacing:{after:40}, children:[new TextRun(t)] });
const num = (t) => new Paragraph({ numbering:{reference:"nums", level:0}, spacing:{after:40}, children: Array.isArray(t)?t:[new TextRun(t)] });

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top:border, bottom:border, left:border, right:border, insideHorizontal:border, insideVertical:border };
function cell(text, w, {head=false, bold=false, fill=null, align=AlignmentType.LEFT}={}) {
  return new TableCell({
    borders, width:{size:w, type:WidthType.DXA},
    shading: fill?{fill, type:ShadingType.CLEAR}:(head?{fill:GREEN, type:ShadingType.CLEAR}:undefined),
    margins:{top:60, bottom:60, left:110, right:110},
    children:[new Paragraph({alignment:align, children:[new TextRun({
      text:String(text), bold:head||bold, color:head?"FFFFFF":DARK, size:head?18:18})]})]
  });
}
function table(cols, rows) {
  const total = cols.reduce((a,c)=>a+c.w,0);
  const headRow = new TableRow({tableHeader:true, children: cols.map(c=>cell(c.t, c.w, {head:true}))});
  const bodyRows = rows.map((r,i)=> new TableRow({children: r.map((v,j)=>cell(v, cols[j].w, {fill: i%2? LIGHT: "FFFFFF"}))}));
  return new Table({ width:{size:total, type:WidthType.DXA}, columnWidths: cols.map(c=>c.w), rows:[headRow, ...bodyRows] });
}

const doc = new Document({
  styles: { default:{document:{run:{font:"Arial", size:22}}},
    paragraphStyles:[
      { id:"Heading1", name:"Heading 1", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{size:30, bold:true, color:GREEN, font:"Arial"}, paragraph:{spacing:{before:260, after:140}, outlineLevel:0}},
      { id:"Heading2", name:"Heading 2", basedOn:"Normal", next:"Normal", quickFormat:true,
        run:{size:24, bold:true, color:DARK, font:"Arial"}, paragraph:{spacing:{before:180, after:100}, outlineLevel:1}},
      { id:"Title", name:"Title", basedOn:"Normal", next:"Normal",
        run:{size:44, bold:true, color:GREEN, font:"Arial"}, paragraph:{spacing:{after:80}}},
    ]},
  numbering:{config:[
    {reference:"bul", levels:[{level:0, format:LevelFormat.BULLET, text:"•", alignment:AlignmentType.LEFT, style:{paragraph:{indent:{left:520, hanging:260}}}}]},
    {reference:"nums", levels:[{level:0, format:LevelFormat.DECIMAL, text:"%1.", alignment:AlignmentType.LEFT, style:{paragraph:{indent:{left:520, hanging:260}}}}]},
  ]},
  sections:[{
    properties:{ page:{ size:{width:12240, height:15840}, margin:{top:1200, right:1200, bottom:1200, left:1200}}},
    footers:{ default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER, children:[
      new TextRun({text:"SMT Data Challenge 2026  |  On the Big Screen!  |  Page ", size:16, color:"888888"}),
      new TextRun({children:[PageNumber.CURRENT], size:16, color:"888888"})]})]})},
    children:[
      new Paragraph({style:"Title", children:[new TextRun("On the Big Screen!")]}),
      P("SMT Data Challenge 2026 — Master Idea List & Top 10 Selection", {bold:true, size:24, color:DARK}),
      P("A catalog of scoreboard-ready concepts built from the SMT player- and ball-tracking data, screened for creativity, relevance, methodological depth, and storytelling value — followed by the ten strongest ideas, each prototyped on the real data (250 games, Level-7 Minor League Baseball, one season).", {italics:true, color:"555555"}),

      H("1. How these ideas were generated and screened"),
      P("Every idea below was tested against three questions. First, is it computable from what the tracking data actually contains — 20 Hz (x, y) player positions, 20 Hz (x, y, z) ball positions, ball-event codes, lineups, and game metadata? Second, does it tell a story a fan can grasp in the seven seconds a graphic is on a Minor League scoreboard? Third, does it exercise a technique from the tutorial track (feature engineering, data visualization, supervised regression, supervised classification) so the methodology is defensible to technical judges? Ideas that a fan could not read at a glance, or that the data could not support, were cut. The survivors are organized by theme, then ranked."),

      H("2. The full idea catalog"),
      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Speed & baserunning")]}),
      bullet("Burner Board — peak sprint speed (mph) on the way to first base, ranked across the league."),
      bullet("Home-to-First Dash — elapsed time from contact to reaching the first-base bag; a live “beat the clock” graphic."),
      bullet("Fastest Out of the Box — reaction and acceleration in the first 1.5 seconds after contact."),
      bullet("Extra-Base Instinct — top speed and path efficiency when a runner takes an extra base."),
      bullet("Pickoff Jump — secondary lead distance and burst on stolen-base attempts."),

      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Power & hitting")]}),
      bullet("Statcast Smash — exit velocity leaderboard; the hardest-hit balls of the night."),
      bullet("Moonshot Meter — estimated carry distance of fly balls and home runs."),
      bullet("Barrel Zone — the sweet-spot combination of exit velocity and launch angle (“barrels”)."),
      bullet("Launch Angle Rainbow — a visual of a hitter’s spray of launch angles and outcomes."),
      bullet("Clutch Contact — hardest-hit ball by inning / leverage for a late-game hype graphic."),

      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Pitching")]}),
      bullet("Radar Gun Live — pitch velocity leaderboard and per-pitcher averages."),
      bullet("Velocity Heartbeat — a starter’s velocity across an outing, showing how he holds his gas."),
      bullet("Effective Velocity — perceived speed adjusted by release extension toward the plate."),
      bullet("Late Life — vertical drop of the ball from release to the plate as a movement proxy."),

      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Defense & fielding")]}),
      bullet("The Robbery Meter — catch probability on every ball to the outfield, and Outs Above Expected."),
      bullet("Outfield Cannons — throw (arm) velocity leaderboard for outfielders and infielders."),
      bullet("Ground Crew Range — distance covered and top closing speed by fielders chasing the ball."),
      bullet("Web Gem of the Game — the single most improbable completed catch, auto-selected."),
      bullet("Double-Play Ballet — pivot time and exchange speed of the second-base combination."),
      bullet("Pop-Time Pipeline — catcher exchange and throw time to second on steal attempts."),

      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Fan-interactive games")]}),
      bullet("Catch or No Catch? — freeze the play at contact and let the crowd vote before the model reveals the odds."),
      bullet("Out or Safe? — a bang-bang play at first shown from the tracking data for a crowd vote."),
      bullet("Guess the Gun — fans guess the pitch speed; closest section wins."),
      bullet("How Far Did It Go? — fans estimate carry distance on a long fly ball."),
      bullet("Beat the Burner — a fan’s phone-tap reaction time raced against a player’s sprint speed."),

      new Paragraph({heading:HeadingLevel.HEADING_2, children:[new TextRun("Composite & storytelling")]}),
      bullet("Five-Tool Scoreboard — a percentile blend of speed, power, and arm into one number."),
      bullet("Player of the Game Engine — a weighted score across contributions in a single game."),
      bullet("Rivalry Radar — team-vs-team tale of the tape built from tracking aggregates."),
      bullet("Prospect Spotlight — a young player’s tool grades animated for the crowd."),

      new Paragraph({pageBreakBefore:true, heading:HeadingLevel.HEADING_1, children:[new TextRun("3. The Top 10 — selected and prototyped")]}),
      P("These ten were chosen for the best balance of fan appeal, methodological depth, and data support. Each was built end-to-end on the real SMT data; the “Headline result” column reports an actual value produced by the accompanying code, not a mock-up. Anonymized player codes are shown as in the data."),
      table(
        [{t:"#", w:400},{t:"Scoreboard product", w:1900},{t:"What it measures", w:2100},{t:"Technique", w:1700},{t:"Headline result (real data)", w:2360}],
        [
          ["1","The Robbery Meter ★","Catch probability & Outs Above Expected on outfield balls","Classification","7,058 chances; model 95.4% acc, Brier 0.039; best defender +9.2 OAE"],
          ["2","Catch or No Catch?","Live crowd vote on a fly ball, revealed by the model","Classification + viz","Suspense plays isolated near 50% catch odds for voting"],
          ["3","Burner Board","Peak sprint speed to first base","Feature eng. + viz","Top runner 22.8 mph peak ground speed"],
          ["4","Statcast Smash","Exit velocity of batted balls","Feature eng. + regression","Top 90th-pct exit velo 121.6 mph; max 122"],
          ["5","Moonshot Meter","Estimated carry distance of flies/HR","Feature eng.","Longest carry 466.9 ft; 578 home runs tagged"],
          ["6","Radar Gun Live","Pitch velocity","Feature eng. + viz","Top pitch 103 mph; leader avg 89.7 over 379 pitches"],
          ["7","Outfield Cannons","Throw / arm velocity","Feature eng.","Hardest throw 102 mph"],
          ["8","Barrel Zone","Sweet-spot EV × launch-angle barrels","Feature eng. + classification","Leader 16 barrels; 13.3% barrel rate"],
          ["9","Ground Crew Range","Distance covered & closing speed on catches","Feature eng. + viz","Top CF averages an 83 ft route per catch"],
          ["10","Five-Tool Scoreboard","Percentile blend of speed, power, arm","Regression / composite","Top all-around score 97.5 / 100"],
        ]
      ),

      H("4. Why the Robbery Meter is the flagship submission"),
      P("Of the ten, the Robbery Meter was chosen for the full write-up because it satisfies the prompt’s example — “an entertainment metric for which player makes the unlikeliest plays” — while doing the most analytical work. It converts raw (x, y) tracking into a calibrated catch-probability model, which simultaneously (a) ranks the league’s best defenders by Outs Above Expected, (b) auto-selects the night’s most improbable completed catch as a Web Gem, and (c) powers a live “Catch or No Catch?” crowd vote. One model, three scoreboard features, spanning feature engineering, supervised classification, and visualization. The remaining nine ideas form a natural product suite around it, and all are implemented in the accompanying code so a club could deploy the whole slate."),
      P("The full methodology, results, and fan-experience design for the flagship are documented in the Narrative Paper; the reproducible analysis is provided as a Quarto (.qmd) file.", {italics:true, color:"555555"}),
    ]
  }]
});

Packer.toBuffer(doc).then(b=>{ fs.writeFileSync(OUT+"/SMT_Master_Idea_List.docx", b); console.log("wrote SMT_Master_Idea_List.docx"); });
