import { marked, type TokenizerAndRendererExtension, type Tokens } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';

// KaTeX support for `marked`.
//
// Adds rendering for the "escaped" TeX display-math delimiters that most
// notebook and chat interfaces support but that vanilla markdown strips as
// character escapes:
//
//   * `\( ... \)` - inline math, rendered intermixed with the surrounding text.
//   * `\[ ... \]` - display math, rendered as a centered block.
//
// Both are registered as inline-level extensions so they are matched before
// `marked`'s built-in escape handling (which would otherwise turn `\(` into a
// literal `(` and drop the backslash). Inline-level matching also lets display
// math be recognized whether it sits on its own line or inline within a
// paragraph; KaTeX's display mode still emits a centered block element.

interface KatexToken extends Tokens.Generic {
    type: string;
    raw: string;
    text: string;
    displayMode: boolean;
}

/**
 * Typeset a TeX string to HTML with KaTeX. `throwOnError` is disabled so parse
 * errors render as an inline error node rather than throwing; the try/catch
 * guards only against truly unexpected input, falling back to the original
 * source so content is never silently lost.
 */
export const renderMath = (text: string, displayMode: boolean): string => {
    try {
        return katex.renderToString(text, {
            displayMode,
            throwOnError: false,
        });
    } catch {
        return displayMode ? `\\[${text}\\]` : `\\(${text}\\)`;
    }
};

/**
 * Strip a single enclosing pair of common TeX math delimiters, reporting
 * whether the content was wrapped as display-style math. Used for `text/latex`
 * output, which arrives as a bare or lightly-wrapped TeX string rather than
 * markdown. Content with no recognized wrapper is treated as display math,
 * matching how such outputs (e.g. equations from SymPy or IPython's `Math`)
 * are conventionally presented.
 */
export const stripMathDelimiters = (raw: string): { text: string; displayMode: boolean } => {
    const trimmed = raw.trim();
    // Order matters: `$$` must be tested before `$`.
    const delimiters: Array<[string, string, boolean]> = [
        ['$$', '$$', true],
        ['\\[', '\\]', true],
        ['\\(', '\\)', false],
        ['$', '$', true],
    ];
    for (const [open, close, displayMode] of delimiters) {
        if (
            trimmed.length >= open.length + close.length &&
            trimmed.startsWith(open) &&
            trimmed.endsWith(close)
        ) {
            return {
                text: trimmed.slice(open.length, trimmed.length - close.length).trim(),
                displayMode,
            };
        }
    }
    return { text: trimmed, displayMode: true };
};

const escapeForRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const createExtension = (
    name: string,
    open: string,
    close: string,
    displayMode: boolean,
): TokenizerAndRendererExtension => {
    const rule = new RegExp(`^${escapeForRegExp(open)}([\\s\\S]+?)${escapeForRegExp(close)}`);
    return {
        name,
        level: 'inline',
        start(src: string) {
            const index = src.indexOf(open);
            return index < 0 ? undefined : index;
        },
        tokenizer(src: string) {
            const match = rule.exec(src);
            if (match) {
                return {
                    type: name,
                    raw: match[0],
                    text: match[1].trim(),
                    displayMode,
                };
            }
            return undefined;
        },
        renderer(token) {
            const katexToken = token as KatexToken;
            return renderMath(katexToken.text, katexToken.displayMode);
        },
    };
};

export const katexExtension = {
    extensions: [
        createExtension('inlineKatex', '\\(', '\\)', false),
        createExtension('blockKatex', '\\[', '\\]', true),
    ],
};

let registered = false;

/**
 * Register the KaTeX extension on the shared `marked` singleton. Idempotent, so
 * it is safe to call from multiple entry points.
 */
export const registerMarkdownExtensions = (): void => {
    if (registered) {
        return;
    }
    registered = true;
    marked.use(katexExtension);
};

registerMarkdownExtensions();

export { marked };
