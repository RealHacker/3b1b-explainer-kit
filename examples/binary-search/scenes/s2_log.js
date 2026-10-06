// Scene 2: the candidate count halves each step (bars), which gives k = log2 n; then a million vs twenty.
(function () {
  const { C, P, env, clamp, text, tex, path, roundRectPath, morphPath, hbar, group, fmt, stagger, easeOut } = window.E;

  const LEVELS = 6;
  const BAR_X = 260, BAR_Y0 = 230, BAR_STEP = 92, BAR_H = 40, BAR_W0 = 560;
  const LABELS = ["n", "\\tfrac{n}{2}", "\\tfrac{n}{4}", "\\tfrac{n}{8}", "\\tfrac{n}{16}", "\\tfrac{n}{32}"];
  const RIGHT_X = 1360;
  const MILLION = 1000000, BINARY_STEPS = 20;
  const CMP_X = 1010, CMP_W = 700, MIN_BAR_FRAC = 0.012;

  window.E.scene("s2_log", {
    header: "Counting the halvings",
    draw({ t, c, e, d, T }) {
      let s = "";
      const dimLeft = 1 - 0.6 * P(t, c(2), 0.8);

      // A single bar halves step by step (path morph); a copy stays behind at each level.
      let left = "";
      const stepT = (k) => c(1) + 0.3 + k * (d(1) * 0.42) / (LEVELS - 1);
      for (let k = 0; k < LEVELS; k++) {
        const y = BAR_Y0 + k * BAR_STEP;
        const w = BAR_W0 / 2 ** k;
        const at = stepT(k);
        const p = P(t, at, 0.55);
        if (p <= 0) continue;
        const prevW = k === 0 ? w : BAR_W0 / 2 ** (k - 1);
        const prevY = k === 0 ? y : y - BAR_STEP;
        const dA = roundRectPath(BAR_X, prevY, prevW, BAR_H, 8), dB = roundRectPath(BAR_X, y, w, BAR_H, 8);
        left += morphPath(dA, dB, easeOut(p), { stroke: C.blue, fill: C.blue, fillOp: 0.35, sw: 2.5 });
        left += text(BAR_X - 40, y + BAR_H / 2, `k=${k}`, { size: 22, fill: C.grey, anchor: "end", op: p });
        left += tex(BAR_X + w + 24, y + BAR_H / 2, LABELS[k], { size: 34, anchor: "start", w: 300, op: P(t, at + 0.3, 0.4) });
      }
      left += text(BAR_X, BAR_Y0 + LEVELS * BAR_STEP + 20, "…  until one candidate is left", { size: 26, fill: C.grey, anchor: "start", op: P(t, stepT(LEVELS - 1) + 0.4, 0.6) });
      s += group(left, { op: dimLeft });

      // Right: the algebra.
      s += text(RIGHT_X, 190, "remaining after k comparisons", { size: 26, fill: C.grey, op: P(t, c(1) + 0.4, 0.6) });
      s += tex(RIGHT_X, 305, "\\dfrac{n}{2^k}", { size: 60, p: P(t, c(1) + 0.6, 0.9), extent: 200 });
      s += tex(RIGHT_X, 485, "\\dfrac{n}{2^k} = 1", { size: 60, p: P(t, e(1, 0.52), 0.9), extent: 360 });
      const kOp = P(t, e(1, 0.78), 0.8);
      s += tex(RIGHT_X, 628, "\\Rightarrow\\; k = \\log_2 n", { size: 64, color: C.teal, p: kOp, extent: 520 });
      s += path(roundRectPath(RIGHT_X - 290, 578, 580, 100, 14), { stroke: C.teal, sw: 2, draw: P(t, e(1, 0.86), 0.9), op: 0.8 });

      // Beat 2: a million elements.
      const b2 = P(t, c(2), 0.6);
      s += tex(RIGHT_X, 750, "\\log_2 1{,}000{,}000 \\approx 19.9", { size: 44, op: b2 });
      const grow = (k) => stagger(t, k, 2, e(2, 0.25), d(2) * 0.55, 0.7);
      const linear = MILLION * grow(0), binary = BINARY_STEPS * grow(1);
      s += text(CMP_X, 830, "linear scan", { size: 26, fill: C.grey, anchor: "start", op: b2 });
      s += hbar(CMP_X + 200, 813, CMP_W - 200, 34, clamp(linear / MILLION), { color: C.coral, op: b2 });
      s += text(CMP_X + CMP_W + 20, 830, fmt(linear), { size: 28, weight: 600, fill: C.coral, anchor: "start", op: b2 });
      s += text(CMP_X, 895, "binary search", { size: 26, fill: C.grey, anchor: "start", op: b2 });
      s += hbar(CMP_X + 200, 878, CMP_W - 200, 34, binary > 0 ? Math.max(MIN_BAR_FRAC, binary / MILLION) : 0, { color: C.green, op: b2 });
      s += text(CMP_X + CMP_W + 20, 895, fmt(binary), { size: 28, weight: 600, fill: C.green, anchor: "start", op: b2 });
      s += text(CMP_X + CMP_W / 2, 958, "worst-case comparisons for n = 1,000,000 · green bar not to scale", { size: 22, fill: C.dim, op: env(t, e(2, 0.3), T, 0.6) });
      return s;
    },
  });
})();
