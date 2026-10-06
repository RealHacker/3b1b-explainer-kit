// Frame scan. Usage: node scan.mjs <build/render.json> <report.json>
//  1. every frame (scanStep): renderFrame must not throw; markup must not contain NaN/undefined/Infinity attributes.
//  2. sampled layout (layoutStep): visible text (incl. KaTeX) must stay on-canvas and must not overlap other text.
// Exit code 1 when errors (1) are found; layout findings are warnings for a human/agent to inspect as stills.
import fs from "fs";
import { loadJob, launch, openPage } from "./common.mjs";

const MAX_ERRORS = 50;
const [jobPath, reportPath] = process.argv.slice(2);
const job = loadJob(jobPath);
const browser = await launch();
const pageErrors = [];
const page = await openPage(browser, job, pageErrors);

const report = await page.evaluate(({ scanStep, layoutStep, maxErrors }) => {
  const W = window.E.W, H = window.E.H;
  const total = window.TIMING.total;
  const BAD_ATTR = /="[^"]*(NaN|undefined|Infinity)[^"]*"/;
  const errors = [];
  let frames = 0;
  for (let i = 0; ; i++) {
    const t = i * scanStep;
    if (t >= total) break;
    frames++;
    try {
      window.renderFrame(t);
      const html = document.getElementById("stage").innerHTML;
      const m = html.match(BAD_ATTR);
      if (m) errors.push({ t: +t.toFixed(3), scene: window.sceneAt(t), msg: `bad attribute value ${m[0].slice(0, 80)}` });
    } catch (e) {
      errors.push({ t: +t.toFixed(3), scene: window.sceneAt(t), msg: e.message });
    }
    if (errors.length >= maxErrors) break;
  }

  const OFF_TOL = 2, VISIBLE_MIN = 0.05, OVERLAP_VISIBLE_MIN = 0.35, OVERLAP_MIN_PX = 4;
  const svgScale = () => document.querySelector("#stage svg").getBoundingClientRect().width / W;
  function visibleOpacity(el) {
    let op = 1;
    for (let n = el; n && n.tagName && n.tagName.toLowerCase() !== "svg"; n = n.parentNode) {
      const a = n.getAttribute && n.getAttribute("opacity");
      if (a != null) op *= parseFloat(a);
    }
    return op;
  }
  const warnings = new Map();
  const warn = (key, t, scene, msg) => {
    const w = warnings.get(key);
    if (w) { w.count++; w.last = +t.toFixed(2); } else warnings.set(key, { t: +t.toFixed(2), last: +t.toFixed(2), scene, msg, count: 1 });
  };
  let layoutFrames = 0;
  for (let t = 0; t < total; t += layoutStep) {
    try { window.renderFrame(t); } catch { continue; }
    layoutFrames++;
    const k = svgScale(), scene = window.sceneAt(t);
    const items = [];
    for (const el of document.querySelectorAll("#stage text")) {
      const txt = el.textContent.trim();
      if (!txt) continue;
      items.push({ el, txt, op: visibleOpacity(el) });
    }
    for (const el of document.querySelectorAll("#stage foreignObject .katex")) {
      items.push({ el, tex: true, txt: "TeX: " + (el.closest("foreignObject").dataset.tex ?? el.textContent).slice(0, 40), op: visibleOpacity(el.closest("foreignObject")) });
    }
    const boxes = [];
    for (const it of items) {
      if (it.op < VISIBLE_MIN) continue;
      let r = it.el.getBoundingClientRect();
      if (it.tex) {
        const range = document.createRange();
        range.selectNodeContents(it.el);
        r = range.getBoundingClientRect();
      }
      if (r.width === 0 || r.height === 0) continue;
      const b = { x0: r.left / k, y0: r.top / k, x1: r.right / k, y1: r.bottom / k, txt: it.txt, op: it.op };
      if (b.x0 < -OFF_TOL || b.y0 < -OFF_TOL || b.x1 > W + OFF_TOL || b.y1 > H + OFF_TOL) {
        warn(`off|${scene}|${it.txt}`, t, scene, `text off-canvas: "${it.txt.slice(0, 50)}" [${b.x0.toFixed(0)},${b.y0.toFixed(0)} - ${b.x1.toFixed(0)},${b.y1.toFixed(0)}]`);
      }
      if (it.op >= OVERLAP_VISIBLE_MIN) boxes.push(b);
    }
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.txt === b.txt) continue;
        const ix = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), iy = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
        if (ix > OVERLAP_MIN_PX && iy > OVERLAP_MIN_PX) {
          const pair = [a.txt, b.txt].sort().map((s) => s.slice(0, 40));
          warn(`ovl|${scene}|${pair.join("|")}`, t, scene, `text overlap: "${pair[0]}" / "${pair[1]}"`);
        }
      }
    }
  }
  return { total, frames, scanStep, layoutFrames, layoutStep, errors, warnings: [...warnings.values()] };
}, { scanStep: job.scanStep, layoutStep: job.layoutStep, maxErrors: MAX_ERRORS });

await browser.close();
for (const e of pageErrors) report.errors.push({ t: null, scene: null, msg: `page error: ${e}` });
fs.writeFileSync(reportPath, JSON.stringify(report, null, 1));
console.log(`scanned ${report.frames} frames (every ${report.scanStep.toFixed(3)}s) + ${report.layoutFrames} layout samples: ` +
  `${report.errors.length} errors, ${report.warnings.length} layout warnings`);
for (const e of report.errors.slice(0, 20)) console.log(`  ERROR t=${e.t} [${e.scene}] ${e.msg}`);
for (const w of report.warnings.slice(0, 30)) console.log(`  WARN  t=${w.t}${w.count > 1 ? `..${w.last} (x${w.count})` : ""} [${w.scene}] ${w.msg}`);
process.exit(report.errors.length ? 1 : 0);
