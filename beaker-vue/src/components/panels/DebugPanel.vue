<template>
    <div class="debug-panel-wrapper">
        <div class="debug-log-container">
            <div class="debug-flex-container">
                <span
                    class="p-input-icon-right"
                    style="padding: 0; margin: 0;"
                >
                    <i class="pi pi-search" />
                    <InputText
                        v-model="filterValue"
                        size="small"
                        placeholder="Type"
                    />
            </span>

                <div class="debug-sort-actions p-buttonset">
                    <Button @click="sortDirection = 'asc'" v-tooltip.bottom="'Sort Asc'" outlined size="small" icon="pi pi-sort-numeric-down" aria-label="Sort Time Asc" />
                    <Button @click="sortDirection = 'desc'" v-tooltip.bottom="'Sort Desc'" outlined size="small" icon="pi pi-sort-numeric-up-alt" aria-label="Sort Time Desc" />
                </div>
            </div>
            <DebugLogMessage
                v-for="(logEntry) in filteredLogs"
                :log-entry="logEntry"
                :key="`${logEntry.type}-${logEntry.timestamp}`"
            />

            <div class="debug-bottom-actions">
                <Button
                    v-if="filteredLogs.length"
                    label="Clear Logs"
                    severity="warning"
                    size="small"
                    @click="$emit('clearLogs')"
                />
                <p v-else>
                    <!-- We could detect if context debug is disabled and add a button here-->
                    No logs yet.
                </p>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>

import { ref, computed, watch } from "vue";
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import DebugLogMessage from "../misc/DebugLogMessage.vue";

const props = defineProps([
    "entries",
    "sortby",
])

const emit = defineEmits([
    'clearLogs'
]);

const filterValue = ref("");
const debouncedFilter = ref("");
const sortDirection = ref("asc");

const hideSubkernelInternals = ref(false);

let filterDebounceTimer: ReturnType<typeof setTimeout> | null = null;
watch(filterValue, (value) => {
    if (filterDebounceTimer !== null) {
        clearTimeout(filterDebounceTimer);
    }
    filterDebounceTimer = setTimeout(() => {
        debouncedFilter.value = value;
        filterDebounceTimer = null;
    }, 400);
});

const filteredLogs = computed(() => {
    const sortby: (arg: any) => number = props.sortby || ((entry) => entry.timestamp);
    const asc = (a: any, b: any) => (sortby(a) > sortby(b) ? 1 : (sortby(a) < sortby(b)) ? -1 : 0);
    const desc = (a: any, b: any) => (sortby(a) < sortby(b) ? 1 : (sortby(a) > sortby(b)) ? -1 : 0);

    const isSubkernelInternal = (entry) => {
        const messageTypes = [
            'new_kernel',
            'init-agent',
            'debug_update',
            'execution_start',
            'execution_end'
        ]
        if (messageTypes.includes(entry.type)) {
            return true;
        }
        const metadataTypes = ['get_subkernel_state', 'preview']
        if (metadataTypes.includes(entry?.body?.metadata?.type)) {
            return true;
        }
        return false;
    }

    const filtered = props.entries
        ?.filter(entry => debouncedFilter.value !== "" ? entry?.type?.includes(debouncedFilter.value) : true)
        ?.filter(entry => hideSubkernelInternals.value ? !isSubkernelInternal(entry) : true);


    // Return sorted list
    if (sortDirection.value === 'asc') {
        return filtered.sort(asc);
    }
    else {
        return filtered.sort(desc);
    }
});


</script>

<style lang="scss">
.debug-panel-wrapper {
    // The internal class for the json viewer-
    // Change the hover color for better contrast
    .vjs-tree-node:hover {
        background-color: var(--p-surface-b);
    }
    height: 100%;
    width: 100%;
    overflow-y: auto;
}

.debug-flex-container {
    display: flex;
    align-items: center;
    margin-bottom: 0.5rem;
    justify-content: space-between;
    flex-wrap: wrap;
}

.debug-log-container {
    padding: 0.5rem;
}

.debug-bottom-actions {
    width: 100%;
    display: flex;
    margin-top: 0.5rem;
    justify-content: center;
    color: var(--p-text-color-secondary);
}

.debug-sort-actions {
    display: flex;
    flex-direction: row;
    .p-button {
        border-color: var(--p-surface-d);
    }
}

.debug-flex-container {
  .p-input-icon-right {
    padding: 0px;
    margin: 0px;
    // padding-right: 0.5rem;
    display: flex;
    flex-direction: row;
    align-items: center;
    position: relative;

    & > i.pi-search {
      position: absolute;
      right: 0.5rem;
      color: var(--p-primary-color);
      pointer-events: none;
    }
  }
}

</style>
