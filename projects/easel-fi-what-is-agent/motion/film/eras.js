// Visuals come from the per-era frame sequence. The engine's scene loader still
// demands a registered drawer for every era without one, so each entry declares
// an explicit no-op: the clip layer is the drawing.
const CLIP_ONLY = () => {};

window.FILM_SIZE = [1080, 1920];
window.PUNCH = 0;
window.ERAS = [
  { id: "p01", dur: 2.37, draw: CLIP_ONLY, clip: { dir: "/project/work/film-frames/p01", fps: 30, n: 71 } },
  { id: "p02", dur: 2.904, draw: CLIP_ONLY, transition: { type: "push", dur: 0.30 }, clip: { dir: "/project/work/film-frames/p02", fps: 30, n: 87 } },
  { id: "p03", dur: 3.009, draw: CLIP_ONLY, transition: { type: "matchCut", dur: 0.24 }, clip: { dir: "/project/work/film-frames/p03", fps: 30, n: 90 } },
  { id: "p04", dur: 2.057, draw: CLIP_ONLY, transition: { type: "blurPush", dur: 0.24 }, clip: { dir: "/project/work/film-frames/p04", fps: 30, n: 62 } },
  { id: "p05", dur: 2.544, draw: CLIP_ONLY, transition: { type: "push", dur: 0.26 }, clip: { dir: "/project/work/film-frames/p05", fps: 30, n: 76 } },
  { id: "p06", dur: 3.078, draw: CLIP_ONLY, transition: { type: "matchCut", dur: 0.28 }, clip: { dir: "/project/work/film-frames/p06", fps: 30, n: 92 } },
  { id: "p07", dur: 3.194, draw: CLIP_ONLY, transition: { type: "push", dur: 0.28 }, clip: { dir: "/project/work/film-frames/p07", fps: 30, n: 96 } },
  { id: "p08", dur: 3.229, draw: CLIP_ONLY, transition: { type: "fadeShift", dur: 0.30 }, clip: { dir: "/project/work/film-frames/p08", fps: 30, n: 97 } },
  { id: "insert-video", dur: 2.5, draw: CLIP_ONLY, transition: { type: "fadeShift", dur: 0.24 }, clip: { dir: "/project/work/film-frames/insert-video", fps: 30, n: 75 } },
  { id: "p09", dur: 2.939, draw: CLIP_ONLY, transition: { type: "blurPush", dur: 0.26 }, clip: { dir: "/project/work/film-frames/p09", fps: 30, n: 88 } },
  { id: "p10", dur: 2.196, draw: CLIP_ONLY, transition: { type: "matchCut", dur: 0.24 }, clip: { dir: "/project/work/film-frames/p10", fps: 30, n: 66 } },
  { id: "p11", dur: 3.264, draw: CLIP_ONLY, transition: { type: "push", dur: 0.28 }, clip: { dir: "/project/work/film-frames/p11", fps: 30, n: 98 } },
  { id: "p12", dur: 3.009, draw: CLIP_ONLY, transition: { type: "fadeShift", dur: 0.28 }, clip: { dir: "/project/work/film-frames/p12", fps: 30, n: 90 } },
];
