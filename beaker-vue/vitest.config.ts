import { fileURLToPath } from 'node:url';
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import viteConfig from './vite.config';

// Component tests run in a real Chromium instance (via Playwright) rather than
// jsdom. The heavy rendering dependencies in this library (CodeMirror, KaTeX,
// PDF.js, Cytoscape, PrimeVue) rely on real layout/focus/canvas APIs that a
// fake DOM does not implement faithfully.
//
// Tests live next to the code they cover, in src/**/__tests__.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      include: ['src/**/__tests__/**/*.{test,spec}.{ts,tsx}'],
      exclude: [...configDefaults.exclude, 'e2e/**', 'dist/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
      setupFiles: ['./src/__tests__/setup.ts'],
      browser: {
        enabled: true,
        provider: playwright(),
        headless: true,
        // One named instance keeps CI simple; add { browser: 'firefox' } /
        // { browser: 'webkit' } here to fan out across engines.
        instances: [{ browser: 'chromium' }],
      },
    },
  }),
);
