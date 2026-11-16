import { Composition, registerRoot } from "remotion";
import type { FC } from "react";
import { AnnotationCard, AnnotationProps } from "./AnnotationCard";
import { RagFlow, RagProps } from "./RagFlow";
import { RecordingMark, RecordingMarkProps } from "./RecordingMark";
import { TitleCard, TitleCardProps } from "./TitleCard";

const annotationDefaults: AnnotationProps = {
  title: "对比",
  leftLabel: "之前",
  rightLabel: "之后",
  callout: "只保留与结论有关的画面",
  durationSeconds: 4,
  testBanner: "",
  palette: {
    bg: "#0F1117",
    surface: "#FFFFFF",
    ink: "#18232B",
    sub: "#5C6970",
    accent: "#38BDF8",
    accent2: "#38BDF8",
  },
};

const ragDefaults: RagProps = {
  title: "混合检索",
  nodes: ["Query", "Rewrite", "BM25", "Vector", "RRF", "Rerank", "LLM"],
  caption: "原理示意，不是系统输出",
  durationSeconds: 6,
  palette: {
    bg: "#0F1117",
    surface: "#F9FBFA",
    ink: "#202B31",
    sub: "#65747A",
    accent: "#38BDF8",
    accent2: "#38BDF8",
  },
};

const frames = (seconds: number) => Math.round(Math.min(8, Math.max(2, seconds)) * 30);

const markDefaults: RecordingMarkProps = {
  title: "证据区域",
  note: "只框已登记画面里与结论有关的部分",
  durationSeconds: 4,
  testBanner: "",
  video: "",
  sourceInSeconds: 0,
  box: { x: 0.18, y: 0.28, w: 0.64, h: 0.36 },
  palette: annotationDefaults.palette,
};

const titleDefaults: TitleCardProps = {
  conflict: "看起来跑通了，其实是假的",
  stakes: "前 3 秒先给出冲突，再谈怎么做",
  kicker: "AI 工具实测",
  durationSeconds: 3,
  testBanner: "",
  palette: annotationDefaults.palette,
  visualContract: {
    font: '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif',
    caption_size_px: 47,
    max_chars_per_line: 18,
    margin_v_px: 120,
    side_margin_ratio: 0.07,
    forbidden_effects: ["bounce", "flash", "shake", "sticker", "flashy_transition"],
  },
};

export const RemotionRoot: FC = () => {
  return (
    <>
      <Composition
        id="AnnotationCard"
        component={AnnotationCard}
        durationInFrames={120}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={annotationDefaults}
        calculateMetadata={({ props }) => ({
          durationInFrames: frames(props.durationSeconds || 4),
          fps: 30,
          width: 1080,
          height: 1920,
        })}
      />
      <Composition
        id="RagFlow"
        component={RagFlow}
        durationInFrames={180}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={ragDefaults}
        calculateMetadata={({ props }) => ({
          durationInFrames: frames(props.durationSeconds || 6),
          fps: 30,
          width: 1080,
          height: 1920,
        })}
      />
      <Composition
        id="RecordingMark"
        component={RecordingMark}
        durationInFrames={120}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={markDefaults}
        calculateMetadata={({ props }) => ({
          durationInFrames: frames(props.durationSeconds || 4),
          fps: 30,
          width: 1080,
          height: 1920,
        })}
      />
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={90}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={titleDefaults}
        calculateMetadata={({ props }) => ({
          durationInFrames: frames(props.durationSeconds || 3),
          fps: 30,
          width: 1080,
          height: 1920,
        })}
      />
    </>
  );
};

registerRoot(RemotionRoot);
