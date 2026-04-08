import type { UserConfig, Plugin, ResolvedConfig } from 'vite';
// import type { UserConfig, Plugin, ResolvedConfig, EmittedAsset, ModuleInfo } from 'vite';
import type { EmittedAsset, ModuleInfo, PluginContext } from 'rollup';

import { walk } from 'estree-walker';


// const { UserConfig, Plugin, ResolvedConfig } = require("vite");

/**
 * Creates a Vite configuration for building context renderer ES modules.
 *
 * Handles Vue/JSX compilation, CSS injection, ES module output, and
 * externalizes vue/beaker-vue/beaker-kernel so they resolve at runtime
 * from the Beaker static file server.
 *
 * Context packages only need to provide overrides for context-specific
 * concerns (extra plugins, resolve aliases, additional entry points).
 */
export async function defineBeakerRendererConfig(overrides?: UserConfig): Promise<UserConfig> {
  const vue = (await import('@vitejs/plugin-vue')).default;
  const vueJsx = (await import('@vitejs/plugin-vue-jsx')).default;
  const cssInjectedByJsPlugin = (await import ("vite-plugin-css-injected-by-js")).default;
  const mergeConfig = (await import('vite')).mergeConfig;

  const base: UserConfig = {
    plugins: [
      vue(),
      vueJsx(),
      cssInjectedByJsPlugin({
          relativeCSSInjection: true,
      }),
      sanitizeJupyterEval(),
    ],
    build: {
      target: 'esnext',
      minify: false,
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
        // external: ['vue', 'beaker-vue', 'beaker-kernel'],
        // external: ['vue'],
        // external: (id) => {
        //   // Bundle only relative/absolute imports (your own code)
        //   if (id.startsWith('.') || id.startsWith('/') || id.startsWith('\0')) return false;
        //   if ((id.startsWith('jupyter') || id.startsWith('@jupyter')) && ![
        //     '@jupyterlab/coreutils',
        //     '@jupyterlab/apputils',
        //     '@jupyterlab/services/lib/serverconnection',
        //     '@jupyterlab/services',
        //     '@jupyterlab/services/lib/kernel/messages',
        //     '@jupyterlab/services/lib/kernel/future',
        //     '@jupyterlab/nbformat',
        //     '@jupyterlab/rendermime',
        //   ].includes(id)) return true;

        //   return false;
        // },
        output: {
          paths: {
            vue: '/static/vue.esm-browser.prod.js?url',
          },
        },
      },
    },
    optimizeDeps: {
      esbuildOptions: {
        target: 'esnext',
      },
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify('production'),
      'global': 'globalThis',
    },
  };
  return mergeConfig(base, overrides ?? {});
}

export function sanitizeJupyterEval(): Plugin {
  return {
    name: "sanitize-eval",
    transform(src, id) {
      // Custom inline plugin to replace 'eval()' calls with 'console.debug()'.
      if (id.includes("@jupyterlab/coreutils/lib/pageconfig")) {
        return src.replaceAll(/\beval\b/g, 'console.debug');
      }
    }
  }
}

/**
 * Extract an ImportExpression from various component definition patterns:
 *   - () => import('./Foo.vue')
 *   - () => { return import('./Foo.vue') }
 *   - defineAsyncComponent(() => import('./Foo.vue'))
 *   - import('./Foo.vue')  (bare import expression)
 */
function findImportExpression(node: any): any | null {
  if (!node) return null;

  // Direct ImportExpression
  if (node.type === 'ImportExpression') {
    return node;
  }

  // Arrow: () => import(...)
  if (node.type === 'ArrowFunctionExpression') {
    // Concise body: () => import(...)
    if (node.body?.type === 'ImportExpression') {
      return node.body;
    }
    // Block body: () => { return import(...) }
    if (node.body?.type === 'BlockStatement') {
      for (const stmt of node.body.body) {
        if (stmt.type === 'ReturnStatement' && stmt.argument?.type === 'ImportExpression') {
          return stmt.argument;
        }
      }
    }
  }

  // Function expression: function() { return import(...) }
  if (node.type === 'FunctionExpression' && node.body?.type === 'BlockStatement') {
    for (const stmt of node.body.body) {
      if (stmt.type === 'ReturnStatement' && stmt.argument?.type === 'ImportExpression') {
        return stmt.argument;
      }
    }
  }

  // defineAsyncComponent(() => import(...))
  if (node.type === 'CallExpression'
      && node.callee?.type === 'Identifier'
      && node.callee.name === 'defineAsyncComponent'
      && node.arguments?.length > 0) {
    return findImportExpression(node.arguments[0]);
  }

  return null;
}

