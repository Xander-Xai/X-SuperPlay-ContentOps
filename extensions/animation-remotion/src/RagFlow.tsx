import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Palette } from "./AnnotationCard";

export type RagProps = {
  title: string;
  nodes: string[];
  caption: string;
  durationSeconds?: number;
  palette: Palette;
};

export const RagFlow: React.FC<RagProps> = ({ title, nodes, caption, palette }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const font = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
  const step = Math.max(8, Math.round((fps * 0.7)));
  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.bg,
        color: palette.ink,
        fontFamily: font,
        padding: "80px 72px",
      }}
    >
      <div style={{ fontSize: 56, fontWeight: 700 }}>{title}</div>
      <div style={{ marginTop: 12, fontSize: 28, color: palette.sub || palette.ink }}>{caption}</div>
      <div style={{ marginTop: 48, display: "flex", flexDirection: "column", gap: 18 }}>
        {nodes.map((node, index) => {
          const start = index * step;
          const opacity = interpolate(frame, [start, start + Math.round(fps * 0.25)], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const line = interpolate(frame, [start, start + step], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div key={`${index}-${node}`} style={{ opacity }}>
              <div
                style={{
                  backgroundColor: palette.surface || "#FFFFFF",
                  borderLeft: `8px solid ${palette.accent}`,
                  borderRadius: 14,
                  padding: "22px 28px",
                  fontSize: 36,
                  fontWeight: 650,
                }}
              >
                {node}
              </div>
              {index < nodes.length - 1 ? (
                <div
                  style={{
                    width: 4,
                    height: Math.round(18 * line),
                    marginLeft: 28,
                    backgroundColor: palette.accent2 || palette.accent,
                  }}
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
