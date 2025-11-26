import fs from "fs";
import { packageFile, backupPackageFile } from "./buildSetup";
const hashSum = require("hash-sum");

// Read in both json files
const pkg = JSON.parse(fs.readFileSync(packageFile).toString());

// Update exports in package.json data
pkg["exports"] = {};

// Write update package file
fs.writeFileSync(packageFile, JSON.stringify(pkg, null, 2), {"encoding": "utf8"})

if (fs.existsSync(backupPackageFile)) {
    const pkgSum = hashSum(fs.readFileSync(packageFile).toString());
    const bkupSum = hashSum(fs.readFileSync(backupPackageFile).toString());
    if (pkgSum === bkupSum) {
        fs.rmSync(backupPackageFile);
    }
    else {
        console.warn(`Warning: Restored package.json file does not match the backup file ${backupPackageFile}`)
    }
}
