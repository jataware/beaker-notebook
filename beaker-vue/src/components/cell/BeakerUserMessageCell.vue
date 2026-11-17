<template>
    <div class="query-cell-grid">
        <div class="query-content">
            <div class="query-prompt">
                <div class="query-label">
                    <span class="pi pi-user query-icon"></span>
                    <span class="query-label-user">User</span>
                </div>
                <div v-if="cell.session_attachments?.length" class="query-attachments">
                    <span
                        v-for="attachment in cell.session_attachments"
                        :key="attachment.id"
                        class="query-attachment"
                        :title="attachment.archive_error || attachment.name"
                    >
                        <i :class="attachment.kind === 'archive' ? 'pi pi-box' : 'pi pi-paperclip'"></i>
                        {{ attachment.name }}
                        <small v-if="attachment.kind === 'archive' && attachment.archive_status === 'extracted'">
                            {{ attachment.file_count }} {{ attachment.file_count === 1 ? 'file' : 'files' }}
                        </small>
                        <i
                            v-if="attachment.archive_status === 'failed'"
                            class="pi pi-exclamation-triangle attachment-warning"
                        ></i>
                    </span>
                </div>
                <div class="query-text">{{ cell.source }}</div>
            </div>
        </div>

        <div class="state-info">
            <div>
                <Badge
                    class="execution-badge"
                    :class="{secondary: badgeData.severity === 'secondary'}"
                    :severity="badgeData.severity"
                    value=" "
                    v-tooltip.top="badgeData.tooltip">
                    <i :class="badgeData.icon"></i>
                </Badge>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { inject, computed, onBeforeMount, getCurrentInstance, onBeforeUnmount, watchEffect, ref } from "vue";
import Badge from 'primevue/badge';
import type { BeakerSessionComponentType } from "../session/BeakerSession.vue";
import { useBaseQueryCell } from './BaseQueryCell';

const props = defineProps([
    'index',
    'cell',
    'badgeData',
    'pending',
]);

const {
  cell,
  events,
  execute,
  exit,
  clear,
} = useBaseQueryCell(props);

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const instance = getCurrentInstance();

const badgeData = computed(() => {
    if (props.badgeData) {
        return badgeData;
    }
    else if (props.pending) {
        return {
            severity: 'secondary',
            icon: 'pi pi-clock',
            tooltip: 'Query is waiting to start'
        };
    }
    else {
        return {
            severity: 'success',
            icon: 'pi pi-check bolded',
            tooltip: 'Query completed successfully'
        };
    }
});

defineExpose({
    execute: () => {},
    enter: () => {},
    exit,
    clear,
    cell,
});

onBeforeMount(() => {
    console.log('a', beakerSession?.cellRegistry);
    if (beakerSession?.cellRegistry && !beakerSession.cellRegistry.hasOwnProperty(cell.value.id)) {
        console.log('b');
      beakerSession.cellRegistry[cell.value.id] = instance.vnode;
    }

});

onBeforeUnmount(() => {
    delete beakerSession.cellRegistry[cell.value.id];
});

</script>

<style lang="scss">

.query-cell-grid {
    display: grid;
    grid-template-areas:
        "content content content exec";
    grid-template-columns: 1fr 1fr 1fr auto;
}

.query-content {
    grid-area: content;
    margin: 0.1rem 0.25rem 0.33rem 0rem;
}

.state-info {
    grid-area: exec;
    display: flex;
    flex-direction: column;
}

.query-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-weight: 600;
    min-height: 1.8rem;

    .query-label-user {
        color: var(--p-green-600);
    }
}

.query-icon {
    color: var(--p-green-600);
    // font-size: 1.1rem;
}

.query-text {
    border-radius: var(--p-surface-border-radius);
    white-space: pre-wrap;
    font-family: inherit;
    margin-top: 0.33rem;
}

.query-attachments {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.25rem;
}

.query-attachment {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--p-content-border-color);
    border-radius: 999px;
    background: var(--p-content-background);
    font-size: 0.85rem;

    small {
        color: var(--p-text-muted-color);
    }
}

.attachment-warning {
    color: var(--p-orange-500);
}

.collapse-control {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0.5rem 0 0.25rem 0;
    background-color: var(--p-surface-0);
}

.collapse-label {
    font-size: 0.875rem;
    color: var(--p-text-color-secondary);
    cursor: pointer;
    user-select: none;
}

.execution-badge {
    font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
    font-size: 1rem;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 2em;
    aspect-ratio: 1/1;
    border-radius: 15%;
    position: relative;

    &.secondary {
        background-color: var(--p-surface-e);
    }
    i {
        font-size: 1rem;
        position: absolute;
        color: inherit;
    }
}

.busy-icon {
    font-weight: bold;
    margin: 0;
}

.brain-icon {
    width: 1rem;
    height: 1rem;

    svg {
        width: 100%;
        height: 100%;
    }

    .brain-svg-path {
        fill: var(--p-badge-secondary-color);
    }
}

.bolded {
    font-weight: bold;
}
</style>
