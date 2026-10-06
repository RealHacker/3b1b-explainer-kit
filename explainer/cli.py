"""explainer: build 3Blue1Brown-style narrated SVG explainer videos from a script.json project.

Commands: init, tts, status, timing, stills, scan, render, mux, verify, build, install-skill.
Run `explainer <command> -h` for options.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explainer.config import KIT_ROOT, ConfigError, Project  # noqa: E402

SKILL_NAME = "3b1b-explainer"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def cmd_init(a):
    from explainer import project_init
    project_init.init(Path(a.project), title=a.title, voice=a.voice, materials=a.materials, force=a.force)
    return 0


def cmd_tts(a):
    from explainer import tts
    p = Project(a.project)
    if a.adopt:
        tts.adopt(p, p.path(a.adopt))
    if a.background:
        return spawn_background(p, a)
    only = set(a.only.split(",")) if a.only else None
    code = tts.run_queue(p, backend_name=a.backend, workers=a.workers, only=only)
    tts.wait_for_others(p)
    return code


def spawn_background(p, a):
    p.cache.mkdir(parents=True, exist_ok=True)
    log_path = p.cache.parent / "tts.log"
    args = [sys.executable, str(Path(__file__).resolve()), "tts", str(p.root)]
    if a.backend:
        args += ["--backend", a.backend]
    if a.workers:
        args += ["--workers", str(a.workers)]
    if a.only:
        args += ["--only", a.only]
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"\n==== background tts started {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
        fh.flush()
        proc = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=flags, start_new_session=os.name != "nt",
                                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    (p.cache.parent / "tts.pid").write_text(str(proc.pid))
    print(f"background TTS started (pid {proc.pid}); log: {log_path}\ncheck progress: explainer status {p.root}")
    return 0


def cmd_status(a):
    from explainer import tts
    p = Project(a.project)
    done, pending, running = tts.status(p)
    total = len(done) + len(pending) + len(running)
    print(f"{p.script['title']}: {len(done)}/{total} clips cached, {len(running)} generating, {len(pending)} pending")
    if running:
        print("  generating:", ", ".join(running))
    if pending:
        print("  pending:", ", ".join(pending))
    log_path = p.cache.parent / "tts.log"
    if log_path.exists():
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-a.lines:]
        print(f"--- last {len(tail)} lines of {log_path}")
        print("\n".join(tail))
    return 0


def cmd_timing(a):
    from explainer import timing
    timing.run(Project(a.project), with_audio=not a.no_audio)
    return 0


def cmd_stills(a):
    from explainer import render
    p = Project(a.project)
    return render.stills(p, a.times, beats=a.beats, prefix=a.prefix)


def cmd_scan(a):
    from explainer import render
    return render.scan(Project(a.project))


def cmd_render(a):
    from explainer import render
    p = Project(a.project)
    if not a.skip_scan and render.scan(p) != 0 and not a.force:
        print("scan found errors; fix them or pass --force")
        return 1
    return render.render(p, workers=a.workers, start=a.start, end=a.end)


def cmd_mux(a):
    from explainer import mux
    return mux.mux(Project(a.project))


def cmd_verify(a):
    from explainer import verify
    p = Project(a.project)
    return verify.verify(p, video=Path(a.video).resolve() if a.video else None, skip_scan=a.skip_scan)


def cmd_build(a):
    from explainer import mux, render, timing, tts, verify
    p = Project(a.project)
    steps = []
    t0 = time.time()
    if not a.skip_tts:
        code = tts.run_queue(p, backend_name=a.backend)
        tts.wait_for_others(p)
        steps.append(("tts", code))
        if code:
            print("TTS failed for some clips; see log above")
            return code
    tl = timing.run(p, with_audio=True)
    if tl["missing"]:
        print(f"clips missing: {tl['missing']}")
        return 1
    if tl["total"] > p.cfg["video"]["max_duration_s"] and not a.force:
        print("timeline exceeds video.max_duration_s; trim the script or pass --force")
        return 1
    code = render.scan(p)
    if code and not a.force:
        print("scan found errors; fix them or pass --force")
        return code
    for name, fn in (("render", lambda: render.render(p, workers=a.workers)), ("mux", lambda: mux.mux(p)),
                     ("verify", lambda: verify.verify(p, skip_scan=True))):
        code = fn()
        steps.append((name, code))
        if code:
            print(f"step '{name}' failed")
            return code
    print(f"build finished in {time.time() - t0:.0f}s -> {p.output_mp4}")
    return 0


def cmd_install_skill(a):
    src = KIT_ROOT / "skill" / SKILL_NAME
    dest = Path(a.dest).expanduser() if a.dest else Path.home() / ".cursor" / "skills" / SKILL_NAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    (dest / "kit-path.txt").write_text(str(KIT_ROOT).replace("\\", "/") + "\n", encoding="utf-8")
    print(f"installed skill to {dest}")
    print(f"  kit-path.txt -> {KIT_ROOT}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="explainer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a new project from the template")
    s.add_argument("project")
    s.add_argument("--title")
    s.add_argument("--voice", help="reference WAV to copy into the project as voice.wav")
    s.add_argument("--materials", nargs="*", default=[], help="source files to copy into materials/")
    s.add_argument("--force", action="store_true", help="write into a non-empty folder")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("tts", help="synthesize missing narration clips (cached by content hash)")
    s.add_argument("project")
    s.add_argument("--background", action="store_true", help="run detached; poll with `explainer status`")
    s.add_argument("--backend", choices=["gradio", "direct"], help="override tts.backend")
    s.add_argument("--workers", type=int, help="parallel workers (Gradio queues serially; direct loads one model each)")
    s.add_argument("--only", help="comma-separated beat ids")
    s.add_argument("--adopt", help="import existing <beat id>.wav files from this folder into the cache first")
    s.set_defaults(fn=cmd_tts)

    s = sub.add_parser("status", help="show TTS queue progress")
    s.add_argument("project")
    s.add_argument("--lines", type=int, default=8)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("timing", help="build timeline (+ narration.wav and subtitles.srt when all clips exist)")
    s.add_argument("project")
    s.add_argument("--no-audio", action="store_true")
    s.set_defaults(fn=cmd_timing)

    s = sub.add_parser("stills", help="render PNG stills: global seconds, scene@local, or scene#beat:frac")
    s.add_argument("project")
    s.add_argument("times", nargs="*")
    s.add_argument("--beats", action="store_true", help="one still at 85%% of every beat, plus a tiled sheet")
    s.add_argument("--prefix", default="still")
    s.set_defaults(fn=cmd_stills)

    s = sub.add_parser("scan", help="evaluate every frame: exceptions, NaN, off-canvas and overlapping text")
    s.add_argument("project")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("render", help="render frames to build/video.mp4")
    s.add_argument("project")
    s.add_argument("--workers", type=int)
    s.add_argument("--start", type=float)
    s.add_argument("--end", type=float)
    s.add_argument("--skip-scan", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("mux", help="combine video, loudness-normalized narration and subtitles")
    s.add_argument("project")
    s.set_defaults(fn=cmd_mux)

    s = sub.add_parser("verify", help="duration, A/V sync, frame scan, narration screen, contact sheet")
    s.add_argument("project")
    s.add_argument("--video", help="verify this MP4 instead of the project output")
    s.add_argument("--skip-scan", action="store_true")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("build", help="tts -> timing -> scan -> render -> mux -> verify")
    s.add_argument("project")
    s.add_argument("--backend", choices=["gradio", "direct"])
    s.add_argument("--workers", type=int, help="render workers")
    s.add_argument("--skip-tts", action="store_true")
    s.add_argument("--force", action="store_true", help="continue past scan errors / length limit")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("install-skill", help=f"copy the {SKILL_NAME} agent skill to ~/.cursor/skills")
    s.add_argument("--dest")
    s.set_defaults(fn=cmd_install_skill)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
