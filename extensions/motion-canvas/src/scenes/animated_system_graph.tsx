import {Circle, Line, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {all, createRef, createRefArray, waitFor} from '@motion-canvas/core';
import {HOLD, TWEEN, readSpec, type GraphStep} from '../lib/spec';

/**
 * animated_system_graph — components appear, connect, then get explained,
 * one measured step at a time.
 *
 * DNA contract (config/accounts/x-superplay-future-intelligence.json):
 * only module_fade_in / single_direction_arrow_flow / node_highlight_switch
 * are allowed. Bounce, flash, shake, sticker and flashy transitions are never
 * used. Every colour is read from the injected brand.palette.
 */
export default makeScene2D(function* (view) {
  const spec = readSpec();
  const palette = spec.palette;
  const nodes = spec.nodes ?? [];
  const rawSteps: GraphStep[] = (spec.steps ?? []).slice();
  if (nodes.length === 0 || rawSteps.length === 0) {
    throw new Error('SPEC_STEPS_REQUIRED');
  }
  view.fill(palette.bg);

  const title = createRef<Txt>();
  const caption = createRef<Txt>();
  const cards = createRefArray<Rect>();
  const labels = createRefArray<Txt>();
  const dots = createRefArray<Circle>();
  const links = createRefArray<Line>();

  view.add(
    <Txt
      ref={title}
      text={spec.title}
      fill={palette.surface}
      fontSize={52}
      fontWeight={700}
      x={0}
      y={-790}
      opacity={0}
    />,
  );

  const top = -560;
  const bottom = 330;
  const gap = nodes.length > 1 ? (bottom - top) / (nodes.length - 1) : 0;
  const nodeY = (index: number) => (nodes.length === 1 ? (top + bottom) / 2 : top + gap * index);

  view.add(
    nodes.map((node, index) => (
      <Rect
        ref={cards}
        width={760}
        height={112}
        radius={14}
        fill={palette.surface}
        stroke={palette.accent}
        lineWidth={2}
        x={0}
        y={nodeY(index)}
        opacity={0}
      >
        <Circle ref={dots} size={18} fill={palette.accent} x={-318} />
        <Txt
          ref={labels}
          text={node.label}
          fill={palette.ink}
          fontSize={40}
          x={-20}
        />
      </Rect>
    )),
  );

  const edges = spec.edges ?? nodes.slice(1).map((node, index) => ({
    from: nodes[index].id,
    to: node.id,
    label: '',
  }));
  const edgeY = (fromId: string, toId: string): [number, number, number, number] => {
    const from = nodes.findIndex(node => node.id === fromId);
    const to = nodes.findIndex(node => node.id === toId);
    return [0, nodeY(Math.max(from, 0)) + 56, 0, nodeY(Math.max(to, 0)) - 56];
  };
  view.add(
    edges.map(edge => {
      const [x1, y1, x2, y2] = edgeY(edge.from, edge.to);
      return (
        <Line
          ref={links}
          points={[[x1, y1], [x2, y2]]}
          stroke={palette.accent}
          lineWidth={3}
          endArrow
          arrowSize={12}
          end={0}
        />
      );
    }),
  );

  view.add(
    <Txt
      ref={caption}
      text=""
      fill={palette.surface}
      fontSize={38}
      x={0}
      y={820}
      opacity={1}
    />,
  );

  const hold = Math.max(0.12, spec.duration_s / rawSteps.length - TWEEN);
  yield* title().opacity(1, TWEEN);
  yield* waitFor(hold);

  for (const step of rawSteps) {
    const shown = new Set(step.show_nodes ?? nodes.map(node => node.id));
    const shownEdges = new Set(
      (step.show_edges ?? edges.map(edge => ({from: edge.from, to: edge.to})))
        .map(edge => `${edge.from}->${edge.to}`),
    );
    const reveal = [
      ...nodes.map((node, index) =>
        cards[index].opacity(shown.has(node.id) ? 1 : 0.35, TWEEN)),
      ...edges.map((edge, index) =>
        links[index].end(
          shownEdges.has(`${edge.from}->${edge.to}`) ? 1 : 0,
          TWEEN,
        )),
    ];
    yield* all(...reveal);
    yield* caption().opacity(0, 0.12);
    caption().text(step.caption);
    yield* caption().opacity(1, 0.12);
    yield* waitFor(hold);
  }
});
