import type { UserConfig, Plugin } from 'vite';

import { walk } from 'estree-walker';
import { EXTENSION_API_VERSION } from '../EXTENSION_API_VERSION';

/**
 * Packages that an extension's build externalizes — i.e., the host bundle
 * provides them at runtime via importmap, and the extension's output bundle
 * uses bare-specifier imports that resolve there.
 *
 * Bumps to this list (additions, removals) are part of the EXTENSION_API
 * contract surface and require an EXTENSION_API_VERSION bump.
 *
 * String entries are matched as exact module names plus any subpath
 * (e.g., "beaker-vue" matches both "beaker-vue" and "beaker-vue/foo").
 * Regex entries are matched against the full import specifier.
 */
export const EXTERNALIZED_PACKAGES: (string | RegExp)[] = [
    // Vue ecosystem
    /^vue($|\/)/,
    /^@vue\//,
    /^pinia($|\/)/,
    /^vue-router($|\/)/,
    // PrimeVue
    /^primevue($|\/)/,
    /^@primevue\//,
    /^@primeuix\//,
    'primeicons',
    // Jupyter
    /^@jupyterlab\//,
    /^@lumino\//,
    /^@jupyter\//,
    // CodeMirror
    /^@codemirror\//,
    /^codemirror($|\/)/,
    '@plutojl/lang-julia',
    'codemirror-lang-r',
    // Beaker packages (host provides these)
    /^beaker-vue($|\/)/,
    /^beaker-kernel($|\/)/,
    // Other commonly-shared runtime deps
    'marked',
    'katex',
    'cytoscape',
    'uuid',
    'lodash',
    'json5',
    'filesize',
    'hash-sum',
    'escape-html',
    'content-disposition',
    'cookie',
    'panel',
    'buffer',
    'path-browserify',
    'scroll-into-view-if-needed',
    'pdfjs-dist',
    'xlsx',
];

/**
 * Returns true if the given import specifier matches one of the
 * EXTERNALIZED_PACKAGES patterns.
 */
function isExternalized(id: string): boolean {
    for (const pattern of EXTERNALIZED_PACKAGES) {
        if (typeof pattern === 'string') {
            if (id === pattern || id.startsWith(pattern + '/')) {
                return true;
            }
        } else if (pattern.test(id)) {
            return true;
        }
    }
    return false;
}

/**
 * Creates a Vite configuration for building Beaker extension bundles
 * (renderers, pages, etc.).
 *
 * Externalizes the host-provided runtime packages (see
 * EXTERNALIZED_PACKAGES) so the host's importmap resolves them at runtime.
 * Handles Vue/JSX compilation, CSS injection, and ES module output.
 *
 * Extension packages typically only need to provide overrides for
 * extension-specific concerns (extra plugins, resolve aliases, additional
 * entry points).
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
        external: (id) => {
          // Bundle relative / absolute / virtual imports (the extension's own code).
          if (id.startsWith('.') || id.startsWith('/') || id.startsWith('\0')) {
            return false;
          }
          return isExternalized(id);
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

// Call-expression wrappers we recursively unwrap to find the underlying
// import(). `__vitePreload` is the most important: vite rewrites all
// dynamic imports through it at transform time, so by the time
// generateBundle runs, every `() => import(...)` has become
// `() => __vitePreload(() => import(...), ...)`.
const UNWRAP_CALL_WRAPPERS = new Set([
  'defineAsyncComponent',
  '__vitePreload',
]);

/**
 * Extract an ImportExpression from various component definition patterns:
 *   - () => import('./Foo.vue')
 *   - () => { return import('./Foo.vue') }
 *   - defineAsyncComponent(() => import('./Foo.vue'))
 *   - import('./Foo.vue')  (bare import expression)
 *   - () => __vitePreload(() => import('./Foo.vue'), ...) (vite post-transform)
 */
