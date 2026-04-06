import { fileURLToPath, URL } from 'node:url';
import { copyFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

import { defineConfig, type UserConfig, type Plugin } from 'vite';
import vueDevTools from 'vite-plugin-vue-devtools';
import { baseConfig } from './vite.config';

const ProxyHost = `${process.env.PROXY || 'http://localhost:8888'}`;
const proxyConfig = {
  target: `${ProxyHost}/`,
  xfwd: true,
  changeOrigin: false,
}


function copyVueEsmPlugin(): Plugin {
  return {
    name: 'copy-vue-esm-browser',
    writeBundle() {
      const src = fileURLToPath(new URL('node_modules/vue/dist/vue.esm-browser.prod.js', import.meta.url));
      const dest = fileURLToPath(new URL('html/static', import.meta.url));
      mkdirSync(dest, { recursive: true });
      copyFileSync(src, path.join(dest, 'vue.esm-browser.prod.js'));
    },
  };
}

// https://vite.dev/config/
export const appConfig: UserConfig = {
  ...baseConfig,
  base: "./",
  server: {
    host: '0.0.0.0',
    port: 8080,
    proxy: {
      '/api': {
        ...proxyConfig,
        ws: true,
        rewriteWsOrigin: false,
      },
      '/beaker': proxyConfig,
      '/appconfig.js': proxyConfig,
      '/files': proxyConfig,
      '/config': proxyConfig,
      '/contexts': proxyConfig,
      '/assets': proxyConfig,
    },
    fs: {
      allow: [".."]
    },
  },
  plugins: [
    ...(baseConfig.plugins ?? []),
    vueDevTools(),
    copyVueEsmPlugin(),
  ],
  build: {
    target: 'esnext',
    assetsDir: 'static/',
    outDir: 'html/',
    rollupOptions: {
      onwarn(warning, warn) {
        // Custom warning suppression for known issues that are not a concern
        if (
          (warning.code === "MISSING_EXPORT" && warning.message.includes('json5') && warning.message.includes('@jupyterlab/settingregistry'))
        ) {
          return;
        }
        warn(warning);
      },
      output: {
        manualChunks: {
          primevue: [
            'primevue',
            'vue',
            '@primevue/themes',
            '@primevue/icons',
            '@primeuix/styled',
            '@primeuix/themes',
            '@primeuix/utils',
          ],
          xlsx: ['xlsx'],
          codemirror: ['codemirror'],
          jupyterlab: [
            '@jupyterlab/coreutils',
            '@jupyterlab/mathjax-extension',
            '@jupyterlab/rendermime',
          ],
          pdfjs: ['pdfjs-dist'],
        },
      }
    }
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'esnext',
    },
  },
  resolve: {
    ...(baseConfig.resolve),
    alias: {
      ...(baseConfig.resolve?.alias),
      // Allows automatic updating when beaker-ts is updated, but will use the dist version of beaker-ts/beaker-kernel
      // when building or running in production mode.
      'beaker-kernel': (
        process.env.NODE_ENV === "development"
        ? fileURLToPath(new URL('../beaker-ts/src', import.meta.url))
        : 'beaker-kernel'
      ),
    },
    dedupe: [
      ...(baseConfig.resolve?.dedupe ?? []),
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
    ]
  }
};

export default defineConfig(appConfig);
