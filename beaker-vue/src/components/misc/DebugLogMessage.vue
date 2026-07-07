<template>
    <div class="debug-message">
        <Panel
            class="debug-message-panel"
            v-if="logEntry?.body"
        >
            <template #header>
                <div class="debug-message-header-container">
                    <div class="debug-message-title">
                        <span style="font-weight: 500">
                            {{title}}
                        </span>
                    </div>
                    <span class="debug-message-date">
                        {{ logEntry?.timestamp.split('T')[1].slice(0, -1) }}
                    </span>
                </div>
            </template>

            <p class="debug-message-body">
                <!-- spans were starting with a space when body text isn't inline. -->
                <span v-if="logEntry?.type === 'agent_llm_response'">
                    <span v-if="logEntry?.body?.split('tool_calls=')?.[1]?.split(`'`)?.[3] === 'final_answer'">Processing final answer from tool output.</span>
                    <span v-else>{{ logEntry?.body?.split('tool_calls=')?.[0]?.split('text=')?.[1].slice(1, -3) }}</span>
                </span>
                <span v-if="logEntry?.type === 'agent_llm_request'" style="color: var(--p-surface-h);">Agent context setup and conversation history -- see details below</span>
                <span v-if="rawStringMessageTypes.includes(logEntry?.type) || !Object.keys(userFacingNames).includes(logEntry?.type)">
                    {{ logEntry?.body }}
                </span>
                <span v-if="logEntry?.type === 'agent_react_tool_output'">
                    <span class="debug-tool-call-title">
                        <span style="font-family: monospace; margin-bottom: 0.25rem;">{{ logEntry?.body?.tool }}</span>
                    </span>
                    <span v-if="logEntry?.body?.tool === 'run_code'">
                        tool output is usually verbose and is hidden by default -- see details below
                    </span>
                    <CodeEditor
                        readonly
                        :modelValue="logEntry?.body?.output?.trim()"
                        class="debug-code-display"
                        v-else-if="logEntry?.body?.output?.trim().length <= 1500"
                    />
                    <p v-else>Tool output was significantly long and has been hidden by default - view additional details below to see the raw output.</p>
                </span>
                <span v-if="logEntry?.type === 'agent_react_final_answer'">
                    {{ logEntry?.body?.final_answer?.response }}
                </span>
            </p>

            <div
                v-if="(logEntry?.type === 'agent_react_tool')"
                class="debug-tool-info"
            >
                <span class="debug-tool-call-title">
                    Tool:
                    <span style="font-family: monospace;">{{ logEntry?.body?.tool }}</span>
                </span>

                <DataTable
                    showGridlines
                    stripedRows
                    class="debug-info-datatable"
                    :value="Object.entries(logEntry?.body?.input).map(([key, value]) => ({key, value}))"
                >
                    <Column field="key"></Column>
                    <Column field="value"></Column>
                </DataTable>
            </div>

            <DataTable
                showGridlines
                stripedRows
                class="debug-info-datatable"
                :value="Object.entries(logEntry?.body).map(([key, value]) => ({key, value}))"
                v-if="pureJsonMessageTypes.includes(logEntry?.type) && logEntry?.body && Object.keys(logEntry?.body).length > 0"
            >
                <Column field="key"></Column>
                <Column field="value"></Column>
            </DataTable>

            <div v-else>
                <CodeEditor
                    readonly
                    :modelValue="logEntry?.body?.command?.trim()"
                    class="debug-code-display"
                    v-if="logEntry?.type === 'execution_start' && !isHiddenByDefault"
                />

                <div class='debug-separator' />

                <div
                    class="debug-dropdown debug-dropdown-details"
                    :onclick="() => {showDetails = !showDetails}"
                >
                    <span class="pi" :class="{
                        'pi-angle-right': !showDetails,
                        'pi-angle-down': showDetails
                    }"/>
                    <span class="debug-dropdown-label">
                        {{showDetails ? 'Hide' : 'Show'}} Additional Details
                    </span>
                </div>
                <div v-if="showDetails" class="log-dropdown-additional-details">

                    <CodeEditor
                        readonly
                        :modelValue="logEntry?.body?.command?.trim()"
                        class="debug-code-display"
                        v-if="logEntry?.type === 'execution_start' && isHiddenByDefault"
                    />
                    <div
                        class="debug-dropdown debug-dropdown-raw"
                        :onclick="() => {showRaw = !showRaw}"
                    >
                        <span class="pi" :class="{
                            'pi-angle-right': !showRaw,
                            'pi-angle-down': showRaw
                        }"/>
                        <span class="debug-dropdown-label">
                            {{showRaw ? 'Hide' : 'Show'}} Raw Message (JSON)
                        </span>
                    </div>
                    <div v-if="showRaw" class="debug-dropdown-body">
                        <vue-json-pretty
                            :data="logEntry.body"
                            :deep="2"
                            showLength
                            showIcon
                            :showDoubleQuotes="isQuotes"
                            :showLineNumber="linenum"
                        />
                    </div>
                </div>
            </div>
        </Panel>
    </div>
