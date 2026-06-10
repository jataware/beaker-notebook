import { describe, it, expect } from 'vitest';
import { renderWithPlugins, screen } from '../../../__tests__/test-utils';
import InlineInput from '../InlineInput.vue';

// InlineInput renders PrimeVue's Inplace; in its collapsed "display" state it
// shows the bound model value. This exercises the real Chromium + PrimeVue
// rendering path rather than a fake DOM.
describe('InlineInput', () => {
  it('displays the bound model value', async () => {
    renderWithPlugins(InlineInput, { props: { modelValue: 'kernel-name' } });

    expect(await screen.findByText('kernel-name')).toBeVisible();
  });
});
