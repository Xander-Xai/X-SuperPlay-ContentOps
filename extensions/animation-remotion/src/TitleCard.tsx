import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Palette } from "./AnnotationCard";

/**
 * Account hook card (3s). DNA-gated: fade/slide only, no bounce, flash, shake,
 * sticker or flashy transition. Every colour, font and safe-zone value is
 * resolved from the account DNA by scripts/animation_render.py and passed in —
 * this component owns no brand token and cannot widen a safe margin.
 */
export type VisualContract = {
  font?: string;
  caption_size_px?: number;
  max_chars_per_line?: number;
  margin_v_px?: number;
  side_margin_ratio?: number;
  forbidden_effects?: string[];
};

export type TitleCardProps = {
  conflict: string;
  stakes: string;
  kicker?: string;
  durationSeconds?: number;
  testBanner?: string;
  palette: Palette & { problem?: string };
  visualContract?: VisualContract;
};

const CANVAS_W = 1080;

export const TitleCard: React.FC<TitleCardProps> = ({
  conflict,
  stakes,
  kicker,
  testBanner,
  palette,
  visualContract = {},
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = (from: number, to: number) =>
    interpolate(frame, [Math.round(fps * from), Math.round(fps * to)], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const kickerOpacity = fade(0.05, 0.35);
  const conflictReveal = fade(0.2, 0.7);
  const ruleWidth = fade(0.5, 1.0);
  const stakesReveal = fade(1.0, 1.6);
  const problem = palette.problem || palette.accent;

  // Layout comes from the DNA contract. Defaults are the strictest common
  // values and apply only when a caller omits the contract; a real render
  // always supplies it from config/accounts/<slug>.json.
  const font = visualContract.font || '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
  const maxChars = visualContract.max_chars_per_line || 18;
  const marginV = visualContract.margin_v_px ?? 120;
  const sideMargin = Math.max(
    Math.round(CANVAS_W * (visualContract.side_margin_ratio || 0.07)),
    24,
  );
  const captionSize = visualContract.caption_size_px || 47;
  // Display size shrinks for long hooks so text wraps inside the safe width
  // instead of overflowing the frame. It is derived from the DNA caption size
  // and never hardcodes a brand constant.
  const conflictSize = Math.round(
    Math.min(captionSize * 1.8, Math.max(captionSize, (CANVAS_W - 2 * sideMargin) / Math.max(6, maxChars) * 1.7)),
  );
  const stakesSize = captionSize;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        color: palette.ink,
        fontFamily: font,
        paddingLeft: sideMargin,
        paddingRight: sideMargin,
        paddingTop: marginV,
        paddingBottom: marginV,
        justifyContent: "center",
        overflow: "hidden",
      }}
    >
      {kicker ? (
        <div
          style={{
            fontSize: Math.round(captionSize * 0.64),
            letterSpacing: 2,
            color: palette.sub || palette.ink,
            opacity: kickerOpacity,
            marginBottom: 48,
          }}
        >
          {kicker}
        </div>
      ) : null}

      <div
        style={{
          fontSize: conflictSize,
          fontWeight: 700,
          lineHeight: 1.18,
          color: problem,
          opacity: conflictReveal,
          transform: `translateY(${(1 - conflictReveal) * 24}px)`,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          overflowWrap: "anywhere",
          maxWidth: "100%",
        }}
      >
        {conflict}
      </div>

      <div
        style={{
          marginTop: 44,
          height: 12,
          width: `${Math.round(ruleWidth * 42)}%`,
          backgroundColor: palette.accent,
        }}
      />

      <div
        style={{
          marginTop: 56,
          fontSize: stakesSize,
          lineHeight: 1.5,
          // Body copy sits on the DNA dark base, so it uses the DNA light
          // "surface" token; "ink" is reserved for text on light cards.
          color: palette.surface || palette.ink,
          opacity: stakesReveal,
          transform: `translateY(${(1 - stakesReveal) * 18}px)`,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          overflowWrap: "anywhere",
          maxWidth: "100%",
        }}
      >
        {stakes}
      </div>

      {testBanner ? (
        <div
          style={{
            position: "absolute",
            left: sideMargin,
            right: sideMargin,
            bottom: Math.min(marginV, 120),
            fontSize: Math.round(captionSize * 0.6),
            color: palette.sub || palette.ink,
          }}
        >
          {testBanner}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
