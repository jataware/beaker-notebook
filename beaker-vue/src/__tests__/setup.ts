// Global setup for component tests (runs once per test file, in-browser).
//
// - Registers @testing-library/jest-dom matchers (toBeVisible, toHaveTextContent, ...).
// - Unmounts any components rendered by @testing-library/vue after each test so
//   state does not leak between tests.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/vue';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
