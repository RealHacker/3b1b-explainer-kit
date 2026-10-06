# 3b1b-explainer-kit

Turn text materials into a narrated, 3Blue1Brown-style explainer video:
programmatic SVG animation (deterministic, rendered frame-by-frame in headless Chromium), Chatterbox TTS voice-over
in a cloned reference voice, soft subtitles, and automated checks. A companion Cursor agent skill
(`skill/3b1b-explainer/`) guides the judgment-heavy parts (storyboard, narration, scene design) and calls this CLI
for everything mechanical.

```
materials ──(you / agent)──> script.json + scenes/*.js
script.json ──tts──> audio/cache/*.wav ──timing──> build/timing.js, narration.wav, subtitles.srt
scenes + timing ──scan/stills/render──> build/video.mp4 ──mux──> output/<title>.mp4 ──verify──> report + contact sheet
```

## Assumptions and prerequisites

Tested on **Windows 11** (PowerShell, 20-core CPU, no GPU). Other OSes should work via `python explainer/cli.py`
but are untested.

| Requirement | Used for | Check |
|---|---|---|
| Python ≥ 3.10 with `numpy`, `gradio_client` | the CLI (orchestrator) | `python -c "import numpy, gradio_client"` |
| Node.js ≥ 18 + `npm install` in this folder (Playwright, KaTeX) | rendering, stills, scan | `node --version` |
| Playwright Chromium | headless rendering | `npx playwright install chromium` |
| ffmpeg + ffprobe on PATH | audio decode, encode, mux, checks | `ffmpeg -version` |
| **Chatterbox Gradio server already running** at `http://127.0.0.1:7860/` | default TTS backend | open the URL; `explainer tts` pings `/config` |
| Chatterbox install + venv (default `E:/Voice/chatterbox/.venv`) | direct TTS fallback | `tts.direct.python` in config |
| Reference voice WAV (5–20 s clean speech of one speaker) | voice cloning | `tts.voice` in config |
| Fonts: Segoe UI, Consolas, Cambria Math (Windows defaults) | typography | — |

