import { defineConfig, type UserConfig } from 'vite';
import dts from 'vite-plugin-dts';
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";
import { baseConfig } from './vite.config';

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
  ],
  build: {
    ...baseConfig.build,
    target: 'esnext',
    minify: false,
    outDir: 'dist',
    cssCodeSplit: true,
    lib: {
      // Curated entries:
      //   - `index` is the root barrel (everything runtime-side).
      //   - `builder/build` is the build-time helpers subpath.
      // No per-file glob; consumers import from these entries via the
      // package.json exports map.
      entry: {
        index: './src/index.ts',
        'builder/build': './src/builder/build.ts',
      },
      formats: ["es"],
      fileName: (_format, entryName) => `${entryName}.mjs`,
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
      // Externalize every npm dep — consumers bring their own. The lib only
      // bundles its own source files (relative/absolute/virtual imports).
      external: (id) => {
        if (id.startsWith('.') || id.startsWith('/') || id.startsWith('\0')) {
          return false;
        }
        return true;
      },
      preserveEntrySignatures: "allow-extension",
    },
  }
};

export default defineConfig(libConfig);
