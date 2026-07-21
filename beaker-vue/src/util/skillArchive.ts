import { unzipSync, strFromU8 } from 'fflate';

// Client-side parsing of an uploaded skill (a bare SKILL.md or a .zip). The zip
// is unpacked in the browser (no temp files); we locate SKILL.md, enumerate the
// valid resource files, and return everything as text so the caller can preview
// (via the backend SKILL.md parser) and upload on save through the normal
// add-integration + resource CRUD paths. The real security boundary stays
// server-side: every resource write is re-validated there. These caps only
// protect the user's own tab from a pathological archive.
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_ENTRIES = 2000;
const MAX_TOTAL_BYTES = 100 * 1024 * 1024;

// Subtrees whose files become skill resources (mirrors the backend
// SKILL_RESOURCE_DIRS). Both "references" and the singular "reference" are
// recognized because real skills use the singular form. Anything outside these
// (and SKILL.md / examples) is ignored.
const RESOURCE_DIRS = ['references', 'reference', 'scripts', 'assets'];

export interface EnumeratedResource {
    resource_type: 'skill_file' | 'skill_example';
    // skill_file
    relative_path?: string;
    name?: string;
    // skill_example
    filename?: string;
    content: string;
}

export interface ParsedSkillUpload {
    skillMd: string;
    resources: EnumeratedResource[];
    // Paths that were skipped because they were not valid UTF-8 text (binary
    // assets are not yet supported); surfaced to the user, not silently dropped.
    skipped: string[];
}

const isZipFile = (file: File): boolean =>
    file.name.toLowerCase().endsWith('.zip')
    || file.type === 'application/zip'
    || file.type === 'application/x-zip-compressed';

// Heuristic text check: reject on NUL bytes, otherwise require a strict UTF-8
// decode. Keeps binary assets out of the text-only resource pipeline.
const isProbablyText = (bytes: Uint8Array): boolean => {
    const sample = bytes.subarray(0, 8192);
    if (sample.includes(0)) {
        return false;
    }
    try {
        new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        return true;
    } catch {
        return false;
    }
};

export async function parseSkillUpload(file: File): Promise<ParsedSkillUpload> {
    if (file.size > MAX_FILE_BYTES) {
        throw new Error(`File is too large (${Math.round(file.size / 1024 / 1024)} MB); the limit is ${MAX_FILE_BYTES / 1024 / 1024} MB.`);
    }
    const buffer = new Uint8Array(await file.arrayBuffer());

    if (!isZipFile(file)) {
        // A bare SKILL.md (any single text file is treated as the SKILL.md body).
        return { skillMd: new TextDecoder('utf-8').decode(buffer), resources: [], skipped: [] };
    }

    let entries: Record<string, Uint8Array>;
    try {
        entries = unzipSync(buffer);
    } catch (e) {
        throw new Error(`Could not read the ZIP archive: ${(e as Error)?.message ?? 'unknown error'}`);
    }

    const paths = Object.keys(entries).filter((p) => !p.endsWith('/'));
    if (paths.length > MAX_ENTRIES) {
        throw new Error(`Archive has ${paths.length} files; the limit is ${MAX_ENTRIES}.`);
    }
    let total = 0;
    for (const p of paths) {
        total += entries[p].length;
        if (total > MAX_TOTAL_BYTES) {
            throw new Error('Archive contents are too large to import in the browser.');
        }
    }

    // Locate SKILL.md at the archive root or exactly one directory deep.
    const skillMdPaths = paths.filter((p) => {
        const parts = p.split('/');
        return (parts.length === 1 && parts[0] === 'SKILL.md')
            || (parts.length === 2 && parts[1] === 'SKILL.md');
    });
    if (skillMdPaths.length === 0) {
        throw new Error('No SKILL.md found at the archive root or one directory deep.');
    }
    if (skillMdPaths.length > 1) {
        throw new Error('The archive contains more than one SKILL.md; it must contain exactly one.');
    }

    const skillMdPath = skillMdPaths[0];
    const rootPrefix = skillMdPath.includes('/')
        ? skillMdPath.slice(0, skillMdPath.lastIndexOf('/') + 1)
        : '';
    const skillMd = new TextDecoder('utf-8').decode(entries[skillMdPath]);

    const resources: EnumeratedResource[] = [];
    const skipped: string[] = [];

    for (const p of paths) {
        if (p === skillMdPath) {
            continue;
        }
        // Ignore anything outside the located skill directory.
        if (rootPrefix && !p.startsWith(rootPrefix)) {
            continue;
        }
        const rel = rootPrefix ? p.slice(rootPrefix.length) : p;
        const parts = rel.split('/');
        const top = parts[0];

        if (top === 'examples') {
            // Examples are flat (examples/<file>); ignore nested paths.
            if (parts.length !== 2) {
                continue;
            }
            const bytes = entries[p];
            if (!isProbablyText(bytes)) {
                skipped.push(rel);
                continue;
            }
            resources.push({ resource_type: 'skill_example', filename: parts[1], content: strFromU8(bytes) });
        } else if (RESOURCE_DIRS.includes(top)) {
            const bytes = entries[p];
            if (!isProbablyText(bytes)) {
                skipped.push(rel);
                continue;
            }
            resources.push({
                resource_type: 'skill_file',
                relative_path: rel,
                name: parts[parts.length - 1],
                content: strFromU8(bytes),
            });
        }
        // Everything else (stray top-level files, other directories) is ignored.
    }

    return { skillMd, resources, skipped };
}
