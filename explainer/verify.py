"""Automated checks on a finished video. Writes build/verify_report.json and build/contact_sheet.png.

fail: duration over limit, stream start/length mismatch, audio lag vs narration.wav, frame-scan errors,
      rendered frames that do not match a fresh browser render of the same timestamp.
warn: narration screen (rate / silence / clipping), layout warnings from the scan, loudness off target.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import audio
from . import render as render_mod
from .tts import beat_paths, log, word_count

ENV_SR = 16000
HOP_S = 0.005
MAX_LAG_S = 1.0
ONSET_WINDOW = (-0.4, 0.6)
ONSET_REL = 0.06
FRAME_MATCH_SAMPLES = 4
FRAME_MATCH_MIN_PSNR = 30.0
FRAME_MATCH_FRACTION = 0.5
CONTACT_FRACTION = 0.85
LOUDNESS_TOL_LU = 1.5
SILENCE_FRAME_S = 0.02
SILENCE_RMS = 0.01


class Report:
    def __init__(self):
        self.items = []

    def add(self, name, status, detail, data=None):
        self.items.append({"check": name, "status": status, "detail": detail, **({"data": data} if data else {})})
        mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "info": "INFO"}[status]
        log(f"{mark}  {name}: {detail}")

    @property
    def failed(self):
        return any(i["status"] == "fail" for i in self.items)


def ffprobe(path):
    res = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {res.stderr.strip()}")
    return json.loads(res.stdout)


def envelope(x, sr):
    hop = int(HOP_S * sr)
    n = x.size // hop
    env = np.abs(x[: n * hop]).reshape(n, hop).mean(axis=1)
    return (env - env.mean()) / (env.std() + 1e-9)


def best_lag(a, b):
    """Lag in seconds of b relative to a (positive = b late)."""
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    max_k = min(int(MAX_LAG_S / HOP_S), n - 1)
    best, best_k = -np.inf, 0
    for k in range(-max_k, max_k + 1):
        s = float(np.dot(a[: n - k], b[k:])) if k >= 0 else float(np.dot(a[-k:], b[: n + k]))
        if s > best:
            best, best_k = s, k
    return best_k * HOP_S


def check_streams(rep, project, info, timing):
    v = project.cfg["video"]
    fps = v["fps"]
    tol = project.cfg["checks"]["av_tolerance_frames"] / fps
    streams = {s["codec_type"]: s for s in info["streams"]}
    dur = float(info["format"]["duration"])
    limit = v["max_duration_s"]
    rep.add("duration", "pass" if dur <= limit else "fail", f"{dur:.3f}s ({dur / 60:.2f} min), limit {limit}s")
    vs, a_s = streams.get("video"), streams.get("audio")
    if not vs or not a_s:
        rep.add("streams", "fail", f"missing stream(s): video={bool(vs)} audio={bool(a_s)}")
        return
    rate = vs.get("r_frame_rate", "0/1").split("/")
    got_fps = float(rate[0]) / float(rate[1] or 1)
    res_ok = (vs["width"], vs["height"]) == (v["width"], v["height"]) and abs(got_fps - fps) < 0.01
    rep.add("video format", "pass" if res_ok else "warn",
            f"{vs['codec_name']} {vs['width']}x{vs['height']} @ {got_fps:g} fps, {vs.get('nb_frames', '?')} frames; "
            f"audio {a_s['codec_name']} {a_s['sample_rate']} Hz")
    if project.cfg["subtitles"]["enabled"]:
        rep.add("subtitles", "pass" if "subtitle" in streams else "warn",
                "soft subtitle track present" if "subtitle" in streams else "no subtitle track")
    vd, ad = float(vs.get("duration", dur)), float(a_s.get("duration", dur))
    vst, ast = float(vs.get("start_time", 0)), float(a_s.get("start_time", 0))
    ok = abs(vd - ad) <= tol and abs(vst) <= tol and abs(ast) <= tol and abs(vd - timing["total"]) <= tol
    rep.add("A/V alignment", "pass" if ok else "fail",
            f"video {vd:.3f}s from {vst:.3f}, audio {ad:.3f}s from {ast:.3f}, timeline {timing['total']:.3f}s (tol {tol * 1000:.0f} ms)")


def check_sync(rep, project, video, timing):
    sr = ENV_SR
    src_path = project.build / "narration.wav"
    if not src_path.exists():
        rep.add("audio lag", "fail", f"{src_path} missing")
        return
    src, fin = audio.read_audio(src_path, sr), audio.read_audio(video, sr)
    es, ef = envelope(src, sr), envelope(fin, sr)
    tol = project.cfg["checks"]["sync_tolerance_ms"] / 1000
    g = best_lag(es, ef)
    per = {}
    fps_env = 1 / HOP_S
    for sc in timing["scenes"]:
        a, b = int(sc["start"] * fps_env), int((sc["start"] + sc["dur"]) * fps_env)
        per[sc["id"]] = round(best_lag(es[a:b], ef[a:b]) * 1000)
    worst = max([abs(g * 1000)] + [abs(v) for v in per.values()])
    rep.add("audio lag", "pass" if worst <= tol * 1000 else "fail",
            f"global {g * 1000:+.0f} ms, worst scene {worst:.0f} ms (tol {tol * 1000:.0f} ms)", per)

    # Speech onset per beat in the final audio, relative to the beat's scheduled start.
    hop = int(SILENCE_FRAME_S * sr)
    rms = audio.frame_rms(fin, sr, SILENCE_FRAME_S)
    thresh = ONSET_REL * float(rms.max() or 1)
    offs = {}
    for sc in timing["scenes"]:
        for c in sc["clips"]:
            t0 = sc["start"] + c["start"]
            i0, i1 = int((t0 + ONSET_WINDOW[0]) * sr / hop), int((t0 + ONSET_WINDOW[1]) * sr / hop)
            seg = rms[max(0, i0):max(0, i1)]
            hit = np.flatnonzero(seg > thresh)
            offs[c["id"]] = round((max(0, i0) + hit[0]) * hop / sr - t0, 3) if hit.size else None
    vals = [v for v in offs.values() if v is not None]
    early = [k for k, v in offs.items() if v is not None and v < -0.1]
    missing = [k for k, v in offs.items() if v is None]
    status = "warn" if early or missing else "info"
    rep.add("beat onsets", status,
            f"speech starts {min(vals):+.2f}..{max(vals):+.2f}s after beat start (positive = leading breath/pause)"
            + (f"; early: {early}" if early else "") + (f"; no onset found: {missing}" if missing else ""), offs)


def check_narration(rep, project):
    ch = project.cfg["checks"]
    sr = project.cfg["audio"]["sample_rate"]
    lo, hi = ch["rate_range"]
    rows, flagged = [], []
    for b in project.beats():
        _, wav, _ = beat_paths(project, b)
        if not wav.exists():
            flagged.append(f"{b.id}: missing")
            continue
        x = audio.read_audio(wav, sr)
        dur = x.size / sr
        rate = dur / word_count(b.say)
        sil = audio.longest_run(audio.frame_rms(x, sr, SILENCE_FRAME_S) < SILENCE_RMS) * SILENCE_FRAME_S
        clips = audio.clipped_runs(x)
        peak = float(np.abs(x).max()) if x.size else 0.0
        issues = []
        if not lo <= rate <= hi:
            issues.append(f"rate {rate:.2f}s/word")
        if sil > ch["max_internal_silence_s"] + project.cfg["tts"]["pause_s"] * b.say.count("|"):
            issues.append(f"silence {sil:.2f}s")
        if clips:
            issues.append(f"{clips} clipped runs")
        rows.append({"id": b.id, "dur": round(dur, 2), "rate": round(rate, 3), "max_silence": round(sil, 2),
                     "peak": round(peak, 3), "issues": issues})
        if issues:
            flagged.append(f"{b.id}: {', '.join(issues)}")
    rates = [r["rate"] for r in rows]
    detail = (f"{len(rows)} clips, rate {min(rates):.2f}-{max(rates):.2f}s/word" if rates else "no clips") + \
        (f"; flagged: {'; '.join(flagged)}" if flagged else "")
    rep.add("narration screen", "warn" if flagged else "pass", detail, rows)


def check_scan(rep, project, skip_scan):
    path = project.build / "scan_report.json"
    if not skip_scan or not path.exists():
        render_mod.scan(project)
    if not path.exists():
        rep.add("frame scan", "fail", "scan did not produce a report")
        return
    r = json.loads(path.read_text(encoding="utf-8"))
    rep.add("frame scan", "fail" if r["errors"] else "pass",
            f"{r['frames']} frames evaluated, {len(r['errors'])} errors", r["errors"][:20] or None)
    ws = r["warnings"]
    rep.add("layout", "warn" if ws else "pass",
            f"{r['layoutFrames']} samples, {len(ws)} off-canvas/overlap findings" +
            ("".join(f"\n        t={w['t']} [{w['scene']}] {w['msg']}" for w in ws[:12])), ws or None)


def extract_frames(video, frames, out_pattern, scale=None):
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    vf = f"select='{sel}'" + (f",scale={scale}" if scale else "")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", vf, "-fps_mode", "passthrough",
                    str(out_pattern)], check=True)


def check_frames(rep, project, video, timing, tmp):
    """Compare frames decoded from the MP4 with fresh browser renders of the same timestamps (PSNR)."""
    fps = project.cfg["video"]["fps"]
    frames = sorted({int(timing["total"] * fps * (i + FRAME_MATCH_FRACTION) / FRAME_MATCH_SAMPLES) for i in range(FRAME_MATCH_SAMPLES)})
    extract_frames(video, frames, Path(tmp) / "mp4_%02d.png")
    job = render_mod.job_file(project)
    specs = [f"{n / fps:.6f}" for n in frames]
    res = subprocess.run(["node", str(render_mod.NODE_TOOLS / "stills.mjs"), str(job), str(tmp), "ref", *specs],
                         cwd=str(render_mod.KIT_ROOT), capture_output=True, text=True)
    refs = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else []
    results = {}
    for i, (n, ref) in enumerate(zip(frames, refs), 1):
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(Path(tmp) / f"mp4_{i:02d}.png"), "-i", ref["file"],
                            "-lavfi", "psnr", "-f", "null", "-"], capture_output=True, text=True)
        line = next((ln for ln in r.stderr.splitlines() if "average:" in ln), "")
        val = line.split("average:")[1].split()[0] if line else "0"
        results[f"frame {n} (t={n / fps:.2f}s)"] = float("inf") if val == "inf" else float(val)
    if not results:
        rep.add("frame match", "fail", f"could not compare frames: {res.stderr.strip()[:200]}")
        return
    worst = min(results.values())
    rep.add("frame match", "pass" if worst >= FRAME_MATCH_MIN_PSNR else "fail",
            f"{len(results)} MP4 frames vs browser render, worst PSNR {worst:.1f} dB (min {FRAME_MATCH_MIN_PSNR})", results)


def contact_sheet(rep, project, video, timing, tmp):
    ch, fps = project.cfg["checks"], project.cfg["video"]["fps"]
    frames = sorted({int((s["start"] + c["start"] + c["dur"] * CONTACT_FRACTION) * fps) for s in timing["scenes"] for c in s["clips"]})
    w = ch["contact_width"]
    extract_frames(video, frames, Path(tmp) / "cs_%03d.png", scale=f"{w}:{w * 9 // 16}")
    files = sorted(Path(tmp).glob("cs_*.png"))
    out = project.build / "contact_sheet.png"
    render_mod.tile_sheet(files, out, ch["contact_columns"], tile_w=w)
    rep.add("contact sheet", "info", f"{len(files)} frames (one per beat at {int(CONTACT_FRACTION * 100)}%) -> {out}")


def check_loudness(rep, project, video):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr[r.stderr.rfind("Summary:"):]
    try:
        integ = float(txt.split("I:")[1].split("LUFS")[0])
        peak = float(txt.split("Peak:")[1].split("dBFS")[0])
    except (IndexError, ValueError):
        rep.add("loudness", "warn", "could not parse ebur128 output")
        return
    target = project.cfg["audio"]["loudness_i"]
    rep.add("loudness", "pass" if abs(integ - target) <= LOUDNESS_TOL_LU else "warn",
            f"integrated {integ:.1f} LUFS (target {target}), true peak {peak:.1f} dBFS")


def verify(project, video=None, skip_scan=False):
    video = Path(video) if video else project.output_mp4
    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    timing = json.loads((project.build / "timing.json").read_text(encoding="utf-8"))
    rep = Report()
    log(f"verifying {video}")
    check_streams(rep, project, ffprobe(video), timing)
    check_sync(rep, project, video, timing)
    check_narration(rep, project)
    check_scan(rep, project, skip_scan)
    with tempfile.TemporaryDirectory() as tmp:
        check_frames(rep, project, video, timing, tmp)
        contact_sheet(rep, project, video, timing, tmp)
    check_loudness(rep, project, video)
    out = project.build / "verify_report.json"
    out.write_text(json.dumps({"video": str(video), "failed": rep.failed, "checks": rep.items}, indent=1), encoding="utf-8")
    n = {s: sum(i["status"] == s for i in rep.items) for s in ("pass", "warn", "fail")}
    log(f"verify: {n['pass']} pass, {n['warn']} warn, {n['fail']} fail -> {out}")
    return 1 if rep.failed else 0
