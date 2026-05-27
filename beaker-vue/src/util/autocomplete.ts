import { LanguageSupport, language as languageFacet } from "@codemirror/language";
import type { Language as CMLanguage, LRLanguage } from "@codemirror/language";
import type { Completion, CompletionContext, CompletionResult } from "@codemirror/autocomplete";
import * as messages from '@jupyterlab/services/lib/kernel/messages';
import { BeakerSession, type IBeakerFuture } from '@jataware/beaker-client';

import { pythonLanguage, python } from "@codemirror/lang-python";
import { rLanguage, r } from 'codemirror-lang-r';
import { markdownLanguage, markdown } from "@codemirror/lang-markdown";
import { jsonLanguage, json } from "@codemirror/lang-json";
import { javascriptLanguage, javascript } from "@codemirror/lang-javascript";
import { julia, type JuliaLanguageConfig } from "@plutojl/lang-julia";
import type { Extension } from "@codemirror/state";

const juliaLanguage: LRLanguage = <LRLanguage>julia().language;

export interface JupyterTypedCompletion {
    start: number;
    end: number;
    text: string;
    type: "keyword" | "path" | "magic" | "variable" | string;
    signature?: string;
}

export interface CompletionStart {
    from: number;
    to: number;
    text: string;
}

export interface BeakerLanguage {
    language: CMLanguage;
    initializer: (options?: object) => LanguageSupport;
    name?: string;
    aliases?: string[];
    applyDefaultFilter?: boolean;
    kernelCompletionFilter?: (completion: Completion, start: CompletionStart | null, context: CompletionContext) => boolean;
    lexerCompletionFilter?: (completion: Completion, start: CompletionStart | null, context: CompletionContext) => boolean;
    fullCompletionFilter?: (completion: Completion, start: CompletionStart | null, context: CompletionContext) => boolean;
    activateOnCompletion?: (completion: Completion) => boolean;
}

export const Python: BeakerLanguage = {
    language: pythonLanguage,
    initializer: python,
    aliases: ["python2", "python3"],
    fullCompletionFilter(completion, start, context) {
        // Only show hidden completions if looking for them
        if (completion.label.startsWith('_')) {
            return start.text.startsWith('_')
        }
        // Only show magic commands if searched for
        else if (completion.label.startsWith('%')) {
            return start.text.startsWith('%');
        }
        return true;
    }
}

export const Julia: BeakerLanguage = {
    language: juliaLanguage,
    name: "julia",
    initializer: julia,
    applyDefaultFilter: false,
    activateOnCompletion(completion) {
        if (completion.label.startsWith('\\') && completion.type.length === 1) {
            return true;
        }
        return false;
    },
}

export const R: BeakerLanguage = {
    language: rLanguage,
    name: "rlang",
    initializer: r,
    aliases: ["r", "ir"],
}

export const Markdown: BeakerLanguage = {
    language: markdownLanguage,
    initializer: markdown,
}

export const Json: BeakerLanguage = {
    language: jsonLanguage,
    initializer: json,
}

export const Javascript: BeakerLanguage = {
    language: javascriptLanguage,
    initializer: javascript,
}


export class BeakerLanguageSupport extends LanguageSupport {
    beakerLanguage: BeakerLanguage;
    constructor(beakerLanguage: BeakerLanguage, language: LanguageSupport["language"], support?: Extension) {
        super(language, support);
        this.beakerLanguage = beakerLanguage;

    }
}

class LanguageRegistryMapping extends Map<string | CMLanguage, BeakerLanguage> {
    reverseLookup: Map<CMLanguage, BeakerLanguage>;

    constructor(...languages: BeakerLanguage[]) {
        super();
        this.reverseLookup = new Map();
        this.update(...languages)
    }

    add(language: BeakerLanguage): void {
        const name = language.language.name || language.name;
        this.set(name, language);
        this.reverseLookup.set(language.language, language);
        if (language.aliases) {
            language.aliases.forEach(alias => this.set(alias, language));
        }
    }

    update(...languages: BeakerLanguage[]) {
        languages.forEach(language => this.add(language));
    }

    get(key: string | CMLanguage): BeakerLanguage {
        if (typeof(key) === "string") {
            return super.get(key);
        }
        else {
            return this.reverseLookup.get(key);
        }
    }
}

export const LanguageRegistry: LanguageRegistryMapping = new LanguageRegistryMapping(
    Python,
    Julia,
    R,
    Markdown,
    Json,
    Javascript,
);


