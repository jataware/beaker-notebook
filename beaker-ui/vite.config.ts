import { fileURLToPath, URL } from 'node:url';
import path from 'node:path';
import { createRequire } from 'node:module';

import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import vueJsx from '@vitejs/plugin-vue-jsx';
import topLevelAwait from 'vite-plugin-top-level-await';
import vueDevTools from 'vite-plugin-vue-devtools';

import { sanitizeJupyterEval, outputJsonRoutesPlugin } from '@jataware/beaker-vue/builder';

const require = createRequire(import.meta.url);

const ProxyHost = `${process.env.PROXY || 'http://localhost:8888'}`;
const proxyConfig = {
    target: `${ProxyHost}/`,
    xfwd: true,
    changeOrigin: false,
};

/**
 * Map of "chunk name" → bare specifier pattern. The build emits a separate
 * chunk per entry; the static-modules.json plugin records each chunk's
 * URL so the Python handler can inject the importmap at request time.
 *
 * Each key here corresponds to a bare specifier extensions will reference
 * (e.g., `import { ... } from 'vue'`).
 */
const SHARED_MODULE_CHUNKS: Record<string, RegExp[]> = {
    'vue': [/[\\/]node_modules[\\/](@vue[\\/]|vue[\\/])/],
    'vue-router': [/[\\/]node_modules[\\/]vue-router[\\/]/],
    'pinia': [/[\\/]node_modules[\\/]pinia[\\/]/],
    'primevue': [
        /[\\/]node_modules[\\/]primevue[\\/]/,
        /[\\/]node_modules[\\/]@primevue[\\/]/,
        /[\\/]node_modules[\\/]@primeuix[\\/]/,
        /[\\/]node_modules[\\/]primeicons[\\/]/,
    ],
    'jupyterlab': [
        /[\\/]node_modules[\\/]@jupyterlab[\\/]/,
        /[\\/]node_modules[\\/]@lumino[\\/]/,
        /[\\/]node_modules[\\/]@jupyter[\\/]/,
    ],
    'codemirror': [
        /[\\/]node_modules[\\/]@codemirror[\\/]/,
        /[\\/]node_modules[\\/]codemirror[\\/]/,
        /[\\/]node_modules[\\/]codemirror-lang-r[\\/]/,
        /[\\/]node_modules[\\/]@plutojl[\\/]/,
    ],
    'xlsx': [/[\\/]node_modules[\\/]xlsx[\\/]/],
    'pdfjs-dist': [/[\\/]node_modules[\\/]pdfjs-dist[\\/]/],
    '@jataware/beaker-client': [
        /[\\/]node_modules[\\/]beaker-kernel[\\/]/,
        /[\\/]beaker-ts[\\/](src|dist)[\\/]/,
        /[\\/]node_modules[\\/]@jataware\/beaker-client[\\/]/,
        /[\\/]@jataware\/beaker-client[\\/](src|dist)[\\/]/
    ],
    '@jataware/beaker-vue': [
        /[\\/]node_modules[\\/]beaker-vue[\\/]/,
        /[\\/]beaker-vue[\\/](src|dist)[\\/]/,
        /[\\/]node_modules[\\/]@jataware\/beaker-vue[\\/]/,
        /[\\/]@jataware\/beaker-vue[\\/](src|dist)[\\/]/
    ],
};

function matchChunk(id: string): string | undefined {
    for (const [name, patterns] of Object.entries(SHARED_MODULE_CHUNKS)) {
        for (const re of patterns) {
            if (re.test(id)) return name;
        }
    }
    return undefined;
}

/**
 * Emits static-modules.json — a mapping of chunk name → output URL.
 *
 * The Python `PageHandler` reads this and injects an `<script type="importmap">`
 * into served HTML so extensions can resolve bare-specifier imports
 * (`from 'vue'`, `from 'beaker-vue'`, etc.) at runtime.
 */
function staticModulesJsonPlugin(): Plugin {
    return {
        name: 'beaker-ui:static-modules-json',
        generateBundle(_options, bundle) {
            const map: Record<string, string> = {};
            for (const [fileName, chunk] of Object.entries(bundle)) {
                if (chunk.type !== 'chunk') continue;
                const chunkName = (chunk as any).name as string | undefined;
                if (!chunkName) continue;
                if (chunkName in SHARED_MODULE_CHUNKS) {
                    map[chunkName] = fileName;
                }
            }
            this.emitFile({
                type: 'asset',
                fileName: 'static-modules.json',
                source: JSON.stringify(map, null, 2),
            });
        },
    };
}

