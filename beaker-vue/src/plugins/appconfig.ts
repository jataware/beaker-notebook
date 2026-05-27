import { ref, capitalize } from 'vue';
import type { Plugin, App, Ref } from 'vue';

declare module 'vue' {
    interface ComponentCustomProperties {
        $tmpl: {
            _: (templateName: string, defaultValue?: string) => string,
            hasTemplateValue: (templateName: string) => boolean,
            getAsset: (assetName: string) => Asset,
            hasAsset: (assetName: string) => boolean,
        }
    }
}


export interface Asset {
    slug: string;
    src: string;
    attrs: {
        [key: string]: string;
    };
}

export interface BeakerAppConfig {
    config: {[key: string]: any},
    setPageTitle: (page: string) => void,
    setPage: (page: string) => void,
    currentPage?: Ref<string>,
}

export const BeakerAppConfigPlugin: Plugin = {
    install(app: App, beakerAppConfig?: any) {
        if (!beakerAppConfig) {
            // Fetch app config from globally defined instance or create fresh, empty version.
            beakerAppConfig = globalThis['beaker_app'] || {};
        }
        const templateValues = beakerAppConfig.templateStrings || {};
        const assetValues = beakerAppConfig.assets || {};
        const currentPage: Ref<string|null> = ref(null);

        const _ = (templateName: string, defaultValue?: string): string => {
            // First try to fetch from current page's settings, since they take priority.
            if (currentPage.value) {
                const page = beakerAppConfig.pages?.[currentPage.value];
                const pageTemplateStrings = page?.template_strings;
                const templateValue = pageTemplateStrings?.[templateName];
                if (templateValue) {
                    return templateValue;
                }
            }
            // If not defined per page, try to return the value defined for the app.
            if (templateName in templateValues) {
                const template: string = templateValues[templateName];

                return template
            }
            // Otherwise, return the default value, or an empty string if the default value is not provided.
            else {
                return defaultValue ? defaultValue : '';
            }
        }

        function hasTemplateValue(templateName: string): boolean {
            return templateName in templateValues;
        }

        function hasAsset(assetName: string): boolean {
            return assetName in assetValues;
        }

        function getAsset(assetName: string): Asset {
            if (assetName in assetValues) {
                return assetValues[assetName];
            }
            else {
                return undefined;
            }
        }

        app.config.globalProperties.$tmpl = {
            _,
            getAsset,
            hasAsset,
            hasTemplateValue
        };

        const setPage = (page: string) => {
            currentPage.value = page;
            setPageTitle(page);
            const globalStyle = beakerAppConfig?.stylesheet;
            const pageStyle = beakerAppConfig?.pages?.[page]?.stylesheet;
            if (globalStyle) {
                setStylesheet(globalStyle, "beakerapp-global");
            }
            if (pageStyle) {
                setStylesheet(pageStyle, "beakerapp-page");
            }
        }

        const setStylesheet = (stylesheet: string | {[key: string]: string}, id: string) => {
            if (typeof(stylesheet) === "string") { // URL
                const linkElement = document.getElementById(id) || document.createElement("link");
                linkElement.setAttribute("href", stylesheet);
                linkElement.setAttribute("rel", "stylesheet");
                linkElement.setAttribute("id", id);
                document.head.appendChild(linkElement);
            }
        }

        const setPageTitle = (page: string) => {
            const pageConfig = beakerAppConfig?.pages?.[page];
            if (pageConfig?.title) {
                document.title = pageConfig.title;
            }
            else if (document.title === ""){
                document.title = `Beaker ${capitalize(page)}`
            }

        }

        app.config.globalProperties.$beakerAppConfig = <BeakerAppConfig>{
            config: beakerAppConfig,
            setPageTitle,
            setPage,
            currentPage,
        };
        app.provide('beakerAppConfig', app.config.globalProperties.$beakerAppConfig);
    },
}

export default BeakerAppConfigPlugin;
