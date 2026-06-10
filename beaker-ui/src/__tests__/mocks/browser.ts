import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

// MSW worker for the browser-mode (Chromium) test environment. Requires the
// service worker script at /mockServiceWorker.js (generated in public/ via
// `npx msw init public/`). Started in src/__tests__/setup.ts.
export const worker = setupWorker(...handlers);
