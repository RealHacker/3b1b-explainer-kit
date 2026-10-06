// Shared helpers for the Playwright-side tools. Each tool takes build/render.json (written by the Python CLI).
import { chromium } from "playwright";
import { pathToFileURL } from "url";
import fs from "fs";

export function loadJob(jsonPath) {
  if (!jsonPath || !fs.existsSync(jsonPath)) {
    console.error(`render job file not found: ${jsonPath}`);
    process.exit(2);
  }
  return JSON.parse(fs.readFileSync(jsonPath, "utf8"));
}

export async function launch() {
  try {
    return await chromium.launch();
  } catch (e) {
    console.error("Chromium failed to launch; run `npx playwright install chromium` in explainer-kit.\n" + e.message);
    process.exit(2);
  }
}

// Opens the project page and waits until scenes, timing and fonts are ready. Collects page errors into `errors`.
export async function openPage(browser, job, errors = []) {
  const page = await browser.newPage({ viewport: { width: job.width, height: job.height } });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(pathToFileURL(job.html).href);
  await page.waitForFunction(() => window.renderFrame && window.TIMING && window.explainerReady, null, { timeout: 30000 });
  await page.evaluate(() => window.explainerReady);
  return page;
}

// Lossless PNG capture. CDP's optimizeForSpeed uses cheaper zlib settings (same pixels, ~2-3x faster than
// page.screenshot); falls back to Playwright's screenshot if the CDP call is unavailable.
export async function makeCapture(page) {
  let cdp = null;
  try {
    cdp = await page.context().newCDPSession(page);
  } catch {
    cdp = null;
  }
  return async () => {
    if (cdp) {
      try {
        const r = await cdp.send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true });
        return Buffer.from(r.data, "base64");
      } catch {
        cdp = null;
      }
    }
    return page.screenshot({ type: "png" });
  };
}

// Resolve a time spec: global seconds, "sceneId@local", or "sceneId#beat:frac" (beat = 1-based index or beat id).
export function resolveTime(timing, spec) {
  const s = String(spec);
  if (s.includes("#")) {
    const [id, rest] = s.split("#");
    const [bi, fr = "0.5"] = rest.split(":");
    const sc = timing.scenes.find((x) => x.id === id);
    if (!sc) throw new Error(`unknown scene '${id}' in spec ${s}`);
    const cl = /^\d+$/.test(bi) ? sc.clips[parseInt(bi, 10) - 1] : sc.clips.find((c) => c.id === bi);
    if (!cl) throw new Error(`unknown beat '${bi}' in spec ${s}`);
    return sc.start + cl.start + cl.dur * parseFloat(fr);
  }
  if (s.includes("@")) {
    const [id, local] = s.split("@");
    const sc = timing.scenes.find((x) => x.id === id);
    if (!sc) throw new Error(`unknown scene '${id}' in spec ${s}`);
    return sc.start + parseFloat(local);
  }
  const t = parseFloat(s);
  if (!Number.isFinite(t)) throw new Error(`bad time spec '${s}'`);
  return t;
}
