<template>
    <div
        class="next-query-cell"
        ref="queryCellRef"
    >
        <div class="query-cell-grid">
            <div class="query-content">
                <div class="query-prompt">
                    <div class="query-label">
                        <span class="pi pi-user query-icon"></span>
                        <span class="query-label-user">User</span>
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

const autoCollapseCodeCells = ref(false);
const queryCellRef = ref<HTMLElement | null>(null);

watchEffect(() => {
    if (cell.value.metadata) {
        cell.value.metadata.auto_collapse_code_cells = autoCollapseCodeCells.value;
    }
});

watchEffect(() => {
    const currentStatus = cell.value.status;
    const currentQueryStatus = cell?.value?.metadata?.query_status;
    const currentEvents = events.value;
    const currentLastExecution = cell.value.last_execution;

    if (currentStatus === 'busy' && currentQueryStatus === 'pending') {
        cell.value.metadata.query_status = 'in-progress'
    } else if (currentStatus === 'failed') {
        cell.value.metadata.query_status = 'failed';
    } else if (currentStatus === 'idle' && currentEvents.length >= 0 && currentQueryStatus === 'in-progress') {
        if (currentLastExecution?.status === 'abort') {
            cell.value.metadata.query_status = 'aborted';
            return;
        }

        const hasAbortEvent = currentEvents.some(event => event.type === 'abort');
        if (hasAbortEvent) {
            cell.value.metadata.query_status = 'aborted';
            return;
        }

        const hasResponseEvent = currentEvents.some(event => event.type === 'response');
        if (hasResponseEvent && currentEvents.length > 0) {
            cell.value.metadata.query_status = 'success';
        }
    }
});

const badgeData = computed(() => {
    const queryStatus = cell.value.metadata?.query_status;
    const cellStatus = cell.value.status;
    const isActive = ['busy', 'awaiting_input'].includes(cellStatus);

    // Define badge configurations for each status
    const statusConfigs = {
        success: {
            severity: 'success',
            icon: 'pi pi-check bolded',
            tooltip: 'Query completed successfully'
        },
        failed: {
            severity: 'danger',
            icon: 'pi pi-times',
            tooltip: 'Query failed with error'
        },
        aborted: {
            severity: 'warn',
            icon: 'pi pi-minus',
            tooltip: 'Query was aborted'
        },
        'in-progress': {
            severity: isActive ? 'info' : 'danger',
            icon: isActive ? 'pi pi-spin pi-spinner busy-icon' : 'pi pi-times',
            tooltip: isActive ? 'Query is active' : 'Query failed with error'
        },
        pending: {
            severity: 'secondary',
            icon: 'pi pi-clock',
            tooltip: 'Query is waiting to start'
        }
    };

    // Return the configuration for the current status, or default for unknown status
    return statusConfigs[queryStatus] || {
        severity: 'secondary',
        icon: null,
        tooltip: 'Query status unknown'
    };
});

const executeOnce = (...args: any[]) => {
    if (['success', 'failed', 'in-progress'].includes(cell.value.metadata?.query_status)) {
        return;
    }
    execute.call(this, args);
}

defineExpose({
    execute: executeOnce,
    enter: () => {},
    exit,
    clear,
    cell,
});

onBeforeMount(() => {
    if (beakerSession?.cellRegistry) {
      beakerSession.cellRegistry[cell.value.id] = instance.vnode;
    }

    if (!cell.value.metadata?.query_status) {
        if(cell.value.metadata) {
            cell.value.metadata.query_status = 'pending';
        }
    }

    if (cell.value.metadata?.auto_collapse_code_cells !== undefined) {
        autoCollapseCodeCells.value = cell.value.metadata.auto_collapse_code_cells;
    }
});

onBeforeUnmount(() => {
    delete beakerSession.cellRegistry[cell.value.id];
});

</script>

<style lang="scss">
.next-query-cell {
    background-color: var(--p-surface-a);
    border-radius: var(--p-surface-border-radius);
    position: relative;
}

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
