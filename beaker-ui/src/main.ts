import { createApp } from 'vue';
import { createPinia } from 'pinia';

import { URLExt } from '@jupyterlab/coreutils';
import { fetch, client } from '@/services/fetch';
import { contextService } from '@/services/context';
import { installBeakerHostPlugins } from 'beaker-vue';
import * as cookie from 'cookie';

import App from '@/App.vue';
import createRouter from '@/router';

import 'primeicons/primeicons.css';
import '@/index.scss';

const defaultSiteConfig = {
  "pathPrefix": "/",
  "username": null,
  "_xsrf": undefined,

};
const siteConfigElement = document.getElementById("site-config");
const siteConfig = (siteConfigElement ? JSON.parse(siteConfigElement.textContent) : defaultSiteConfig);

const pathPrefix = siteConfig.pathPrefix;
const baseUrl = URLExt.normalize(pathPrefix);
client.setBaseUrl(baseUrl);

const confUrl = '/config' + `?q=${Date.now().toString()}`;
const configResponse = await fetch(confUrl);
const config = await configResponse.json();
const baseHost = URLExt.parse(config.baseUrl).host;

config.pathPrefix = pathPrefix;
config.baseUrl = baseUrl;
config.baseHost = baseHost;

const app = createApp(App, {config});
const router = createRouter(config);

app.provide('siteConfig', siteConfig);
app.use(createPinia());
app.use(router);
installBeakerHostPlugins(app, {
    appConfig: config.appConfig,
    fetchClient: client,
    contextService,
});

const cookies = cookie.parse(document.cookie);
const xsrfCookie = cookies._xsrf;
client.setDefaultHeaders(baseHost, {"X-XSRFToken": xsrfCookie})

app.mount('#app');
