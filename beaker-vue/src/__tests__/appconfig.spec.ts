// @vitest-environment jsdom
import { createApp } from 'vue';
import { describe, expect, it } from 'vitest';

import { BeakerAppConfigPlugin } from '../plugins/appconfig';

describe('Beaker app asset URLs', () => {
    it('resolves local assets against the server base URL', () => {
        const app = createApp({});
        const config = {
            assets: {
                header_logo: { slug: 'header_logo', src: '/assets/beaker-crdc/logo.svg', alt: 'Logo' },
                external: { slug: 'external', src: 'https://example.com/logo.svg' },
                prefixed: { slug: 'prefixed', src: '/user/test/assets/app/logo.svg' },
                data: { slug: 'data', src: 'data:image/svg+xml,test' },
            },
        };
        app.use(BeakerAppConfigPlugin, config, '/user/test/');
        const tmpl = app.config.globalProperties.$tmpl;

        expect(tmpl.getAsset('header_logo')).toEqual({
            slug: 'header_logo', src: '/user/test/assets/beaker-crdc/logo.svg', alt: 'Logo',
        });
        expect(config.assets.header_logo.src).toBe('/assets/beaker-crdc/logo.svg');
        expect(tmpl.getAsset('external').src).toBe('https://example.com/logo.svg');
        expect(tmpl.getAsset('prefixed').src).toBe('/user/test/assets/app/logo.svg');
        expect(tmpl.getAsset('data').src).toBe('data:image/svg+xml,test');
    });

    it('resolves app and page stylesheet assets', () => {
        const app = createApp({});
        app.use(BeakerAppConfigPlugin, {
            stylesheet: '/assets/app/global.css',
            pages: { notebook: { stylesheet: '/assets/app/page.css' } },
        }, '/nested/');
        app.config.globalProperties.$beakerAppConfig.setPage('notebook');

        expect(document.getElementById('beakerapp-global')?.getAttribute('href'))
            .toBe('/nested/assets/app/global.css');
        expect(document.getElementById('beakerapp-page')?.getAttribute('href'))
            .toBe('/nested/assets/app/page.css');
        app.config.globalProperties.$beakerAppConfig.setPage('chat');
        expect(document.getElementById('beakerapp-page')).toBeNull();
        expect(document.getElementById('beakerapp-global')).not.toBeNull();
        document.getElementById('beakerapp-global')?.remove();
    });

    it('keeps asset paths unchanged at the root', () => {
        const app = createApp({});
        app.use(BeakerAppConfigPlugin, { assets: { logo: { src: '/assets/app/logo.svg' } } });
        expect(app.config.globalProperties.$tmpl.getAsset('logo').src).toBe('/assets/app/logo.svg');
    });
});
