# Worked examples

Invoke the CLI with the full path from SKILL.md (`<KIT>/explainer.cmd` on Windows). `explainer` below is shorthand.

## Gold-standard project

`<KIT>/examples/binary-search/` is a complete 2-scene, ~33 s video:

- `materials/source.md` — the text the narration was written from
- `script.json` — 4 beats, legend, phonetic `say` on the formula line
- `scenes/s1_halving.js` — progressive array, color-coded discard, brace + comparison
- `scenes/s2_log.js` — shrinking bars, KaTeX `n/2^k = 1`, morph to a million-vs-20 comparison
- `output/Why_Binary_Search_Takes_log_n_Steps.mp4` — verified (duration, A/V sync, frame match, layout)

Rebuild without regenerating voice (clips are cached):

```
explainer build <KIT>/examples/binary-search --skip-tts
```

Copy patterns from those scene files (keyed to `c(i)` / `e(i, frac)`, `E.tex`, `E.morph`, `E.brace`, `E.hbar`) rather than inventing a new style.

## Agent session: paper section → video

User: *Use the 3b1b-explainer skill. Make a ~5 minute explainer of sections 2–3 of paper.pdf. Voice: E:/voices/me.wav.*

1. Read sections 2–3 of `paper.pdf`. List numbers and figures you might show.
2. Post the plan template from SKILL.md (title, word budget, scene table, color legend, accuracy notes). **Stop.**
3. After approval:

```
explainer init E:/work/paper-explainer --title "How the scheduler picks a node" --voice E:/voices/me.wav --materials paper.pdf
```

4. Write `script.json` (~5 min → ~750 words, 6–8 scenes, 15–45 words/beat, `pronunciations` for every acronym).
5. Start voice immediately, then design scenes in parallel:

```
explainer tts E:/work/paper-explainer --background
explainer timing E:/work/paper-explainer --no-audio
```

6. One `scenes/<id>.js` per scene, starting from `<KIT>/templates/project/scenes/s1_intro.js`. Preview:

```
explainer stills E:/work/paper-explainer --beats --prefix wip
explainer scan E:/work/paper-explainer
```

Read the PNGs. Fix clipped/overlapping labels. Poll `explainer status E:/work/paper-explainer` until every clip is cached.

7. `explainer timing E:/work/paper-explainer` — if over `max_duration_s`, cut words and re-run `tts` (only edited beats regenerate).
8. `explainer build E:/work/paper-explainer` (cached TTS is a no-op). Read `build/verify_report.json` and `build/contact_sheet.png`. No FAIL; explain or fix every WARN.
9. Report the MP4 path, duration, scene list, checks, contact sheet, and schematic-visual caveats.

## Agent session: regenerate one rushed line

User: *Beat s3_b2 sounds rushed.*

1. Split the `say` with `|` or shorten the sentence in `script.json` (`text` can stay for subtitles).
2. `explainer tts <project> --only s3_b2` then `explainer status <project>`.
3. `explainer timing <project>` and `explainer stills <project> s3_node#s3_b2:0.5`.
4. `explainer build <project> --skip-tts` if other clips are already cached.

## Agent session: CLI-only, no storyboard wait

If the user already supplied a finished `script.json` and scene files, skip steps 1–2 and run `explainer build <project>`. Still inspect stills and the contact sheet before calling it done.
