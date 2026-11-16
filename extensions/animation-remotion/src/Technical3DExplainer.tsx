import React from "react";
import { ThreeCanvas } from "@remotion/three";
import { useFrame } from "@react-three/fiber";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

const FONT = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';

export type Technical3DPalette = {
  bg: string;
  ink: string;
  accent: string;
  surface?: string;
  sub?: string;
  accent2?: string;
  problem?: string;
};

export type Technical3DNode = {
  label: string;
  position: [number, number, number];
};

export type Technical3DExplainerProps = {
  title: string;
  nodes: Technical3DNode[];
  highlightIndex: number;
  duration_s: number;
  palette: Technical3DPalette;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Frame-driven camera orbit. No useFrame delta / wall-clock input is used. */
const CameraRig: React.FC<{ frame: number; totalFrames: number }> = ({ frame, totalFrames }) => {
  useFrame(({ camera }) => {
    const t = interpolate(frame, [0, Math.max(1, totalFrames - 1)], [0, 1], clamp);
    const angle = -0.35 + t * 0.7;
    const radius = 10.5;
    camera.position.set(Math.sin(angle) * radius, 1.6, Math.cos(angle) * radius);
    camera.lookAt(0, 0, 0);
  });
  return null;
};

const SolidNode: React.FC<{
  node: Technical3DNode;
  index: number;
  highlightIndex: number;
  frame: number;
  palette: Technical3DPalette;
}> = ({ node, index, highlightIndex, frame, palette }) => {
  const appearAt = 3 + index * 8;
  const opacity = interpolate(frame, [appearAt, appearAt + 12], [0, 1], clamp);
  const rise = interpolate(frame, [appearAt, appearAt + 12], [-0.5, 0], clamp);
  const highlighted = index === highlightIndex;
  const highlightAt = 3 + highlightIndex * 8 + 12;
  const scale = highlighted
    ? interpolate(frame, [highlightAt, highlightAt + 10], [1, 1.22], clamp)
    : 1;

  const [x, y, z] = node.position;
  return (
    <mesh position={[x, y + rise, z]} scale={scale}>
      <boxGeometry args={[1.0, 0.62, 0.3]} />
      <meshStandardMaterial
        color={highlighted ? palette.accent : palette.surface}
        emissive={highlighted ? palette.accent : palette.bg}
        emissiveIntensity={highlighted ? 0.28 : 0.04}
        metalness={0.12}
        roughness={0.62}
        transparent
        opacity={opacity}
      />
    </mesh>
  );
};

/**
 * Parameterized 3D technical explainer. Every pixel is derived from props and
 * the current frame only: frame-driven orbit, sequential fade/position entry,
 * one accent-highlighted node. All colours come from props.palette; text is
 * plain HTML so no font asset is loaded at render time.
 */
export const Technical3DExplainer: React.FC<Technical3DExplainerProps> = ({
  title,
  nodes,
  highlightIndex,
  duration_s,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const totalFrames =
    durationInFrames || Math.round(Math.min(8, Math.max(2, duration_s)) * fps);
  const active = highlightIndex >= 0 && highlightIndex < nodes.length ? highlightIndex : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, fontFamily: FONT }}>
      <ThreeCanvas
        width={1080}
        height={1920}
        camera={{ fov: 42, near: 0.1, far: 100, position: [0, 1.6, 10.5] }}
        style={{ position: "absolute", inset: 0 }}
      >
        <color attach="background" args={[palette.bg]} />
        <ambientLight intensity={0.65} />
        <directionalLight position={[4, 6, 6]} intensity={1.1} color={palette.surface} />
        <pointLight position={[-5, -2, 4]} intensity={0.7} color={palette.accent} />
        <CameraRig frame={frame} totalFrames={totalFrames} />
        {nodes.map((node, index) => (
          <SolidNode
            key={`${index}-${node.label}`}
            node={node}
            index={index}
            highlightIndex={active}
            frame={frame}
            palette={palette}
          />
        ))}
      </ThreeCanvas>

      <div style={{ position: "absolute", left: 76, top: 150, right: 76 }}>
        <div style={{ fontSize: 30, letterSpacing: 3, color: palette.accent }}>3D / STRUCTURE</div>
        <div style={{ fontSize: 58, fontWeight: 600, lineHeight: 1.2, marginTop: 18, color: palette.surface }}>
          {title}
        </div>
        <div style={{ width: 96, height: 6, backgroundColor: palette.accent, marginTop: 24 }} />
      </div>

      <div style={{ position: "absolute", left: 76, right: 76, bottom: 250 }}>
        {nodes.map((node, index) => {
          const nodeOpacity = interpolate(
            frame,
            [3 + index * 8, 3 + index * 8 + 12],
            [0, 1],
            clamp,
          );
          const isActive = index === active;
          return (
            <div
              key={`${index}-${node.label}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 18,
                marginTop: 16,
                opacity: nodeOpacity,
                color: isActive ? palette.accent : palette.surface,
              }}
            >
              <div
                style={{
                  width: 12,
                  height: 12,
                  backgroundColor: isActive ? palette.accent : palette.sub,
                }}
              />
              <div style={{ fontSize: 34 }}>{node.label}</div>
              {isActive ? (
                <div style={{ fontSize: 24, color: palette.sub, marginLeft: "auto" }}>FOCUS</div>
              ) : null}
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          bottom: 120,
          color: palette.sub,
          fontSize: 26,
        }}
      >
        3D 结构示意，非真实芯片/部署/测量结果
      </div>
    </AbsoluteFill>
  );
};

export default Technical3DExplainer;
