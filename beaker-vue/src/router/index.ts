import { createRouter as vueCreateRouter, createWebHistory } from 'vue-router'
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
}

export const reformatRoutes = (routeMap: Routes) => {
  const hasHomeRouteDefined = Object.hasOwn(routeMap, "/");
  return Object.entries(routeMap).map(([slug, routeObject]) => {
    const result: RouteRecordRaw = {
      path: routeObject.path,
      name: slug,
      component: routeObject.component,
      meta: {
        componentPath: routeObject.componentPath,
        role: routeObject.role,
      },
    }
    if (!hasHomeRouteDefined && routeObject.role === "home") {
      result["alias"] = "/";
    }
    return result;
  });
}

export const convertPagesToRoutes = (pages: Pages): Routes => {
  const pageRoutes = {};
  Object.values(pages).map((pageDef) => {
    if (Object.hasOwn(defaultRouteMap, pageDef.slug)) {
      const routeDef = {...defaultRouteMap[pageDef.slug]};
      if (routeDef.role) {
        routeDef.role = (pageDef.default ? "home" : "alt");
      }
      pageRoutes[pageDef.slug] = routeDef;
    }
  })
  return pageRoutes;
}

export const createRouter = (config) => {
  const routeMap = config?.appConfig?.pages
    ? convertPagesToRoutes(config.appConfig.pages)
    : { ...defaultRouteMap };

  // only include playground in development
  if (!import.meta.env.DEV) {
    delete routeMap.playground;
  }

  const routes = reformatRoutes(routeMap);

  return vueCreateRouter({
    history: createWebHistory(import.meta.env?.BASE_URL),
    routes,
  });
}

export default createRouter;
