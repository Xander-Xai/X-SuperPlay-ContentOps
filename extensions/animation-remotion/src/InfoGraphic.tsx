import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Palette } from "./AnnotationCard";

/**
 * Information-first explainer visuals (the B-roll IS the main picture).
 *
 * Design rules followed, from the `video-shotcraft` recipe cards and the
 * account DNA (config/accounts/x-superplay-future-intelligence.json):
 *   - one idea per shot; each settled frame must stand on its own
 *   - graphic over prose: flow arrows, numbered cards, big numbers, comparison
 *   - accent appears on ONE current item at a time (a visual anchor)
 *   - no blue/purple gradient, no flash, no bounce, no glass (DNA forbidden_effects)
 *   - colour comes only from the DNA palette passed by animation_render.py
 *
 * Motion is staged element arrival + a restrained continuous drift: each item
 * lands on its own beat and then holds, so the frame is readable and the gate
 * still sees real in-frame change. No upstream source is vendored.
 */
export type InfoGraphicProps = {
  kind: "flow" | "checklist" | "metric" | "compare" | "quote";
  eyebrow?: string;
  title: string;
  items: string[];
  caption?: string;
  durationSeconds?: number;
  palette: Palette & { problem?: string };
};

const CANVAS_W = 1080;
const FONT = '"Noto Sans CJK SC", "Microsoft YaHei", sans-serif';

