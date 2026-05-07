<template>
    <div
        class="tool-call-row"
        :class="`tool-call-row-${toolCall.state} ${expanded && 'expanded'} ${hasExpandable && 'expandable'}`"
        @click="toggleExpanded"
    >
        <div class="tool-call-icon-col">
            <i :class="{expanded, expandable: hasExpandable}" class="pi tool-call-icon"/>
        </div>
        <div class="tool-call-content-col">
            <div class="tool-call-summary">
                <code class="tool-call-name">{{ toolCall.tool_name }}</code>
                <span class="tool-call-state-pill" :class="`tool-call-state-${toolCall.state}`">
                    <i v-if="toolCall.state === 'running'" class="pi pi-spin pi-spinner"/>
                    <i v-else-if="toolCall.state === 'pending'" class="pi pi-clock"/>
                    <i v-else-if="toolCall.state === 'done'" class="pi pi-check"/>
                    <i v-else-if="toolCall.state === 'error'" class="pi pi-times"/>
                    <i v-else-if="toolCall.state === 'cancelled'" class="pi pi-ban"/>
                    {{ stateLabel }}
                </span>
            </div>

            <template v-if="toolCall.tool_name !== 'run_code'">
            <div v-if="argEntries.length > 0" class="tool-call-args">
                <div
                    v-for="[key, value] in argEntries"
                    :key="key"
                    class="tool-call-arg-row"
                >
                    <span class="tool-call-arg-key">{{ key }}</span>
                    <span class="tool-call-arg-value">{{ truncateValue(value) }}</span>
                </div>
            </div>

            <div v-if="expanded" class="tool-call-detail" @click.stop>
                <div v-if="argEntries.length > 0">
                    <div class="tool-call-detail-header">Arguments (full)</div>
                    <pre class="tool-call-detail-pre">{{ formattedArgs }}</pre>
                </div>
                <div v-if="toolCall.output_preview">
                    <div class="tool-call-detail-header">
                        Output preview{{ toolCall.output_truncated ? ' (truncated)' : '' }}
                    </div>
                    <pre class="tool-call-detail-pre">{{ toolCall.output_preview }}</pre>
                </div>
                <div v-if="toolCall.error">
                    <div class="tool-call-detail-header tool-call-detail-header-error">Error</div>
                    <pre class="tool-call-detail-pre tool-call-detail-pre-error">{{ toolCall.error.ename }}: {{ toolCall.error.evalue }}</pre>
                    <pre v-if="toolCall.error.traceback?.length" class="tool-call-detail-pre tool-call-detail-pre-error">{{ toolCall.error.traceback.join('') }}</pre>
                </div>
            </div>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { IBeakerToolCall } from "beaker-kernel";
import { has } from "lodash";

const props = defineProps<{
    toolCall: IBeakerToolCall;
}>();

const ARG_LINE_BUDGET = 80;

const expanded = ref(false);

const argEntries = computed<[string, unknown][]>(() => {
    const input = props.toolCall.tool_input;
    if (!input || typeof input !== "object") {
        return [];
    }
    return Object.entries(input as Record<string, unknown>);
});

const formattedArgs = computed(() => {
    try {
        return JSON.stringify(props.toolCall.tool_input ?? {}, null, 2);
    }
    catch {
        return String(props.toolCall.tool_input);
    }
});

const stateLabel = computed(() => {
    const labels: Record<string, string> = {
        pending: "Pending",
        running: "In Progress",
        done: "Done",
        error: "Error",
        cancelled: "Cancelled",
    };
    return labels[props.toolCall.state] ?? props.toolCall.state;
});

const caretIcon = computed(() => {
    if (hasExpandable.value) {
        return expanded.value ? "pi pi-caret-down" : "pi pi-caret-right";
    }
    else {
        return "pi pi-wrench"
    }

});

const isRunCode = computed(() => {
    return props.toolCall.tool_name === 'run_code'
});

const hasExpandable = computed(() => {
    if (isRunCode.value) return false;
    return argEntries.value.length > 0
        || Boolean(props.toolCall.output_preview)
        || Boolean(props.toolCall.error);
});

