import { describe, expect, it } from 'vitest';
import {
    getIntegrationProviderSlug,
    getIntegrationProviderType,
    type Integration,
} from '../util/integration';

describe('integration provider helpers', () => {
    it('parses a provider', () => {
        const integration = { provider: 'mcp:example' } as Integration;
        expect(getIntegrationProviderType(integration)).toBe('mcp');
        expect(getIntegrationProviderSlug(integration)).toBe('example');
    });

    it('handles a missing provider', () => {
        const integration = {} as Integration;
        expect(getIntegrationProviderType(integration)).toBe('');
        expect(getIntegrationProviderSlug(integration)).toBeUndefined();
    });
});
