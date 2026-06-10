import { describe, it, expect } from 'vitest';
import { createMessageId } from '../util';

describe('createMessageId', () => {
  it('embeds the message type in the id', () => {
    const id = createMessageId('execute_request');
    expect(id).toMatch(/^beaker-[0-9a-f]{16}-execute_request$/);
  });

  it('produces a unique id on each call', () => {
    const a = createMessageId('execute_request');
    const b = createMessageId('execute_request');
    expect(a).not.toBe(b);
  });
});
