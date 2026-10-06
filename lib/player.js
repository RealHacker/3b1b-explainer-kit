// Maps global time to the active scene and renders it into the root SVG.
// Requires window.TIMING (build/timing.js) and scenes registered in window.SCENES.
(function () {
  const { W, H, C, DEFS, text, group, P, clamp } = window.E;
  const SCENE_FADE_IN = 0.45;
  const SCENE_FADE_OUT = 0.5;
  const HEADER_X = 72, HEADER_Y = 62, HEADER_CHAR_W = 13.5;
  const KATEX_FONTS = ["KaTeX_Main", "KaTeX_Math", "KaTeX_Size1", "KaTeX_Size2", "KaTeX_Size3", "KaTeX_Size4", "KaTeX_AMS"];
  const VIDEO = window.VIDEO || { width: W, height: H };

  function sceneCtx(sc, t) {
    const clips = sc.clips;
    const get = (i) => {
      if (typeof i === "string") {
        const hit = clips.find((c) => c.id === i);
        if (!hit) throw new Error(`scene ${sc.id}: no beat '${i}'`);
        return hit;
      }
      return clips[Math.max(0, Math.min(clips.length - 1, i - 1))];
    };
    return {
      t,
      T: sc.dur,
      n: clips.length,
      id: sc.id,
      beat: get,
      c: (i) => get(i).start,            // beat i start (1-based index or beat id), scene-local seconds
      d: (i) => get(i).dur,              // beat i duration
      e: (i, fr) => get(i).start + get(i).dur * fr, // point at fraction of beat i
      end: (i) => get(i).start + get(i).dur,
    };
  }

  function header(label, op) {
    if (!label) return "";
    return group(
      text(HEADER_X, HEADER_Y, label, { size: 24, fill: C.grey, anchor: "start", ls: 1.5, weight: 600 }) +
      `<line x1="${HEADER_X}" y1="84" x2="${HEADER_X + label.length * HEADER_CHAR_W}" y2="84" stroke="${C.dim}" stroke-width="2"/>`,
      { op });
  }

  function sceneAt(tGlobal) {
    const T = window.TIMING;
    let sc = T.scenes[T.scenes.length - 1];
    for (const s of T.scenes) {
      if (tGlobal < s.start + s.dur) { sc = s; break; }
    }
    return sc;
  }

  function frameSVG(tGlobal) {
    const sc = sceneAt(tGlobal);
    const t = tGlobal - sc.start;
    const def = window.SCENES[sc.id];
    let body = "";
    if (def) {
      body = def.draw(sceneCtx(sc, t));
    } else {
      body = text(W / 2, H / 2, `missing scene ${sc.id}`, { fill: C.coral });
    }
    const op = Math.min(P(t, 0, SCENE_FADE_IN), 1 - P(t, sc.dur - SCENE_FADE_OUT, SCENE_FADE_OUT));
    const label = def && (def.header ?? sc.header);
    const hdr = label ? header(label, clamp(op)) : "";
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${VIDEO.width}" height="${VIDEO.height}" viewBox="0 0 ${W} ${H}">` +
      DEFS + `<rect width="${W}" height="${H}" fill="${C.bg}"/>` +
      group(body, { op: clamp(op) }) + hdr +
      `<rect width="${W}" height="${H}" fill="url(#vignette)" pointer-events="none"/></svg>`;
  }

  window.renderFrame = function (t) {
    document.getElementById("stage").innerHTML = frameSVG(t);
    return true;
  };
  window.sceneAt = (t) => sceneAt(t).id;
  window.totalDuration = () => window.TIMING.total;
  window.explainerReady = (async () => {
    if (window.katex && document.fonts) {
      await Promise.all(KATEX_FONTS.map((fam) => document.fonts.load(`40px ${fam}`).catch(() => null)));
      await document.fonts.ready;
    }
    return true;
  })();
})();
