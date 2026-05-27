<template>
    <div
        class="panel-cell-container"
    >
        <div class="flex-background">
            <slot name="notebook-background" />
        </div>
        <span class="chat-help-text-display query-answer-chat-override">
            <slot name="help-text"></slot>
        </span>
        <component
            v-for="(cell, index) in chatCompatibleCells"
            :cell="cell"
            :key="cell.id || index"
            :is="props.cellMap[cell.cell_type]"
            class="beaker-chat-cell"
        />
    </div>
</template>

<script setup lang="tsx">
import { ref, inject, computed } from 'vue';
import { BeakerSession } from '@jataware/beaker-client';

const session = inject<BeakerSession>('session');

const props = defineProps([
    "cellMap"
])

/**
 * New notebook interface flattens and exposes query cells children as top-level sibling cells.
 * Do not show these on the chat interface, as those cells are shown as part of the AgentActivity pane. 
 */
const chatCompatibleCells = computed(() => {
    return session.notebook.cells.filter(cell => !cell.metadata?.parent_query_cell)
})

</script>

<style lang="scss">
.panel-cell-container {
    position: relative;
    display: flex;
    flex: 1;
    flex-direction: column;
    z-index: 3;
    overflow: auto;
}

.flex-background {
    flex: 1;
}

.chat-help-text-display {
    margin-bottom: 1rem;
}
</style>