const clampOpts = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const InfoGraphic: React.FC<InfoGraphicProps> = ({
  kind, eyebrow, title, items, caption, durationSeconds = 6, palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const progress = Math.min(1, frame / Math.max(1, durationInFrames - 1));
  const appear = (at: number, len = 0.4) => interpolate(
    frame, [Math.round(fps * at), Math.round(fps * (at + len))], [0, 1], clampOpts);

  // The only ambient motion: a slow, small push. Elements themselves land on
  // beats; nothing flashes, bounces or shakes (DNA forbidden effects).
  const drift = interpolate(progress, [0, 1], [0, -18]);
  const scale = interpolate(progress, [0, 1], [1.0, 1.02]);

  const titleSize = kind === "quote" ? 84 : 66;
  const ink = palette.ink;
  const accent = palette.accent;
  const surface = palette.surface || "#FFFFFF";
  const sub = palette.sub || ink;

  const head = (
    <>
      {eyebrow ? (
        <div style={{ fontSize: 30, letterSpacing: 4, color: sub,
                      opacity: appear(0.05, 0.3), marginBottom: 28 }}>{eyebrow}</div>
      ) : null}
      <div style={{ fontSize: titleSize, fontWeight: 800, lineHeight: 1.2,
                    color: palette.problem || accent, opacity: appear(0.15, 0.4),
                    whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {title}
      </div>
      <div style={{ height: 9, width: 180, marginTop: 26, backgroundColor: accent,
                    transform: `scaleX(${appear(0.35, 0.4)})`, transformOrigin: "left" }} />
    </>
  );

  const flowBody = (
    <div style={{ marginTop: 60, display: "flex", flexDirection: "column", gap: 22 }}>
      {(items || []).map((item, i) => {
        const a = appear(0.5 + i * 0.45, 0.3);
        const active = a > 0.6 && (i === 0 || appear(0.5 + (i - 1) * 0.45, 0.3) > 0.9)
          && (i === items.length - 1 || appear(0.5 + (i + 1) * 0.45, 0.1) < 0.5);
        return (
          <div key={i}>
            <div style={{ display: "flex", alignItems: "center", gap: 24, opacity: a,
                          transform: `translateX(${(1 - a) * 36}px)` }}>
              <div style={{ flex: "0 0 auto", width: 76, height: 76, borderRadius: 38,
                            backgroundColor: active ? accent : surface,
                            border: `4px solid ${accent}`, color: active ? surface : accent,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 34, fontWeight: 800 }}>{i + 1}</div>
              <div style={{ fontSize: 42, fontWeight: 650, color: ink,
                            whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{item}</div>
            </div>
            {i < items.length - 1 ? (
              <div style={{ width: 5, height: 34, marginLeft: 35, backgroundColor: accent,
                            opacity: appear(0.6 + i * 0.45, 0.2) }} />
            ) : null}
          </div>
        );
      })}
    </div>
  );

  const checklistBody = (
    <div style={{ marginTop: 52, display: "flex", flexDirection: "column", gap: 20 }}>
      {(items || []).map((item, i) => {
        const a = appear(0.45 + i * 0.4, 0.3);
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 22,
                                backgroundColor: surface, borderRadius: 18,
                                borderLeft: `10px solid ${accent}`, padding: "22px 26px",
                                opacity: a, transform: `translateY(${(1 - a) * 24}px)` }}>
            <div style={{ flex: "0 0 auto", fontSize: 32, fontWeight: 800, color: accent }}>✓</div>
            <div style={{ fontSize: 38, fontWeight: 600, color: ink,
                          whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{item}</div>
          </div>
        );
      })}
    </div>
  );

  const metricBody = (
    <div style={{ marginTop: 70 }}>
      {(items || []).map((item, i) => {
        const a = appear(0.5 + i * 0.6, 0.35);
        return (
          <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 28, marginTop: 28,
                                opacity: a, transform: `translateY(${(1 - a) * 28}px)` }}>
            {(() => {
              const m = String(item).match(/^(\d+(?:[–-]\d+)?)(.*)$/);
              return m ? (
                <>
                  <div style={{ fontSize: 116, fontWeight: 900, color: accent,
                                fontVariantNumeric: "tabular-nums" }}>{m[1]}</div>
                  <div style={{ fontSize: 40, color: ink, fontWeight: 600 }}>{m[2]}</div>
                </>
              ) : (
                <div style={{ fontSize: 46, color: ink, fontWeight: 600 }}>{item}</div>
              );
            })()}
          </div>
        );
      })}
    </div>
  );

  const compareBody = (
    <div style={{ marginTop: 64, display: "flex", flexDirection: "column", gap: 26 }}>
      {(items || []).slice(0, 2).map((item, i) => {
        const a = appear(0.45 + i * 0.6, 0.35);
        const bad = i === 0;
        return (
          <div key={i} style={{ backgroundColor: surface, borderRadius: 20,
                                borderLeft: `12px solid ${bad ? (palette.problem || accent) : accent}`,
                                padding: "30px 32px", opacity: a,
                                transform: `translateX(${(1 - a) * (bad ? -30 : 30)}px)` }}>
            <div style={{ fontSize: 28, color: bad ? (palette.problem || accent) : accent,
                          fontWeight: 800, marginBottom: 14 }}>{bad ? "✕ 常见做法" : "✓ 建议做法"}</div>
            <div style={{ fontSize: 40, color: ink, fontWeight: 600,
                          whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{item}</div>
          </div>
        );
      })}
    </div>
  );

  const quoteBody = (
    <div style={{ marginTop: 80 }}>
      {(items || []).map((item, i) => {
        const a = appear(0.55 + i * 0.9, 0.45);
        return (
          <div key={i} style={{ fontSize: 54, fontWeight: 700, color: ink, lineHeight: 1.5,
                                marginTop: i ? 60 : 0, opacity: a,
                                transform: `translateY(${(1 - a) * 30}px)`,
                                whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {item}
          </div>
        );
      })}
    </div>
  );

  const body = kind === "flow" ? flowBody : kind === "checklist" ? checklistBody
    : kind === "metric" ? metricBody : kind === "compare" ? compareBody : quoteBody;

  return (
    <AbsoluteFill style={{ backgroundColor: palette.bg, overflow: "hidden", fontFamily: FONT }}>
      <AbsoluteFill style={{ transform: `scale(${scale}) translateY(${drift}px)`,
                             transformOrigin: "50% 42%", padding: "110px 80px 300px",
                             justifyContent: "center" }}>
        {head}
        {body}
        {caption ? (
          <div style={{ marginTop: 48, fontSize: 28, color: sub,
                        opacity: appear(0.8, 0.4) }}>{caption}</div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
