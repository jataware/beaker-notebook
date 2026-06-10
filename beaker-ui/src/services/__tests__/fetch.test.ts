import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { worker } from '../../__tests__/mocks/browser';
import { FetchClient } from '../fetch';

// Demonstrates network-layer mocking with MSW: the FetchClient issues a real
// `fetch`, intercepted by the worker, so we assert on resolved URLs and the
// default-header logic without touching a live backend.
describe('FetchClient', () => {
  it('resolves relative URLs against the base URL', async () => {
    let seenUrl = '';
    worker.use(
      http.get('https://beaker.test/api/status', ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({ ok: true });
      }),
    );

    const client = new FetchClient();
    client.setBaseUrl('https://beaker.test/');
    const res = await client.fetch('/api/status');

    expect(seenUrl).toBe('https://beaker.test/api/status');
    await expect(res.json()).resolves.toEqual({ ok: true });
  });

  it('applies default headers whose URL pattern matches', async () => {
    let authHeader: string | null = null;
    worker.use(
      http.get('https://beaker.test/api/secure', ({ request }) => {
        authHeader = request.headers.get('authorization');
        return HttpResponse.json({});
      }),
    );

    const client = new FetchClient();
    client.setBaseUrl('https://beaker.test/');
    client.setDefaultHeaders('/api/', { authorization: 'Bearer test-token' });
    await client.fetch('/api/secure');

    expect(authHeader).toBe('Bearer test-token');
  });
});
