// Motion Canvas vite-plugin transforms `*?scene` imports at dev/build time.
// TypeScript needs an ambient declaration for those virtual module ids.
declare module '*?scene' {
  import type {FullSceneDescription} from '@motion-canvas/core';
  const scene: FullSceneDescription;
  export default scene;
}
