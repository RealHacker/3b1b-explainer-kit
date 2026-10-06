"""`explainer init`: scaffold a project folder from templates/project."""
import copy
import json
import shutil
from pathlib import Path

from .config import CONFIG_NAME, DEFAULTS, KIT_ROOT

TEMPLATE = KIT_ROOT / "templates" / "project"


def init(root, title=None, voice=None, materials=(), force=False):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()) and not force:
        raise RuntimeError(f"{root} is not empty (use --force to write into it)")
    root.mkdir(parents=True, exist_ok=True)
    for src in TEMPLATE.rglob("*"):
        dest = root / src.relative_to(TEMPLATE)
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    cfg = copy.deepcopy(DEFAULTS)
    if voice:
        vsrc = Path(voice).resolve()
        if not vsrc.exists():
            raise FileNotFoundError(f"voice file not found: {vsrc}")
        shutil.copy2(vsrc, root / "voice.wav")
    cfg_path = root / CONFIG_NAME
    if not cfg_path.exists():
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    script_path = root / "script.json"
    if title:
        data = json.loads(script_path.read_text(encoding="utf-8"))
        data["title"] = title
        script_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    mat = root / "materials"
    mat.mkdir(exist_ok=True)
    for m in materials or ():
        shutil.copy2(Path(m), mat / Path(m).name)

    print(f"initialized project at {root}")
    if not (root / "voice.wav").exists():
        print("  note: put a reference voice at voice.wav (or set tts.voice in the config)")
    print("  next: edit script.json and scenes/*.js, then run `explainer tts <project> --background`")
