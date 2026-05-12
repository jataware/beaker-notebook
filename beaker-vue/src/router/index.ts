// Route-related type contracts and generic helpers. Part of the
// EXTENSION_API contract surface — extensions declare routes against these
// types.
//
// The concrete `defaultRouteMap`, `createRouter`, and `applyResolvedRoutes`
// implementations live in beaker-ui (host-side), since they're tied to
// specific host pages and the vue-router instance.

import type { RouteRecordRaw } from 'vue-router';

export type Slug = string;

export interface Page {
    slug?: Slug;
    title?: string;
    default?: boolean;
    stylesheet?: string | { [key: string]: string };
    template_bundle?: { [key: string]: string };
    role?: string;
}

export interface Route {
    path: string;
    component: any;
    componentPath?: string;
    role?: string;
    alias?: RouteRecordRaw['alias'];
}

/**
 * A route definition from the backend's resolved routes.
 * May include an `import` field for dynamically loaded page components.
 */
export interface ResolvedRoute {
    path: string;
    name: string;
    import?: string;
    export?: string;
    role?: string;
    default?: boolean;
}

export type Pages = { [key: Slug]: Page };
export type Routes = { [key: Slug]: Route };

/**
 * Convert a Routes map into vue-router's RouteRecordRaw[] format.
 * Pure utility; no defaults / host coupling.
 */
export const reformatRoutes = (
    routeMap: Routes,
    config: { [key: string]: string } = {},
): RouteRecordRaw[] => {
    const hasHomeRouteDefined = Object.hasOwn(routeMap, '/');
    return Object.entries(routeMap).map(([slug, routeObject]) => {
        const result: RouteRecordRaw = {
            path: routeObject.path,
            name: slug,
            component: routeObject.component,
            meta: {
                componentPath: routeObject.componentPath,
                role: routeObject.role,
            },
        };
        if (!hasHomeRouteDefined && routeObject.role === 'home') {
            result['alias'] = '/';
        }
        return result;
    });
};
