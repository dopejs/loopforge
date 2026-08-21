/// <reference types="vite/client" />

/** Injected by Vite's `define`; see vite.config.ts. */
declare const __APP_VERSION__: string;

declare module "*.svg" {
  const source: string;
  export default source;
}
