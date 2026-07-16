import { describe, it, expect } from 'vitest';
import type { PartialJSONObject } from '@lumino/coreutils';
import { LatexRenderer } from '../renderers';

// `text/latex` output is delivered as a raw TeX string; the renderer signature
// types it as PartialJSONObject, so cast at the call site in these tests.
const render = (data: string) =>
    LatexRenderer.render('text/latex', data as unknown as PartialJSONObject, {});

describe('LatexRenderer', () => {
    it('typesets a display-delimited LaTeX string with KaTeX', () => {
        const { bindMapping } = render('$$ x^2 + y^2 = z^2 $$');
        expect(bindMapping.html).toContain('class="katex');
        expect(bindMapping.html).toContain('katex-display');
        // Delimiters must be stripped, not rendered literally.
        expect(bindMapping.html).not.toContain('$$');
        // Confirm the old debug stub is gone.
        expect(bindMapping.html).not.toContain('DEADBEEF');
    });

    it('typesets an unwrapped LaTeX string', () => {
        const { bindMapping } = render('\\frac{a}{b}');
        expect(bindMapping.html).toContain('class="katex');
    });

    it('typesets a SymPy-style $\\displaystyle ...$ output', () => {
        const { bindMapping } = render('$\\displaystyle \\int x\\,dx$');
        expect(bindMapping.html).toContain('class="katex');
        expect(bindMapping.html).not.toMatch(/^\$/);
    });
});
