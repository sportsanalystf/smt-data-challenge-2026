// Builds Abstract.docx and Narrative_Paper.docx for the flagship "Robbery Meter".
const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
        AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, Footer } = require("docx");

const GREEN="0B6B3A", DARK="1B1B1B", ACCENT="C8102E", LIGHT="E8F2EC";
const BASE=require("path").resolve(__dirname, "..");
const FIG=BASE+"/outputs/figures";

const baseStyles = {
  default:{document:{run:{font:"Arial", size:22}, paragraph:{spacing:{after:120, line:276}}}},
  paragraphStyles:[
    {id:"Heading1", name:"Heading 1", basedOn:"Normal", next:"Normal", quickFormat:true,
      run:{size:28, bold:true, color:GREEN, font:"Arial"}, paragraph:{spacing:{before:280, after:120}, outlineLevel:0}},
    {id:"Heading2", name:"Heading 2", basedOn:"Normal", next:"Normal", quickFormat:true,
      run:{size:23, bold:true, color:DARK, font:"Arial"}, paragraph:{spacing:{before:180, after:80}, outlineLevel:1}},
    {id:"Title", name:"Title", basedOn:"Normal", next:"Normal",
      run:{size:40, bold:true, color:GREEN, font:"Arial"}, paragraph:{spacing:{after:60}}},
  ]
};
const P = (runs) => new Paragraph({ children: Array.isArray(runs)?runs:[new TextRun(runs)] });
const t = (text, o={}) => new TextRun({text, ...o});
function img(file, w, h, caption) {
  const p = new Paragraph({ alignment:AlignmentType.CENTER, spacing:{before:120, after:40},
    children:[new ImageRun({ type:"png", data:fs.readFileSync(FIG+"/"+file),
      transformation:{width:w, height:h}, altText:{title:caption, description:caption, name:file}})]});
  const cap = new Paragraph({ alignment:AlignmentType.CENTER, spacing:{after:160},
    children:[new TextRun({text:caption, italics:true, size:18, color:"666666"})]});
  return [p, cap];
}
const border={style:BorderStyle.SINGLE, size:1, color:"CCCCCC"};
const borders={top:border,bottom:border,left:border,right:border,insideHorizontal:border,insideVertical:border};
function cell(text,w,{head=false,fill=null}={}) {
  return new TableCell({borders, width:{size:w,type:WidthType.DXA},
    shading: fill?{fill,type:ShadingType.CLEAR}:(head?{fill:GREEN,type:ShadingType.CLEAR}:undefined),
    margins:{top:50,bottom:50,left:110,right:110},
    children:[new Paragraph({spacing:{after:0}, children:[new TextRun({text:String(text), bold:head, color:head?"FFFFFF":DARK, size:18})]})]});
}
function table(cols, rows){
  const total=cols.reduce((a,c)=>a+c.w,0);
  const head=new TableRow({tableHeader:true, children:cols.map(c=>cell(c.t,c.w,{head:true}))});
  const body=rows.map((r,i)=>new TableRow({children:r.map((v,j)=>cell(v,cols[j].w,{fill:i%2?LIGHT:"FFFFFF"}))}));
  return new Table({width:{size:total,type:WidthType.DXA}, columnWidths:cols.map(c=>c.w), rows:[head,...body]});
}
const footer = (title) => ({default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER, spacing:{after:0}, children:[
  new TextRun({text:title+"  |  Page ", size:16, color:"888888"}),
  new TextRun({children:[PageNumber.CURRENT], size:16, color:"888888"})]})]})});
const pageProps = {page:{size:{width:12240,height:15840}, margin:{top:1440,right:1440,bottom:1440,left:1440}}};

