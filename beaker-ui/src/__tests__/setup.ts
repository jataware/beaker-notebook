// Global setup for beaker-ui tests (browser mode).
//
// - Registers @testing-library/jest-dom matchers.
// - Boots the MSW worker so tests can intercept network calls; handlers added
//   per-test via `worker.use(...)` are reset between tests.
// - Unmounts Testing Library components after each test.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/vue';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { worker } from './mocks/browser';

beforeAll(async () => {
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true });
});

afterEach(() => {
  cleanup();
  worker.resetHandlers();
});

afterAll(() => {
  worker.stop();
});
