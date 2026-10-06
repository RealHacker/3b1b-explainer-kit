---
name: 3b1b-explainer
description: Plans, narrates, animates and renders 3Blue1Brown-style explainer videos (programmatic SVG animation + Chatterbox TTS voice-over + ffmpeg) from text materials such as papers, docs, articles or notes, using the explainer-kit CLI. Use when the user asks for an explainer video, animated or narrated walkthrough, "3b1b-style" video, or a video that explains a document, paper section, algorithm or system.
---

# 3b1b-style explainer videos

The mechanical work (TTS queue + cache, timeline, frame rendering, mux, checks) is done by the **explainer-kit** CLI.
Your job is the judgment: what to explain, the storyboard, the narration, and scene design.

## Locate the kit and CLI

Resolve `KIT` in this order; stop at the first that exists and contains `explainer/cli.py`:

1. `kit-path.txt` next to this `SKILL.md` (written by `explainer install-skill`)
2. Environment variable `EXPLAINER_KIT`
3. Search the workspace root and its parents for `explainer-kit/explainer/cli.py`
4. `E:/Explainit/explainer-kit` (this machine's default)

If none exist, **stop and ask** where explainer-kit is installed. Do not assume `explainer` is on PATH.

- Windows CLI: `<KIT>/explainer.cmd`
- Elsewhere: `python <KIT>/explainer/cli.py`

Call that full path for every command below (written as `explainer` for brevity). Read [reference.md](reference.md) before writing scenes. A gold-standard project is `<KIT>/examples/binary-search/`. A full agent walkthrough is in [examples.md](examples.md). Assumptions and install steps: `<KIT>/README.md`.

## Assumptions (check before TTS)

- Python ≥ 3.10 with `numpy` and `gradio_client`; Node ≥ 18 + `npm install` in `KIT`; Playwright Chromium; ffmpeg/ffprobe on PATH.
- **Chatterbox Gradio is already running** at `http://127.0.0.1:7860/` (the kit does not start it), **or** you pass `--backend direct` and the Chatterbox venv in `tts.direct.python` works.
- A reference voice WAV (5–20 s, one speaker) is available.

## Workflow

Copy this checklist and keep it updated:

```
- [ ] 1. Read the materials; confirm scope, length, audience, voice file
- [ ] 2. Plan + storyboard -> user review (stop and wait)
- [ ] 3. init project, write script.json
- [ ] 4. Start TTS in the background
- [ ] 5. Write scenes while TTS runs; stills + scan loop
- [ ] 6. timing with real durations; trim if over length
- [ ] 7. build (render, mux, verify); inspect contact sheet + findings
- [ ] 8. Report
```

### 1. Read the materials
Read the requested sections fully (for PDFs, extract text and look at figures/tables). Note every number you might show
and where it comes from (section, figure, table). Ask only what the materials cannot answer: target length (default under
8 min), audience (default technical — no introductory material), sections in/out of scope, reference voice WAV.

### 2. Plan + storyboard (user review)
Present, then **stop and wait for approval** before generating anything:

```markdown
## Plan: <title>
Target: <N> min, audience: <...>. Scenes: <k>. Narration budget: ~<W> words.
Color legend: blue = <...>, teal = <...>, gold = <...>, purple = <...>, coral = <...>, green = <...>
| # | Scene (header) | Point it makes | Visual (what builds on screen) | Source | ~words |
Accuracy notes: <numbers shown + source; visuals that are schematic>
Tech: explainer-kit, voice <file>, 1920x1080@30
Open questions: <...>
```

Word budget: `W ≈ (target_s − scenes × 1.9 − gaps × 0.5) / 0.37` (Chatterbox speaks ~0.33–0.37 s/word;
each scene adds 0.8 s lead + ~1.1 s tail; each gap between beats is 0.5 s). 8 min with 9 scenes ≈ 1150 words; aim 5–10% under.

### 3. Project + script
```
explainer init <project> --title "<title>" --voice <voice.wav> --materials <files...>
```
Write `script.json` (schema in reference.md): scenes → beats. One beat = one narrated idea = one visual step (15–45 words).
Put the storyboard's visual description in each scene's `visual` field and the color legend in `legend`.

Narration rules:
- Written for the ear: short declarative sentences, ≤ 28 words per sentence (longer ones get split at commas).
- Spell acronyms phonetically via `pronunciations` (global) or per-beat `say`: e.g. `"DSec": "D-Sec"`, `"3FS": "three F S"`,
  `"QEMU": "kemu"`, `"EROFS": "E-ROFS"`, `"API": "A P I"`, `"eBPF": "e B P F"`, `"ublk": "U B L K"`. `text` stays as written
  (it becomes the subtitles); `say` is what the voice reads.
- Numbers and symbols in `say` as words ("eight thousand one hundred ninety-two", "n over two to the k").
- `|` inside `say` inserts a deliberate pause and synthesizes the halves separately — use it when a line comes out rushed.
- No filler intros/outros ("In this video…", "Thanks for watching"). Open on the problem, close on the key idea.

### 4. TTS in the background — start it right away
```
explainer tts <project> --background      # Gradio server (default), cached per beat
explainer status <project>                # progress + log tail
```
Gradio takes ~60–110 s per ≤28-word chunk on CPU (the app reloads the model per call), so a 1100-word script
takes ~1.5–2 h. Faster: `--backend direct --workers 2` (loads ChatterboxTTS in the venv; ~5× real time).
Editing a beat's text only regenerates that beat (cache key = spoken text + voice + settings). Re-run `tts` after edits.

### 5. Scenes (while TTS runs)
One file per scene in `scenes/<scene id>.js`, registered with `E.scene(id, {header, draw(ctx)})`; start from
`<KIT>/templates/project/scenes/s1_intro.js`. `explainer timing <project> --no-audio` gives an estimated timeline
so scenes can be written and previewed before audio exists; real durations slot in later automatically because
all reveals are keyed to beats (`c(i)`, `e(i, frac)`), never to absolute seconds.

Preview loop (fast, no full render):
```
explainer stills <project> s2_request@4.5 s3_node#2:0.8 --prefix wip   # scene@local-seconds, scene#beat:fraction
explainer stills <project> --beats                                     # one still per beat + tiled sheet
explainer scan <project>                                               # every frame: exceptions/NaN; layout: off-canvas/overlap text
```
Look at the PNGs yourself (Read tool) — clipped labels, overlaps and cramped layouts are only obvious visually.
Fix every scan error; treat layout warnings as "inspect a still at that time", then fix or accept knowingly.

### 6. Real timing
When `status` shows all clips cached: `explainer timing <project>`. If the total exceeds `video.max_duration_s`,
trim narration (not tails/gaps) and re-run `tts` — only edited beats regenerate. Then re-check stills.

### 7. Build and verify
```
explainer build <project>        # tts (cached) -> timing -> scan -> render -> mux -> verify
```
(or the steps individually: `render`, `mux`, `verify`). Then read `build/verify_report.json` findings and look at
`build/contact_sheet.png` (one frame per beat from the final MP4). Acceptance: no FAIL; each WARN explained or fixed.

### 8. Report
MP4 path + duration, scene list, verification summary (duration, sync, scan, narration screen, loudness),
contact sheet image, known limitations (schematic visuals, anything approximated, TTS quirks).

## Visual style (3b1b look without copying it)
- Dark background, few bright semantic colors, thin strokes, generous empty space; one focal idea on screen at a time.
- **Progressive construction**: draw diagrams in the order the narration introduces them (stroke-draw, write-on,
  staggered appearance); transform existing objects (move, morph, recolor) instead of cutting to new ones.
- **Semantic colors are fixed for the whole video** (declare in `legend`): e.g. blue = control/base, teal = shared data,
  gold = the tracked item/token, purple = actors, coral = cost/failure/writes, green = success. Never reuse a color for
  another meaning; grey/dim for structure and secondary text.
- Motion explains: tokens travel along real paths, bars grow to real values, counters count. Every animation
  should correspond to a sentence being spoken; visuals may lead speech by ~0.2 s (leading breath), never lag by more.
- Text: short labels, not sentences; ≥ 22 px at 1080p; keep 60 px clear of edges; headers top-left via `header`.
- Math via `E.tex` (KaTeX), revealed left-to-right with `p`.
- No 3Blue1Brown branding, pi creatures, logos, or copied scenes/music; the look is a style, not an asset.

## Accuracy
- Every number on screen comes from the materials; attribute it on screen or in the header when it matters
  ("paper, Fig. 10", "Table 3"). Never invent benchmark values, ratios or dates.
- Schematic visuals (curve shapes, illustrative counts, not-to-scale bars) must be labeled as such on screen
  ("schematic", "not to scale", "illustrative").
- Don't state causal claims or comparisons the source doesn't make; when simplifying, say "roughly" / "about".
- If the materials are ambiguous, ask during planning rather than guessing.

## Lessons from the DSec build (apply by default)
- Phonetic `say` for every acronym; check the first generated clips by listening to rates in `status` output
  (0.28–0.55 s/word is normal; < 0.28 sounds rushed → split with `|` or rephrase).
- Each take begins with a ~0.1–0.5 s breath: speech onset lags the beat start. That is expected; the `beat onsets`
  check reports it; do not "fix" it by shifting visuals late.
- Budget length early. The 8-minute limit was hit after drafting; trimming three beats and regenerating cost time.
  Estimate with 0.37 s/word *plus* per-scene overhead before TTS starts.
- Check stills for clipped/overlapping text at the right edge and under moving objects — most DSec fixes were layout.
- Clamp every custom easing input (use `P()`); an unclamped ease produced a "131%" gauge.
- Keep scenes pure functions of `t` and use `E.rng(seed)`, never `Math.random`/`Date` — parallel workers must agree.
- CPU-only torch: direct TTS ~5× real time, model load ~20 s; Gradio adds a model reload per call. Rendering runs ~9–16 fps
  with 8 workers (KaTeX-heavy scenes are slower).
- ffmpeg input seeking (`-ss` before `-i`) can land on the wrong frame; the kit extracts frames by index.

## Troubleshooting quick map
- `status` shows a clip stuck "generating" with no log progress → the worker died; its lock is stale and is reclaimed automatically on the next `tts` run.
- Gradio unreachable → `tts` falls back to direct ChatterboxTTS (`tts.fallback`), or pass `--backend direct`.
- Scene shows "missing scene <id>" → file not loaded or `E.scene` id mismatch with `script.json`.
- `explainer` is not recognized → you used PATH; invoke `<KIT>/explainer.cmd` (or `python <KIT>/explainer/cli.py`).
- More in `<KIT>/README.md` → Troubleshooting.
