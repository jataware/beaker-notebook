import { describe, it, expect } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { parseSkillUpload, type EnumeratedResource } from '../skillArchive';

const SKILL_MD = '---\nname: test-skill\ndescription: A test skill.\n---\n# Test\n\nBody.';

// jsdom's File does not implement arrayBuffer(); build a minimal File-like with
// the fields parseSkillUpload uses (name/type/size/arrayBuffer). In a real
// browser the native File provides all of these.
function fakeFile(bytes: Uint8Array, name: string, type: string): File {
    return {
        name,
        type,
        size: bytes.byteLength,
        arrayBuffer: async () =>
            bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    } as unknown as File;
}

function zipFile(files: Record<string, Uint8Array>, name = 'skill.zip'): File {
    return fakeFile(zipSync(files), name, 'application/zip');
}

function mdFile(text: string, name = 'SKILL.md'): File {
    return fakeFile(strToU8(text), name, 'text/markdown');
}

const relPaths = (resources: EnumeratedResource[]) =>
    resources.filter((r) => r.resource_type === 'skill_file').map((r) => r.relative_path).sort();
const exampleNames = (resources: EnumeratedResource[]) =>
    resources.filter((r) => r.resource_type === 'skill_example').map((r) => r.filename).sort();

describe('parseSkillUpload', () => {
    it('reads a bare SKILL.md with no resources', async () => {
        const result = await parseSkillUpload(mdFile(SKILL_MD));
        expect(result.skillMd).toBe(SKILL_MD);
        expect(result.resources).toEqual([]);
        expect(result.skipped).toEqual([]);
    });

    it('locates SKILL.md at the archive root and enumerates resources', async () => {
        const result = await parseSkillUpload(zipFile({
            'SKILL.md': strToU8(SKILL_MD),
            'references/guide.md': strToU8('guide'),
            'scripts/run.py': strToU8('print(1)'),
            'assets/data.json': strToU8('{}'),
            'examples/ex1.md': strToU8('# Ex1'),
        }));
        expect(result.skillMd).toBe(SKILL_MD);
        expect(relPaths(result.resources)).toEqual(['assets/data.json', 'references/guide.md', 'scripts/run.py']);
        expect(exampleNames(result.resources)).toEqual(['ex1.md']);
    });

    it('locates SKILL.md one directory deep and strips the root prefix', async () => {
        const result = await parseSkillUpload(zipFile({
            'my-skill/SKILL.md': strToU8(SKILL_MD),
            'my-skill/reference/node.md': strToU8('node'),
            'my-skill/scripts/run.py': strToU8('x'),
        }));
        // Singular "reference/" is recognized; paths are relative to the skill root.
        expect(relPaths(result.resources)).toEqual(['reference/node.md', 'scripts/run.py']);
    });

    it('recognizes singular resource and example directory names', async () => {
        const result = await parseSkillUpload(zipFile({
            'SKILL.md': strToU8(SKILL_MD),
            'reference/a.md': strToU8('a'),
            'script/b.py': strToU8('b'),
            'asset/c.json': strToU8('{}'),
            'example/ex.md': strToU8('# Ex'),
        }));
        expect(relPaths(result.resources)).toEqual(['asset/c.json', 'reference/a.md', 'script/b.py']);
        expect(exampleNames(result.resources)).toEqual(['ex.md']);
    });

    it('captures example content and file content', async () => {
        const result = await parseSkillUpload(zipFile({
            'SKILL.md': strToU8(SKILL_MD),
            'references/guide.md': strToU8('guide body'),
            'examples/ex1.md': strToU8('# Ex1\n\ndesc'),
        }));
        const file = result.resources.find((r) => r.resource_type === 'skill_file');
        const example = result.resources.find((r) => r.resource_type === 'skill_example');
        expect(file?.content).toBe('guide body');
        expect(example?.content).toBe('# Ex1\n\ndesc');
    });

    it('rejects an archive with no SKILL.md', async () => {
        await expect(parseSkillUpload(zipFile({ 'references/guide.md': strToU8('x') })))
            .rejects.toThrow(/No SKILL.md/);
    });

    it('rejects an archive with more than one SKILL.md', async () => {
        await expect(parseSkillUpload(zipFile({
            'a/SKILL.md': strToU8(SKILL_MD),
            'b/SKILL.md': strToU8(SKILL_MD),
        }))).rejects.toThrow(/more than one/);
    });

    it('skips binary (non-text) files and reports them', async () => {
        const result = await parseSkillUpload(zipFile({
            'SKILL.md': strToU8(SKILL_MD),
            'references/guide.md': strToU8('text'),
            'assets/logo.png': new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x00, 0x01]), // has NUL
        }));
        expect(relPaths(result.resources)).toEqual(['references/guide.md']);
        expect(result.skipped).toEqual(['assets/logo.png']);
    });

    it('ignores files outside SKILL.md and the recognized resource dirs', async () => {
        const result = await parseSkillUpload(zipFile({
            'my-skill/SKILL.md': strToU8(SKILL_MD),
            'my-skill/LICENSE.txt': strToU8('license'),
            'my-skill/docs/notes.md': strToU8('notes'),
            'my-skill/references/guide.md': strToU8('guide'),
        }));
        expect(relPaths(result.resources)).toEqual(['references/guide.md']);
        expect(result.skipped).toEqual([]);
    });

    it('ignores nested example paths (examples are flat)', async () => {
        const result = await parseSkillUpload(zipFile({
            'SKILL.md': strToU8(SKILL_MD),
            'examples/ex1.md': strToU8('# Ex1'),
            'examples/nested/ex2.md': strToU8('# Ex2'),
        }));
        expect(exampleNames(result.resources)).toEqual(['ex1.md']);
    });
});
