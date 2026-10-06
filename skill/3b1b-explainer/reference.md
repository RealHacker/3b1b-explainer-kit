# explainer-kit reference

## Project layout
```
<project>/
  explainer.config.json   all settings (defaults filled in by `init`)
  script.json             scenes -> beats (narration)
  scenes/*.js             one file per scene (files starting with "_" load first: shared helpers)
  materials/              source texts (not read by the tool; for you)
  voice.wav               reference voice (tts.voice)
  audio/cache/<key>.wav   narration cache (+ <key>.json metadata); audio/tts.log for background runs
  build/                  timing.json/js, narration.wav, subtitles.srt, index.html, video.mp4, stills/,
                          scan_report.json, verify_report.json, contact_sheet.png
  output/<name>.mp4/.srt  final deliverable
```

## script.json
```json
{
  "title": "Video title (MP4 metadata; default output file name)",
  "legend": { "blue": "control plane", "gold": "the request" },
  "roles": { "focus": "#F4C05A" },
  "pronunciations": { "DSec": "D-Sec", "API": "A P I" },
  "scenes": [
    {
      "id": "s1_request",
      "header": "§3.2 Request path",
      "visual": "free-text storyboard note (ignored by the tool)",
      "tail_s": 1.5,
      "beats": [
        { "id": "s1_b1", "text": "Shown as subtitles.", "say": "Optional spoken override. | Pipe = pause.", "gap_after_s": 0.8 }
      ]
    }
  ]
}
```
- `beats` may also be called `clips` (legacy). Ids must be unique across scenes and beats; missing ids become `<scene>_b<n>`.
- `say` defaults to `text` with `pronunciations` applied (whole-word, case-sensitive).
- `legend` is documentation for you and the viewer; `roles` optionally overrides `E.ROLE` colors.
- `tail_s` per scene overrides `timing.scene_tail_s`; `gap_after_s` per beat overrides `timing.beat_gap_s`.

## Timeline model
Scene length = `scene_lead_s` + Σ beat durations + gaps + tail. Beat duration = measured clip length
(estimated at `est_sec_per_word` until the clip exists). Scenes fade in 0.45 s / out 0.5 s automatically.

## Scene API
```js
(function () {
  const { C, P, env, text, box, arrow } = window.E;
  window.E.scene("s1_request", {
    header: "§3.2 Request path",          // optional; falls back to script.json header
    draw({ t, T, n, c, d, e, end, beat, id }) { return "<svg markup>"; },
  });
})();
```
ctx: `t` scene-local seconds · `T` scene length · `n` beat count · `c(i)` beat start · `d(i)` duration · `end(i)` ·
`e(i, frac)` time at a fraction of beat i · `beat(i)` → `{id, start, dur, text}`. `i` = 1-based index or beat id.
Scene coordinates are always 1920×1080 (the player scales to `video.width/height`).

## Engine `window.E`
Canvas: `W` 1920, `H` 1080. `f(n)` = SVG number format. `esc(str)` HTML-escapes. `fmt(n)` locale integer (e.g. 380000 → "380,000").

Timing/easing (all clamp input):
- `P(t, start, dur, ease=smooth)` → 0..1 progress · `env(t, a, b, fin=.5, fout=.5)` fade in at a, out at b
- `stagger(t, i, n, start, dur, span=.4)` per-item progress · `tween(t, [[t0, v0], [t1, v1, ease?], ...])` numbers/colors/arrays
- eases: `smooth` (smootherstep), `easeOut`, `easeIn`, `easeInOut`, `linear`, `backOut`, `thereAndBack`
- `lerp`, `clamp`, `mix`, `lerpColor(hexA, hexB, t)`, `rng(seed)` deterministic PRNG

Primitives (return SVG strings; `op` = opacity, `draw`/`p` = stroke-draw progress 0..1):
- `text(x, y, str, {size, fill, anchor, weight, family, italic, ls, glow, op})` · `lines(x, y, "a\nb", {lh})`
- `write(x, y, str, p, opts)` typewriter reveal · `label(x, y, str, {size, color, bg, anchor})` text on a pill plate
- `rect(x, y, w, h, {stroke, fill, fillOp, rx, sw, dash, glow, draw, op})` · `circle(x, y, r, {fill, stroke, draw})`
- `path(d, {stroke, fill, sw, dash, draw, glow})` any path with stroke-draw
- `box(x, y, w, h, {title, sub, color, draw, glow, dash, size, subSize})` titled box
- `arrow(pts, {color, sw, p, head, head2, dash, hs})` polyline arrow, head rides the tip · `line(x1, y1, x2, y2, o)`
- `token(pts, frac, color, r, op)` glowing dot along a polyline · `hop(a, b, frac, {lift, color, r})` arcing token
- `brace(x1, y1, x2, y2, {depth, flip, label, color, draw})` curly brace (tip right of travel direction)
- `hbar(x, y, w, h, frac, {color, frame})` · `checkMark(x, y, s, color, p)` · `crossMark(...)`
- `group(svg, {op, tx, ty, s, ox, oy, rot})` transform/opacity wrapper (camera moves: scale around ox/oy)
- `axes(x, y, w, h, {x:[a,b], y:[a,b], xTicks, yTicks, xLabel, yLabel, draw})` → `{svg, X(v), Y(v)}` · `plot(ax, fn, a, b, {color, p})`
- `tex(x, y, "\\frac{a}{b}", {size, color, anchor, p, extent, display, op})` KaTeX; `p` wipes left→right over `extent` px
- `mathText(x, y, [[str, italic, color], ...])` quick inline math without KaTeX