function findImportExpression(node: any): any | null {
  if (!node) return null;

  // Direct ImportExpression
  if (node.type === 'ImportExpression') {
    return node;
  }

  // Arrow: () => <body>
  if (node.type === 'ArrowFunctionExpression') {
    // Concise body: recurse into the body (handles import, wrapped call, etc.)
    if (node.body && node.body.type !== 'BlockStatement') {
      return findImportExpression(node.body);
    }
    // Block body: () => { return <expr> }
    if (node.body?.type === 'BlockStatement') {
      for (const stmt of node.body.body) {
        if (stmt.type === 'ReturnStatement') {
          const result = findImportExpression(stmt.argument);
          if (result) return result;
        }
      }
    }
  }

  // Function expression: function() { return <expr> }
  if (node.type === 'FunctionExpression' && node.body?.type === 'BlockStatement') {
    for (const stmt of node.body.body) {
      if (stmt.type === 'ReturnStatement') {
        const result = findImportExpression(stmt.argument);
        if (result) return result;
      }
    }
  }

  // Call expression: unwrap recognized wrappers (defineAsyncComponent, __vitePreload, etc.)
  if (node.type === 'CallExpression'
      && node.callee?.type === 'Identifier'
      && UNWRAP_CALL_WRAPPERS.has(node.callee.name)
      && node.arguments?.length > 0) {
    return findImportExpression(node.arguments[0]);
  }

  return null;
}

interface RawRouteInfo {
  /** All literal-valued fields from the route object, passed through verbatim. */
  fields: Record<string, string | number | boolean | null>;
  /** Raw source path from the import() expression in the `component` field. */
  sourceImport?: string;
}

/**
 * Errors collected while walking the AST. We accumulate rather than throwing
 * eagerly so the build error reports every issue at once.
 */
interface ExtractionErrors {
  noRoutesObject: boolean;
  emptyRoutesObject: boolean;
  nonLiteralFields: Array<{ slug: string; field: string }>;
  unsupportedComponentShape: string[]; // slug list
  missingRequiredFields: Array<{ slug: string; field: 'path' | 'name' }>;
}

function extractRoutesFromAst(ast: any, routeIdentifier: string): {
  routes: Record<string, RawRouteInfo>;
  errors: ExtractionErrors;
} {
  const routes: Record<string, RawRouteInfo> = {};
  const errors: ExtractionErrors = {
    noRoutesObject: true,
    emptyRoutesObject: false,
    nonLiteralFields: [],
    unsupportedComponentShape: [],
    missingRequiredFields: [],
  };

  walk(ast, {
    enter(node: any) {
      // Match: const <routeIdentifier> = { ... }
      // Also match: export const <routeIdentifier> = { ... }
      if (node.type === 'VariableDeclarator'
          && node.id?.type === 'Identifier'
          && node.id.name === routeIdentifier
          && node.init?.type === 'ObjectExpression') {

        errors.noRoutesObject = false;
        if (node.init.properties.length === 0) {
          errors.emptyRoutesObject = true;
        }

        for (const routeProp of node.init.properties) {
          if (routeProp.type === 'SpreadElement') continue;
          if (routeProp.type !== 'Property') continue;

          const slug = routeProp.key.value ?? routeProp.key.name;
          if (routeProp.value?.type !== 'ObjectExpression') continue;

          const route: RawRouteInfo = { fields: {} };

          for (const prop of routeProp.value.properties) {
            if (prop.type !== 'Property') continue;
            const key = prop.key.value ?? prop.key.name;

            if (key === 'component') {
              const importExpr = findImportExpression(prop.value);
              if (importExpr?.source?.type === 'Literal') {
                route.sourceImport = importExpr.source.value;
              } else {
                errors.unsupportedComponentShape.push(slug);
              }
            } else if (prop.value.type === 'Literal') {
              // Generic literal pass-through for any other field.
              route.fields[key] = prop.value.value;
            } else {
              errors.nonLiteralFields.push({ slug, field: key });
            }
          }

          // Default `name` to the slug if not provided.
          if (route.fields.name === undefined) {
            route.fields.name = slug;
          }

          // Required-field checks.
          if (typeof route.fields.path !== 'string' || route.fields.path === '') {
            errors.missingRequiredFields.push({ slug, field: 'path' });
          }
          if (typeof route.fields.name !== 'string' || route.fields.name === '') {
            errors.missingRequiredFields.push({ slug, field: 'name' });
          }

          routes[slug] = route;
        }

        this.skip();
      }
    },
  });

  return { routes, errors };
}

/**
 * Format extraction errors into a multi-line message for the build error.
 * Returns null if there are no errors.
 */
