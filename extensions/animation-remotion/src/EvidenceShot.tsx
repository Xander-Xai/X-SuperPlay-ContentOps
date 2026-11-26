import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Palette } from "./AnnotationCard";

/**
 * B-roll shot: a real still (source capture or generated illustration) is the
 * main picture, with a restrained camera move and a word-level callout.
 *
 * Method (b-roll-finder + video-shotcraft recipe cards):
 *   - the image carries the evidence or the concept; text is a short anchor,
 *     never a slide of prose
 *   - camera push / pan gives in-frame motion without a distracting mask
 *   - the callout lands on the spoken keyword (timed by the shot planner)
 *   - no blue/purple gradient, flash or bounce (account DNA forbidden effects)
 *
 * The caller supplies the image only from registered, rights-checked sources.
 * This component never fetches or approves media.
 */
export type EvidenceShotProps = {
  image: string;          // project-relative path staged into Remotion public/
  kicker?: string;
  callout: string;        // short keyword anchor tied to the spoken line
  note?: string;          // optional one-line evidence/attribution caption
  move?: "push" | "pan-left" | "pan-right" | "pull";
  emphasis?: "box" | "underline" | "none";
  durationSeconds?: number;
  palette: Palette & { problem?: string };
};

const CANVAS_W = 1080;
const CANVAS_H = 1920;
const FONT = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
const CLAMP = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const EvidenceShot: React.FC<EvidenceShotProps> = ({
  image, kicker, callout, note, move = "push", emphasis = "box",
  durationSeconds = 5, palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = Math.min(1, frame / Math.max(1, durationInFrames - 1));

  // Continuous camera move: a slow push in, a lateral glide, or a pull back.
  // This is the in-frame motion a real B-roll cut needs, not a page flip.
  const scale = move === "push" ? interpolate(t, [0, 1], [1.0, 1.16], CLAMP)
    : move === "pull" ? interpolate(t, [0, 1], [1.18, 1.0], CLAMP)
    : 1.12;
  const x = move === "pan-left" ? interpolate(t, [0, 1], [4, -4], CLAMP)
    : move === "pan-right" ? interpolate(t, [0, 1], [-4, 4], CLAMP) : 0;
  const y = move === "push" ? interpolate(t, [0, 1], [2, -2], CLAMP) : 0;

  const a = (from: number, to: number) => interpolate(
    frame, [Math.round(fps * from), Math.round(fps * to)], [0, 1], CLAMP);
  const calloutIn = a(0.15, 0.55);
  const noteIn = a(0.5, 0.9);

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, overflow: "hidden", fontFamily: FONT }}>
      {/* The registered still is the main picture. */}
      <AbsoluteFill style={{ transform: `scale(${scale}) translate(${x}%, ${y}%)`,
                             transformOrigin: "50% 45%" }}>
        <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </AbsoluteFill>

      {/* Bottom reading band: solid DNA surface, so text is readable over any image. */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 470,
                    background: `linear-gradient(to bottom, ${palette.bg}00, ${palette.bg}F2 32%)` }} />

      <div style={{ position: "absolute", left: 64, right: 64, bottom: 76 }}>
        {kicker ? (
          <div style={{ fontSize: 30, letterSpacing: 3, color: palette.accent,
                        fontWeight: 700, marginBottom: 18 }}>{kicker}</div>
        ) : null}
        <div style={{ display: "inline-block", padding: emphasis === "underline" ? "0 0 10px" : "14px 24px",
                      borderBottom: emphasis === "underline" ? `10px solid ${palette.accent}` : "none",
                      backgroundColor: emphasis === "box" ? palette.accent : "transparent",
                      borderRadius: emphasis === "box" ? 14 : 0,
                      transform: `translateY(${(1 - calloutIn) * 24}px)`, opacity: calloutIn }}>
          <span style={{ fontSize: 62, fontWeight: 900, lineHeight: 1.2,
                         color: emphasis === "box" ? palette.surface : palette.ink,
                         whiteSpace: "pre-wrap" }}>{callout}</span>
        </div>
        {note ? (
          <div style={{ marginTop: 20, fontSize: 27, color: palette.sub,
                        opacity: noteIn, whiteSpace: "pre-wrap" }}>{note}</div>
        ) : null}
      </div>

      {/* Frame edge: a thin DNA-coloured rule keeps the series visually consistent. */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 8,
                    backgroundColor: palette.accent, opacity: 0.85 }} />
    </AbsoluteFill>
  );
};
