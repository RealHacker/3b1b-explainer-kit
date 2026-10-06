"""Narration synthesis with a content-addressed clip cache.

Each beat's audio is cached at <cache>/<key>.wav where key = hash(spoken text + voice file + synthesis settings),
so editing one line only regenerates that line. Workers claim beats with lock files, so several `explainer tts`
processes (foreground or background) can share one queue without duplicating work.
"""
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import numpy as np

from . import audio

CACHE_VERSION = 1
KEY_FIELDS = ("exaggeration", "cfg_weight", "temperature", "seed", "max_chunk_words", "chunk_gap_s", "pause_s",
              "attempts", "accept_rate", "target_rate", "trim_threshold", "edge_pad_s")
SEED_STRIDE = 97
RETRY_BACKOFF_S = 5
GRADIO_PING_TIMEOUT_S = 8
DIRECT_WORKER = Path(__file__).with_name("tts_direct_worker.py")
MSG_PREFIX = "@@JSON "

_log_lock = threading.Lock()
_voice_hash_cache = {}


def log(msg):
    with _log_lock:
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def voice_hash(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"reference voice not found: {path}")
    k = (str(path), path.stat().st_mtime_ns)
    if k not in _voice_hash_cache:
        _voice_hash_cache[k] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _voice_hash_cache[k]


