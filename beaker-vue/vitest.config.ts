import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // `tests/` currently holds the Playwright e2e suite, which uses the
      // Playwright test API and requires a live server; excluding it keeps
      // vitest from trying to collect those specs. The `e2e/**` entry reflects
      // where the Playwright tests are expected to live and where we will
      // likely relocate them (see the note in playwright.config.ts). Once that
      // move happens, the `tests/**` exclusion can be dropped.
      exclude: [...configDefaults.exclude, 'e2e/**', 'tests/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
