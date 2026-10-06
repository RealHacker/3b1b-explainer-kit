// Scene template. A scene is a pure function of scene-local time: draw(ctx) returns an SVG string.
// ctx: t (local seconds), T (scene length), n (beats), c(i)/d(i)/end(i) (beat start/duration/end),
//      e(i, frac) (time at a fraction of beat i). i is 1-based or a beat id from script.json.
// Build on-screen elements progressively and key each reveal to the beat that narrates it.
(function () {
  const { C, W, P, env, text, write, box, arrow, token, tex, group, clamp } = window.E;

  window.E.scene("s1_intro", {
    header: "Introduction",
    draw({ t, c, d, e, end, T }) {
      let s = "";
      // Beat 1: the title writes on, then a box draws in.
      s += write(W / 2, 330, "Replace me with the first idea", P(t, c(1), 1.4), { size: 56, weight: 600 });
      s += box(760, 450, 400, 150, { title: "concept", sub: "what it is", color: C.blue, draw: P(t, e(1, 0.4), 1.0) });

      // Beat 2: an arrow draws and a token (gold = the thing being tracked) travels along it.
      const path = [[1160, 525], [1500, 525]];
      s += arrow(path, { color: C.grey, p: P(t, c(2), 0.8) });
      s += token(path, P(t, c(2) + 0.6, d(2) * 0.5), C.gold, 12, env(t, c(2) + 0.5, T - 0.6));
      s += tex(W / 2, 780, "T(n) = O(\\log n)", { size: 52, op: P(t, e(2, 0.5), 0.6) });
      return s;
    },
  });
})();
