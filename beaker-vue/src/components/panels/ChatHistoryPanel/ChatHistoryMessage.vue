<template>
    <div class="chat-history-message">
        <Panel class="chat-history-message-panel" :toggleable="true"
            :style="{collapsed}"
            @toggle="collapsed = !collapsed"
            :pt="{
                contentContainer: ({state}) => {
                    // Force internal collapsed state to be false, preventing
                    // panel contents from being hidden via v-show.
                    state.d_collapsed = false;
                    // Add the class 'collapsed' to the element if the out ref is true
                    return (collapsed ? 'collapsed' : undefined);
                },
            }"
        >
            <template #header>
                <div
                    class="chat-history-message-header-container"
                    @click="collapsed = !collapsed"
                >
                    <div class="chat-history-message-title">
                        <span style="font-weight: 500">
                            {{ capitalized(message?.type) }}Message
                        </span>
                        <span v-if="message?.type.toLowerCase() === 'ai' && message?.tool_calls"
                            class="chat-history-message-tool-use pi pi-hammer"
                            v-tooltip="`Tool${message.tool_calls.length > 1 ? 's' : ''} called: ` + message.tool_calls.map(tc => `'${tc.name}'`).join(', ')"
                        ></span>
                    </div>
                    <span class="chat-history-message-title-token-count" >
                        {{ ((record?.token_count ?? 0)/1000).toFixed(2) }}k tokens
                    </span>
                </div>
            </template>
            <template #togglericon>
                <component :is="collapsed ? PlusIcon : MinusIcon" />
            </template>

            <div>
                <div v-if="message.text.trim()" class="message-text monospace">{{ message?.text.trim() }}</div>
                <div
                    v-if="message?.type === 'ai' && message?.tool_calls?.length > 0"
                    class="toolcall-info"
                >
                    <div
                        v-for="tool_call in message?.tool_calls"
                        :key="tool_call.id"
                    >

                        <div class="tool-call-title">
                            Tool: &nbsp;
                            <span class="monospace">{{ tool_call.name }}</span>
                        </div>
                        <div>
                            Arguments:
                        </div>
                        <DataTable
                            showGridlines
                            stripedRows
                            class="chat-history-datatable"
                            :value="Object.entries(tool_call?.args).map(([key, value]) => ({key, value}))"
                        >
                            <Column field="key"></Column>
                            <Column field="value"></Column>
                        </DataTable>
                    </div>
                </div>
            </div>
            <div v-if="collapsed" class="expand" @click="collapsed = false">Click to expand</div>
        </Panel>
    </div>
</template>
<script lang="ts" setup>

import { ref, computed } from "vue";
import MinusIcon from '@primevue/icons/minus';
import PlusIcon from '@primevue/icons/plus';
import Panel from 'primevue/panel';
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import 'vue-json-pretty/lib/styles.css';

const props = defineProps([
    "record",
    "idx",
    "tool-call-message",
])

const collapsed = ref(true);
const message = computed(() => props.record?.message);

const capitalized = (str: string) => (
    str ? str.replace(/(?<edge>[-_]|\b)(?<letter>.)/g, (match, edge, char, offset, string, groups) => char.toUpperCase()) : str
);

</script>

<style lang="scss">

.chat-history-message-panel {
    margin-bottom: 0.75rem;
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

.chat-history-message-header-container {
    width: 100%;
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    cursor: pointer;
}

.chat-history-message-title {
    display: flex;
    flex-direction: row;
    gap: 0.2rem;
    flex: 0 1 auto;
    min-width: 0;
    flex-wrap: wrap;
}

.chat-history-message-title-token-count {
    color: var(--p-grey-300);
    flex: 0 0 auto;
    margin-right: 0.5rem;
}

.chat-history-message-body {
    margin: 0 0 0.25rem 0;
    font-size: 0.9rem;
}

.chat-history-message-panel .p-panel-content-container.collapsed .p-panel-content {
    position: relative;
    overflow: hidden;
    height: 5rem;
    padding-bottom: 0rem;

    & .expand {
        text-align: center;
        color: var(--p-button-text-primary-active-background);
        display: block;
        position: absolute;
        background-color: inherit;
        padding-top: 1.25rem;
        left: 0;
        right: 0;
        bottom: 0;
        height: 2.5rem;
        font-size: 0.75rem;
        cursor: pointer;
        background-color: transparent;
        box-shadow:
                inset 0px -4rem 1.5rem -2.4rem var(--p-slate-500),
                inset 0px -3.5rem 1rem -2.0rem var(--p-slate-500);
    }
}

.message-text {
    &:not(:last-child) {
        margin-bottom: 1.5rem;
    }
}

.tool-call-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
}

.chat-history-message-tool-use {
    margin-left: 0.5em;
    position: relative;
    top: 0.125em;
}

.chat-history-datatable {
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
    thead.p-datatable-thead {
        display: none;
    }
    tbody tr td {
        vertical-align: top;
        padding: 1rem 0.5rem;
        font-family: monospace;
    }
    tbody tr:nth-child(1) td {
        border-top: 1px solid var(--p-surface-d);
    }
}
</style>
