import {Line, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {all, createRef, createRefArray, waitFor, type ThreadGenerator} from '@motion-canvas/core';
import {HOLD, TWEEN, readSpec, type StateStep} from '../lib/spec';

/**
 * agent_state_machine — states, conditional branches and a failure fallback.
 *
 * The failure marker (brand.palette.problem) is shown only while a failure
 * step is active; the following resolution step restores the accent colour.
 * No bounce/flash/sticker/flashy transition. Every colour comes from the
 * account's brand.palette, injected by the adapter.
 */
export default makeScene2D(function* (view) {
  const spec = readSpec();
  const palette = spec.palette;
  const states = spec.states ?? [];
  const rawSteps: StateStep[] = (spec.state_steps ?? []).slice();
  if (states.length === 0 || rawSteps.length === 0) {
    throw new Error('SPEC_STATE_STEPS_REQUIRED');
  }
  view.fill(palette.bg);

  const title = createRef<Txt>();
  const caption = createRef<Txt>();
  const boxes = createRefArray<Rect>();
  const labels = createRefArray<Txt>();
  const links = createRefArray<Line>();
  const edgeLabels = createRefArray<Txt>();

  view.add(
    <Txt
      ref={title}
      text={spec.title}
      fill={palette.surface}
      fontSize={52}
      fontWeight={700}
      x={0}
      y={-800}
      opacity={0}
    />,
  );

  const top = -570;
  const bottom = 300;
  const gap = states.length > 1 ? (bottom - top) / (states.length - 1) : 0;
  const stateY = (index: number) =>
    states.length === 1 ? (top + bottom) / 2 : top + gap * index;

  view.add(
    states.map((state, index) => (
      <Rect
        ref={boxes}
        width={720}
        height={104}
        radius={14}
        fill={palette.surface}
        stroke={state.kind === 'error' ? palette.problem : palette.accent}
        lineWidth={2}
        x={0}
        y={stateY(index)}
        opacity={0.45}
      >
        <Txt ref={labels} text={state.label} fill={palette.ink} fontSize={38} />
      </Rect>
    )),
  );

  const transitions = spec.transitions ?? [];
  view.add(
    transitions.map(transition => {
      const from = states.findIndex(state => state.id === transition.from);
      const to = states.findIndex(state => state.id === transition.to);
      const x = from % 2 === 0 ? 430 : -430;
      return (
        <>
          <Line
            ref={links}
            points={[
              [x, stateY(Math.max(from, 0))],
              [x, stateY(Math.max(to, 0))],
            ]}
            stroke={transition.on_failure ? palette.problem : palette.accent}
            lineWidth={3}
            endArrow
            arrowSize={12}
            end={0}
          />
          <Txt
            ref={edgeLabels}
            text={transition.label}
            fill={palette.sub}
            fontSize={26}
            x={x + (x > 0 ? 120 : -120)}
            y={(stateY(Math.max(from, 0)) + stateY(Math.max(to, 0))) / 2}
            opacity={0}
          />
        </>
      );
    }),
  );

  view.add(
    <Txt ref={caption} text="" fill={palette.surface} fontSize={36} x={0} y={830} />,
  );

  const hold = Math.max(0.12, spec.duration_s / rawSteps.length - TWEEN);
  yield* title().opacity(1, TWEEN);
  yield* waitFor(hold);

  for (const step of rawSteps) {
    const activeIndex = states.findIndex(state => state.id === step.active_state);
    const changes: ThreadGenerator[] = states.map((_state, index) =>
      boxes[index].opacity(index === activeIndex ? 1 : 0.35, TWEEN));
    transitions.forEach((transition, index) => {
      const isActive =
        step.active_transition?.from === transition.from &&
        step.active_transition?.to === transition.to;
      changes.push(links[index].end(isActive ? 1 : 0, TWEEN));
      changes.push(
        edgeLabels[index].opacity(
          isActive ? 1 : 0.25,
          TWEEN,
        ),
      );
      // Failure colour is temporary by DNA: it may not survive the resolution.
      const failure = step.failure === true && isActive;
      changes.push(
        links[index].stroke(
          failure
            ? palette.problem
            : transition.on_failure
              ? palette.sub
              : palette.accent,
          TWEEN,
        ),
      );
    });
    yield* all(...changes);
    yield* caption().opacity(0, 0.12);
    caption().text(step.caption);
    yield* caption().opacity(1, 0.12);
    yield* waitFor(hold);
  }
});