export const getCompletions = async (completionContext: CompletionContext, session: BeakerSession): Promise<CompletionResult | null>  => {
    const completionLang = completionContext.state.facet(languageFacet);
    const language = LanguageRegistry.get(completionLang);
    const code = completionContext.state.doc.toString();
    const cursor_pos = completionContext.pos;
    const completionStart: CompletionStart | null = completionContext.matchBefore(/[#%_([{\w]{1,}/);

    if (!completionStart && !completionContext.explicit) {
        return null;
    }

    // Get autocompletions from subkernel
    const complete_request: IBeakerFuture<messages.ICompleteRequestMsg, messages.ICompleteReplyMsg> = session.sendBeakerMessage(
        "complete_request",
        {
            "code": code,
            "cursor_pos": cursor_pos,
        }
    )

    // While the kernel is processing the request, get the language autocompletes to filter against.
    const languageAutocompletes = completionContext.state.languageDataAt("autocomplete", 0);
    const promises: Promise<CompletionResult>[] = [];
    if (Array.isArray(languageAutocompletes)) {
        languageAutocompletes.forEach((autocomplete) => {
            const result = autocomplete(completionContext);
            promises.push(Promise.resolve(result));
        })
    }
    else {
        throw Error("Unable to retrieve autocomplete options.")
    }
    let results: CompletionResult[] = await Promise.all(promises);
    results = results.filter(result => Boolean(result));

    let languageResults: Completion[] = results.flatMap((result) => result?.options || []);
    const complete_reply = await complete_request.done;
    let from: number, to: number;

    if (results.length > 1) {
        from = results.map(result => result.from).reduce((prevResult, result,) => {
            return (prevResult === result ? prevResult : undefined);
        });
        to = results.map(result => result.to).reduce((prevResult, result,) => {
            return (prevResult === result ? prevResult : undefined);
        });
    }
    else if (results.length === 1) {
        from = results[0].from;
        to = results[0].to;
    }
    else {
        from = undefined;
        to = undefined;
    }

    let kernelResults: Completion[] = [];
    let kernelOptions: Set<string> = new Set([]);
    if (complete_reply.content.status === "ok") {
        if (from === undefined) {
            from = complete_reply.content.cursor_start;
        }
        else if (from !== complete_reply.content.cursor_start) {
            from = complete_reply.content.cursor_start;
            if (complete_reply.content.matches.length && languageResults.length) {
                languageResults = [];
            }
        }
        if (to === undefined) {
            to = complete_reply.content.cursor_end;
        }
        else if (to !== complete_reply.content.cursor_end) {
            to = complete_reply.content.cursor_end;
            if (complete_reply.content.matches.length && languageResults.length) {
                languageResults = [];
            }
        }

        if ((complete_reply.content.metadata?._jupyter_types_experimental as [])?.length > 0) {
            const typed_options: JupyterTypedCompletion[] = complete_reply.content.metadata._jupyter_types_experimental as unknown as JupyterTypedCompletion[];
            kernelResults = typed_options.map((option) => {
                const boost = (option.type == "param" ? 50 : 5);
                return {
                    label: option.text,
                    type: option.type,
                    boost: boost,
                    detail: (option.signature !== "" ? option.signature : undefined),
                }
            });
            kernelOptions = new Set(typed_options.map(option => option.text))
        }
        else if (complete_reply.content.matches?.length > 0) {
            kernelResults = complete_reply.content.matches.map((option) => {
                    const boost = (option.endsWith("=") ? 50 : 5);
                    return {
                        label: option,
                        boost: boost,
                    }
                });
            kernelOptions = new Set(complete_reply.content.matches)
        }
    }

    if (language?.lexerCompletionFilter) {
        languageResults = languageResults.filter(option => language.lexerCompletionFilter(option, completionStart, completionContext));
    }
    if (language?.kernelCompletionFilter) {
        kernelResults = kernelResults.filter(option  => language.kernelCompletionFilter(option, completionStart, completionContext));
    }

    let options = [
        ...kernelResults,
        ...languageResults.filter(option => !kernelOptions.has(option.label))
    ];
    if (language?.fullCompletionFilter !== undefined) {
        options = options.filter(option => language.fullCompletionFilter(option, completionStart, completionContext));
    }

    return {
        from,
        to,
        filter: (language?.applyDefaultFilter !== undefined ? language.applyDefaultFilter : true),
        options,
    };
};
