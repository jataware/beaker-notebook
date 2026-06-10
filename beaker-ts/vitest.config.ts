import { defineConfig, mergeConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import viteConfig from './vite.config';

// Two test projects:
//
//   unit        - pure, non-DOM logic in the fast Node environment.
//                 Files: src/**/__tests__/*.test.ts  (excluding *.browser.test.ts)
//
//   integration - tests that import BeakerSession and therefore pull in
//                 @jupyterlab/* + @lumino/* (which reference DOM globals like
//                 `document` / `DragEvent` at module load). These run in real
//                 Chromium. The kernel websocket is still fully mocked; the
//                 browser just provides a faithful DOM for jupyterlab.
//                 Files: src/**/__tests__/*.browser.test.ts
//
// `npm run test` runs both; `vitest --project unit` runs just the fast ones.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      projects: [
        {
          extends: true,
          test: {
            name: 'unit',
            environment: 'node',
            include: ['src/**/__tests__/**/*.test.ts'],
            exclude: ['src/**/__tests__/**/*.browser.test.ts'],
          },
        },
        {
          extends: true,
          test: {
            name: 'integration',
            include: ['src/**/__tests__/**/*.browser.test.ts'],
            browser: {
              enabled: true,
              provider: playwright(),
              headless: true,
              instances: [{ browser: 'chromium' }],
            },
          },
        },
      ],
    },
  }),
);
