import { createRouter as vueCreateRouter, createWebHistory } from 'vue-router';
import { defineAsyncComponent } from 'vue';
import type { RouteRecordRaw } from 'vue-router';

export type Slug = string;

export interface Page {
  slug?: Slug;
  title?: string;
  default?: boolean;
  stylesheet?: string | {[key: string]: string};
  template_bundle?: {[key: string]: string};
  role?: string;
}

export interface Route {
    path: string;
    component: any;
    componentPath?: string;
    role?: string;
    alias?: RouteRecordRaw["alias"];
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
}

export type Pages = { [key: Slug]: Page}
export type Routes = { [key: Slug]: Route }

export const defaultRouteMap: Routes = {
    "notebook": {
      "path": "/notebook",
      "component": () => import('@/pages/NextNotebookInterface.vue'),
      "role": "home",
    },
    "next-notebook": {
      "path": "/legacy",
      "component": () => import('@/pages/NotebookInterface.vue'),
      "role": "alt",
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
    "dev": {
      "path": "/dev",
      "component": () => import('@/pages/DevInterface.vue'),
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

export const reformatRoutes = (routeMap: Routes, config: {[key: string]: string} = {}) => {
  const hasHomeRouteDefined = Object.hasOwn(routeMap, "/");
  const pathPrefix = config?.pathPrefix || "";
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
    if (!hasHomeRouteDefined && routeObject.role === "home") {
      result["alias"] = "/";
    }
    return result;
  });
};

export const convertPagesToRoutes = (pages: Pages): Routes => {
  const pageRoutes: Routes = {};
  Object.values(pages).map((pageDef) => {
    if (Object.hasOwn(defaultRouteMap, pageDef.slug)) {
      const routeDef = {...defaultRouteMap[pageDef.slug]};
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
export const applyResolvedRoutes = (routeMap: Routes, resolvedRoutes: {[path: string]: ResolvedRoute}): Routes => {
  for (const [, routeDef] of Object.entries(resolvedRoutes)) {
    const slug = routeDef.name;
    if (routeDef.import) {
      // Dynamic import — load the page component from the asset URL
      const importUrl = routeDef.import;
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
      // Known built-in route — use the default component
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

  // Apply resolved routes from backend (includes dynamic imports from asset routes.json)
  if (config?.routes) {
    applyResolvedRoutes(routeMap, config.routes);
  }

  // Only include playground in development
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
