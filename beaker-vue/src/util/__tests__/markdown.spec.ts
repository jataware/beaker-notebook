import { describe, it, expect } from 'vitest';
import { marked, renderMath, stripMathDelimiters } from '../markdown';

describe('marked KaTeX extension', () => {
    it('renders inline math delimited by \\( ... \\)', () => {
        const html = marked.parse('The value is \\(a^2 + b^2\\) today.') as string;
        // KaTeX emits a span with the `katex` class; the backslash delimiters
        // must not survive as literal text.
        expect(html).toContain('class="katex"');
        expect(html).not.toContain('\\(');
        expect(html).not.toContain('\\)');
        // Inline math should not be in display mode.
        expect(html).not.toContain('katex-display');
        // Surrounding text is preserved.
        expect(html).toContain('The value is');
        expect(html).toContain('today.');
    });

    it('renders display math delimited by \\[ ... \\] as a centered block', () => {
        const html = marked.parse('\\[ \\int_0^1 x\\,dx = \\frac{1}{2} \\]') as string;
        expect(html).toContain('class="katex');
        expect(html).toContain('katex-display');
        expect(html).not.toContain('\\[');
        expect(html).not.toContain('\\]');
    });

    it('handles inline math embedded within a sentence', () => {
        const html = marked.parse('Given \\(x = 5\\), compute the result.') as string;
        expect(html).toContain('class="katex"');
        expect(html).toContain('Given');
        expect(html).toContain('compute the result.');
    });

    it('leaves ordinary parentheses untouched', () => {
        const html = marked.parse('This is (not math) at all.') as string;
        expect(html).not.toContain('class="katex"');
        expect(html).toContain('(not math)');
    });

    it('does not crash on invalid TeX and preserves surrounding text', () => {
        const html = marked.parse('Broken \\(\\frac{1\\) here.') as string;
        // throwOnError is disabled, so KaTeX renders an error node rather than
        // throwing; the sentence text is still present.
        expect(html).toContain('Broken');
        expect(html).toContain('here.');
    });
});

describe('stripMathDelimiters', () => {
    it('strips $$ ... $$ as display math', () => {
        expect(stripMathDelimiters('$$ x^2 $$')).toEqual({ text: 'x^2', displayMode: true });
    });

    it('strips \\[ ... \\] as display math', () => {
        expect(stripMathDelimiters('\\[ x^2 \\]')).toEqual({ text: 'x^2', displayMode: true });
    });

    it('strips \\( ... \\) as inline math', () => {
        expect(stripMathDelimiters('\\( x^2 \\)')).toEqual({ text: 'x^2', displayMode: false });
    });

    it('strips single $ ... $ (e.g. SymPy) as display math', () => {
        expect(stripMathDelimiters('$\\displaystyle x^2$')).toEqual({
            text: '\\displaystyle x^2',
            displayMode: true,
        });
    });

    it('treats an unwrapped string as display math', () => {
        expect(stripMathDelimiters('\\frac{1}{2}')).toEqual({
            text: '\\frac{1}{2}',
            displayMode: true,
        });
    });

    it('prefers $$ over $ when both could match', () => {
        // Must not strip only the outer single $ from a $$-wrapped string.
        expect(stripMathDelimiters('$$a$$')).toEqual({ text: 'a', displayMode: true });
    });
});

describe('renderMath', () => {
    it('typesets a bare TeX string to KaTeX HTML', () => {
        const html = renderMath('\\frac{1}{2}', true);
        expect(html).toContain('class="katex');
        expect(html).toContain('katex-display');
    });
});
