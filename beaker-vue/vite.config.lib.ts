import { defineConfig, type UserConfig } from 'vite';
import dts from 'vite-plugin-dts';
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";
import { entryPoints, baseConfig } from './vite.config';

export const libConfig: UserConfig = {
  ...baseConfig,
  plugins: [
    ...(baseConfig.plugins ?? []),
    cssInjectedByJsPlugin({
      relativeCSSInjection: true,
    }),
    dts({
      tsconfigPath: "tsconfig.lib.json",
      insertTypesEntry: true,
      declarationOnly: false,
      outDir: "./dist",
      logLevel: "error",
    }),
    {
      name: "export-exports",
      buildStart(options) {
        const prefix = './dist/';
        const exportObject = Object.fromEntries(
          Object.keys(entryPoints).map((key) => {
            const importPath = ('./' + key.replace(/(^|\/)index/, '')).replace(/\/$/, '');
            return [
                importPath,
                {
                  import: `${prefix}${key}.js`,
                  types: `${prefix}${key}.d.ts`
                }
              ]
            ;
          })
        );
        this.emitFile({
          type: "asset",
          fileName: "exports.json",
          source: JSON.stringify(exportObject, null, 2),
        });
      }
    }
  ],
  build: {
    ...baseConfig.build,
    target: 'esnext',
    minify: false,
    outDir: 'dist',
    cssCodeSplit: true,
    lib: {
      entry: entryPoints,
      formats: ["es"],
      fileName: (format, entryName) => {
        return `${entryName}.js`
      },

    },
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
      external: [
        /^@?codemirror/,
        /^@?jupyterlab/,
        /^@?plutojl/,
        /^@?primevue/,
        /^@?primeuix/,
        "ansi-html-community",
        "beaker-kernel",
        "buffer",
        "content-disposition",
        "cookie",
        "cytoscape",
        "escape-html",
        "filesize",
        "hash-sum",
        "isomorphic-fetch",
        "json5",
        "katex",
        "marked",
        "panel",
        "path-browserify",
        "pinia",
        "primeicons",
        "scroll-into-view-if-needed",
        "uuid",
        /^vue/,
      ],
      preserveEntrySignatures: "allow-extension",
    },
  }
};

export default defineConfig(libConfig);
