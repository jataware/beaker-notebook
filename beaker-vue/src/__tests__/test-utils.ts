// Shared helpers for component tests.
//
// Most components in this library assume PrimeVue (and often a Pinia store) are
// installed on the app. `renderWithPlugins` wraps @testing-library/vue's
// `render` so individual tests don't have to repeat that plugin wiring.
import { vi } from 'vitest';
import { render, type RenderOptions } from '@testing-library/vue';
import { createTestingPinia, type TestingOptions } from '@pinia/testing';
import PrimeVue from 'primevue/config';
import type { Component } from 'vue';

interface RenderWithPluginsOptions {
  /** Props passed to the component under test. */
  props?: Record<string, unknown>;
  /** Slot content, forwarded to Testing Library. */
  slots?: RenderOptions<Component>['slots'];
  /** Options forwarded to createTestingPinia (e.g. initialState, stubActions). */
  pinia?: TestingOptions;
  /** Extra global config (plugins, components, stubs, provides) merged in. */
  global?: RenderOptions<Component>['global'];
}

export function renderWithPlugins(
  component: Component,
  options: RenderWithPluginsOptions = {},
) {
  const { props, slots, pinia, global } = options;
  return render(component, {
    props,
    slots,
    global: {
      ...global,
      plugins: [
        createTestingPinia({ createSpy: vi.fn, ...pinia }),
        [PrimeVue, { ripple: false }],
        ...(global?.plugins ?? []),
      ],
    },
  });
}

// Re-export the commonly-used Testing Library surface so tests can import
// everything from one place:
//   import { renderWithPlugins, screen, fireEvent } from '@/__tests__/test-utils';
// (explicit named re-exports — `export *` does not survive the browser-mode
// ESM interop).
export { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/vue';
