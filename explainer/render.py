"""Page generation and the Playwright-driven steps: scan, stills, render."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import KIT_ROOT
from .tts import log

LIB = KIT_ROOT / "lib"
NODE_TOOLS = KIT_ROOT / "render"
KATEX_DIST = KIT_ROOT / "node_modules" / "katex" / "dist"
MAX_AUTO_WORKERS = 8
RESERVED_CORES = 4
STILL_BEAT_FRACTION = 0.85
SHEET_TILE_W = 480


def _url(p):
    return Path(p).resolve().as_uri()


def scene_scripts(project):
    listed = project.cfg["paths"].get("scripts")
    if listed:
        files = [project.path(s) for s in listed]
    else:
        d = project.path(project.cfg["paths"]["scenes_dir"])
        if not d.exists():
            raise FileNotFoundError(f"scenes folder not found: {d}")
        files = sorted(d.glob("*.js"), key=lambda p: (not p.name.startswith("_"), p.name))
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"scene scripts not found: {missing}")
    return files


def write_page(project):
    """Write build/index.html (loads kit lib + project scenes + timing) and build/render.json."""
    from . import timing as timing_mod
    b = project.build
    b.mkdir(parents=True, exist_ok=True)
    timing_mod.write_timing(project, timing_mod.build_timeline(project))
    v = project.cfg["video"]
    roles = project.script.get("roles", {})
    tags = []
    if KATEX_DIST.exists():
        tags.append(f'<link rel="stylesheet" href="{_url(KATEX_DIST / "katex.min.css")}">')
        tags.append(f'<script src="{_url(KATEX_DIST / "katex.min.js")}"></script>')
    else:
        log("WARN KaTeX not installed (npm install in explainer-kit); E.tex falls back to plain text")
    tags.append(f"<script>window.VIDEO = {json.dumps({'width': v['width'], 'height': v['height'], 'fps': v['fps']})};"
                f" window.PALETTE_ROLES = {json.dumps(roles)};</script>")
    tags.append(f'<script src="{_url(LIB / "engine.js")}"></script>')
    tags += [f'<script src="{_url(s)}"></script>' for s in scene_scripts(project)]
    tags.append(f'<script src="{_url(b / "timing.js")}"></script>')
    tags.append(f'<script src="{_url(LIB / "player.js")}"></script>')
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{project.script['title']}</title>
<style>html,body{{margin:0;padding:0;background:#101216;overflow:hidden}}#stage{{width:{v['width']}px;height:{v['height']}px}}#stage svg{{display:block}}</style>
</head><body><div id="stage"></div>
{chr(10).join(tags)}
<script>const q = new URLSearchParams(location.search); window.explainerReady.then(() => window.renderFrame(parseFloat(q.get("t") || "0")));</script>
</body></html>
"""
    (b / "index.html").write_text(html, encoding="utf-8")
    return b / "index.html"


def job_file(project, start=None, end=None, workers=None, out=None):
    write_page(project)
    total = json.loads((project.build / "timing.json").read_text(encoding="utf-8"))["total"]
    v, r = project.cfg["video"], project.cfg["render"]
    auto = max(1, min(MAX_AUTO_WORKERS, (os.cpu_count() or 2) - RESERVED_CORES))
    job = {
        "html": str(project.build / "index.html"), "build": str(project.build),
        "width": v["width"], "height": v["height"], "fps": v["fps"], "crf": v["crf"], "preset": v["preset"],
        "workers": workers or r["workers"] or auto,
        "start": max(0.0, start or 0.0), "end": min(total, end if end is not None else total),
        "scanStep": r["scan_step_s"] or 1.0 / v["fps"], "layoutStep": r["layout_step_s"],
        "out": str(out or project.build / "video.mp4"),
    }
    path = project.build / "render.json"
    path.write_text(json.dumps(job, indent=1), encoding="utf-8")
    return path


def node(script, *args):
    if shutil.which("node") is None:
        raise RuntimeError("node not found on PATH")
    if not (KIT_ROOT / "node_modules" / "playwright").exists():
        raise RuntimeError("playwright not installed: run `npm install` in explainer-kit")
    return subprocess.run(["node", str(NODE_TOOLS / script), *map(str, args)], cwd=str(KIT_ROOT))


def scan(project):
    job = job_file(project)
    return node("scan.mjs", job, project.build / "scan_report.json").returncode


def render(project, workers=None, start=None, end=None):
    job = job_file(project, start=start, end=end, workers=workers)
    return node("render.mjs", job).returncode


def stills(project, specs, beats=False, prefix="still"):
    job = job_file(project)
    specs = list(specs)
    if beats:
        timing = json.loads((project.build / "timing.json").read_text(encoding="utf-8"))
        specs += [f"{s['id']}#{c['id']}:{STILL_BEAT_FRACTION}" for s in timing["scenes"] for c in s["clips"]]
    if not specs:
        raise ValueError("give time specs or --beats")
    out_dir = project.build / "stills"
    res = subprocess.run(["node", str(NODE_TOOLS / "stills.mjs"), str(job), str(out_dir), prefix, *specs],
                         cwd=str(KIT_ROOT), capture_output=True, text=True)
    if res.stderr:
        print(res.stderr.strip())
    lines = res.stdout.strip().splitlines()
    results = json.loads(lines[-1]) if lines else []
    for r in results:
        print(f"  {r['spec']:<28} t={r['t']:8.3f}  {r['file']}")
    if beats and results:
        sheet = out_dir / f"{prefix}_sheet.png"
        tile_sheet([r["file"] for r in results], sheet, project.cfg["checks"]["contact_columns"])
        print(f"sheet: {sheet}")
    return res.returncode


def tile_sheet(files, out, columns, tile_w=SHEET_TILE_W):
    """Tile PNGs into one contact sheet with ffmpeg (xstack)."""
    n = len(files)
    if n == 0:
        return
    cols = min(columns, n)
    tile_h = tile_w * 9 // 16
    inputs = []
    for f in files:
        inputs += ["-i", str(f)]
    scaled = "".join(f"[{i}:v]scale={tile_w}:{tile_h}[v{i}];" for i in range(n))
    if n == 1:
        graph = f"[0:v]scale={tile_w}:{tile_h}[out]"
    else:
        layout = "|".join(f"{(i % cols) * tile_w}_{(i // cols) * tile_h}" for i in range(n))
        graph = scaled + "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}:fill=black[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-frames:v", "1", str(out)], check=True)
