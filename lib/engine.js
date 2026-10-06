// Immediate-mode SVG animation engine: every frame is a pure function of time.
// Scenes author in a fixed 1920x1080 coordinate space; the player scales to the configured resolution.
(function () {
  const W = 1920, H = 1080;

  // Palette. Colors carry fixed meanings inside a video; declare the mapping once (script.json "legend")
  // and never reuse a color for a different concept.
  const C = {
    bg: "#101216",
    white: "#ECECEC",
    grey: "#8A8F98",
    dim: "#3A3F48",
    faint: "#23272E",
    blue: "#58C4DD",
    teal: "#5CD0B3",
    gold: "#F4C05A",
    purple: "#B48CE0",
    coral: "#FC6255",
    green: "#83C167",
    orange: "#F39C4A",
  };
  // Default semantic roles; a project may remap via window.PALETTE_ROLES before scenes load.
  const ROLE = Object.assign({
    text: C.white, muted: C.grey, structure: C.dim,
    primary: C.blue, shared: C.teal, focus: C.gold, actor: C.purple,
    cost: C.coral, good: C.green, accent: C.orange,
  }, window.PALETTE_ROLES || {});

  const FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif";
  const MONO = "Consolas, 'Cascadia Mono', monospace";
  const MATH = "'Cambria Math', Cambria, 'Times New Roman', serif";

  // ------------------------------------------------------------------ easing & tweening
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const smooth = (t) => { t = clamp(t); return t * t * t * (t * (6 * t - 15) + 10); };
  const easeOut = (t) => { t = clamp(t); return 1 - Math.pow(1 - t, 3); };
  const easeIn = (t) => { t = clamp(t); return t * t * t; };
  const easeInOut = (t) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
  const linear = (t) => clamp(t);
  const BACK_OVERSHOOT = 1.70158;
  const backOut = (t) => { t = clamp(t); const c = BACK_OVERSHOOT; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
  const thereAndBack = (t) => { t = clamp(t); return smooth(t < 0.5 ? 2 * t : 2 - 2 * t); };
  // Progress of an animation that starts at `start` and lasts `dur`. Input is clamped before easing.
  const P = (t, start, dur = 1, ease = smooth) => ease(dur <= 0 ? (t >= start ? 1 : 0) : clamp((t - start) / dur));
  // Fade in at `a`, fade out at `b` (b may be Infinity).
  const env = (t, a, b = Infinity, fin = 0.5, fout = 0.5) => Math.min(P(t, a, fin), 1 - P(t, b, fout));
  // Staggered progress for item i of n spread over [start, start+dur]; `span` = fraction each item takes.
  const stagger = (t, i, n, start, dur, span = 0.4, ease = smooth) => {
    const each = dur * span, step = n > 1 ? (dur - each) / (n - 1) : 0;
    return P(t, start + i * step, each, ease);
  };

  function hexToRgb(h) {
    const s = h.replace("#", "");
    const v = parseInt(s.length === 3 ? s.split("").map((c) => c + c).join("") : s, 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function lerpColor(a, b, t) {
    const x = hexToRgb(a), y = hexToRgb(b), u = clamp(t);
    return "#" + x.map((v, i) => Math.round(lerp(v, y[i], u)).toString(16).padStart(2, "0")).join("");
  }
  const mix = (a, b, t) => {
    if (typeof a === "number") return lerp(a, b, t);
    if (typeof a === "string") return lerpColor(a, b, t);
    return a.map((v, i) => mix(v, b[i], t));
  };
  // Keyframed value: keys = [[time, value, ease?], ...] sorted by time. Values: numbers, colors, or arrays.
  function tween(t, keys, ease = smooth) {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const [t1, v1, e1] = keys[i];
      if (t <= t1) {
        const [t0, v0] = keys[i - 1];
        return mix(v0, v1, (e1 || ease)(t1 === t0 ? 1 : (t - t0) / (t1 - t0)));
      }
    }
    return keys[keys.length - 1][1];
  }

  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const f = (n) => (Math.round(n * 100) / 100).toString();
  const fmt = (n) => Math.round(n).toLocaleString("en-US");

  function roundRectPath(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    return `M${f(x + r)},${f(y)} H${f(x + w - r)} A${r},${r} 0 0 1 ${f(x + w)},${f(y + r)} V${f(y + h - r)} ` +
      `A${r},${r} 0 0 1 ${f(x + w - r)},${f(y + h)} H${f(x + r)} A${r},${r} 0 0 1 ${f(x)},${f(y + h - r)} ` +
      `V${f(y + r)} A${r},${r} 0 0 1 ${f(x + r)},${f(y)} Z`;
  }

  // Stroke reveal via normalized path length.
  function drawAttrs(p) {
    if (p >= 1) return "";
    return ` pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${f(1 - clamp(p))}"`;
  }

  // ------------------------------------------------------------------ primitives
  // Any SVG path with stroke-draw progress `draw` (0..1); fill fades in over the second half of the draw.
  function path(d, o = {}) {
    const p = o.draw ?? 1, op = o.op ?? 1;
    if (p <= 0 || op <= 0 || !d) return "";
    const fill = o.fill ?? "none";
    const fillOp = (o.fillOp ?? 1) * clamp((p - 0.5) / 0.5);
    const filt = o.glow ? ` filter="url(#glow)"` : "";
    let s = "";
    if (fill !== "none") s += `<path d="${d}" fill="${fill}" fill-opacity="${f(fillOp)}" stroke="none"/>`;
    if ((o.stroke ?? C.white) !== "none") {
      s += `<path d="${d}" fill="none" stroke="${o.stroke ?? C.white}" stroke-width="${o.sw ?? 3}" stroke-linejoin="round"` +
        ` stroke-linecap="round"${o.dash ? ` stroke-dasharray="${o.dash}"` : drawAttrs(p)}${filt}/>`;
    }
    return `<g opacity="${f(op)}">${s}</g>`;
  }

  function rect(x, y, w, h, o = {}) {
    const p = o.draw ?? 1;
    const op = o.op ?? 1;
    if (p <= 0 || op <= 0) return "";
    const stroke = o.stroke ?? C.white;
    const fill = o.fill ?? "none";
    const fillOp = (o.fillOp ?? 1) * clamp((p - 0.5) / 0.5);
    const dash = o.dash ? ` stroke-dasharray="${o.dash}"` : "";
    const filt = o.glow ? ` filter="url(#glow)"` : "";
    const d = roundRectPath(x, y, w, h, o.rx ?? 10);
    let s = "";
    if (fill !== "none") s += `<path d="${d}" fill="${fill}" fill-opacity="${f(fillOp)}" stroke="none"/>`;
    if (stroke !== "none") {
      s += `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${o.sw ?? 3}"` +
        (o.dash ? dash : drawAttrs(p)) + filt + `/>`;
    }
    return `<g opacity="${f(op)}">${s}</g>`;
  }

  function text(x, y, str, o = {}) {
    const op = o.op ?? 1;
    if (op <= 0 || str === "" || str == null) return "";
    const size = o.size ?? 30;
    const anchor = o.anchor ?? "middle";
    const weight = o.weight ?? 400;
    const fam = o.family ?? FONT;
    const style = o.italic ? ` font-style="italic"` : "";
    const ls = o.ls ? ` letter-spacing="${o.ls}"` : "";
    const filt = o.glow ? ` filter="url(#glow)"` : "";
    const content = o.raw ? str : esc(str);
    return `<text x="${f(x)}" y="${f(y)}" font-family="${fam}" font-size="${size}" font-weight="${weight}"` +
      ` fill="${o.fill ?? C.white}" text-anchor="${anchor}" dominant-baseline="${o.baseline ?? "middle"}"` +
      ` opacity="${f(op)}"${style}${ls}${filt}>${content}</text>`;
  }

  // Multi-line text; lines separated by \n.
  function lines(x, y, str, o = {}) {
    const lh = o.lh ?? (o.size ?? 30) * 1.3;
    return str.split("\n").map((ln, i) => text(x, y + i * lh, ln, o)).join("");
  }

  // Character-by-character reveal ("write" effect).
  function write(x, y, str, p, o = {}) {
    if (p <= 0) return "";
    const n = str.length;
    const shown = clamp(p) * n;
    const full = Math.floor(shown);
    const partial = shown - full;
    let s = esc(str.slice(0, full));
    if (full < n) s += `<tspan opacity="${f(partial)}">${esc(str[full])}</tspan>`;
    const rest = full + 1 < n ? `<tspan opacity="0">${esc(str.slice(full + 1))}</tspan>` : "";
    return text(x, y, s + rest, { ...o, raw: true });
  }

  // Text on a rounded plate, for labels that sit over busy diagrams.
  const LABEL_CHAR_W = 0.56;
  function label(x, y, str, o = {}) {
    const op = o.op ?? 1;
    if (op <= 0) return "";
    const size = o.size ?? 24, padX = o.padX ?? size * 0.55, padY = o.padY ?? size * 0.32;
    const w = (o.w ?? str.length * size * LABEL_CHAR_W) + 2 * padX, h = size + 2 * padY;
    const anchor = o.anchor ?? "middle";
    const x0 = anchor === "start" ? x : anchor === "end" ? x - w : x - w / 2;
    const color = o.color ?? C.grey;
    return group(
      rect(x0, y - h / 2, w, h, { stroke: o.border ?? color, sw: 1.5, fill: o.bg ?? C.bg, fillOp: o.bgOp ?? 0.92, rx: h / 2 }) +
      text(x0 + w / 2, y, str, { size, fill: o.fill ?? color, weight: o.weight ?? 500, family: o.family }),
      { op });
  }

  function polyLen(pts) {
    let L = 0;
    for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    return L;
  }

  function pointAt(pts, fr) {
    const L = polyLen(pts);
    let target = clamp(fr) * L;
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      const seg = Math.hypot(x1 - x0, y1 - y0);
      if (target <= seg || i === pts.length - 1) {
        const u = seg === 0 ? 0 : clamp(target / seg);
        return { x: lerp(x0, x1, u), y: lerp(y0, y1, u), a: Math.atan2(y1 - y0, x1 - x0) };
      }
      target -= seg;
    }
    const last = pts[pts.length - 1];
    return { x: last[0], y: last[1], a: 0 };
  }

  function head(x, y, a, color, size = 16, op = 1) {
    const p1 = [x - size * Math.cos(a - 0.45), y - size * Math.sin(a - 0.45)];
    const p2 = [x - size * Math.cos(a + 0.45), y - size * Math.sin(a + 0.45)];
    return `<path d="M${f(x)},${f(y)} L${f(p1[0])},${f(p1[1])} L${f(p2[0])},${f(p2[1])} Z" fill="${color}" opacity="${f(op)}"/>`;
  }

  // Polyline arrow revealed to fraction p.
  function arrow(pts, o = {}) {
    const p = o.p ?? 1;
    const op = o.op ?? 1;
    if (p <= 0 || op <= 0) return "";
    const color = o.color ?? C.white;
    const sw = o.sw ?? 3;
    const d = "M" + pts.map((q) => `${f(q[0])},${f(q[1])}`).join(" L");
    const dash = o.dash ? ` stroke-dasharray="${o.dash}"` : drawAttrs(p);
    let s = `<path d="${d}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round"${dash}/>`;
    if (o.head !== false) {
      const tip = pointAt(pts, p);
      s += head(tip.x, tip.y, tip.a, color, o.hs ?? 16, clamp(p * 4));
    }
    if (o.head2) {
      const t0 = pointAt(pts, 0);
      s += head(t0.x, t0.y, t0.a + Math.PI, color, o.hs ?? 16, clamp(p * 4));
    }
    return `<g opacity="${f(op)}">${s}</g>`;
  }

  function line(x1, y1, x2, y2, o = {}) {
    return arrow([[x1, y1], [x2, y2]], { ...o, head: o.head ?? false });
  }

  function circle(x, y, r, o = {}) {
    const op = o.op ?? 1;
    if (op <= 0 || r <= 0) return "";
    const filt = o.glow ? ` filter="url(#glow)"` : "";
    const p = o.draw ?? 1;
    const strokeAttrs = o.stroke ? ` stroke="${o.stroke}" stroke-width="${o.sw ?? 3}"${drawAttrs(p)}` : "";
    return `<circle cx="${f(x)}" cy="${f(y)}" r="${f(r)}" fill="${o.fill ?? "none"}"${strokeAttrs} opacity="${f(op)}"${filt}/>`;
  }

  // Glowing token moving along a polyline.
  function token(pts, fr, color = C.gold, r = 11, op = 1) {
    if (op <= 0) return "";
    const q = pointAt(pts, fr);
    return circle(q.x, q.y, r * 2.2, { fill: color, op: 0.18 * op }) + circle(q.x, q.y, r, { fill: color, op, glow: true });
  }

  // Token that travels from a to b with an arc of height `lift` (negative = upward).
  function hop(a, b, fr, o = {}) {
    const u = clamp(fr);
    const x = lerp(a[0], b[0], u), y = lerp(a[1], b[1], u) + (o.lift ?? -80) * 4 * u * (1 - u);
    const r = o.r ?? 11, op = o.op ?? 1, color = o.color ?? C.gold;
    if (op <= 0) return "";
    return circle(x, y, r * 2.2, { fill: color, op: 0.18 * op }) + circle(x, y, r, { fill: color, op, glow: true });
  }

  function group(content, o = {}) {
    const op = o.op ?? 1;
    if (op <= 0 || !content) return "";
    const tr = [];
    if (o.tx || o.ty) tr.push(`translate(${f(o.tx ?? 0)},${f(o.ty ?? 0)})`);
    if (o.rot) tr.push(`rotate(${f(o.rot)}${o.ox != null ? ` ${f(o.ox)} ${f(o.oy)}` : ""})`);
    if (o.s != null && o.s !== 1) {
      if (o.ox != null) tr.push(`translate(${f(o.ox)},${f(o.oy)}) scale(${f(o.s)}) translate(${f(-o.ox)},${f(-o.oy)})`);
      else tr.push(`scale(${f(o.s)})`);
    }
    const t = tr.length ? ` transform="${tr.join(" ")}"` : "";
    return `<g opacity="${f(op)}"${t}>${content}</g>`;
  }

  // Labeled box: title centered, optional subtitle.
  function box(x, y, w, h, o = {}) {
    const color = o.color ?? C.blue;
    const p = o.draw ?? 1;
    const op = o.op ?? 1;
    let s = "";
    if (o.glow) s += rect(x - 6, y - 6, w + 12, h + 12, { stroke: color, sw: 2, op: 0.5 * o.glow, rx: (o.rx ?? 12) + 6, glow: true });
    s += rect(x, y, w, h, { stroke: color, fill: o.fill ?? color, fillOp: o.fillOp ?? 0.12, draw: p, rx: o.rx ?? 12, sw: o.sw ?? 3, dash: o.dash });
    const tOp = clamp((p - 0.55) / 0.45);
    const cy = y + h / 2;
    if (o.title) {
      const dy = o.sub ? -(o.subSize ?? 22) * 0.62 : 0;
      s += text(x + w / 2, cy + dy, o.title, { size: o.size ?? 30, weight: o.weight ?? 600, fill: o.tcolor ?? C.white, op: tOp, family: o.family });
    }
    if (o.sub) {
      s += text(x + w / 2, cy + (o.size ?? 30) * 0.62, o.sub, { size: o.subSize ?? 22, fill: o.scolor ?? C.grey, op: tOp, family: o.subFamily });
    }
    return group(s, { op });
  }

  function checkMark(x, y, s, color, p = 1, op = 1) {
    return arrow([[x - s, y], [x - s * 0.3, y + s * 0.7], [x + s, y - s * 0.8]], { color, sw: 6, head: false, p, op });
  }

  function crossMark(x, y, s, color, p = 1, op = 1) {
    return arrow([[x - s, y - s], [x + s, y + s]], { color, sw: 6, head: false, p: clamp(p * 2), op }) +
      arrow([[x + s, y - s], [x - s, y + s]], { color, sw: 6, head: false, p: clamp(p * 2 - 1), op });
  }

  // Horizontal bar with value label.
  function hbar(x, y, w, h, frac, o = {}) {
    const op = o.op ?? 1;
    const color = o.color ?? C.blue;
    let s = rect(x, y, w, h, { stroke: o.frame ?? C.dim, sw: 2, rx: o.rx ?? 4 });
    const fw = Math.max(0, w * clamp(frac));
    if (fw > 0.5) s += `<rect x="${f(x)}" y="${f(y)}" width="${f(fw)}" height="${h}" rx="${o.rx ?? 4}" fill="${color}" fill-opacity="${o.fillOp ?? 0.85}"/>`;
    return group(s, { op });
  }

  function mathText(x, y, parts, o = {}) {
    // parts: array of [string, italic?, color?]
    const tsp = parts.map(([s, it, col]) =>
      `<tspan${it ? ` font-style="italic"` : ""}${col ? ` fill="${col}"` : ""}>${esc(s)}</tspan>`).join("");
    return text(x, y, tsp, { ...o, raw: true, family: MATH });
  }

  // Curly brace from (x1,y1) to (x2,y2). The tip points to the right of the travel direction
  // (a left-to-right brace points down); flip:true points it the other way. Optional label beyond the tip.
  function brace(x1, y1, x2, y2, o = {}) {
    const op = o.op ?? 1, p = o.draw ?? 1;
    if (op <= 0 || p <= 0) return "";
    const L = Math.hypot(x2 - x1, y2 - y1), a = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
    const d = (o.depth ?? 18) * (o.flip ? -1 : 1), q = d / 2;
    const m = L / 2, r = Math.min(Math.abs(d), L / 4);
    const dd = `M0,0 Q0,${f(q)} ${f(r)},${f(q)} L${f(m - r)},${f(q)} Q${f(m)},${f(q)} ${f(m)},${f(d)} ` +
      `Q${f(m)},${f(q)} ${f(m + r)},${f(q)} L${f(L - r)},${f(q)} Q${f(L)},${f(q)} ${f(L)},0`;
    let s = `<g transform="translate(${f(x1)},${f(y1)}) rotate(${f(a)})">` + path(dd, { stroke: o.color ?? C.grey, sw: o.sw ?? 2.5, draw: p }) + `</g>`;
    if (o.label) {
      const nx = -Math.sin(a * Math.PI / 180), ny = Math.cos(a * Math.PI / 180);
      const g = (o.gap ?? 30) + Math.abs(d);
      const sign = o.flip ? -1 : 1;
      s += text((x1 + x2) / 2 + nx * g * sign, (y1 + y2) / 2 + ny * g * sign, o.label,
        { size: o.size ?? 26, fill: o.lcolor ?? o.color ?? C.grey, op: clamp((p - 0.5) * 2) });
    }
    return group(s, { op });
  }

  // ------------------------------------------------------------------ shapes & morphs
  const polyPath = (pts, closed = true) =>
    pts.length ? "M" + pts.map((q) => `${f(q[0])},${f(q[1])}`).join(" L") + (closed ? " Z" : "") : "";

  // Resample a polyline/polygon to n points evenly spaced by arc length.
  function resample(pts, n, closed = true) {
    const src = closed ? pts.concat([pts[0]]) : pts;
    const out = [];
    for (let i = 0; i < n; i++) {
      const q = pointAt(src, closed ? i / n : i / Math.max(1, n - 1));
      out.push([q.x, q.y]);
    }
    return out;
  }
  const circlePts = (cx, cy, r, n = 96, phase = -Math.PI / 2) =>
    Array.from({ length: n }, (_, i) => [cx + r * Math.cos(phase + 2 * Math.PI * i / n), cy + r * Math.sin(phase + 2 * Math.PI * i / n)]);
  const regularPts = (cx, cy, r, sides, phase = -Math.PI / 2) => circlePts(cx, cy, r, sides, phase);
  const rectPts = (x, y, w, h) => [[x + w / 2, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]];

  // Morph between two point lists (any lengths): both are resampled to n points and interpolated.
  const MORPH_SAMPLES = 120;
  function morphPts(a, b, t, n = MORPH_SAMPLES, closed = true) {
    const A = resample(a, n, closed), B = resample(b, n, closed), u = clamp(t);
    return A.map((q, i) => [lerp(q[0], B[i][0], u), lerp(q[1], B[i][1], u)]);
  }
  // Draw a morphing shape; o.from/o.to colors interpolate stroke and fill.
  function morph(a, b, t, o = {}) {
    const u = clamp(t);
    const stroke = o.to ? lerpColor(o.from ?? C.white, o.to, u) : (o.stroke ?? C.white);
    const fill = o.fill ? (o.fillTo ? lerpColor(o.fill, o.fillTo, u) : o.fill) : "none";
    return path(polyPath(morphPts(a, b, u, o.n, o.closed ?? true), o.closed ?? true), { ...o, stroke, fill });
  }
  // Numeric interpolation between two path strings with identical command structure; crossfades otherwise.
  const NUM_RE = /-?\d*\.?\d+(?:e[-+]?\d+)?/gi;
  function morphPath(dA, dB, t, o = {}) {
    const na = dA.match(NUM_RE) || [], nb = dB.match(NUM_RE) || [];
    const skel = (d) => d.replace(NUM_RE, "#");
    if (na.length === nb.length && skel(dA) === skel(dB)) {
      let i = 0;
      const d = dA.replace(NUM_RE, () => f(lerp(parseFloat(na[i]), parseFloat(nb[i++]), clamp(t))));
      return path(d, o);
    }
    const op = o.op ?? 1;
    return path(dA, { ...o, op: op * (1 - clamp(t)) }) + path(dB, { ...o, op: op * clamp(t) });
  }

  // ------------------------------------------------------------------ axes & plots
  // Returns {svg, X(v), Y(v)} mapping data to canvas. o: {x:[min,max], y:[min,max], xTicks, yTicks, xLabel, yLabel, draw}
  function axes(x, y, w, h, o = {}) {
    const [x0, x1] = o.x ?? [0, 1], [y0, y1] = o.y ?? [0, 1];
    const X = (v) => x + (v - x0) / (x1 - x0) * w, Y = (v) => y + h - (v - y0) / (y1 - y0) * h;
    const p = o.draw ?? 1, color = o.color ?? C.grey, op = o.op ?? 1;
    let s = arrow([[x, y + h], [x + w + 24, y + h]], { color, sw: 2.5, p, hs: 12 }) +
      arrow([[x, y + h], [x, y - 24]], { color, sw: 2.5, p, hs: 12 });
    const tickOp = clamp((p - 0.6) / 0.4);
    for (const v of o.xTicks ?? []) {
      s += line(X(v), y + h - 6, X(v), y + h + 6, { color, sw: 2, op: tickOp });
      s += text(X(v), y + h + 30, o.xFmt ? o.xFmt(v) : String(v), { size: o.tickSize ?? 20, fill: color, op: tickOp });
    }
    for (const v of o.yTicks ?? []) {
      s += line(x - 6, Y(v), x + 6, Y(v), { color, sw: 2, op: tickOp });
      s += text(x - 16, Y(v), o.yFmt ? o.yFmt(v) : String(v), { size: o.tickSize ?? 20, fill: color, anchor: "end", op: tickOp });
    }
    if (o.xLabel) s += text(x + w, y + h + 62, o.xLabel, { size: 22, fill: color, anchor: "end", op: tickOp });
    if (o.yLabel) s += text(x, y - 46, o.yLabel, { size: 22, fill: color, anchor: "start", op: tickOp });
    return { svg: group(s, { op }), X, Y };
  }
  // Graph of fn over [a,b] on axes ax, drawn to fraction o.p.
  const PLOT_SAMPLES = 160;
  function plot(ax, fn, a, b, o = {}) {
    const n = o.n ?? PLOT_SAMPLES, pts = [];
    for (let i = 0; i <= n; i++) {
      const v = lerp(a, b, i / n), yv = fn(v);
      if (Number.isFinite(yv)) pts.push([ax.X(v), ax.Y(yv)]);
    }
    return pts.length > 1 ? arrow(pts, { color: o.color ?? C.blue, sw: o.sw ?? 4, p: o.p ?? 1, head: false, op: o.op }) : "";
  }

  // ------------------------------------------------------------------ KaTeX
  // Renders LaTeX with KaTeX inside a foreignObject. Needs lib/katex (loaded by the player page).
  // o: {size (px), color, anchor: middle|start|end, op, p (left-to-right wipe reveal), w, h, display}
  const texCache = new Map();
  let texSeq = 0;
  function tex(x, y, latex, o = {}) {
    const op = o.op ?? 1, p = o.p ?? 1;
    if (op <= 0 || p <= 0) return "";
    const size = o.size ?? 44, color = o.color ?? C.white;
    if (!window.katex) return mathText(x, y, [[latex, true, color]], { size, anchor: o.anchor, op });
    const key = latex + "|" + (o.display ? 1 : 0);
    if (!texCache.has(key)) {
      try {
        texCache.set(key, window.katex.renderToString(latex, { throwOnError: true, displayMode: !!o.display, output: "html" }));
      } catch (e) {
        throw new Error(`KaTeX failed on "${latex}": ${e.message}`);
      }
    }
    const w = o.w ?? 1600, h = o.h ?? size * 3;
    const anchor = o.anchor ?? "middle";
    const fx = anchor === "start" ? x : anchor === "end" ? x - w : x - w / 2;
    const justify = anchor === "start" ? "flex-start" : anchor === "end" ? "flex-end" : "center";
    const html = `<div xmlns="http://www.w3.org/1999/xhtml" style="width:${w}px;height:${h}px;display:flex;align-items:center;` +
      `justify-content:${justify};color:${color};font-size:${size}px;line-height:1;white-space:nowrap">${texCache.get(key)}</div>`;
    let body = `<foreignObject data-tex="${esc(latex).replace(/"/g, "&quot;")}" x="${f(fx)}" y="${f(y - h / 2)}" width="${w}" height="${h}">${html}</foreignObject>`;
    if (p < 1) {
      const id = `texclip${texSeq++}`;
      const ext = o.extent ?? w;
      const cx0 = anchor === "start" ? x : anchor === "end" ? x - ext : x - ext / 2;
      body = `<clipPath id="${id}"><rect x="${f(cx0)}" y="${f(y - h / 2)}" width="${f(ext * clamp(p))}" height="${h}"/></clipPath>` +
        `<g clip-path="url(#${id})">${body}</g>`;
    }
    return `<g opacity="${f(op)}">${body}</g>`;
  }

  const DEFS = `<defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <radialGradient id="vignette" cx="50%" cy="45%" r="75%">
      <stop offset="60%" stop-color="#000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.45"/>
    </radialGradient>
  </defs>`;

  // Deterministic pseudo-random numbers (never use Math.random in scenes).
  function rng(seed) {
    let s = seed >>> 0;
    return () => {
      s = (s + 0x6D2B79F5) >>> 0;
      let t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Scene registration: E.scene("s1_intro", { header: "...", draw(ctx) { return svgString; } })
  window.SCENES = window.SCENES || {};
  const scene = (id, def) => { window.SCENES[id] = def; };

  window.E = {
    W, H, C, ROLE, FONT, MONO, MATH,
    clamp, lerp, smooth, easeOut, easeIn, easeInOut, linear, backOut, thereAndBack, P, env, stagger, tween, lerpColor, mix,
    esc, fmt, f, roundRectPath,
    path, rect, text, lines, write, label, arrow, line, circle, token, hop, group, box, checkMark, crossMark, hbar,
    pointAt, polyLen, head, mathText, brace,
    polyPath, resample, circlePts, regularPts, rectPts, morphPts, morph, morphPath,
    axes, plot, tex,
    rng, DEFS, scene,
  };
})();
