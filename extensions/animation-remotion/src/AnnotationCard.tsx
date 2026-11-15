import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export type Palette = {
  bg: string;
  surface?: string;
  ink: string;
  sub?: string;
  accent: string;
  accent2?: string;
};

export type AnnotationProps = {
  title: string;
  leftLabel: string;
  rightLabel: string;
  callout: string;
  durationSeconds?: number;
  testBanner?: string;
  palette: Palette;
};

export const AnnotationCard: React.FC<AnnotationProps> = ({
  title,
  leftLabel,
  rightLabel,
  callout,
  testBanner,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const enter = interpolate(frame, [0, Math.round(fps * 0.4)], [0, 1], {
    extrapolateRight: "clamp",
  });
  const bar = interpolate(frame, [Math.round(fps * 0.3), Math.round(fps * 1.1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const calloutOpacity = interpolate(
    frame,
    [Math.round(fps * 1.2), Math.round(fps * 1.8)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const font = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        color: palette.ink,
        fontFamily: font,
        padding: 72,
      }}
    >
      <div style={{ fontSize: 64, fontWeight: 700, opacity: enter, lineHeight: 1.2 }}>{title}</div>
      <div
        style={{
          marginTop: 28,
          height: 8,
          width: `${Math.round(bar * 100)}%`,
          backgroundColor: palette.accent,
        }}
      />
      <div style={{ display: "flex", gap: 28, marginTop: 64 }}>
        {[leftLabel, rightLabel].map((label, index) => (
          <div
            key={label}
            style={{
              flex: 1,
              backgroundColor: palette.surface || "#FFFFFF",
              borderRadius: 20,
              padding: 36,
              minHeight: 420,
              transform: `translateY(${(1 - enter) * (40 + index * 16)}px)`,
              opacity: enter,
              borderTop: `8px solid ${index === 1 ? palette.accent : palette.accent2 || palette.sub || palette.ink}`,
            }}
          >
            <div style={{ fontSize: 28, color: palette.sub || palette.ink, marginBottom: 24 }}>
              {index === 0 ? "A" : "B"}
            </div>
            <div style={{ fontSize: 44, fontWeight: 650, lineHeight: 1.3 }}>{label}</div>
          </div>
        ))}
      </div>
      <div
        style={{
          marginTop: 56,
          fontSize: 36,
          lineHeight: 1.45,
          opacity: calloutOpacity,
          color: palette.ink,
        }}
      >
        {callout}
      </div>
      {testBanner ? (
        <div
          style={{
            position: "absolute",
            left: 72,
            right: 72,
            bottom: 72,
            fontSize: 28,
            color: palette.sub || palette.ink,
          }}
        >
          {testBanner}
        </div>
      ) : null}
      <div style={{ position: "absolute", right: 72, top: 72, fontSize: 22, color: palette.sub || palette.ink }}>
        {Math.min(durationInFrames, frame + 1)}/{durationInFrames}
      </div>
    </AbsoluteFill>
  );
};
