<template>
  <div class="data-container">
    <div class="log-container">

      <!-- Some dev options to format json body display
      <div style="padding-bottom: 0.5rem; display: none;">
        <Checkbox
          v-model="options"
          id="quotes"
          name="quotes"
          value="quotes"
        />
        <label for="quotes" class="ml-2">quotes</label>

        <Checkbox
          class="ml-2"
          v-model="options"
          id="linenum"
          name="linenum"
          value="linenum"
        />
        <label for="linenum" class="ml-2">linenum</label>
      </div>
      -->

      <div class="flex-container">
        <div
          class="p-input-icon-left"
          style="padding: 0; margin: 0;"
        >
          <i class="pi pi-search" />
          <InputText
            v-model="filterValue"
            size="small"
            placeholder="Type"
          />
        </div>

        <div class="sort-actions p-buttonset">
          <Button @click="sortDirection = 'asc'" v-tooltip.bottom="'Sort Asc'" outlined size="small" icon="pi pi-sort-numeric-down" aria-label="Sort Time Asc" />
          <Button @click="sortDirection = 'desc'" v-tooltip.bottom="'Sort Desc'" outlined size="small" icon="pi pi-sort-numeric-up-alt" aria-label="Sort Time Desc" />
        </div>

      </div>

      <Panel
        class="log-panel"
        :class="{odd: ((index as number) % 2) !== 0}"
        :data-index="logEntry.timestamp"
        v-for="(logEntry,index) in filteredLogs" :key="`${logEntry.type}-${logEntry.timestamp}`"
        :header="logEntry.type"
      >
        <vue-json-pretty
          :data="logEntry.body"
          :deep="2"
          showLength
          showIcon
          :showDoubleQuotes="isQuotes"
          :showLineNumber="linenum"
        />
      </Panel>

      <div
        class="bottom-actions"
      >
        <Button
          v-if="filteredLogs.length"
          label="Clear Logs"
          severity="warning"
          size="small"
          @click="$emit('clearLogs')"
        />
        <p v-else>
        <!-- We could detect if context debug is disabled and add a button here-->
          No logs. Ensure debug is enabled on context configuration.
        </p>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>

import { ref, computed, watch } from "vue";
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import VueJsonPretty from 'vue-json-pretty';
import 'vue-json-pretty/lib/styles.css';
// import Checkbox from 'primevue/checkbox'; // Commented dev opts in template
import Panel from 'primevue/panel';

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

const options = ref([]);

const isQuotes = computed(() => {
  return options.value.includes('quotes');
});

const linenum = computed(() => {
  return options.value.includes('linenum');
})

const filteredLogs = computed(() => {
  const sortby: (arg: any) => number = props.sortby || ((entry) => entry.timestamp);
  const asc = (a: any, b: any) => (sortby(a) > sortby(b) ? 1 : (sortby(a) < sortby(b)) ? -1 : 0);
  const desc = (a: any, b: any) => (sortby(a) < sortby(b) ? 1 : (sortby(a) > sortby(b)) ? -1 : 0);

  const filtered = props.entries?.filter(entry => entry.type.includes(debouncedFilter.value));

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
.data-container {
  // The internal class for the json viewer-
  // Change the hoder color for better contrast
  .vjs-tree-node:hover{
    background-color: var(--p-surface-b);
  }
  height: 100%;
  width: 100%;
  overflow-y: auto;
}

.ml-2 {
  margin-left: 0.5rem;
}

.flex-container {
  display: flex;
  align-items: center;
  margin-bottom: 0.5rem;
  justify-content: space-between;
  flex-wrap: wrap;
}

.log-container {
  padding: 0.5rem;
}

.log-panel {
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

  // If we wanted to alternate widget panel-heading bg color or so:
  // &.odd {
  //   .p-panel-header {
  //     background: var(--p-surface-b);
  //   }
  // }
}

.log-panel::before {
  content: attr(data-index);
  color: var(--p-gray-300);
  position: absolute;
  right: 1rem;
  top: 0.4rem;
}

.bottom-actions {
  width: 100%;
  display: flex;
  margin-top: 0.5rem;
  justify-content: center;
  color: var(--p-text-color-secondary);
}

.sort-actions {
  .p-button {
    border-color: var(--p-surface-d);
  }
}

</style>
