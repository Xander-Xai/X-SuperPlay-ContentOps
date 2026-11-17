/** The runtime clip spec injected by the adapter through Vite `define`.
 *  Every colour is DNA-owned (resolved by animation_backend.palette_from_dna
 *  and injected into `palette`); a scene never hardcodes a brand colour.
 */
export interface MotionPalette {
  bg: string;
  ink: string;
  accent: string;
  sub: string;
  surface: string;
  problem: string;
  accent2?: string;
}

export interface GraphNode {
  id: string;
  label: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface GraphStep {
  caption: string;
  show_nodes?: string[];
  show_edges?: Array<{from: string; to: string}>;
}

export interface StateNode {
  id: string;
  label: string;
  kind?: 'normal' | 'error' | 'terminal';
}

export interface StateTransition {
  from: string;
  to: string;
  label: string;
  on_failure?: boolean;
}

export interface StateStep {
  caption: string;
  active_state: string;
  active_transition?: {from: string; to: string};
  failure?: boolean;
}

export interface MotionCanvasSpec {
  template: 'animated_system_graph' | 'agent_state_machine';
  duration_s: number;
  width: number;
  height: number;
  fps: number;
  title: string;
  caption?: string;
  palette: MotionPalette;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  steps?: GraphStep[];
  states?: StateNode[];
  transitions?: StateTransition[];
  state_steps?: StateStep[];
}

export function readSpec(): MotionCanvasSpec {
  const spec = __MOTION_CANVAS_SPEC__ as MotionCanvasSpec;
  if (!spec || !spec.palette || !spec.palette.bg || !spec.palette.ink) {
    throw new Error('MOTION_CANVAS_SPEC_MISSING: adapter must inject a DNA palette');
  }
  return spec;
}

/** Fade/one-direction flow only. Bounce, flash, shake, sticker and flashy
 *  transitions are forbidden by the account DNA and are never used here. */
export const TWEEN = 0.45;
export const HOLD = 0.55;
