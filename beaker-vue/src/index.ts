// Public API of beaker-vue. Maintained explicitly — DO NOT auto-glob.
// Changes to this surface are part of the EXTENSION_API_VERSION contract.
// See plans/beaker-ui-split.md for versioning policy.

// Component / composable / renderer / util namespaces.
export * as components from './components';
export * as composables from './composables';
export * as renderers from './renderers';
export * as utils from './util';

// Routing types (extensions defining routes import from here).
export * as router from './router';

// Directive bindings (host installs these via installBeakerHostPlugins;
// extensions can also reference them directly if needed).
export * as directives from './directives';

// Host plugin contract: install function + inject keys.
export * from './plugins';

// Workspace contract type.
export * from './types';

// Direct renderer convenience exports.
export {
    defaultRenderers,
    JSONRenderer,
    MarkdownRenderer,
    LatexRenderer,
    TableRenderer,
    JavascriptRenderer,
    wrapJupyterRenderer,
} from './renderers';
export type { BeakerMimeRenderer, BeakerRenderOutput } from './renderers';

// Extension API version constant.
export { EXTENSION_API_VERSION } from './EXTENSION_API_VERSION';
