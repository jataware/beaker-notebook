import { createRouter as vueCreateRouter, createWebHistory } from 'vue-router';
import { defineAsyncComponent } from 'vue';
import { router as bvRouter } from 'beaker-vue';
const { reformatRoutes } = bvRouter;
type Pages = bvRouter.Pages;
type Routes = bvRouter.Routes;
type ResolvedRoute = bvRouter.ResolvedRoute;


export const defaultRouteMap: Routes = {
    "notebook": {
        "path": "/notebook",
        "component": () => import('@/pages/NotebookInterface.vue'),
        "role": "home",
    },
    "chat": {
        "path": "/chat",
        "component": () => import('@/pages/ChatInterface.vue'),
        "role": "alt",
    },
    "integrations": {
        "path": "/integrations",
        "component": () => import('@/pages/IntegrationsInterface.vue'),
    },
    "admin": {
        "path": "/admin",
        "component": () => import('@/pages/BeakerAdmin.vue'),
    },
    "playground": {
        "path": "/playground",
        "component": () => import('@/pages/PlaygroundInterface.vue'),
    },
};

export const convertPagesToRoutes = (pages: Pages): Routes => {
    const pageRoutes: Routes = {};
    Object.values(pages).map((pageDef) => {
        if (Object.hasOwn(defaultRouteMap, pageDef.slug)) {
            const routeDef = { ...defaultRouteMap[pageDef.slug] };
            if (routeDef.role) {
                routeDef.role = (pageDef.default ? "home" : "alt");
            }
            pageRoutes[pageDef.slug] = routeDef;
        }
    });
    return pageRoutes;
};

/**
 * Apply resolved routes from the backend config onto a route map.
 * Routes with an `import` field get a dynamically loaded component.
 * Routes without `import` are matched against the defaultRouteMap.
 */
export const applyResolvedRoutes = (
    routeMap: Routes,
    resolvedRoutes: { [path: string]: ResolvedRoute },
): Routes => {
    for (const [, routeDef] of Object.entries(resolvedRoutes)) {
        const slug = routeDef.name;
        if (routeDef.import && !routeDef.default) {
            // Defensively normalize: dynamic import() treats specifiers
            // without a './' / '../' / '/' prefix as bare module specifiers
            // and looks them up in the importmap. For chunk file paths,
            // we want them resolved as URLs — prepend '/' if needed.
            // (The Python handler also normalizes; this is belt + suspenders.)
            let importUrl = routeDef.import;
            if (!importUrl.startsWith('/') && !importUrl.startsWith('./') && !importUrl.startsWith('../')) {
                importUrl = `/${importUrl}`;
            }
            const exportName = routeDef.export || "default";
            routeMap[slug] = {
                path: routeDef.path,
                component: defineAsyncComponent(async () => {
                    const mod = await import(/* @vite-ignore */ importUrl);
                    return mod[exportName] ?? mod.default;
                }),
                role: routeDef.role,
            };
        } else if (Object.hasOwn(defaultRouteMap, slug)) {
            routeMap[slug] = {
                ...defaultRouteMap[slug],
                path: routeDef.path,
                role: routeDef.role ?? defaultRouteMap[slug].role,
            };
        }
    }
    return routeMap;
};

export const createRouter = (config: any) => {
    let routeMap: Routes;

    if (config?.appConfig?.pages) {
        routeMap = convertPagesToRoutes(config.appConfig.pages);
    } else {
        routeMap = { ...defaultRouteMap };
    }

    if (config?.routes) {
        applyResolvedRoutes(routeMap, config.routes);
    }

    if (!(import.meta?.env?.DEV)) {
        delete routeMap.playground;
    }

    const routes = reformatRoutes(routeMap, config);

    return vueCreateRouter({
        history: createWebHistory(config.pathPrefix),
        routes,
    });
};

export default createRouter;
