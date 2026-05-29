/** @type {import('typedoc').TypeDocOptions} */
export default {
    entryPoints: ["../src/index.ts", "../src/session.ts", "../src/notebook.ts", "../src/util.ts", "../src/history.ts"],
    //entryPoints: ["../src/index.ts", "../src/session.ts", "../src/notebook.ts", ],
    out: "../../docs/beaker-ts",
};
