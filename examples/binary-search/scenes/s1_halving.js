// Scene 1: fifteen sorted cells; each comparison with the middle cell discards half of the candidates.
(function () {
  const { C, W, MATH, P, env, clamp, tween, text, write, rect, label, brace, arrow, group, lerpColor, stagger } = window.E;

  const VALUES = [3, 7, 12, 15, 19, 22, 26, 30, 34, 38, 41, 45, 52, 58, 63];
  const TARGET = 41;
  const CELL_W = 92, CELL_H = 92, GAP = 14;
  const X0 = (W - (VALUES.length * (CELL_W + GAP) - GAP)) / 2;
  const ROW_Y = 430;
  const cx = (i) => X0 + i * (CELL_W + GAP) + CELL_W / 2;

  // Binary search trace: interval before each comparison, the mid, and the verdict.
  const STEPS = [
    { lo: 0, hi: 14, mid: 7, cut: [0, 7], say: "41 > 30  →  keep the right half" },
    { lo: 8, hi: 14, mid: 11, cut: [11, 14], say: "41 < 45  →  keep the left half" },
    { lo: 8, hi: 10, mid: 9, cut: [8, 9], say: "41 > 38  →  keep the right half" },
    { lo: 10, hi: 10, mid: 10, cut: null, say: "41 = 41  →  found" },
  ];
  const DISCARD_S = 0.6, POINTER_LEAD_S = 0.75;

  window.E.scene("s1_halving", {
    header: "One comparison, half the array",
    draw({ t, c, e, T }) {
      // Verdict times: first comparison resolves as beat 2 starts; the rest spread across beat 2.
      const verdict = [c(2) + 0.25, e(2, 0.42), e(2, 0.64), e(2, 0.84)];
      const pointAt = verdict.map((v, k) => (k === 0 ? e(1, 0.62) : v - POINTER_LEAD_S));
      const discardAt = VALUES.map(() => Infinity);
      STEPS.forEach((s, k) => { if (s.cut) for (let i = s.cut[0]; i <= s.cut[1]; i++) discardAt[i] = verdict[k]; });
      const step = pointAt.reduce((acc, v, k) => (t >= v ? k : acc), -1);
      const found = P(t, verdict[3], 0.5);

      let s = "";
      s += label(W - 250, 190, `target  ${TARGET}`, { size: 30, color: C.green, op: P(t, c(1) + 0.2, 0.6) });
      s += write(260, 190, "sorted array, n = 15", P(t, c(1) + 0.3, 1.0), { size: 30, fill: C.grey, anchor: "start" });

      VALUES.forEach((v, i) => {
        const appear = stagger(t, i, VALUES.length, c(1), 1.4, 0.35);
        const gone = P(t, discardAt[i], DISCARD_S);
        const isMid = step >= 0 && STEPS[step].mid === i && t < discardAt[i];
        const hit = i === 10 ? found : 0;
        let stroke = lerpColor(C.blue, C.coral, clamp(gone * 2));
        if (gone >= 1) stroke = C.dim;
        if (isMid) stroke = C.gold;
        if (hit > 0) stroke = lerpColor(C.gold, C.green, hit);
        const op = appear * (1 - 0.72 * gone);
        s += rect(cx(i) - CELL_W / 2, ROW_Y, CELL_W, CELL_H, {
          stroke, fill: stroke, fillOp: isMid || hit ? 0.22 : 0.1, draw: appear, rx: 10, sw: 3, glow: isMid || hit > 0.5, op,
        });
        s += text(cx(i), ROW_Y + CELL_H / 2, String(v), { size: 34, weight: 600, fill: gone > 0.5 ? C.grey : C.white, op: op * P(t, c(1) + 0.4 + i * 0.05, 0.4) });
        s += text(cx(i), ROW_Y + CELL_H + 26, String(i), { size: 18, fill: C.dim, op: appear * 0.9 });
      });

      // Middle pointer glides between successive mids.
      if (step >= 0) {
        const keys = STEPS.map((st, k) => [pointAt[k], cx(st.mid)]);
        const px = tween(t, keys.map(([tk, x], k) => [k === 0 ? tk : tk + 0.35, x]));
        const pop = env(t, pointAt[0], verdict[3] + 0.4, 0.4, 0.5);
        s += arrow([[px, ROW_Y - 92], [px, ROW_Y - 18]], { color: C.gold, sw: 4, p: P(t, pointAt[0], 0.5), op: pop });
        s += text(px, ROW_Y - 118, "middle", { size: 24, fill: C.gold, op: pop });
      }

      // Brace under the live interval [lo, hi].
      const live = (k) => {
        const st = STEPS[Math.min(k, STEPS.length - 1)];
        if (k < STEPS.length && STEPS[k].cut) {
          const [a, b] = STEPS[k].cut;
          return a === st.lo ? [b + 1, st.hi] : [st.lo, a - 1];
        }
        return [st.lo, st.hi];
      };
      const keysLo = [[c(1) + 1.2, STEPS[0].lo]], keysHi = [[c(1) + 1.2, STEPS[0].hi]];
      verdict.forEach((v, k) => { const [lo, hi] = live(k); keysLo.push([v + DISCARD_S, lo]); keysHi.push([v + DISCARD_S, hi]); });
      const lo = tween(t, keysLo), hi = tween(t, keysHi);
      const bx1 = cx(lo) - CELL_W / 2, bx2 = cx(hi) + CELL_W / 2;
      const settled = verdict.reduce((acc, v, k) => (t >= v + DISCARD_S ? k : acc), -1);
      const [sLo, sHi] = settled < 0 ? [STEPS[0].lo, STEPS[0].hi] : live(settled);
      const count = sHi - sLo + 1;
      s += brace(bx1, ROW_Y + CELL_H + 50, bx2, ROW_Y + CELL_H + 50, {
        depth: 20, color: C.blue, draw: P(t, c(1) + 1.2, 0.8), label: `${count} candidate${count === 1 ? "" : "s"}`, size: 26, lcolor: C.blue,
      });

      // Verdict caption for the current comparison.
      STEPS.forEach((st, k) => {
        const next = k + 1 < STEPS.length ? pointAt[k + 1] : T;
        s += text(W / 2, 800, st.say, { size: 36, family: MATH, fill: k === 3 ? C.green : C.white, op: env(t, verdict[k] - 0.25, next - 0.3, 0.35, 0.3) });
      });

      // Running count of candidates.
      const seq = ["15", "7", "3", "1"];
      let row = text(W / 2 - 330, 900, "candidates", { size: 26, fill: C.grey, anchor: "end", op: P(t, verdict[0], 0.5) });
      seq.forEach((n, k) => {
        const at = k === 0 ? verdict[0] : verdict[k - 1] + DISCARD_S;
        const x = W / 2 - 250 + k * 170;
        row += text(x, 900, n, { size: 34, weight: 600, fill: k === 3 ? C.green : C.white, op: P(t, at, 0.4) });
        if (k > 0) row += text(x - 85, 900, "→", { size: 30, fill: C.dim, op: P(t, at, 0.4) });
      });
      s += group(row, {});
      return s;
    },
  });
})();
