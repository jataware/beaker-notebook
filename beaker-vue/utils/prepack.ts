import fs from "fs";
import path from "path";
import { packageFile, backupPackageFile, distDir} from "./buildSetup";


// Backup original file before making changes
fs.copyFileSync(packageFile, backupPackageFile);

// Read in both json files
const pkg = JSON.parse(fs.readFileSync(packageFile).toString());
const exportData = JSON.parse(fs.readFileSync(path.join(distDir, "exports.json")).toString());

// Update exports in package.json data
pkg["exports"] = exportData;

// Write update package file
fs.writeFileSync(packageFile, JSON.stringify(pkg, null, 2), {"encoding": "utf8"})
