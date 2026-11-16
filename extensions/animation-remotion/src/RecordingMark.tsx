import { AbsoluteFill, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Palette } from "./AnnotationCard";

export type Box = { x: number; y: number; w: number; h: number };

export type RecordingMarkProps = {
  title: string;
  note: string;
  durationSeconds?: number;
  testBanner?: string;
  video: string;
  sourceInSeconds: number;
  box: Box;
  palette: Palette;
};

export const RecordingMark: React.FC<RecordingMarkProps> = ({
  title,
  note,
  testBanner,
  video,
  sourceInSeconds,
  box,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = interpolate(frame % Math.round(fps * 1.2), [0, fps * 0.6, fps * 1.2], [0.45, 1, 0.45], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const font = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, color: palette.ink, fontFamily: font }}>
      <OffthreadVideo
        src={staticFile(video)}
        trimBefore={Math.max(0, Math.round(sourceInSeconds * fps))}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
      <div
        style={{
          position: "absolute",
          left: `${box.x * 100}%`,
          top: `${box.y * 100}%`,
          width: `${box.w * 100}%`,
          height: `${box.h * 100}%`,
          border: `6px solid ${palette.accent}`,
          boxShadow: `0 0 0 8px ${palette.accent}33`,
          opacity: pulse,
        }}
      />
      <div style={{ position: "absolute", left: 48, right: 48, top: 48, fontSize: 42, fontWeight: 700, color: palette.surface || "#FFFFFF", textShadow: "0 2px 8px #000" }}>
        {title}
      </div>
      <div style={{ position: "absolute", left: 48, right: 48, bottom: testBanner ? 120 : 48, fontSize: 32, lineHeight: 1.4, color: palette.surface || "#FFFFFF", textShadow: "0 2px 8px #000" }}>
        {note}
      </div>
      {testBanner ? (
        <div style={{ position: "absolute", left: 48, right: 48, bottom: 48, fontSize: 26, color: palette.accent }}>
          {testBanner}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
