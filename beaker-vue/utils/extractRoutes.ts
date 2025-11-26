const fs = require('fs');
const path = require('path');

console.log("Extracting routes...")

// Generate just enough mock `window` to allow router to work.
globalThis.window = <any>{
    location: {
        "href":"about:blank",
        "origin":"",
        "protocol":"about:",
        "host":"blank",
        "hostname":"blank",
        "port":"",
        "pathname":"",
        "search":"",
        "hash":""
    },
    history: {
        length: 0,
        scrollRestoration: "auto",
        state: {},
    },
    addEventListener() {},
    removeEventListener() {},

};
globalThis.location = globalThis.window.location;

const createRouter = (await import('./src/router'))?.default;
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
// console.log("  dist/routes.json");
// fs.writeFileSync(path.resolve('dist/routes.json'), routeJson);
console.log("  html/routes.json");
fs.writeFileSync(path.resolve('html/routes.json'), routeJson);
console.log("Done.")
