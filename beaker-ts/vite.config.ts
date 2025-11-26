import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';



// https://vite.dev/config/
export default defineConfig({
  plugins: [
    dts({
      tsconfigPath: "tsconfig.json"
    })
  ],
  build: {
    lib: {
      name: "beaker-kernel",
      "entry": "src/index.ts",
      formats: ["es"],
      fileName: "beaker-kernel"
    },
    target: 'esnext',
    minify: false,
    outDir: 'dist/',
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
        "uuid",
        "node-fetch",
      ],
      preserveEntrySignatures: "exports-only",
      input: "src/index.ts",
      output: {
        preserveModules: true,
        preserveModulesRoot: "src/",
        inlineDynamicImports: false,
        entryFileNames: "[name].js"
      }
    }
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'esnext',
    },
  }
})
