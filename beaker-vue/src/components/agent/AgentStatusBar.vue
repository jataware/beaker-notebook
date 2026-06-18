<template>
    <div v-if="isActive" class="agent-status-bar">
        <span class="status-icon">
            <ThinkingIcon/>
        </span>
        <div class="status-content">
            <span class="status-label">Agent Running</span>
            <span v-if="lastThoughtText" class="status-thought">{{ lastThoughtText }}</span>
        </div>
        <span class="status-animation"></span>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import ThinkingIcon from '../../assets/icon-components/BrainIcon.vue';
import { type IBeakerCell } from "@jataware/beaker-client";

const props = defineProps<{
    // The currently active query cell, or null when the agent is idle.
    cell: IBeakerCell | null;
}>();

const isActive = computed(() => {
    if (!props.cell) return false;
    const queryStatus = props.cell.metadata?.query_status;
    const status = props.cell.status as string;
    return queryStatus === 'in-progress' && ['busy', 'awaiting_input'].includes(status);
});

const lastThoughtText = computed(() => {
    const events = props.cell?.events ?? [];
    const thoughtEvents = events.filter(event => event.type === 'thought');
    if (thoughtEvents.length === 0) return null;

    const lastThought = thoughtEvents[thoughtEvents.length - 1];

    if (typeof lastThought.content === 'string') {
        return lastThought.content;
    } else if (typeof lastThought.content === 'object' && lastThought.content?.thought) {
        return lastThought.content.thought;
    } else if (typeof lastThought.content === 'object') {
        const content = lastThought.content;
        return content.thought || content.text || content.message || JSON.stringify(content);
    }

    return null;
});
</script>

<style scoped lang="scss">
.agent-status-bar {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background-color: var(--p-surface-b);
    border-bottom: 1px solid var(--p-surface-border);
    // Cap height so long activity text can never push content off-screen
    // (~3 lines of the thought + the label line).
    max-height: 5rem;
    overflow: hidden;
}

.status-icon {
    display: inline-block;
    height: 1rem;
    color: var(--p-primary-500);
    flex-shrink: 0;
    margin-top: 0.1rem;

    svg {
        fill: currentColor;
        stroke: currentColor;
        width: 1rem;
        animation: status-pulse 2s ease-in-out infinite;
    }
}

.status-content {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
    flex: 1;
    overflow: hidden;
}

.status-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--p-text-color);
    flex-shrink: 0;
}

.status-thought {
    font-size: 0.8125rem;
    color: var(--p-text-color-secondary);
    line-height: 1.3;
    white-space: pre-wrap;
    // Keep the most recent activity readable while clamping to a few lines;
    // any overflow is truncated with an ellipsis so the bar stays bounded.
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.status-animation {
    font-size: 1rem;
    flex-shrink: 0;
    width: 2.5em;
    margin-left: auto;
    clip-path: view-box;
}

.status-animation:after {
    overflow: hidden;
    display: inline-block;
    vertical-align: bottom;
    position: relative;
    animation: status-ellipsis 2000ms steps(36, end) infinite;
    content: "\2026\2026\2026";
    width: 2.5em;
}

@keyframes status-ellipsis {
    from {
        right: 100%;
    }
    to {
        right: -100%;
    }
}

@keyframes status-pulse {
    0%, 100% {
        opacity: 1;
        transform: scale(1);
    }
    50% {
        opacity: 0.7;
        transform: scale(1.1);
    }
}
</style>
