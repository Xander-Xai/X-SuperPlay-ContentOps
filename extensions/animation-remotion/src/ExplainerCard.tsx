import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Palette } from "./AnnotationCard";

/**
 * Full-bleed explainer card: account-DNA typography on a clean canvas.
 *
 * Motion follows the `video-shotcraft` skill's information-first rule -- the
 * frame settles so the viewer can read; a slow continuous camera drift and
 * staggered item reveals keep it alive without flash, bounce or a focus mask.
 * The `aideos` derived-camera idea is the other influence (motion is a function
 * of time, not a batch of pulses). No upstream source is vendored.
 *
 * Colour and type arrive from the account DNA via animation_render.py; this
 * component owns no brand value, asserts no claim and grants no publication.
 */
export type ExplainerCardProps = {
  kicker?: string;
  title: string;
  items: string[];
  footnote?: string;
  durationSeconds?: number;
  palette: Palette & { problem?: string };
  visualContract?: {
    font?: string;
    caption_size_px?: number;
    max_chars_per_line?: number;
    margin_v_px?: number;
    side_margin_ratio?: number;
    forbidden_effects?: string[];
  };
};

const CANVAS_W = 1080;

export const ExplainerCard: React.FC<ExplainerCardProps> = ({
  kicker, title, items, footnote, durationSeconds = 5, palette, visualContract = {},
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const progress = Math.min(1, frame / Math.max(1, durationInFrames - 1));

  const font = visualContract.font || '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
  const marginV = visualContract.margin_v_px ?? 110;
  const sideMargin = Math.max(Math.round(CANVAS_W * (visualContract.side_margin_ratio || 0.075)), 24);
  const captionSize = visualContract.caption_size_px || 46;
  const titleSize = Math.round(
    Math.min(captionSize * 1.7,
      Math.max(captionSize, (CANVAS_W - 2 * sideMargin) / Math.max(5, visualContract.max_chars_per_line || 12) * 1.6)),
  );

  const zoom = interpolate(progress, [0, 1], [1.0, 1.05]);
  const driftY = interpolate(progress, [0, 1], [0, -24]);
  const fade = (from: number, to: number) => interpolate(
    frame, [Math.round(fps * from), Math.round(fps * to)], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const revealAt = (index: number) => 0.3 + index * 0.72;
  const reveal = (index: number) => fade(revealAt(index), revealAt(index) + 0.35);

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, overflow: "hidden", fontFamily: font }}>
      <AbsoluteFill style={{
        transform: `scale(${zoom}) translateY(${driftY}px)`, transformOrigin: "50% 46%",
        paddingLeft: sideMargin, paddingRight: sideMargin, paddingTop: marginV,
        paddingBottom: marginV + 200, justifyContent: "center", color: palette.ink,
      }}>
        {kicker ? (
          <div style={{ fontSize: Math.round(captionSize * 0.6), letterSpacing: 3,
                        color: palette.sub || palette.surface, opacity: fade(0.1, 0.45),
                        marginBottom: 38 }}>{kicker}</div>
        ) : null}
        <div style={{ fontSize: titleSize, fontWeight: 800, lineHeight: 1.22,
                      color: palette.problem || palette.accent, maxWidth: "100%",
                      whiteSpace: "pre-wrap", wordBreak: "break-word", overflowWrap: "anywhere" }}>
          {title}
        </div>
        <div style={{ height: 10, width: "34%", marginTop: 30, backgroundColor: palette.accent }} />
        <div style={{ marginTop: 34 }}>
          {(items || []).map((item, index) => {
            const a = reveal(index);
            return (
              <div key={index} style={{ display: "flex", alignItems: "flex-start",
                                        gap: Math.round(captionSize * 0.5), marginTop: 24,
                                        opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
                <div style={{ flex: "0 0 auto", minWidth: Math.round(captionSize * 1.5),
                              fontSize: Math.round(captionSize * 0.72), fontWeight: 700,
                              color: palette.accent }}>
                  {String(index + 1).padStart(2, "0")}
                </div>
                <div style={{ fontSize: captionSize, lineHeight: 1.4,
                              color: palette.surface || palette.ink, maxWidth: "86%",
                              whiteSpace: "pre-wrap", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                  {item}
                </div>
              </div>
            );
          })}
        </div>
        {footnote ? (
          <div style={{ marginTop: 40, fontSize: Math.round(captionSize * 0.62),
                        color: palette.sub || palette.surface, opacity: reveal(items.length) }}>
            {footnote}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