function formatExtractionErrors(errors: ExtractionErrors, routesFile: string, routeIdentifier: string): string | null {
  const lines: string[] = [];

  if (errors.noRoutesObject) {
    lines.push(
      `outputJsonRoutesPlugin: No '${routeIdentifier}' identifier with an object-literal value found in '${routesFile}'.`,
    );
  }
  if (errors.emptyRoutesObject) {
    lines.push(`outputJsonRoutesPlugin: '${routeIdentifier}' is an empty object.`);
  }
  for (const { slug, field } of errors.missingRequiredFields) {
    lines.push(`outputJsonRoutesPlugin: Route '${slug}' is missing required field '${field}'.`);
  }
  for (const { slug, field } of errors.nonLiteralFields) {
    lines.push(
      `outputJsonRoutesPlugin: Route '${slug}' field '${field}' is not a literal value. ` +
      `Routes must be statically analyzable; field values must be string/number/boolean literals.`,
    );
  }
  for (const slug of errors.unsupportedComponentShape) {
    lines.push(
      `outputJsonRoutesPlugin: Route '${slug}' has an unsupported 'component' shape. ` +
      `Use one of: () => import('./Foo.vue'), function() { return import('./Foo.vue') }, ` +
      `or defineAsyncComponent(() => import('./Foo.vue')).`,
    );
  }

  return lines.length === 0 ? null : lines.join('\n');
}

/**
 * Vite plugin that extracts route metadata from a routes file at build
 * time and emits a `routes.json` next to the bundle.
 *
 * Supported routes-file shape (part of the EXTENSION_API contract):
 *
 *   export const routes = {
 *     "my-page": {
 *       path: "/my-page",                                 // required, string literal
 *       name: "My Page",                                  // optional, defaults to slug
 *       role: "home",                                     // optional
 *       component: () => import('./MyPage.vue'),          // required, import expression
 *       // ...any other string/number/boolean literal fields are passed through
 *     },
 *   };
 *
 * The variable identifier defaults to `routes` and can be overridden via
 * the `routeIdentifier` argument. Non-literal field values cause a hard
 * build error — routes must be statically analyzable.
 *
 * Emitted output is an envelope:
 *   { "extensionApiVersion": "1.0", "routes": { ... } }
 */
export function outputJsonRoutesPlugin(routesFile: string = "./src/routes.ts", routeIdentifier: string = "routes"): Plugin {
  let routesFileInfo: { id: string } | null = null;

  return {
    name: 'emit-routes-json',

    async buildStart() {
      routesFileInfo = await this.resolve(routesFile);
      if (!routesFileInfo) {
        this.error(`outputJsonRoutesPlugin: Could not resolve routes file '${routesFile}'`);
      }
    },

    async generateBundle(_options, bundle) {
      if (!routesFileInfo) return;

      const mod = this.getModuleInfo(routesFileInfo.id);
      if (!mod?.ast) {
        this.error(`outputJsonRoutesPlugin: No AST available for '${routesFileInfo.id}'`);
        return;
      }

      const { routes: rawRoutes, errors } = extractRoutesFromAst(mod.ast, routeIdentifier);

      const errorMsg = formatExtractionErrors(errors, routesFileInfo.id, routeIdentifier);
      if (errorMsg) {
        this.error(errorMsg);
        return;
      }

      // Build a mapping from resolved module IDs to output chunk filenames.
      // Each chunk's moduleIds contains the resolved absolute paths of every
      // module that was rolled into that chunk.
      const moduleIdToChunkFile: Record<string, string> = {};
      for (const [fileName, chunk] of Object.entries(bundle)) {
        if (chunk.type !== 'chunk') continue;
        if (chunk.facadeModuleId) {
          moduleIdToChunkFile[chunk.facadeModuleId] = fileName;
        }
        for (const moduleId of chunk.moduleIds) {
          moduleIdToChunkFile[moduleId] = fileName;
        }
      }

      // Resolve each route's source import path to an output filename.
      const outputRoutes: Record<string, Record<string, any>> = {};
      for (const [slug, route] of Object.entries(rawRoutes)) {
        const outputRoute: Record<string, any> = { ...route.fields };

        if (route.sourceImport) {
          const resolved = await this.resolve(route.sourceImport, routesFileInfo.id);
          if (!resolved) {
            this.error(`Route '${slug}': could not resolve import '${route.sourceImport}'`);
            return;
          }
          const chunkFile = moduleIdToChunkFile[resolved.id];
          if (!chunkFile) {
            this.error(
              `Route '${slug}': resolved module '${resolved.id}' not found in any output chunk. ` +
              `Ensure the component is included in a build entry point.`,
            );
            return;
          }
          outputRoute.import = chunkFile;
          outputRoute.export = 'default';
        }

        outputRoutes[slug] = outputRoute;
      }

      const envelope = {
        extensionApiVersion: EXTENSION_API_VERSION,
        routes: outputRoutes,
      };

      this.emitFile({
        type: 'asset',
        needsCodeReference: false,
        fileName: 'routes.json',
        source: JSON.stringify(envelope, null, 2),
      });
    },
  };
}