// ---------------------------------------------------------------- ABSTRACT
const abstract = new Document({ styles: baseStyles, sections:[{
  properties: pageProps, footers: footer("SMT Data Challenge 2026 — Abstract"),
  children:[
    new Paragraph({style:"Title", children:[t("The Robbery Meter")]}),
    P([t("Turning Outfield Tracking Data into a Live Scoreboard Story", {bold:true, size:24, color:DARK})]),
    P([t("SMT Data Challenge 2026 — “On the Big Screen!”  ·  Category: Defensive entertainment metric, visualization, and interactive fan experience", {italics:true, color:"555555", size:20})]),
    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("Abstract")]}),
    P([t("Baseball is entertainment, and the most electric moment in any ballpark is a defender running down a ball that looked uncatchable. We turn that moment into a scoreboard product. Using 250 games of SMT player- and ball-tracking data from a full Minor League season, we identified 7,058 outfield catch opportunities and engineered three physically meaningful features from the raw 20 Hz positions: the fielder’s route distance to the ball, the ball’s hang time, and the required closing speed those two imply. A calibrated logistic model estimates the probability that any given ball is caught, achieving 95.4% classification accuracy and a Brier score of 0.039 against an 85.0% base catch rate.")]),
    P([t("From this single model we derive three ready-to-air features. First, "), t("Outs Above Expected",{bold:true}), t(" ranks the league’s best defenders by catches made beyond what the model expected; the top outfielder was +9.2 outs above expected across 254 chances. Second, an automatically selected "), t("Web Gem of the Night",{bold:true}), t(" surfaces the most improbable completed catch — for example, a right fielder who covered 140 feet in 6.5 seconds to make a catch the model gave a 19% chance, a “Robbery Score” of 81 out of 100. Third, a "), t("“Catch or No Catch?”",{bold:true}), t(" crowd-vote game freezes the play at contact and lets fans predict the outcome before the model reveals the odds, converting the same math into live audience participation.")]),
    P([t("The Robbery Meter bridges technical rigor and fan engagement: it is defensible to analysts as a calibrated tracking-data model, and instantly legible to a family in the stands as a number between 0 and 100. It requires only data the league already collects, and it scales from a single highlight graphic to a season-long leaderboard. We provide the full, reproducible pipeline and nine companion scoreboard concepts so a club could deploy an entire in-game analytics slate from one codebase.")]),
  ]
}]});

