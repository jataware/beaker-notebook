import type { App } from 'vue';
import PrimeVue from 'primevue/config';
import Tooltip from 'primevue/tooltip';
import FocusTrap from 'primevue/focustrap';
import ToastService from 'primevue/toastservice';
import ConfirmationService from 'primevue/confirmationservice';
import DialogService from 'primevue/dialogservice';

import { vKeybindings } from '../directives/keybindings';
import { vAutoScroll } from '../directives/autoscroll';
import BeakerThemePlugin from './theme';
import BeakerAppConfigPlugin from './appconfig';
import { DefaultTheme } from '../themes';

import type { IFetchClient } from '../types/fetch';
import type { IBeakerContextService } from '../types/context';
import { BeakerFetchClientKey, BeakerContextServiceKey } from './keys';

export interface BeakerHostPluginOptions {
    /** PrimeVue theme preset; defaults to DefaultTheme from beaker-vue. */
    theme?: any;
    /** CSS selector that toggles dark mode; defaults to '.beaker-dark'. */
    darkModeSelector?: string;
    /** App config injected into the BeakerAppConfigPlugin. */
    appConfig?: any;
    /** Configured FetchClient instance; provided via inject key. */
    fetchClient?: IFetchClient;
    /** ContextService instance; provided via inject key. */
    contextService?: IBeakerContextService;
}

/**
 * Installs the full set of host-contract plugins, services, directives, and
 * provides on a Vue app. This is the single source of truth for what the
 * host commits to providing for library components and extensions.
 *
 * Bumps to this contract (added / removed / renamed installations) should
 * bump EXTENSION_API_VERSION accordingly.
 */
export function installBeakerHostPlugins(
    app: App,
    options: BeakerHostPluginOptions = {},
): void {
    app.use(PrimeVue, {
        theme: {
            preset: options.theme ?? DefaultTheme,
            options: {
                darkModeSelector: options.darkModeSelector ?? '.beaker-dark',
                cssLayer: {
                    name: 'primevue',
                    order: 'primevue, beaker',
                },
            },
        },
    });
    app.use(ToastService);
    app.use(ConfirmationService);
    app.use(DialogService);
    app.use(BeakerAppConfigPlugin, options.appConfig);
    app.use(BeakerThemePlugin);

    app.directive('tooltip', Tooltip);
    app.directive('focustrap', FocusTrap);
    app.directive('keybindings', vKeybindings);
    app.directive('autoscroll', vAutoScroll);

    if (options.fetchClient) {
        app.provide(BeakerFetchClientKey, options.fetchClient);
    }
    if (options.contextService) {
        app.provide(BeakerContextServiceKey, options.contextService);
    }
}
