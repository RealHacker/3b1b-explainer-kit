"""Project configuration and script loading.

Every project has an explicit `explainer.config.json`; values missing from it fall back to DEFAULTS.
Relative paths in the config are resolved against the project folder.
"""
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "explainer.config.json"

DEFAULTS = {
    "paths": {
        "script": "script.json",
        "scenes_dir": "scenes",
        "scripts": None,
        "materials": "materials",
        "build": "build",
        "cache": "audio/cache",
        "output": "output",
    },
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "crf": 17,
        "preset": "medium",
        "max_duration_s": 480,
        "output_name": None,
    },
    "timing": {
        "scene_lead_s": 0.8,
        "beat_gap_s": 0.5,
        "scene_tail_s": 1.1,
        "scene_tail_overrides": {},
        "est_sec_per_word": 0.37,
    },
    "tts": {
        "backend": "gradio",
        "fallback": "direct",
        "gradio_url": "http://127.0.0.1:7860/",
        "gradio_api": "/generate",
        "voice": "voice.wav",
        "exaggeration": 0.5,
        "cfg_weight": 0.5,
        "temperature": 0.8,
        "seed": 1234,
        "max_chunk_words": 28,
        "chunk_gap_s": 0.22,
        "pause_s": 0.55,
        "attempts": 3,
        "accept_rate": [0.24, 0.62],
        "target_rate": 0.4,
        "request_retries": 3,
        "request_timeout_s": 900,
        "workers": 1,
        "trim_threshold": 0.012,
        "edge_pad_s": 0.06,
        "direct": {
            "python": "E:/Voice/chatterbox/.venv/Scripts/python.exe",
            "threads": 8,
            "device": "cpu",
        },
    },
    "audio": {
        "sample_rate": 24000,
        "narration_peak": 0.89,
        "loudness_i": -16,
        "loudness_tp": -1.5,
        "loudness_lra": 11,
        "aac_bitrate": "192k",
        "out_sample_rate": 48000,
    },
    "subtitles": {"enabled": True, "max_chars": 84, "wrap_chars": 44},
    "render": {"workers": 0, "scan_step_s": None, "layout_step_s": 0.5},
    "checks": {
        "rate_range": [0.28, 0.55],
        "max_internal_silence_s": 1.0,
        "sync_tolerance_ms": 40,
        "av_tolerance_frames": 2,
        "contact_columns": 6,
        "contact_width": 480,
    },
}


class ConfigError(Exception):
    pass


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Beat:
    id: str
    scene: str
    text: str
    say: str
    gap_after_s: float | None


@dataclass
class Scene:
    id: str
    header: str | None
    tail_s: float | None
    beats: list


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        cfg_path = self.root / CONFIG_NAME
        if not cfg_path.exists():
            raise ConfigError(f"{cfg_path} not found; run `explainer init {self.root}` or create it")
        try:
            user = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigError(f"{cfg_path}: invalid JSON: {e}") from e
        self.cfg = deep_merge(DEFAULTS, user)
        self._script = None

    def path(self, value):
        p = Path(value)
        return p if p.is_absolute() else (self.root / p)

    @property
    def build(self):
        return self.path(self.cfg["paths"]["build"])

    @property
    def cache(self):
        return self.path(self.cfg["paths"]["cache"])

    @property
    def output_dir(self):
        return self.path(self.cfg["paths"]["output"])

    @property
    def voice(self):
        return self.path(self.cfg["tts"]["voice"])

    @property
    def script(self):
        if self._script is None:
            self._script = load_script(self.path(self.cfg["paths"]["script"]))
        return self._script

    @property
    def slug(self):
        name = self.cfg["video"].get("output_name")
        if name:
            return name
        return re.sub(r"[^A-Za-z0-9]+", "_", self.script["title"]).strip("_") or "explainer"

    @property
    def output_mp4(self):
        return self.output_dir / f"{self.slug}.mp4"

    def scenes(self):
        return self.script["scenes_parsed"]

    def beats(self):
        return [b for s in self.scenes() for b in s.beats]


def apply_pronunciations(text, prons):
    for word, spoken in prons.items():
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", spoken, text)
    return text


def load_script(path):
    if not path.exists():
        raise ConfigError(f"script not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON: {e}") from e
    if not data.get("scenes"):
        raise ConfigError(f"{path}: needs a non-empty 'scenes' list")
    data.setdefault("title", path.parent.name)
    prons = data.get("pronunciations", {})
    seen, scenes = set(), []
    for si, sc in enumerate(data["scenes"]):
        sid = sc.get("id") or f"s{si}"
        if sid in seen:
            raise ConfigError(f"duplicate scene/beat id '{sid}'")
        seen.add(sid)
        raw = sc.get("beats", sc.get("clips"))
        if not raw:
            raise ConfigError(f"scene '{sid}' has no beats")
        beats = []
        for bi, b in enumerate(raw, 1):
            bid = b.get("id") or f"{sid}_b{bi}"
            if bid in seen:
                raise ConfigError(f"duplicate scene/beat id '{bid}'")
            seen.add(bid)
            text = (b.get("text") or "").strip()
            if not text:
                raise ConfigError(f"beat '{bid}' has empty text")
            say = (b.get("say") or apply_pronunciations(text, prons)).strip()
            beats.append(Beat(bid, sid, text, say, b.get("gap_after_s")))
        scenes.append(Scene(sid, sc.get("header"), sc.get("tail_s"), beats))
    data["scenes_parsed"] = scenes
    return data
