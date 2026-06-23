import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Integration } from '@/util/integration';
import type { BeakerWorkflow } from '@/composables/useWorkflows';
import { fetch } from '@/util/fetch';


export interface IProcedureInfo {
    slug: string;
    name: string;
    languages: string[];
    description: string|null;
}


export interface IToolInfo {
    name: string
    description: string
    doc_string: string
    is_autosummarized: boolean
    arguments: [][]
    return_info: []
}


export interface IActionInfo {
    name: string;
    documentation: string;
    scope: string;
}


export interface ISubkernelInfo {
    cls: string
    slug: string
    display_name: string
    description: string
    kernel_name: string
    language: string
    tools: {[key: string]: IToolInfo};
    weight: number;
}


export interface ILanguageInfo {
    slug: string
    display_name: string
}


export interface ILLMInfo {
    model_provider: string
    model_name: string
}


export interface IAgentInfo {
    cls: string
    description: string
    tools: {[key: string]: IToolInfo};
    agent_prompt: string
    version: string|null;
}


export interface IContextInfo {
     slug: string
     short_name: string
     full_name: string
     cls: string
     description: string
     weight: number

     agent: IAgentInfo
     actions: {[key: string]: IActionInfo}
     tools: {[key: string]: IToolInfo}
     integrations: {[key: string]: {[key: string]: Integration}}
     workflows: {[key: string]: BeakerWorkflow}
     subkernels: {[key: string]: ISubkernelInfo}
     languages: {[key: string]: ILanguageInfo}
     procedures: {[key: string]: IProcedureInfo}

     version: string | null;
     last_updated: Date | null;
     metadata: {[key: string]: any};

}

export const useContextStore = defineStore('beaker-contexts', () => {
    const _contextInfo = ref<IContextInfo[]>([]);

    const contextList = computed(() => {
        return _contextInfo.value;
    });

    const contextMap = computed(() => {
        return Object.fromEntries(contextList.value.map((context) => [context.slug, context]));
    });

    const refresh = async (forceUpdate: boolean = false, verbose: boolean = false) => {
        const params = new URLSearchParams({
            ...(forceUpdate ? {update: "1"} : {}),
            ...(verbose ? {verbose: "1"} : {}),
        });

        const url = `/beaker/contexts${params.size ? "?" + params.toString() : ""}`;
        const contextInfoReq = await fetch(url, {});
        _contextInfo.value = await contextInfoReq.json();
    }

    refresh();

    return {
        contextList,
        contextMap,
        refresh
    };
});
