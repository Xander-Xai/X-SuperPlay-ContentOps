// Video export is started from the editor's Video Settings tab (the ffmpeg
// exporter receives frames over the editor websocket). There is no official
// headless CLI. The adapter injects the clip spec through this Vite `define`
// so a single pinned project can render many parameterised clips without
// rewriting source files or creating a second cache/registry.
import {readFileSync} from 'node:fs';
import {defineConfig} from 'vite';
import motionCanvas from '@motion-canvas/vite-plugin';
import ffmpeg from '@motion-canvas/ffmpeg';

const specPath = process.env.MOTION_CANVAS_SPEC_PATH || '';
let spec: Record<string, unknown> = {};
if (specPath) {
  spec = JSON.parse(readFileSync(specPath, 'utf8')) as Record<string, unknown>;
}

export default defineConfig({
  define: {
    __MOTION_CANVAS_SPEC__: JSON.stringify(spec),
  },
  plugins: [motionCanvas(), ffmpeg()],
});
