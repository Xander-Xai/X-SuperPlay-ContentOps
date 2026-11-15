import { Composition, registerRoot } from "remotion";
import type { FC } from "react";
import { AnnotationCard, AnnotationProps } from "./AnnotationCard";
import { RagFlow, RagProps } from "./RagFlow";

const annotationDefaults: AnnotationProps = {
  title: "对比",
  leftLabel: "之前",
  rightLabel: "之后",
  callout: "只保留与结论有关的画面",
  durationSeconds: 4,
  testBanner: "",
  palette: {
    bg: "#F4F2ED",
    surface: "#FFFFFF",
    ink: "#18232B",
    sub: "#5C6970",
    accent: "#087FA6",
    accent2: "#C4DCE3",
  },
};

const ragDefaults: RagProps = {
  title: "混合检索",
  nodes: ["Query", "Rewrite", "BM25", "Vector", "RRF", "Rerank", "LLM"],
  caption: "原理示意，不是系统输出",
  durationSeconds: 6,
  palette: {
    bg: "#E9EDEF",
    surface: "#F9FBFA",
    ink: "#202B31",
    sub: "#65747A",
    accent: "#157F8B",
    accent2: "#AABDC1",
  },
};

const frames = (seconds: number) => Math.round(Math.min(8, Math.max(2, seconds)) * 30);

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
    </>
  );
};

registerRoot(RemotionRoot);
