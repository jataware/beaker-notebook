// Context / agent / subkernel / tool info types. Part of the EXTENSION_API
// contract surface — describes the shape of data that flows from the Beaker
// Kernel + Context + Agent triplet into the UI.
//
// (Note: `Integration` and `BeakerWorkflow` are referenced loosely here
// because their canonical definitions live in lib utility / composable
// modules; the types below use `unknown` to avoid circular imports.)

export interface IProcedureInfo {
    slug: string;
    name: string;
    languages: string[];
    description: string | null;
}

export interface IToolInfo {
    name: string;
    description: string;
    doc_string: string;
    is_autosummarized: boolean;
    arguments: [][];
    return_info: [];
}

export interface IActionInfo {
    name: string;
    documentation: string;
    scope: string;
}

export interface ISubkernelInfo {
    cls: string;
    slug: string;
    display_name: string;
    description: string;
    kernel_name: string;
    language: string;
    tools: { [key: string]: IToolInfo };
    weight: number;
}

export interface ILanguageInfo {
    slug: string;
    display_name: string;
}

export interface ILLMInfo {
    model_provider: string;
    model_name: string;
}

export interface IAgentInfo {
    cls: string;
    description: string;
    tools: { [key: string]: IToolInfo };
    agent_prompt: string;
    version: string | null;
}

export interface IContextInfo {
    slug: string;
    short_name: string;
    full_name: string;
    cls: string;
    description: string;
    weight: number;

    agent: IAgentInfo;
    actions: { [key: string]: IActionInfo };
    tools: { [key: string]: IToolInfo };
    integrations: { [key: string]: { [key: string]: unknown } };
    workflows: { [key: string]: unknown };
    subkernels: { [key: string]: ISubkernelInfo };
    languages: { [key: string]: ILanguageInfo };
    procedures: { [key: string]: IProcedureInfo };

    version: string | null;
    last_updated: Date | null;
    metadata: { [key: string]: any };
}

import type { Ref, ComputedRef } from 'vue';

/** Minimal interface the host must satisfy for the BeakerContextServiceKey inject. */
export interface IBeakerContextService {
    contextList: Ref<IContextInfo[] | undefined>;
    contextMap: ComputedRef<{ [slug: string]: IContextInfo }>;
    refresh(forceUpdate?: boolean, verbose?: boolean): Promise<void>;
}