Shapes & morphs:
- `circlePts(cx, cy, r, n)`, `regularPts(cx, cy, r, sides)`, `rectPts(x, y, w, h)`, `polyPath(pts, closed)`, `resample(pts, n)`
- `morph(ptsA, ptsB, t, {stroke, from, to, fill, fillTo, sw})` any two outlines (resampled to equal points)
- `morphPath(dA, dB, t, opts)` numeric interpolation when both paths share a command structure
  (e.g. two `roundRectPath` results); crossfades otherwise
- `pointAt(pts, frac)` → `{x, y, a}` · `polyLen(pts)` · `roundRectPath(x, y, w, h, r)`

Palette `E.C`: bg `#101216`, white `#ECECEC`, grey `#8A8F98`, dim `#3A3F48`, faint `#23272E`, blue `#58C4DD`,
teal `#5CD0B3`, gold `#F4C05A`, purple `#B48CE0`, coral `#FC6255`, green `#83C167`, orange `#F39C4A`.
`E.ROLE`: text, muted, structure, primary(blue), shared(teal), focus(gold), actor(purple), cost(coral), good(green), accent(orange).
Fonts: `E.FONT` (Segoe UI), `E.MONO` (Consolas), `E.MATH` (Cambria Math). Filters in DEFS: `url(#glow)`, `url(#vignette)`.

## Time specs (stills)
`12.5` global seconds · `s2_request@4.5` scene-local seconds · `s2_request#3:0.8` beat 3 at 80% · `s2_request#s2_b3:0.8` by beat id.

## CLI
| command | does |
|---|---|
| `init <p> [--title] [--voice wav] [--materials f...]` | scaffold project with full default config |
| `tts <p> [--background] [--backend gradio\|direct] [--workers N] [--only ids] [--adopt dir]` | synthesize missing clips |
| `status <p>` | cached / generating / pending + log tail |
| `timing <p> [--no-audio]` | timeline (+ narration.wav, subtitles.srt when complete) |
| `stills <p> specs... [--beats] [--prefix]` | PNGs in build/stills (+ sheet with --beats) |
| `scan <p>` | per-frame errors + sampled layout warnings → build/scan_report.json |
| `render <p> [--workers] [--start s] [--end s]` | build/video.mp4 (runs scan first) |
| `mux <p>` | output/<name>.mp4 + .srt |
| `verify <p> [--video mp4]` | checks → build/verify_report.json, contact_sheet.png; exit 1 on FAIL |
| `build <p> [--skip-tts] [--force]` | tts → timing → scan → render → mux → verify |

## Config keys (explainer.config.json; defaults shown by `init`)
- `paths`: script, scenes_dir, scripts (explicit ordered list overrides scenes_dir), build, cache, output
- `video`: width, height, fps, crf, preset, max_duration_s, output_name
- `timing`: scene_lead_s, beat_gap_s, scene_tail_s, scene_tail_overrides {scene: s}, est_sec_per_word
- `tts`: backend (gradio|direct), fallback, gradio_url, gradio_api, voice, exaggeration, cfg_weight, temperature, seed,
  max_chunk_words, chunk_gap_s, pause_s, attempts, accept_rate [lo, hi] s/word, target_rate, request_retries,
  request_timeout_s, workers, trim_threshold, edge_pad_s, direct {python, threads, device}
- `audio`: sample_rate, narration_peak, loudness_i/tp/lra, aac_bitrate, out_sample_rate
- `subtitles`: enabled, max_chars, wrap_chars · `render`: workers (0 = auto), scan_step_s, layout_step_s
- `checks`: rate_range, max_internal_silence_s, sync_tolerance_ms, av_tolerance_frames, contact_columns, contact_width

Changing any `tts` synthesis setting (not backend/url/workers) or the voice file changes cache keys → full regeneration.
