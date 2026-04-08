import path from "path";

const pkg_json = process.env?.npm_package_json;

export const packageFile = pkg_json ? path.resolve(pkg_json) : path.resolve("package.json");
export const backupPackageFile = path.join(path.dirname(packageFile), `.${path.basename(packageFile)}.bak`);
export const distDir = path.resolve("dist");
