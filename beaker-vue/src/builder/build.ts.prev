import type { UserConfig } from 'vite';

/**
 * Creates a Vite configuration for building context renderer ES modules.
 *
 * Handles Vue/JSX compilation, CSS injection, ES module output targeting
 * `../assets/`, and externalizes vue/beaker-vue/beaker-kernel so they
 * resolve at runtime from the Beaker static file server.
 *
 * Context packages only need to provide overrides for context-specific
 * concerns (extra plugins, resolve aliases, additional entry points).
 */
export async function defineBeakerRendererConfig(overrides?: UserConfig): Promise<UserConfig> {
    const vue = (await import('@vitejs/plugin-vue')).default;
    const vueJsx = (await import('@vitejs/plugin-vue-jsx')).default;
    const cssInjectedByJsPlugin = (await import ("vite-plugin-css-injected-by-js")).default;
    const mergeConfig = (await import('vite')).mergeConfig;
    // import vue from '@vitejs/plugin-vue';
    // import vueJsx from '@vitejs/plugin-vue-jsx';
    // import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";
    const base: UserConfig = {
        plugins: [
            vue(),
            vueJsx(),
            cssInjectedByJsPlugin({
                relativeCSSInjection: true,
            }),
        ],
        build: {
            target: 'esnext',
            minify: false,
            outDir: '../assets/',
            cssCodeSplit: true,
            emptyOutDir: true,
            lib: {
                entry: {
                    "renderers": "./src/renderers.ts",
                },
                formats: ["es"],
                fileName: (_format, entryName) => `${entryName}.js`,
            },
            rollupOptions: {
                external: ['vue', '@jataware/beaker-vue', '@jataware/beaker-client'],
                output: {
                    paths: {
                        vue: '/static/vue.esm-browser.prod.js?url',
                    },
                },
            },
        },
    };
    return mergeConfig(base, overrides ?? {});
}