</template>
<script lang="ts" setup>

import { ref, computed } from "vue";
import VueJsonPretty from 'vue-json-pretty';
import 'vue-json-pretty/lib/styles.css';
import Panel from 'primevue/panel';
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import CodeEditor from "./CodeEditor.vue";

const props = defineProps([
    "logEntry",
    "options"
])

const isQuotes = computed(() => {
    return props.options?.value?.includes('quotes');
});

const linenum = computed(() => {
    return props.options?.value?.includes('linenum');
})

const userFacingNames = {
    'execution_start': 'Execution Start',
    'execution_end': 'Execution End',
    'debug_update': 'Debug Update',
    'new_kernel': 'New Kernel',
    'init-agent': "Agent Initialization",
    'llm_query': 'Agent Query',
    'agent_llm_request': 'Agent Message',
    'agent_llm_response': 'Agent Response',
    'agent_react_tool': 'Tool Invocation',
    'agent_react_tool_output': "Tool Output",
    'agent_react_final_answer': "Agent Final Answer"
}

// messages with non-bespoke grouped handling

const rawStringMessageTypes = [
    'new_kernel',
    'llm_query'
]

const pureJsonMessageTypes = [
    'debug_update',
    'init-agent',
    // catch-all for coerced/non-present fields, assume json
    'undefined'
]

const isHiddenByDefault = computed(() =>
    ['get_subkernel_state', 'preview'].includes(props?.logEntry?.body?.metadata?.type))

const title = computed(() => {
    const messageMetadataType = props?.logEntry?.body?.metadata?.type;
    const executionType = props?.logEntry?.type === 'execution_start' ? 'Start' : props?.logEntry?.type === 'execution_end' ? 'End' : ""
    if (messageMetadataType === 'get_subkernel_state') {
        return `Fetch Subkernel State (${executionType})`
    } else if (messageMetadataType === 'preview') {
        return `Subkernel Preview (${executionType})`
    }

    const formattedRawName = props?.logEntry?.type?.startsWith('agent_') ? props?.logEntry?.type?.slice(6) : props?.logEntry?.type;
    return userFacingNames?.[props?.logEntry?.type] ?? formattedRawName ?? 'Message';
})

const showDetails = ref(false);
const showRaw = ref(false);

</script>

<style lang="scss">

.log-message-details-date {
    display: flex;
    flex-direction: row;
    gap: 0.5rem;
}

.debug-message-panel {
    margin-top: 0.5rem;
    // margin-bottom: 0;
    position: relative;
    white-space: pre-wrap;

    .p-panel-header {
        background: var(--p-surface-b);
        padding: 0.5rem 1rem;
    }
    .p-panel-content {
        padding: 0.5rem 0.75rem;
    }
}

.debug-message-header-container {
    width: 100%;
    display: flex;
    flex-direction: row;
    justify-content: space-between;
}

.debug-message-title {
    display: flex;
    flex-direction: row;
    gap: 0.2rem;
    flex: 0 1 auto;
    min-width: 0;
    flex-wrap: wrap;
}

.debug-message-date {
    color: var(--p-grey-300);
    flex: 0 0 auto;
}

.debug-message-body {
    margin: 0 0 0.25rem 0;
    font-size: 0.9rem;
}

.debug-tool-call-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
}

.debug-tool-info {
    display: flex;
    flex-direction: column;
}

.debug-dropdown {
    font-size: 0.8rem;
    display: flex;
    flex-direction: row;
    gap: 0.2rem;
    justify-content: flex-start;
    color: var(--p-surface-h);
    span.pi {
        font-size: 0.85rem;
    }
    * {
        margin: auto 0.2rem auto 0;
    }
    &:hover {
        cursor: pointer;
        .debug-dropdown-label {
            text-decoration: underline;
            color: var(--p-surface-f);
        }
    }
}

.debug-dropdown-additional-details {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}

.debug-info-datatable {
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
    thead.p-datatable-thead {
        display: none;
    }
    tbody tr td {
        padding: 0.2rem;
        font-family: monospace;
    }
    tbody tr:nth-child(1) td {
        border-top: 1px solid var(--p-surface-d);
    }
}

.debug-dropdown-body {
    margin-top: 0.5rem;
}

.debug-plain-string {
    font-family: monospace;
    margin: 0.25rem 0;
    font-size: 0.85rem;
}

.debug-code-display {
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
}

.debug-separator {
    background-color: var(--p-surface-d);
    height: 1px;
    width: 100%;
    margin: 0.5rem 0;
}

</style>
