// Deterministic frame renderer: N workers (one Chromium each — pages in a shared browser serialize on its
// screenshot pipeline) render contiguous frame ranges, each piped into its own ffmpeg; segments are then
// concatenated losslessly. Usage: node render.mjs <build/render.json>
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { loadJob, launch, openPage, makeCapture } from "./common.mjs";

const PROGRESS_EVERY = 300;
const job = loadJob(process.argv[2]);
const { fps } = job;
const segDir = path.join(job.build, "segments");
fs.rmSync(segDir, { recursive: true, force: true });
fs.mkdirSync(segDir, { recursive: true });

const firstFrame = Math.round(job.start * fps);
const lastFrame = Math.round(job.end * fps); // exclusive
const nFrames = lastFrame - firstFrame;
if (nFrames <= 0) {
  console.error(`nothing to render (start ${job.start}, end ${job.end})`);
  process.exit(2);
}
const workers = Math.max(1, Math.min(job.workers, nFrames));
console.log(`rendering ${nFrames} frames (${(nFrames / fps).toFixed(1)}s) at ${job.width}x${job.height} with ${workers} workers`);

function ffmpegFor(out) {
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
    "-c:v", "libx264", "-preset", job.preset, "-crf", String(job.crf), "-pix_fmt", "yuv420p", "-r", String(fps), out],
    { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => {
    ff.on("error", rej);
    ff.on("close", (code) => (code === 0 ? res() : rej(new Error(`ffmpeg exit ${code} for ${out}`))));
  });
  return { ff, done };
}

const write = (stream, buf) => new Promise((res) => {
  if (stream.write(buf)) res();
  else stream.once("drain", res);
});

const t0 = Date.now();
let rendered = 0;
const chunk = Math.ceil(nFrames / workers);
const segs = [];
const browsers = [];

async function runWorker(k) {
  const a = firstFrame + k * chunk, b = Math.min(lastFrame, a + chunk);
  if (a >= b) return;
  const out = path.join(segDir, `seg_${String(k).padStart(2, "0")}.mp4`);
  segs[k] = out;
  const errors = [];
  const browser = await launch();
  browsers.push(browser);
  const page = await openPage(browser, job, errors);
  const capture = await makeCapture(page);
  const { ff, done } = ffmpegFor(out);
  let pipeErr = null;
  ff.stdin.on("error", (e) => { pipeErr = e; });
  for (let fr = a; fr < b; fr++) {
    if (pipeErr) throw pipeErr;
    if (errors.length) break;
    await page.evaluate((t) => window.renderFrame(t), fr / fps);
    await write(ff.stdin, await capture());
    rendered++;
    if (rendered % PROGRESS_EVERY === 0) {
      const el = (Date.now() - t0) / 1000;
      console.log(`${rendered}/${nFrames} frames, ${el.toFixed(0)}s elapsed, ETA ${(el / rendered * (nFrames - rendered)).toFixed(0)}s`);
    }
  }
  ff.stdin.end();
  await done;
  await browser.close();
  if (errors.length) throw new Error(`page errors in worker ${k}: ${errors.slice(0, 3).join("; ")}`);
}

const closeAll = () => Promise.all(browsers.map((b) => b.close().catch(() => null)));
try {
  await Promise.all(Array.from({ length: workers }, (_, k) => runWorker(k)));
} catch (e) {
  console.error(`render failed: ${e.message}`);
  await closeAll();
  process.exit(1);
}
const list = segs.filter(Boolean).map((s) => `file '${s.replace(/\\/g, "/")}'`).join("\n");
fs.writeFileSync(path.join(segDir, "list.txt"), list);
await new Promise((res, rej) => {
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(segDir, "list.txt"),
    "-c", "copy", job.out], { stdio: "inherit" });
  ff.on("close", (c) => (c === 0 ? res() : rej(new Error("segment concat failed"))));
});
console.log(`${path.basename(job.out)} written in ${((Date.now() - t0) / 1000).toFixed(0)}s (${(nFrames / ((Date.now() - t0) / 1000)).toFixed(1)} fps)`);