interface RawRouteInfo {
  path: string;
  name: string;
  role?: string;
  sourceImport?: string;  // raw source path from the import() expression
}

function extractRoutesFromAst(ast: any, routeIdentifier: string): Record<string, RawRouteInfo> {
  const routeObject: Record<string, RawRouteInfo> = {};
  walk(ast, {
    enter(node: any) {
      // Match: const <routeIdentifier> = { ... }
      // Also match: export const <routeIdentifier> = { ... }
      if (node.type === 'VariableDeclarator'
          && node.id?.type === 'Identifier'
          && node.id.name === routeIdentifier
          && node.init?.type === 'ObjectExpression') {

        for (const routeProp of node.init.properties) {
          if (routeProp.type !== 'Property' && routeProp.type !== 'SpreadElement') continue;
          if (routeProp.type === 'SpreadElement') continue;

          const routeName = routeProp.key.value ?? routeProp.key.name;
          const route: RawRouteInfo = { path: '', name: routeName };

          if (routeProp.value?.type !== 'ObjectExpression') continue;

          for (const prop of routeProp.value.properties) {
            if (prop.type !== 'Property') continue;
            const key = prop.key.value ?? prop.key.name;

            switch (key) {
              case 'path':
              case 'role':
              case 'name':
                if (prop.value.type === 'Literal') {
                  route[key] = prop.value.value;
                }
                break;
              case 'component': {
                const importExpr = findImportExpression(prop.value);
                if (importExpr?.source?.type === 'Literal') {
                  route.sourceImport = importExpr.source.value;
                }
                break;
              }
            }
          }

          routeObject[routeName] = route;
        }

        this.skip();
      }
    },
  });
  return routeObject;
}

export function outputJsonRoutesPlugin(routesFile: string = "./src/routes.ts", routeIdentifier: string = "routes"): Plugin {
  let routesFileInfo: { id: string } | null = null;

  return {
    name: 'emit-routes-json',

    async buildStart() {
      routesFileInfo = await this.resolve(routesFile);
      if (!routesFileInfo) {
        this.warn(`outputJsonRoutesPlugin: Could not resolve routes file '${routesFile}'`);
      }
    },

    async generateBundle(_options, bundle) {
      if (!routesFileInfo) return;

      const mod = this.getModuleInfo(routesFileInfo.id);
      if (!mod?.ast) {
        this.warn(`outputJsonRoutesPlugin: No AST available for '${routesFileInfo.id}'`);
        return;
      }

      const rawRoutes = extractRoutesFromAst(mod.ast, routeIdentifier);

      // Build a mapping from resolved module IDs to output chunk filenames.
      // Each chunk's moduleIds contains the resolved absolute paths of every
      // module that was rolled into that chunk.
      const moduleIdToChunkFile: Record<string, string> = {};
      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type !== 'chunk') continue;
        // facadeModuleId is the entry point's resolved ID
        if (chunk.facadeModuleId) {
          moduleIdToChunkFile[chunk.facadeModuleId] = fileName;
        }
        // Also index all modules in this chunk for non-entry imports
        for (const moduleId of chunk.moduleIds) {
          moduleIdToChunkFile[moduleId] = fileName;
        }
      }

      // Resolve each route's source import path to an output filename
      const outputRoutes: Record<string, { path: string; name: string; role?: string; import?: string; export?: string }> = {};
      for (const [slug, route] of Object.entries(rawRoutes)) {
        const outputRoute: typeof outputRoutes[string] = {
          path: route.path,
          name: route.name,
        };
        if (route.role) {
          outputRoute.role = route.role;
        }

        if (route.sourceImport) {
          // Resolve the relative import path to an absolute module ID
          const resolved = await this.resolve(route.sourceImport, routesFileInfo.id);
          if (resolved) {
            const chunkFile = moduleIdToChunkFile[resolved.id];
            if (chunkFile) {
              outputRoute.import = chunkFile;
              outputRoute.export = 'default';
            } else {
              this.warn(
                `Route '${slug}': resolved module '${resolved.id}' not found in any output chunk. ` +
                `Ensure the component is included in a build entry point.`
              );
            }
          } else {
            this.warn(`Route '${slug}': could not resolve import '${route.sourceImport}'`);
          }
        }

        outputRoutes[slug] = outputRoute;
      }

      this.emitFile({
        type: 'asset',
        needsCodeReference: false,
        fileName: 'routes.json',
        source: JSON.stringify(outputRoutes, null, 2),
      });
    },
  };
}