The Gradio app must expose Chatterbox's `/generate` endpoint (`text, audio_prompt_path, exaggeration, temperature,
seed_num, cfgw` — the stock `gradio_tts_app.py`). The kit does not start the server.

## Install

```powershell
cd E:\Explainit\explainer-kit
python -m pip install -r requirements.txt
npm install
npx playwright install chromium        # skip if already installed
# optional: put the kit on PATH so `explainer` works anywhere
$env:PATH = "E:\Explainit\explainer-kit;$env:PATH"
# or call the launcher by full path / `python explainer/cli.py` / `python -m explainer`
# install the agent skill to ~/.cursor/skills/3b1b-explainer (writes kit-path.txt)
explainer install-skill
```
`explainer.cmd` uses `python` from PATH, or `%EXPLAINER_PYTHON%` if set.

## Quickstart

```powershell
explainer init my-video --title "How X Works" --voice E:\voices\me.wav --materials notes.md
# edit my-video\script.json and my-video\scenes\*.js (see examples\binary-search)
explainer tts my-video --background     # narration in the background (cached per beat)
explainer timing my-video --no-audio    # estimated timeline so scenes can be previewed now
explainer stills my-video --beats       # PNG per beat + sheet in build\stills
explainer scan my-video                 # frame errors + layout warnings
explainer status my-video               # TTS progress
explainer build my-video                # timing -> scan -> render -> mux -> verify (waits for TTS)
```
Result: `my-video\output\How_X_Works.mp4` (+ `.srt`), `build\verify_report.json`, `build\contact_sheet.png`.

The included example (`examples\binary-search`, 2 scenes, 33 s) was built with exactly `explainer build examples\binary-search`.

## Using it with the agent skill

Install the skill (`explainer install-skill` writes `kit-path.txt` so the agent can find this kit from any
workspace; or copy `skill/3b1b-explainer` to `%USERPROFILE%/.cursor/skills/3b1b-explainer`),
then ask the agent something like:

> Use the 3b1b-explainer skill: make a ~5 minute explainer of sections 2–3 of paper.pdf, voice E:\voices\me.wav.

The skill makes the agent read the materials, propose a storyboard and wait for your approval, write the script with
phonetic pronunciations, start TTS in the background, build scenes with the library while the audio generates,
inspect stills, run `build`, and report the verification results. The skill is auto-invoked for explainer-video
requests; mention it by name to force it.

Without the skill you do the same steps by hand with the CLI (Quickstart above); `skill/3b1b-explainer/SKILL.md`
doubles as a checklist of style and accuracy rules.

## Project layout

```
my-video/
  explainer.config.json   every setting, defaults filled in by init
  script.json             title, legend, pronunciations, scenes -> beats
  scenes/*.js             one file per scene; "_*.js" helpers load first (or list order in paths.scripts)
  materials/              your source texts (for you / the agent; not parsed)
  voice.wav               reference voice
  audio/cache/            <hash>.wav + <hash>.json per beat; tts.log, tts.pid for background runs
  build/                  timing.json/.js, narration.wav, subtitles.srt, index.html, render.json,
                          video.mp4, segments/, stills/, scan_report.json, verify_report.json, contact_sheet.png
  output/                 <title>.mp4 + .srt
```

## script.json

```json
{
  "title": "Why Binary Search Takes log n Steps",
  "legend": { "blue": "cells still in play", "gold": "middle element", "coral": "discarded" },
  "pronunciations": { "API": "A P I" },
  "scenes": [
    {
      "id": "s1_halving",
      "header": "One comparison, half the array",
      "visual": "storyboard note (ignored by the tool)",
      "tail_s": 1.1,
      "beats": [
        { "id": "s1_b1", "text": "Subtitle / on-screen wording.",
          "say": "Optional spoken override. | A pipe inserts a pause.", "gap_after_s": 0.5 }
      ]
    }
  ]
}
```
- `text` → subtitles; `say` (default: `text` with `pronunciations` applied) → TTS.
- Beat ids must be unique; scenes reference them as `c("s1_b1")` or by 1-based index `c(1)`.
- `clips` is accepted as an alias of `beats`.

Scene files register with `E.scene(id, { header, draw(ctx) })` and return SVG markup for scene-local time `ctx.t`.
Full API (tweening/easing, stroke-draw, morphs, tokens, labels, braces, axes/plots, KaTeX, palette) is in
[`skill/3b1b-explainer/reference.md`](skill/3b1b-explainer/reference.md); a commented template is
`templates/project/scenes/s1_intro.js`.

## Configuration (`explainer.config.json`)

All keys are optional in the file; missing ones use these defaults. Relative paths resolve against the project folder.

| key | default | meaning |
|---|---|---|
| `paths.script` / `scenes_dir` / `scripts` | `script.json` / `scenes` / `null` | inputs; `scripts` = explicit ordered list of JS files |
| `paths.build` / `cache` / `output` | `build` / `audio/cache` / `output` | outputs |
| `video.width` × `height` @ `fps` | 1920 × 1080 @ 30 | output resolution (scenes always author in 1920×1080) |
| `video.crf` / `preset` | 17 / `medium` | x264 quality |
| `video.max_duration_s` | 480 | `build` refuses longer timelines (unless `--force`); `verify` fails |
| `video.output_name` | from title | output file stem |
| `timing.scene_lead_s` / `beat_gap_s` / `scene_tail_s` | 0.8 / 0.5 / 1.1 | timeline padding; `scene_tail_overrides` per scene |
| `timing.est_sec_per_word` | 0.37 | estimate for clips not yet generated |
| `tts.backend` / `fallback` | `gradio` / `direct` | fallback used when the server does not answer `/config` |
| `tts.gradio_url` / `gradio_api` | `http://127.0.0.1:7860/` / `/generate` | server |
| `tts.voice` | `voice.wav` | reference WAV |
| `tts.exaggeration` / `cfg_weight` / `temperature` / `seed` | 0.5 / 0.5 / 0.8 / 1234 | Chatterbox settings |
| `tts.max_chunk_words` / `chunk_gap_s` / `pause_s` | 28 / 0.22 / 0.55 | chunking; `pause_s` for `|` |
| `tts.attempts` / `accept_rate` / `target_rate` | 3 / [0.24, 0.62] / 0.4 | re-roll takes with seed+97·k outside the rate window |
| `tts.request_retries` / `request_timeout_s` | 3 / 900 | transport retries with backoff |
| `tts.workers` | 1 | parallel workers (Gradio queues serially server-side) |
| `tts.direct.python` / `threads` / `device` | `E:/Voice/chatterbox/.venv/Scripts/python.exe` / 8 / `cpu` | fallback |
| `audio.narration_peak` | 0.89 | narration track peak normalization |
| `audio.loudness_i` / `loudness_tp` / `loudness_lra` | −16 / −1.5 / 11 | ffmpeg loudnorm at mux |
| `audio.aac_bitrate` / `out_sample_rate` | 192k / 48000 | final audio |
| `subtitles.enabled` / `max_chars` / `wrap_chars` | true / 84 / 44 | SRT cue size, 2-line wrap |
| `render.workers` | 0 (auto: cores − 4, max 8) | parallel Chromium pages |
| `render.scan_step_s` / `layout_step_s` | 1/fps / 0.5 | scan sampling |
| `checks.rate_range` / `max_internal_silence_s` | [0.28, 0.55] / 1.0 | narration screen |
| `checks.sync_tolerance_ms` / `av_tolerance_frames` | 40 / 2 | sync checks |
| `checks.contact_columns` / `contact_width` | 6 / 480 | contact sheet |

**Cache key** = SHA-256 of spoken text + reference-voice bytes + synthesis settings (exaggeration, cfg_weight,
temperature, seed, chunking, attempts/rate window, trim). Backend, URL and worker count are *not* part of the key, so
Gradio and direct clips are interchangeable. Editing one beat regenerates only that beat.

## What `verify` checks

| check | fails / warns when |
|---|---|
| duration | FAIL above `video.max_duration_s` |
| video format, subtitles | WARN if resolution/fps differ from config or the subtitle track is missing |
| A/V alignment | FAIL if video, audio and timeline lengths or stream start times differ by > 2 frames |
| audio lag | FAIL if envelope cross-correlation of MP4 audio vs `narration.wav` shows > 40 ms lag, globally or in any scene |
| beat onsets | INFO: speech onset per beat (the leading breath of each take, normally +0.05–0.5 s); WARN if speech starts early |
| narration screen | WARN on s/word outside `rate_range`, internal silence > 1 s, or flat-topped (clipped) peaks |
| frame scan | FAIL on exceptions or NaN/undefined/Infinity in any frame's markup (every frame) |
| layout | WARN on visible text (incl. KaTeX) off-canvas or overlapping other text (sampled every 0.5 s) |
| frame match | FAIL if 4 frames decoded from the MP4 differ from a fresh browser render of the same timestamp (PSNR < 30 dB) |
| loudness | WARN if integrated loudness is > 1.5 LU off target |
| contact sheet | always: `build/contact_sheet.png`, one final-MP4 frame per beat — look at it |

## Re-using an existing project (the DSec video)

`E:\Explainit` (the DSec explainer) runs through the kit via `E:\Explainit\explainer.config.json`, which points the
kit at the existing `script.json`, lists the scene files in load order (`paths.scripts`), keeps the original per-scene
tails, and writes everything to `kit-build\` so the original `build\` and deliverables are untouched:
```powershell
explainer tts E:\Explainit --adopt audio/clips   # import the 38 existing clips into the cache (no regeneration)
explainer verify E:\Explainit --video E:\Explainit\DSec_explainer.mp4
explainer build E:\Explainit --skip-tts          # full re-render -> kit-build\output\DSec_explainer_kit.mp4
```
`--adopt <dir>` imports `<beat id>.wav` files under the current cache keys; it assumes they match the current text.

## Troubleshooting

- **`Gradio server ... not reachable; falling back to direct`** — start the Gradio app, or accept the fallback
  (faster anyway on CPU). Set `tts.fallback` to `null` to make this an error.
- **Gradio is slow (~60–110 s per chunk).** The stock app reloads the model on every API call (its `gr.State` is
  never populated for API clients). Use `--backend direct --workers 2` for long scripts; clips are interchangeable.
- **Gradio output is peak-normalized 16-bit** (the Audio component rescales); loudness is equalized at mux, so levels match.
- **A clip sounds rushed or garbled** — check `audio/tts.log` for its s/word; rephrase, split with `|`, or delete
  `audio/cache/<key>.*` (key in `<key>.json` → `id`) and re-run `tts`. Changing `tts.seed` regenerates *everything*.
- **`status` shows a clip generating forever** — if the worker died, its lock holds a dead PID and is reclaimed on the next run.
- **`missing scene <id>`** in stills — the scene file is not loaded (check `paths.scenes_dir`/`scripts`) or its
  `E.scene` id differs from `script.json`.
- **KaTeX shows as italic plain text** — run `npm install` in the kit (`node_modules/katex` missing).
- **Chromium fails to launch** — `npx playwright install chromium` in the kit folder.
- **Timeline over the limit** — trim narration words (0.37 s/word) rather than gaps; `build --force` overrides.
- **Layout warnings** — render a still at the reported time (`explainer stills <p> 432.5`) and judge; transient overlaps
  during motion are often fine.
- **Render speed** — ~9–16 fps at 1080p with 8 workers on 20 cores; lower `video.width/height` for drafts
  (e.g. 1280×720) — scenes are resolution-independent.
- **Console shows `?`/mojibake for arrows or ellipses** — cosmetic (Windows code page); files are UTF-8.

## Limitations

- TTS quality depends on Chatterbox: occasional mispronunciations, rushed takes, or breaths; the rate screen catches
  timing outliers but not wrong words — listen to the final video.
- The layout check sees text only (not boxes/arrows) and uses bounding boxes, so it can flag harmless crossings.
- Subtitle cue timing within a beat is proportional to characters, not word-aligned.
- Scenes are hand-written JavaScript; the kit provides primitives and checks, not automatic diagram layout.
- Windows is the only tested OS; `explainer.cmd` is Windows-only (use `python explainer/cli.py` elsewhere).
