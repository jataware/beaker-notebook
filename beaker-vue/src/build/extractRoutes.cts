#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

export default async function main(routerPath: string) {
    console.log("Extracting routes...");

    if ( globalThis.window === undefined ) {
        const jsdom = require("jsdom");
        const dom = new jsdom.JSDOM(``, {url: "https://beakerhub/"});
        globalThis.window = dom.window;
        globalThis.location = dom.window.location;
        globalThis.document = dom.window.document;
    }

    const createRouter = (await import(routerPath))?.default;
    const router = createRouter({});
    const routes = router.getRoutes();

    const output = Object.fromEntries(routes.map((route) => [
        route.path, {
            name: route.name,
            role: route.meta?.role,
            component: route.meta?.componentPath,
        }
    ]));

    const routeJson = JSON.stringify(output, undefined, 2);

    console.log("Writing route json file(s)...");
    console.log("  html/routes.json");
    fs.writeFileSync(path.resolve('html/routes.json'), routeJson);
    console.log("Done.");
}

// CLI entry point
const routerPath = process.argv[2];
if (!routerPath) {
    console.error("Usage: extractRoutes <routerPath>");
    process.exit(1);
}
main(path.resolve(routerPath));