// Module-resolution aliases, exported so the test config (vitest.config.ts)
// resolves `@/...` / bridge imports identically to the app build without
// duplicating — and drifting from — this list.
export const resolveAlias = [
    // Bridge aliases — route lib subpath imports into beaker-vue's source.
    // Pages currently use `@/components/X.vue` style; these resolve them
    // to beaker-vue's published src. (Transitional: pages will be rewritten
    // to use the curated `from 'beaker-vue'` barrel imports in a future
    // cleanup pass. Listed BEFORE the generic '@' alias so they win.)
    { find: '@/components', replacement: fileURLToPath(new URL('../beaker-vue/src/components', import.meta.url)) },
    { find: '@/composables', replacement: fileURLToPath(new URL('../beaker-vue/src/composables', import.meta.url)) },
    { find: '@/renderers', replacement: fileURLToPath(new URL('../beaker-vue/src/renderers', import.meta.url)) },
    { find: '@/plugins', replacement: fileURLToPath(new URL('../beaker-vue/src/plugins', import.meta.url)) },
    { find: '@/directives', replacement: fileURLToPath(new URL('../beaker-vue/src/directives', import.meta.url)) },
    { find: '@/themes', replacement: fileURLToPath(new URL('../beaker-vue/src/themes', import.meta.url)) },
    { find: /^@\/util$/, replacement: fileURLToPath(new URL('../beaker-vue/src/util/index.ts', import.meta.url)) },
    { find: '@/util/integration', replacement: fileURLToPath(new URL('../beaker-vue/src/util/integration', import.meta.url)) },
    // Beaker-ui local paths (must come after the more-specific bridge entries above).
    { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
    { find: 'path', replacement: path.resolve(require.resolve('path-browserify'), '..') },
    // Allows automatic updating when beaker-ts is updated; uses the dist
    // version when building in production mode.
    {
        find: '@jataware/beaker-vue',
        replacement: (
            process.env.NODE_ENV === 'development'
                ? fileURLToPath(new URL('../beaker-vue/src', import.meta.url))
                : '@jataware/beaker-vue'
        ),
    },
    {
        find: '@jataware/beaker-client',
        replacement: (
            process.env.NODE_ENV === 'development'
                ? fileURLToPath(new URL('../beaker-ts/src', import.meta.url))
                : '@jataware/beaker-client'
        ),
    },
];

export default defineConfig({
    base: './',
    plugins: [
        vue(),
        vueJsx(),
        topLevelAwait(),
        sanitizeJupyterEval(),
        vueDevTools(),
        outputJsonRoutesPlugin('./src/router/index.ts', 'defaultRouteMap'),
        staticModulesJsonPlugin(),
    ],
    resolve: {
        alias: resolveAlias,
        dedupe: [
            'vue',
            'primevue',
            '@primevue/themes',
            '@primevue/icons',
            '@primeuix/styled',
            '@primeuix/themes',
            '@primeuix/utils',
            '@lumino',
            '@lumino/widgets',
            '@lumino/algorithm',
            '@lumino/coreutils',
            '@lumino/polling',
            '@lumino/signaling',
            '@jupyterlab',
            '@jupyterlab/ui-components',
            '@jupyterlab/services',
            '@jupyterlab/apputils',
            '@jupyterlab/translation',
            '@jupyterlab/statedb',
            'react-dom',
            'xlsx',
            '@jupyterlab/coreutils',
            '@jupyterlab/mathjax-extension',
            '@jupyterlab/rendermime',
        ],
    },
    server: {
        host: '0.0.0.0',
        port: 8080,
        proxy: {
            '/api': { ...proxyConfig, ws: true, rewriteWsOrigin: false },
            '/beaker': proxyConfig,
            '/appconfig.js': proxyConfig,
            '/files': proxyConfig,
            '/config': proxyConfig,
            '/contexts': proxyConfig,
            '/assets': proxyConfig,
        },
        fs: {
            strict: false,
            allow: ['..'],
        },
    },
    build: {
        target: 'esnext',
        assetsDir: 'static/',
        outDir: 'html/',
        manifest: true,
        ssrManifest: true,
        rollupOptions: {
            onwarn(warning, warn) {
                if (
                    warning.code === 'MISSING_EXPORT' &&
                    warning.message.includes('json5') &&
                    warning.message.includes('@jupyterlab/settingregistry')
                ) {
                    return;
                }
                warn(warning);
            },
            output: {
                manualChunks(id: string) {
                    return matchChunk(id);
                },
            },
        },
    },
    optimizeDeps: {
        esbuildOptions: {
            target: 'esnext',
        },
    },
});
