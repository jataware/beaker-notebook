<template>
    <div
        class="cell-container drag-sort-enable"
        ref="cellsContainerRef"
    >
        <BeakerCell
            v-for="(cell, index) in session.notebook.cells"
            :cell="cell"
            :selected="cell.id === notebook.selectedCellId"
            :index="index"
            :key="`outercell-${cell.id}`"
            class="beaker-cell"
            :hide-cell-type-selector="cell.cell_type === 'query'"
            :hide-execute-button="cell.cell_type === 'query'"
            :class="{
                selected: (cell.id === notebook.selectedCellId),
                'drag-source': (index == dragSourceIndex),
                'drag-above': (index === dragOverIndex && index < dragSourceIndex),
                'drag-below': (index === dragOverIndex && index > dragSourceIndex),
                'drag-itself': (index === dragOverIndex && index === dragSourceIndex ),
                'drag-active': isDragActive,
            }"
            :drag-enabled="isDragEnabled"
            @move-cell="handleMoveCell"
            @dragstart="handleDragStart($event, cell, index)"
            @drop="handleDrop($event, index)"
            @dragover="handleDragOver($event, cell, index)"
            @dragend="handleDragEnd"
        >
            <component
                :is="typeof cellMap === 'function' ? cellMap(cell) : cellMap[cell.cell_type]"
                :cell="cell"
            />
        </BeakerCell>
        <div
            class="drop-overflow-catcher"
            @dragover="dragOverIndex = session.notebook.cells.length-1; $event.preventDefault();"
            @drop="handleDrop($event, session.notebook.cells.length-1)"
        >
            <slot name="notebook-background" />
        </div>
    </div>
</template>

<script setup lang="tsx">
import { ref, inject, computed } from 'vue';
import type { BeakerSession } from '@jataware/beaker-client';
import BeakerCell from '../cell/BeakerCell.vue';
import type { BeakerNotebookComponentType } from './BeakerNotebook.vue';

const session = inject<BeakerSession>('session');
const cellMap = inject("cell-component-mapping");
const notebook = inject<BeakerNotebookComponentType>("notebook");

const cellsContainerRef = ref(null);
const isDragActive = ref(false);
const dragSourceIndex = ref(-1);
const dragOverIndex = ref(-1);
const isDragEnabled = computed(() => session.notebook?.cells.length > 1);

const emit = defineEmits([]);


/**
 * Modifies array in place to move a cell to a new location (or any other elem)
 **/
function arrayMove(arr, old_index, new_index) {
    arr.splice(new_index, 0, arr.splice(old_index, 1)[0]);
}

function handleMoveCell(fromIndex, toIndex) {
    arrayMove(session.notebook.cells, fromIndex, toIndex)
}

/**
 * Sets call to item being moved
 * As well as dataTransfer so that drop target knows which one was dropped
 **/
function handleDragStart(event: DragEvent, beakerCell, index)  {
    if (event.target instanceof HTMLElement && event.dataTransfer !== null && event.target.matches(".drag-handle *")) {
        const paintTarget = event.target.closest('.beaker-cell');

        event.dataTransfer.dropEffect = 'move';
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('x-beaker/cell', JSON.stringify({
            id: beakerCell.id,
            index: index,
        }));
        if (paintTarget !== null) {
            event.dataTransfer.setDragImage(paintTarget, 0, 0);
        }
        isDragActive.value = true;
        dragSourceIndex.value = index;
    }
}

/**
 * Handles when dragging over a valid drop target
 * Both appends class to cell to mark placement of dragged cell if dropped there.,
 * as well as preventing the animation where the dragged cell animates back to
 * its place when dropped into a proper target.
 **/
function handleDragOver(event: DragEvent, beakerCell, index) {
    if (event?.dataTransfer?.types.includes("x-beaker/cell")) {
        dragOverIndex.value = index;
        event.preventDefault(); // Allow dropping
    }
}

/**
 * Handles reordering of cells if dropped within the sort-enabled cells area.
 **/
function handleDrop(event: DragEvent, index) {

    const target = event.target as HTMLElement;
    const allowedDropArea = target.closest('.drag-sort-enable');

    if (!allowedDropArea) {
        return;
    }

    const cellData = JSON.parse(event.dataTransfer?.getData('x-beaker/cell') || 'null');
    const sourceId = cellData.id;
    const sourceIndex = cellData.index;
    const targetId = session.notebook.cells[index].id

    if (sourceId !== targetId){
        arrayMove(session.notebook.cells, sourceIndex, index);
    }
}

function handleDragEnd() {
    isDragActive.value = false;
    dragOverIndex.value = -1;
    dragSourceIndex.value = -1;
}


function scrollBottomCellContainer(event) {
    if (cellsContainerRef.value) {
        cellsContainerRef.value.scrollTop = cellsContainerRef.value.scrollHeight;
    }
}


defineExpose({
    scrollBottomCellContainer,
});

</script>

<style lang="scss">
.cell-container {
    position: relative;
    flex: 1;
    background-color: var(--p-surface-b);
    // This z property is important, ensures the nice Beaker logo svg backdrop
    // is visible (on top of the notebook)
    z-index: 50;
    overflow: auto;
    width: 100%;
    height: 100%;

    // separators between cells
    > .beaker-cell {
        padding-top: 2px;
        border-collapse: separate;

    }
}

.drop-overflow-catcher {
    flex: 1;
}

</style>
