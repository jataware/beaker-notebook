<template>
    <BeakerQueryCellEvent
        :event="props.event"
        :parent-query-cell="props.parentQueryCell"
        :code-styles="isExpanded ? '' : 'code-cell-collapsed'"
        :should-hide-answered-questions="true"
    >
        <template #code-cell-controls>
            <Button
                :icon="!isExpanded ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"
                size="small"
                class="code-cell-toggle-button"
                @click.stop="toggleExpansion"
                :title="!isExpanded ? 'Shrink code cell' : 'Expand code cell'"
            />
        </template>
    </BeakerQueryCellEvent>

</template>

<script setup lang="ts">
import { ref } from "vue";
import Button from "primevue/button";
import BeakerQueryCellEvent from "../cell/BeakerQueryCellEvent.vue";


const isExpanded = ref(false);

const props = defineProps([
    'event',
    'parentQueryCell',
]);

const toggleExpansion = (event) => {
  event.stopPropagation();
  isExpanded.value = !isExpanded.value;
};

</script>


<style lang="scss">
.code-cell-collapsed {
  max-height: 200px;
  overflow-y: hidden;
}
.code-cell-toggle-button {
  position: absolute;
  top: 5.5rem;
  right: 0;
  margin: 0;
  width: 2rem;
  height: 2rem;
  padding: 0;
  background: var(--p-surface-g);
  border-color: var(--p-surface-g);
  &>.p-button-icon {
    font-weight: bold;
  }
}
</style>