def cache_key(say, tcfg, vhash):
    payload = {"v": CACHE_VERSION, "say": say, "voice": vhash, **{k: tcfg[k] for k in KEY_FIELDS}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def beat_paths(project, beat):
    key = cache_key(beat.say, project.cfg["tts"], voice_hash(project.voice))
    base = project.cache / key
    return key, base.with_suffix(".wav"), base.with_suffix(".json")


def word_count(text):
    return max(1, len(re.findall(r"[\w'’-]+", text)))


def split_chunks(say, max_words):
    """Split spoken text into (chunk, is_phrase_end) pieces: '|' marks an explicit pause, long sentences split at commas."""
    out = []
    phrases = [p.strip() for p in say.split("|") if p.strip()]
    for pi, phrase in enumerate(phrases):
        chunks, cur = [], []
        for s in re.split(r"(?<=[.!?])\s+", phrase):
            words = s.split()
            if cur and len(cur) + len(words) > max_words:
                chunks.append(" ".join(cur))
                cur = []
            if len(words) > max_words:
                for part in re.split(r"(?<=[,:;])\s+", s):
                    pw = part.split()
                    if cur and len(cur) + len(pw) > max_words:
                        chunks.append(" ".join(cur))
                        cur = []
                    cur.extend(pw)
            else:
                cur.extend(words)
        if cur:
            chunks.append(" ".join(cur))
        for ci, c in enumerate(chunks):
            out.append((c, ci == len(chunks) - 1 and pi < len(phrases) - 1))
    return out


# ---------------------------------------------------------------- locks

def _pid_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_owner(lock):
    try:
        return int(lock.read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def claim(lock):
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            if _pid_alive(lock_owner(lock)):
                return False
            lock.unlink(missing_ok=True)
    return False


# ---------------------------------------------------------------- backends

class GradioBackend:
    name = "gradio"

    def __init__(self, tcfg, voice):
        from gradio_client import Client, handle_file
        self.cfg = tcfg
        self.client = Client(tcfg["gradio_url"], verbose=False)
        self.voice = handle_file(str(voice))

    def generate(self, text, seed, sr):
        job = self.client.submit(
            text=text, audio_prompt_path=self.voice, exaggeration=self.cfg["exaggeration"],
            temperature=self.cfg["temperature"], seed_num=seed, cfgw=self.cfg["cfg_weight"],
            api_name=self.cfg["gradio_api"])
        result = job.result(timeout=self.cfg["request_timeout_s"])
        path = result if isinstance(result, str) else result.get("path") if isinstance(result, dict) else None
        if not path or not Path(path).exists():
            raise RuntimeError(f"gradio returned no audio file: {result!r}")
        return audio.read_audio(path, sr)

    def close(self):
        pass


class DirectBackend:
    """Runs ChatterboxTTS in the Chatterbox venv as a persistent JSON-lines subprocess."""
    name = "direct"

    def __init__(self, tcfg, voice, scratch):
        d = tcfg["direct"]
        py = Path(d["python"])
        if not py.exists():
            raise FileNotFoundError(f"Chatterbox venv python not found: {py} (set tts.direct.python)")
        self.cfg = tcfg
        self.scratch = Path(scratch)
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [str(py), str(DIRECT_WORKER), str(voice), str(tcfg["exaggeration"]), str(d["threads"]), d["device"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, encoding="utf-8", bufsize=1,
            env={**os.environ, "TQDM_DISABLE": "1", "PYTHONWARNINGS": "ignore", "PYTHONIOENCODING": "utf-8"})
        self._read_message(expect="ready")
        self.n = 0

    def _read_message(self, expect=None):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"direct TTS worker exited (code {self.proc.poll()})")
            if not line.startswith(MSG_PREFIX):
                continue
            msg = json.loads(line[len(MSG_PREFIX):])
            if msg.get("error"):
                raise RuntimeError(f"direct TTS worker: {msg['error']}")
            if expect and msg.get("status") != expect:
                continue
            return msg

    def generate(self, text, seed, sr):
        self.n += 1
        out = self.scratch / f"direct_{os.getpid()}_{threading.get_ident()}_{self.n}.wav"
        job = {"text": text, "seed": seed, "temperature": self.cfg["temperature"],
               "cfg_weight": self.cfg["cfg_weight"], "exaggeration": self.cfg["exaggeration"], "out": str(out)}
        self.proc.stdin.write(json.dumps(job) + "\n")
        self.proc.stdin.flush()
        self._read_message(expect="done")
        try:
            return audio.read_audio(out, sr)
        finally:
            out.unlink(missing_ok=True)

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()


def gradio_reachable(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/config", timeout=GRADIO_PING_TIMEOUT_S) as r:
            return r.status == 200
    except OSError:
        return False


def choose_backend(tcfg, forced=None):
    name = forced or tcfg["backend"]
    if name == "gradio" and not gradio_reachable(tcfg["gradio_url"]):
        fb = tcfg.get("fallback")
        if fb == "direct":
            log(f"Gradio server {tcfg['gradio_url']} not reachable; falling back to direct ChatterboxTTS")
            return "direct"
        raise RuntimeError(f"Gradio server {tcfg['gradio_url']} not reachable and no fallback configured")
    if name not in ("gradio", "direct"):
        raise ValueError(f"unknown tts.backend '{name}'")
    return name


def make_backend(name, tcfg, voice, scratch):
    return GradioBackend(tcfg, voice) if name == "gradio" else DirectBackend(tcfg, voice, scratch)


# ---------------------------------------------------------------- synthesis

def with_retries(fn, tries, what):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # network hiccups, server restarts, worker crashes
            if i == tries - 1:
                raise
            log(f"  {what}: {type(e).__name__}: {e}; retry {i + 1}/{tries - 1} in {RETRY_BACKOFF_S * (i + 1)}s")
            time.sleep(RETRY_BACKOFF_S * (i + 1))


def synthesize(backend, beat, tcfg, sr):
    lo, hi = tcfg["accept_rate"]
    pieces, takes = [], []
    for chunk, phrase_end in split_chunks(beat.say, tcfg["max_chunk_words"]):
        n_words = word_count(chunk)
        best = None
        for attempt in range(tcfg["attempts"]):
            seed = tcfg["seed"] + attempt * SEED_STRIDE
            t0 = time.time()
            x = with_retries(lambda: backend.generate(chunk, seed, sr), tcfg["request_retries"], beat.id)
            x = audio.trim(x, sr, tcfg["trim_threshold"], tcfg["edge_pad_s"])
            dur = x.size / sr
            rate = dur / n_words
            log(f"  {beat.id} '{chunk[:44]}' seed {seed}: {dur:.2f}s, {rate:.2f}s/word, {time.time() - t0:.0f}s")
            score = abs(rate - tcfg["target_rate"])
            if best is None or score < best[0]:
                best = (score, x, rate, seed)
            if lo <= rate <= hi:
                break
        if not lo <= best[2] <= hi:
            log(f"  WARN {beat.id}: no take within {lo}-{hi}s/word, kept {best[2]:.2f}")
        pieces.append(best[1])
        pieces.append(np.zeros(int((tcfg["pause_s"] if phrase_end else tcfg["chunk_gap_s"]) * sr), np.float32))
        takes.append({"chunk": chunk, "seed": best[3], "rate": round(best[2], 3)})
    return np.concatenate(pieces[:-1]), takes


def status(project):
    done, pending, running = [], [], []
    for b in project.beats():
        key, wav, _ = beat_paths(project, b)
        if wav.exists():
            done.append(b.id)
        elif _pid_alive(lock_owner(project.cache / f"{key}.lock")):
            running.append(b.id)
        else:
            pending.append(b.id)
    return done, pending, running


def adopt(project, src_dir):
    """Import existing per-beat WAVs (named <beat id>.wav) into the cache under the current keys."""
    src_dir = Path(src_dir)
    sr = project.cfg["audio"]["sample_rate"]
    project.cache.mkdir(parents=True, exist_ok=True)
    n = 0
    for b in project.beats():
        key, wav, meta = beat_paths(project, b)
        src = src_dir / f"{b.id}.wav"
        if wav.exists() or not src.exists():
            continue
        x = audio.read_audio(src, sr)
        audio.write_wav(wav, x, sr)
        meta.write_text(json.dumps({"id": b.id, "say": b.say, "dur": x.size / sr, "backend": "adopted",
                                    "source": str(src)}, indent=1), encoding="utf-8")
        n += 1
    log(f"adopted {n} clips from {src_dir}")
    return n


def run_queue(project, backend_name=None, workers=None, only=None):
    tcfg = project.cfg["tts"]
    sr = project.cfg["audio"]["sample_rate"]
    project.cache.mkdir(parents=True, exist_ok=True)
    voice = project.voice
    voice_hash(voice)
    todo = [b for b in project.beats() if (only is None or b.id in only) and not beat_paths(project, b)[1].exists()]
    if not todo:
        log("all narration clips cached")
        return 0
    name = choose_backend(tcfg, backend_name)
    n_workers = max(1, workers or tcfg["workers"])
    log(f"{len(todo)} clips to synthesize with backend={name}, workers={n_workers}")
    q = queue.Queue()
    for b in todo:
        q.put(b)
    failures = []

    def worker(k):
        backend = None
        try:
            while True:
                try:
                    beat = q.get_nowait()
                except queue.Empty:
                    return
                key, wav, meta = beat_paths(project, beat)
                lock = project.cache / f"{key}.lock"
                if wav.exists() or not claim(lock):
                    continue
                try:
                    if backend is None:
                        backend = make_backend(name, tcfg, voice, project.cache / "tmp")
                    t0 = time.time()
                    log(f"[w{k}] {beat.id}: {beat.say[:70]}")
                    x, takes = synthesize(backend, beat, tcfg, sr)
                    audio.write_wav(wav, x, sr)
                    meta.write_text(json.dumps({"id": beat.id, "say": beat.say, "dur": x.size / sr, "backend": name,
                                                "takes": takes, "elapsed_s": round(time.time() - t0, 1)},
                                               indent=1), encoding="utf-8")
                    log(f"[w{k}] DONE {beat.id} {x.size / sr:.2f}s in {time.time() - t0:.0f}s")
                except Exception:
                    failures.append(beat.id)
                    log(f"[w{k}] FAIL {beat.id}\n{traceback.format_exc()}")
                finally:
                    lock.unlink(missing_ok=True)
        finally:
            if backend is not None:
                backend.close()

    threads = [threading.Thread(target=worker, args=(k,), daemon=True) for k in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done, pending, running = status(project)
    log(f"queue finished: {len(done)} cached, {len(pending)} pending, {len(running)} in progress elsewhere, "
        f"{len(failures)} failed {failures if failures else ''}")
    return 1 if failures else 0


def wait_for_others(project, poll_s=10):
    """Block until no other process holds a lock on this project's beats."""
    while True:
        _, _, running = status(project)
        if not running:
            return
        log(f"waiting for {len(running)} clips being generated by another process: {running}")
        time.sleep(poll_s)
