"""Combine rendered video, loudness-normalized narration and soft subtitles into the final MP4."""
import json
import shutil
import subprocess

from .tts import log


def mux(project):
    b = project.build
    video, narration, srt = b / "video.mp4", b / "narration.wav", b / "subtitles.srt"
    for p in (video, narration):
        if not p.exists():
            raise FileNotFoundError(f"{p} missing; run `explainer render` / `explainer timing` first")
    total = json.loads((b / "timing.json").read_text(encoding="utf-8"))["total"]
    a = project.cfg["audio"]
    use_subs = project.cfg["subtitles"]["enabled"] and srt.exists()
    out = project.output_mp4
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(narration)]
    if use_subs:
        cmd += ["-i", str(srt)]
    cmd += ["-map", "0:v", "-map", "1:a"] + (["-map", "2:s"] if use_subs else [])
    cmd += ["-c:v", "copy",
            "-af", f"loudnorm=I={a['loudness_i']}:TP={a['loudness_tp']}:LRA={a['loudness_lra']}",
            "-ar", str(a["out_sample_rate"]), "-c:a", "aac", "-b:a", a["aac_bitrate"]]
    if use_subs:
        cmd += ["-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    cmd += ["-metadata:s:a:0", "language=eng", "-metadata", f"title={project.script['title']}",
            "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        log("ffmpeg mux failed")
        return res.returncode
    if use_subs:
        shutil.copy2(srt, out.with_suffix(".srt"))
    log(f"wrote {out}")
    return 0
