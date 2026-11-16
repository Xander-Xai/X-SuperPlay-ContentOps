import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Palette } from "./AnnotationCard";

/**
 * Account-A 3s conflict hook. DNA-gated motion: fade/slide only, no bounce,
 * flash, shake, sticker or flashy transition. All colours come from the
 * account DNA palette resolved by scripts/animation_render.py; this component
 * never hardcodes a brand colour.
 */
export type TitleCardProps = {
  conflict: string;
  stakes: string;
  kicker?: string;
  durationSeconds?: number;
  testBanner?: string;
  palette: Palette & { problem?: string };
};

export const TitleCard: React.FC<TitleCardProps> = ({
  conflict,
  stakes,
  kicker,
  testBanner,
  palette,
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
  const font = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        color: palette.ink,
        fontFamily: font,
        padding: 88,
        justifyContent: "center",
      }}
    >
      {kicker ? (
        <div
          style={{
            fontSize: 30,
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
          fontSize: 92,
          fontWeight: 800,
          lineHeight: 1.18,
          color: problem,
          opacity: conflictReveal,
          transform: `translateY(${(1 - conflictReveal) * 24}px)`,
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
          fontSize: 46,
          lineHeight: 1.5,
          // Body copy sits directly on the DNA dark base, so it uses the DNA
          // light "surface" token; "ink" is reserved for text on light cards.
          color: palette.surface || palette.ink,
          opacity: stakesReveal,
          transform: `translateY(${(1 - stakesReveal) * 18}px)`,
        }}
      >
        {stakes}
      </div>

      {testBanner ? (
        <div
          style={{
            position: "absolute",
            left: 88,
            right: 88,
            bottom: 120,
            fontSize: 28,
            color: palette.sub || palette.ink,
          }}
        >
          {testBanner}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
