"""Audio I/O via ffmpeg (any input format) plus a small numpy WAV writer and analysis helpers."""
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

WAV_FLOAT = 3
WAV_PCM = 1


class ToolMissing(RuntimeError):
    pass


def require(tool):
    if shutil.which(tool) is None:
        raise ToolMissing(f"'{tool}' not found on PATH")


def read_audio(path, sr):
    """Decode any audio file to mono float32 at `sr` (values above 1.0 are preserved)."""
    require("ffmpeg")
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(sr), "-"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {path}: {res.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def write_wav(path, x, sr, pcm16=False):
    """Write mono WAV atomically. float32 keeps headroom; pcm16 clips to [-1, 1]."""
    path = Path(path)
    x = np.asarray(x, dtype=np.float32)
    if pcm16:
        data = (np.clip(x, -1.0, 1.0) * 32767.0).round().astype("<i2").tobytes()
        fmt, bits = WAV_PCM, 16
    else:
        data = x.astype("<f4").tobytes()
        fmt, bits = WAV_FLOAT, 32
    block = bits // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, fmt, 1, sr, sr * block, block, bits)
    header += b"data" + struct.pack("<I", len(data))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(header + data)
    tmp.replace(path)


def trim(x, sr, threshold, pad_s):
    idx = np.flatnonzero(np.abs(x) > threshold)
    if idx.size == 0:
        return x
    pad = int(pad_s * sr)
    return x[max(0, idx[0] - pad): min(x.size, idx[-1] + pad)]


def frame_rms(x, sr, frame_s):
    hop = max(1, int(frame_s * sr))
    n = x.size // hop
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))


def longest_run(mask):
    """Length of the longest run of True values."""
    if not mask.any():
        return 0
    padded = np.concatenate(([0], mask.astype(np.int8), [0]))
    d = np.diff(padded)
    return int((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max())


FLAT_EPS = 1e-6


def clipped_runs(x, level=0.999, min_run=3):
    """Number of flat-topped runs (>= min_run identical samples at the signal's full-scale peak).

    Float TTS output may exceed 1.0 without clipping (the narration builder normalizes it), so only
    plateaus at the peak count; in fixed-point sources those are true digital clipping.
    """
    a = np.abs(x)
    peak = float(a.max()) if a.size else 0.0
    if peak < level:
        return 0
    flat = np.concatenate(([False], np.abs(np.diff(x)) < FLAT_EPS))
    mask = (a >= level * peak) & (flat | np.roll(flat, -1))
    if not mask.any():
        return 0
    padded = np.concatenate(([0], mask.astype(np.int8), [0]))
    d = np.diff(padded)
    lengths = np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
    return int((lengths >= min_run).sum())
