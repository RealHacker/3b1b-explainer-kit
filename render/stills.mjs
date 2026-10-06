// Render PNG stills. Usage: node stills.mjs <build/render.json> <outDir> <prefix> <spec...>
// Prints a JSON array [{spec, t, file}] on the last line of stdout.
import path from "path";
import fs from "fs";
import { loadJob, launch, openPage, resolveTime } from "./common.mjs";

const [jobPath, outDir, prefix, ...specs] = process.argv.slice(2);
const job = loadJob(jobPath);
fs.mkdirSync(outDir, { recursive: true });
const browser = await launch();
const errors = [];
const page = await openPage(browser, job, errors);
const timing = await page.evaluate(() => window.TIMING);
const results = [];
let failed = false;
for (const spec of specs) {
  let t;
  try {
    t = resolveTime(timing, spec);
  } catch (e) {
    console.error(e.message);
    failed = true;
    continue;
  }
  await page.evaluate((x) => window.renderFrame(x), t);
  const file = path.join(outDir, `${prefix}_${String(spec).replace(/[^\w-]+/g, "_")}.png`);
  await page.screenshot({ path: file });
  results.push({ spec, t: Number(t.toFixed(3)), file });
}
await browser.close();
if (errors.length) {
  console.error("page errors:\n  " + errors.join("\n  "));
  failed = true;
}
console.log(JSON.stringify(results));
process.exit(failed ? 1 : 0);
