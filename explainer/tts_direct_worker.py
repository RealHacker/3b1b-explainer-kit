"""ChatterboxTTS worker run inside the Chatterbox venv (it needs torch + chatterbox, not the kit).

Protocol: one JSON job per stdin line -> one '@@JSON {...}' line on stdout. Other stdout noise is ignored by the parent.
Usage: python tts_direct_worker.py <voice.wav> <exaggeration> <threads> <device>
"""
import json
import random
import sys
import time
import traceback

PREFIX = "@@JSON "


def send(msg):
    sys.stdout.write(PREFIX + json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    voice, exaggeration, threads, device = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    try:
        import numpy as np
        import torch
        import torchaudio as ta
        from chatterbox.tts import ChatterboxTTS
        torch.set_num_threads(threads)
        t0 = time.time()
        model = ChatterboxTTS.from_pretrained(device=device)
        model.prepare_conditionals(voice, exaggeration=exaggeration)
        print(f"model ready in {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    except Exception:
        send({"error": "model load failed:\n" + traceback.format_exc()})
        return 1
    send({"status": "ready", "sr": model.sr})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            seed = int(job["seed"])
            torch.manual_seed(seed)
            random.seed(seed)
            np.random.seed(seed)
            wav = model.generate(job["text"], exaggeration=job["exaggeration"],
                                 cfg_weight=job["cfg_weight"], temperature=job["temperature"])
            ta.save(job["out"], wav.cpu(), model.sr)
            send({"status": "done", "out": job["out"]})
        except Exception:
            send({"error": traceback.format_exc()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
