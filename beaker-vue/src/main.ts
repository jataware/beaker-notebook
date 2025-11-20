import { createApp } from 'vue';
import { createPinia } from 'pinia';

import { URLExt, PageConfig } from '@jupyterlab/coreutils';
import PrimeVue from 'primevue/config';
import Tooltip from 'primevue/tooltip';
import ConfirmationService from 'primevue/confirmationservice';
import DialogService from 'primevue/dialogservice';
import ToastService from 'primevue/toastservice';
import FocusTrap from 'primevue/focustrap';
import { vKeybindings } from './directives/keybindings';
import { vAutoScroll } from './directives/autoscroll';
import BeakerThemePlugin from './plugins/theme';
import BeakerAppConfigPlugin from './plugins/appconfig';
import { fetch, client } from './util/fetch';
import * as cookie from 'cookie';

import App from './App.vue';
import createRouter from './router';
import { DefaultTheme } from './themes';

import 'primeicons/primeicons.css';
import './index.scss';


const baseUrl = PageConfig.getBaseUrl();
const confUrl = URLExt.join(baseUrl, '/config') + `?q=${Date.now().toString()}`;
const configResponse = await fetch(confUrl);
const config = await configResponse.json();
const baseHost = URLExt.parse(config.baseUrl).host;


const app = createApp(App, {config});
const router = createRouter(config);

app.use(createPinia());
app.use(router);
app.use(PrimeVue, {
    theme: {
        preset: DefaultTheme,
        options: {
            darkModeSelector: '.beaker-dark',
            cssLayer: {
                name: 'primevue',
                order: 'primevue, beaker'
            }
        }

    },
});
app.use(ToastService);
app.use(ConfirmationService);
app.use(DialogService);
app.use(BeakerAppConfigPlugin, config.appConfig);
app.use(BeakerThemePlugin);
app.directive('tooltip', Tooltip);
app.directive('focustrap', FocusTrap);
app.directive('keybindings', vKeybindings);
app.directive('autoscroll', vAutoScroll);

const cookies = cookie.parse(document.cookie);
const xsrfCookie = cookies._xsrf;
client.setDefaultHeaders(baseHost, {"X-XSRFToken": xsrfCookie})

app.mount('#app');
