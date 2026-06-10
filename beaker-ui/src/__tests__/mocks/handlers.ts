import { http, HttpResponse } from 'msw';

// Default request handlers shared across tests. Individual tests can override
// or add handlers at runtime with `worker.use(...)` (see setup.ts), which are
// reset after each test.
//
// Start with a permissive stub for the app config endpoint so tests that
// incidentally trigger it don't error; real assertions should register their
// own focused handlers.
export const handlers = [
  http.get('*/config', () => HttpResponse.json({})),
];