// ---------------------------------------------------------------- NARRATIVE
const narr = new Document({ styles: baseStyles, sections:[{
  properties: pageProps, footers: footer("SMT Data Challenge 2026 — The Robbery Meter"),
  children:[
    new Paragraph({style:"Title", children:[t("The Robbery Meter")]}),
    P([t("Turning Outfield Tracking Data into a Live Scoreboard Story", {bold:true, size:24, color:DARK})]),
    P([t("SMT Data Challenge 2026 — “On the Big Screen!”", {italics:true, color:"555555", size:20})]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("1. The problem: the best moment in baseball has no number")]}),
    P([t("A pitch has a velocity. A home run has an exit velocity and a distance. But the play that makes a Minor League crowd rise to its feet — an outfielder sprinting into the gap and laying out for a ball that should have dropped — has no number on the scoreboard. It is described, replayed, and forgotten. The prompt for this year’s challenge asks for “an entertainment metric for which player makes the unlikeliest plays.” That is exactly the gap we set out to fill: to give the most exciting defensive moment in the game a single, honest, fan-readable number, and to build the scoreboard features that number unlocks.")]),
    P([t("Our guiding constraint was the seven-second rule. A scoreboard graphic has about seven seconds of a fan’s attention. Whatever we built had to be reducible to something a child could read at a glance, while remaining rigorous enough that a scout or analyst would trust it. We call the result the "), t("Robbery Meter",{bold:true}), t(": the probability that a batted ball is caught, and its inverse — how much of a “robbery” it is when a fielder catches it anyway.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("2. The data")]}),
    P([t("The SMT dataset provides optical tracking for 250 games from a single Level-7 Minor League season. Player positions are recorded at 20 Hz as (x, y) coordinates in feet; the ball is tracked in three dimensions (x, y, z). A companion event table time-stamps each pitch, hit, acquisition, throw, and the end of every play, and a lineup table maps each of the thirteen tracked player roles to an anonymized player code. The coordinate system places the origin at home plate, with the x-axis running toward first base and the y-axis toward second.")]),
    P([t("From this raw feed we extracted, in a single pass over every game, the events that matter for defense: each time a batter put a ball in play, whether it traveled to the outfield, and whether an outfielder ultimately caught it. This produced 7,058 clean outfield catch opportunities — the population the Robbery Meter is built on — alongside batted-ball, pitch, throw, and baserunning features that power the companion metrics described in Section 7.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("3. From problem to solution: engineering the features")]}),
    P([t("A catch is hard for two reasons: the ball is far from the fielder, and there is little time to get there. We turned those intuitions into three engineered features, each computed directly from the tracking data.")]),
    P([t("Route distance",{bold:true}), t(" is the straight-line distance, in feet, from where the fielder stood at the instant of contact to where the ball was caught or landed. "), t("Hang time",{bold:true}), t(" is the elapsed time, in seconds, between contact and that same endpoint. From these we derived the "), t("required closing speed",{bold:true}), t(" — route distance divided by hang time — the average speed a fielder would need to sustain to arrive on time. This third feature encodes the physics of the play: a 60-foot route is routine with five seconds of hang time and nearly impossible with two.")]),
    P([t("Building these features required care with the event stream. We defined a catch opportunity as a batted ball whose trajectory carried it past the infield, and classified it as caught only when an outfielder acquired the ball in flight. For balls that were not caught, we located the landing point from the ball’s descent and measured the route to the nearest outfielder, so that difficult non-catches are represented fairly rather than ignored.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("4. The model")]}),
    P([t("We fit a logistic-regression classifier that maps the three features to a catch probability. The model is deliberately simple: three interpretable inputs, a transparent functional form, and no black box. This matters for a scoreboard product — when the graphic tells 4,000 fans a catch was a 20% play, the club needs to be able to explain why, and “the ball was 140 feet away with six seconds to get there” is an explanation anyone can follow.")]),
    ...img("fig_catch_probability_model.png", 520, 327,
      "Figure 1. The Robbery Meter model. Catch probability falls as the fielder’s route lengthens and rises with more hang time. A 60-foot route is nearly automatic with 5 seconds of hang time but a coin flip with 3."),
    P([t("On the 7,058 opportunities, the model classified outcomes with 95.4% accuracy and a Brier score of 0.039 against a base catch rate of 85.0% — well-calibrated probabilities, not just correct labels. The fitted coefficients confirm the physics: longer routes and higher required speeds sharply reduce catch probability, while additional hang time increases it. The model’s shape (Figure 1) is smooth and monotonic, exactly what a defensible fan metric should be.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("5. Three scoreboard products from one model")]}),
    new Paragraph({heading:HeadingLevel.HEADING_2, children:[t("5.1 Outs Above Expected — the season leaderboard")]}),
    P([t("Summing “catch made minus catch probability” over every opportunity gives each fielder an Outs Above Expected (OAE) total: how many outs they recorded beyond what an average defender would have, given the same chances. This is the scoreboard’s season-long story — a running leaderboard of the league’s best gloves. The top outfielder in our data was +9.2 outs above expected across 254 chances, converting 223 catches where the model expected roughly 214.")]),
    ...img("fig_oae_leaderboard.png", 470, 336,
      "Figure 2. Outs Above Expected leaderboard. Positive bars are defenders who caught more than expected given their chances."),
    new Paragraph({heading:HeadingLevel.HEADING_2, children:[t("5.2 Web Gem of the Night — the highlight engine")]}),
    P([t("Every completed catch carries a Robbery Score of 100 × (1 − catch probability). Sorting the night’s catches by this score automatically surfaces the single most improbable play — no producer required. In our data the season’s top Web Gem was a right fielder who ran 140 feet in 6.5 seconds to complete a catch the model rated a 19% chance: a Robbery Score of 81. Figure 3 shows the graphic the scoreboard would display — the fielder’s tracked route in red, the ball’s path dashed, and the odds front and center.")]),
    ...img("fig_webgem_hero.png", 430, 360,
      "Figure 3. The Web Gem graphic. The fielder’s tracked route (red) and the ball’s flight (dashed) over a field diagram, annotated with the Robbery Meter odds — a highlight the crowd can read instantly."),
    new Paragraph({heading:HeadingLevel.HEADING_2, children:[t("5.3 “Catch or No Catch?” — the crowd-vote game")]}),
    P([t("The same model powers live audience participation. When a fly ball is hit, the broadcast freezes at the moment of contact and the scoreboard asks the crowd to vote: will he catch it? Fans vote from their phones or by cheering, the play resumes, and the model’s pre-computed probability is revealed alongside the result. The most compelling plays to feature are the ones the model rates closest to a coin flip; our pipeline isolates these near-50% opportunities automatically, guaranteeing genuine suspense rather than obvious outcomes. It is the same mathematics as the OAE leaderboard, repackaged as a game.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("6. Why this works on the big screen")]}),
    P([t("The Robbery Meter succeeds against all three of the challenge’s stated aims. It is "), t("creative and relevant",{bold:true}), t(" because it names a moment fans already love but that no existing stat captures. It is "), t("methodologically sound",{bold:true}), t(" because it is a calibrated classifier built from first-principles features, transparent enough to defend to a technical judge. And it is "), t("a story anyone can tell",{bold:true}), t(": one number between 0 and 100, a red line tracing a sprint across the grass, and a question — will he catch it? — that needs no baseball literacy to enjoy.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("7. A companion scoreboard suite")]}),
    P([t("The Robbery Meter anchors a broader slate of nine scoreboard features we built on the same data and codebase, so a club could deploy an entire in-game analytics package rather than a single graphic. Each was prototyped on the real season and produces live values today.")]),
    table(
      [{t:"Feature", w:2100},{t:"What the crowd sees", w:3900},{t:"Headline value", w:2760}],
      [
        ["Burner Board","Fastest sprint to first base, in mph","Top runner 22.8 mph"],
        ["Statcast Smash","Hardest-hit balls of the night","121.6 mph (90th-pct leader)"],
        ["Moonshot Meter","Estimated carry distance of long flies","466.9 ft longest"],
        ["Radar Gun Live","Pitch velocity leaderboard","103 mph top pitch"],
        ["Outfield Cannons","Throw / arm velocity","102 mph hardest throw"],
        ["Barrel Zone","Sweet-spot exit velo × launch angle","13.3% barrel-rate leader"],
        ["Ground Crew Range","Ground covered chasing fly balls","83 ft average route (top CF)"],
        ["Five-Tool Scoreboard","One number blending speed, power, arm","97.5 / 100 top score"],
        ["How Far / Guess the Gun","Fan estimation mini-games","Built on the above feeds"],
      ]
    ),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("8. Limitations and future work")]}),
    P([t("Our features are honest but approximate. Route distance is measured as a straight line rather than the fielder’s true curved path, so it slightly understates effort on balls hit over a player’s head; hang time and catch classification depend on the event stream’s timing. The model uses three features for interpretability, but wall proximity, the fielder’s starting direction, and ball spin would sharpen it further. Because the data is a single anonymized level and season, leaguewide rates should be read as within-sample. Natural extensions include a full route-efficiency term (actual path length versus optimal), separate models by outfield position, and a real-time inference layer that scores a play within a second of contact for live broadcast. None of these change the core result: the tracking data the league already collects is enough to give baseball’s best moment a number.")]),

    new Paragraph({heading:HeadingLevel.HEADING_1, children:[t("9. Conclusion")]}),
    P([t("The Robbery Meter takes the play that makes a ballpark gasp and gives it a number the whole ballpark can read. From one calibrated model we produced a defensive leaderboard, an automatic highlight engine, and a live crowd-vote game — three products, one pipeline, all built from raw tracking data. It is the kind of idea the prompt asked for: original, grounded in the data, rigorous under the hood, and, above all, fun on the big screen.")]),
    P([t("Reproducibility: the complete analysis — feature extraction, model, leaderboards, and figures — is provided as a Quarto (.qmd) file and supporting Python modules alongside this paper.", {italics:true, color:"555555", size:20})]),
  ]
}]});

Promise.all([
  Packer.toBuffer(abstract).then(b=>fs.writeFileSync(BASE+"/Abstract.docx", b)),
  Packer.toBuffer(narr).then(b=>fs.writeFileSync(BASE+"/Narrative_Paper.docx", b)),
]).then(()=>console.log("wrote Abstract.docx and Narrative_Paper.docx"));
