import { describe, it, expect } from 'vitest';
import { convertPagesToRoutes, applyResolvedRoutes, defaultRouteMap } from '../index';

// Pure routing-logic tests: how backend config (pages / resolved routes) maps
// onto the route table. This is the unit-test layer for routing; full
// navigation (click link -> URL -> rendered page) belongs in the Playwright
// E2E suite.
describe('convertPagesToRoutes', () => {
  it('keeps only pages present in the default route map', () => {
    const routes = convertPagesToRoutes({
      notebook: { slug: 'notebook', default: true },
      unknown: { slug: 'unknown', default: false },
    } as any);

    expect(Object.keys(routes)).toEqual(['notebook']);
    expect(routes.notebook.path).toBe('/notebook');
  });

  it('marks the default page role "home" and others "alt"', () => {
    const asHome = convertPagesToRoutes({ chat: { slug: 'chat', default: true } } as any);
    const asAlt = convertPagesToRoutes({ chat: { slug: 'chat', default: false } } as any);

    expect(asHome.chat.role).toBe('home');
    expect(asAlt.chat.role).toBe('alt');
  });
});

describe('applyResolvedRoutes', () => {
  it('overrides the path of a known route from resolved config', () => {
    const routeMap = { ...defaultRouteMap };
    applyResolvedRoutes(routeMap, {
      '/custom-notebook': { name: 'notebook', path: '/custom-notebook' } as any,
    });

    expect(routeMap.notebook.path).toBe('/custom-notebook');
  });
});
