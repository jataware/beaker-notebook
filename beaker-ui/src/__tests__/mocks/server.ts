import { setupServer } from 'msw/node';
import { handlers } from './handlers';

// MSW server for any Node-environment tests (e.g. a pure-logic test file that
// opts out of browser mode). The browser-mode suite uses ./browser.ts instead.
// Kept so the same `handlers` drive both environments.
export const server = setupServer(...handlers);
