import { fileURLToPath } from 'node:url';
import { defineConfig, configDefaults } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import vueJsx from '@vitejs/plugin-vue-jsx';
import { playwright } from '@vitest/browser-playwright';

import { resolveAlias } from './vite.config';

// Unit / page / routing tests for the application.
//
// We build a focused config here rather than reusing the full app vite config:
// the app config carries dev-server, build, and dev-tooling plugins
// (vue-devtools, the route/static-modules JSON emitters) that are irrelevant
// to — and would interfere with — a test run. We DO reuse `resolveAlias` so
// `@/...` and the beaker-vue bridge imports resolve exactly as they do in the
// real build.
//
// Like beaker-vue, tests run in a real Chromium instance via Playwright; pages
// pull in the same heavy rendering dependencies that a fake DOM mishandles.
//
// Tests live in src/**/__tests__.
export default defineConfig({
  plugins: [vue(), vueJsx()],
  resolve: {
    alias: resolveAlias,
  },
  test: {
    include: ['src/**/__tests__/**/*.{test,spec}.{ts,tsx}'],
    exclude: [...configDefaults.exclude, 'tests/**', 'dist/**', 'html/**'],
    root: fileURLToPath(new URL('./', import.meta.url)),
    setupFiles: ['./src/__tests__/setup.ts'],
    browser: {
      enabled: true,
      provider: playwright(),
      headless: true,
      instances: [{ browser: 'chromium' }],
    },
  },
});
