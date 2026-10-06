"""Global timeline from measured clip durations, plus the narration track and SRT subtitles."""
import json
import re

import numpy as np

from . import audio
from .tts import beat_paths, log, word_count


def beat_duration(project, beat):
    _, wav, meta = beat_paths(project, beat)
    if wav.exists():
        if meta.exists():
            try:
                return float(json.loads(meta.read_text(encoding="utf-8"))["dur"]), True
            except (ValueError, KeyError, OSError):
                pass
        sr = project.cfg["audio"]["sample_rate"]
        return audio.read_audio(wav, sr).size / sr, True
    return word_count(beat.say) * project.cfg["timing"]["est_sec_per_word"], False


def build_timeline(project):
    tc = project.cfg["timing"]
    fps = project.cfg["video"]["fps"]
    t, scenes, missing = 0.0, [], []
    for sc in project.scenes():
        start, local, clips = t, tc["scene_lead_s"], []
        for i, b in enumerate(sc.beats):
            dur, real = beat_duration(project, b)
            if not real:
                missing.append(b.id)
            clips.append({"id": b.id, "start": round(local, 3), "dur": round(dur, 3), "text": b.text, "real": real})
            local += dur
            if i < len(sc.beats) - 1:
                local += b.gap_after_s if b.gap_after_s is not None else tc["beat_gap_s"]
        tail = sc.tail_s if sc.tail_s is not None else tc["scene_tail_overrides"].get(sc.id, tc["scene_tail_s"])
        local += tail
        scenes.append({"id": sc.id, "header": sc.header, "start": round(start, 3), "dur": round(local, 3), "clips": clips})
        t += local
    return {"fps": fps, "total": round(t, 3), "scenes": scenes, "missing": missing}


def split_subs(text, max_chars):
    sentences = re.split(r"(?<=[.!?:;])\s+", text.strip())
    cues, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > max_chars:
            cues.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
        while len(cur) > max_chars:
            cut = cur.rfind(", ", 0, max_chars)
            if cut < 20:
                cut = cur.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            cues.append(cur[: cut + 1].strip())
            cur = cur[cut + 1:].strip()
    if cur:
        cues.append(cur)
    return cues


def wrap2(cue, width):
    if len(cue) <= width:
        return cue
    mid = len(cue) // 2
    left, right = cue.rfind(" ", 0, mid), cue.find(" ", mid)
    if left == -1 and right == -1:
        return cue
    cut = left if right == -1 or (left != -1 and mid - left <= right - mid) else right
    return cue[:cut] + "\n" + cue[cut + 1:]


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_timing(project, timing):
    b = project.build
    b.mkdir(parents=True, exist_ok=True)
    (b / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    (b / "timing.js").write_text("window.TIMING = " + json.dumps(timing) + ";\n", encoding="utf-8")


def build_audio(project, timing):
    """Place each clip at its timeline position; peak-normalize; write narration.wav and subtitles.srt."""
    if timing["missing"]:
        raise RuntimeError(f"cannot build narration, {len(timing['missing'])} clips missing: {timing['missing']}")
    acfg, scfg = project.cfg["audio"], project.cfg["subtitles"]
    sr = acfg["sample_rate"]
    n_total = int(round(timing["total"] * sr))
    track = np.zeros(n_total, np.float32)
    beats = {b.id: b for b in project.beats()}
    cues = []
    for s in timing["scenes"]:
        for c in s["clips"]:
            _, wav, _ = beat_paths(project, beats[c["id"]])
            x = audio.read_audio(wav, sr)
            g0 = s["start"] + c["start"]
            i0 = int(round(g0 * sr))
            n = max(0, min(x.size, n_total - i0))
            track[i0:i0 + n] += x[:n]
            parts = split_subs(c["text"], scfg["max_chars"])
            total_w = sum(len(p) for p in parts)
            acc = 0.0
            for p in parts:
                d = c["dur"] * len(p) / total_w
                cues.append((g0 + acc, g0 + acc + d, p))
                acc += d
    peak = float(np.abs(track).max()) if track.size else 0.0
    if peak > 0:
        track *= acfg["narration_peak"] / peak
    audio.write_wav(project.build / "narration.wav", track, sr, pcm16=True)
    srt = project.build / "subtitles.srt"
    with open(srt, "w", encoding="utf-8") as fh:
        for i, (a, b2, p) in enumerate(cues, 1):
            fh.write(f"{i}\n{srt_time(a)} --> {srt_time(b2)}\n{wrap2(p, scfg['wrap_chars'])}\n\n")
    log(f"narration.wav written (peak normalized from {peak:.3f}); {len(cues)} subtitle cues")


def run(project, with_audio=True):
    timing = build_timeline(project)
    write_timing(project, timing)
    total = timing["total"]
    limit = project.cfg["video"]["max_duration_s"]
    log(f"timeline {total:.1f}s ({total / 60:.2f} min, limit {limit}s); {len(timing['missing'])} clips estimated")
    for s in timing["scenes"]:
        log(f"  {s['id']:<14} start {s['start']:7.2f}  dur {s['dur']:6.2f}  beats {len(s['clips'])}")
    if total > limit:
        log(f"WARN timeline exceeds max_duration_s by {total - limit:.1f}s; trim narration")
    if with_audio and not timing["missing"]:
        build_audio(project, timing)
    elif with_audio:
        log("narration not built yet (clips missing); timing.js uses estimates")
    return timing