const truncateValue = (value: unknown): string => {
    let stringified: string;
    if (value === null || value === undefined) {
        stringified = String(value);
    }
    else if (typeof value === "string") {
        stringified = value;
    }
    else {
        try {
            stringified = JSON.stringify(value);
        }
        catch {
            stringified = String(value);
        }
    }
    if (stringified.length > ARG_LINE_BUDGET) {
        return stringified.slice(0, ARG_LINE_BUDGET) + "…";
    }
    return stringified;
};

const toggleExpanded = () => {
    expanded.value = !expanded.value;
};
</script>

<style lang="scss">
.tool-call-row {
    display: grid;
    grid-template-columns: 1.4rem 1fr;
    gap: 0.25rem 0.5rem;
    border: 1px solid var(--p-surface-d);
    border-radius: var(--p-surface-border-radius);
    padding: 0.4rem 0.6rem;
    background-color: var(--p-surface-a);
    font-size: 0.85rem;
    cursor: pointer;
    user-select: none;

    & + .tool-call-row {
        margin-top: 0.4rem;
    }

    &:not(.expandable) {
        cursor: auto;
    }

    // Wrench shown normally
    &:not(:hover) .tool-call-icon.expandable,
    .tool-call-icon:not(.expandable) {
        background-color: var(--p-primary-50);
        --color: var(--p-primary-500);
        &::after {
            content: "\e9ff";
        }
    }

    // Caret shown while hovering
    &:hover .expandable.tool-call-icon {
        --color: var(--p-text-color-secondary);
        background-color: var(--p-surface-b);
        &::after {
            content: "\e901";
        }
        &.expanded::after {
            content: "\e902";
        }
    }


}

.tool-call-icon {
    color: var(--color);
    aspect-ratio: 1;
    padding: 0.25rem;
    background-color: var(--p-primary-100);
    border-radius: var(--p-surface-border-radius);
}

.tool-call-icon-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.55555rem;
    padding-top: 0.1rem;
}

.tool-call-content-col {
    min-width: 0;
    display: grid;
}

.tool-call-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;

    .tool-call-name {
        font-weight: 600;
        font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
    }
}

.tool-call-state-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-left: auto;

    i {
        font-size: 0.7rem;
    }
}

.tool-call-state-pending {
    background-color: var(--p-surface-c);
    color: var(--p-text-color-secondary);
}

.tool-call-state-running {
    background-color: var(--p-primary-100);
    color: var(--p-primary-700);
}

.tool-call-state-done {
    background-color: var(--p-green-100);
    color: var(--p-green-700);
}

.tool-call-state-error {
    background-color: var(--p-red-100);
    color: var(--p-red-700);
}

.tool-call-state-cancelled {
    background-color: var(--p-surface-c);
    color: var(--p-text-color-secondary);
}

.tool-call-args {
    margin: 0.35rem 0 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.tool-call-arg-row {
    display: flex;
    gap: 0.6rem;
    align-items: baseline;
    font-size: 0.8rem;

    .tool-call-arg-key {
        font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
        color: var(--p-text-color-secondary);
        min-width: 6rem;
        flex-shrink: 0;
    }

    .tool-call-arg-value {
        font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
        word-break: break-all;
    }
}

.tool-call-detail {
    margin: 0.5rem 0 0 0;
    border-top: 1px dashed var(--p-surface-d);
    padding-top: 0.4rem;

    .tool-call-detail-header {
        font-weight: 600;
        font-size: 0.75rem;
        color: var(--p-text-color-secondary);
        margin: 0.4rem 0 0.2rem 0;

        &.tool-call-detail-header-error {
            color: var(--p-red-700);
        }
    }

    .tool-call-detail-pre {
        background-color: var(--p-surface-b);
        border-radius: var(--p-surface-border-radius);
        padding: 0.4rem 0.5rem;
        font-size: 0.75rem;
        overflow-x: auto;
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;

        &.tool-call-detail-pre-error {
            background-color: var(--p-red-50);
            color: var(--p-red-800);
        }
    }
}
</style>
