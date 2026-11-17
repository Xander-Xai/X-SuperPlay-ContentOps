import {makeProject} from '@motion-canvas/core';
import {readSpec} from './lib/spec';
import animatedSystemGraph from './scenes/animated_system_graph?scene';
import agentStateMachine from './scenes/agent_state_machine?scene';

// One pinned project, one exported clip. The adapter selects the scene via the
// injected spec; both scene modules are present so the project always compiles.
const spec = readSpec();
const scenes =
  spec.template === 'agent_state_machine'
    ? [agentStateMachine]
    : [animatedSystemGraph];

export default makeProject({
  name: 'contentops-motion-canvas',
  scenes,
});
