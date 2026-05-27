<template>
    <div
        class="beaker-cell"
        tabindex="0"
        @click="clicked"
        ref="beakerCellRef"
        :class="{collapsed}"
        :cell-id="cell.id"
        :style="collapsed ? { '--dynamic-collapse-height': collapseHeight } : {}"
    >
        <div class="collapse-box" @click.prevent="collapseCell"></div>
        <div
            class="drag-handle"
        >
            <DraggableMarker
                :draggable="props.dragEnabled"
            />
        </div>
        <div class="cell-contents">
            <slot name="default">
            </slot>

            <slot name="child-cells">
            </slot>
        </div>

        <div class="menu-area" ref="menuAreaRef">
        <slot name="hover-menu">
            <div class="hover-menu"
                @pointerenter="overlayMenuHoverHandler"
                @pointerleave="overlayMenuHoverHandler"
            >
                <Button
                    ref="cellMenuButton"
                    class="cell-menu-button"
                    text
                    small
                    icon="pi pi-ellipsis-v"
                    @click.prevent="hoverMenuRef.show($event);"
                />
                <Popover
                    class="menu-overlay"
                    ref="hoverMenuRef"
                    :cell-id="cell.id"
                    @pointerenter="overlayMenuHoverHandler"
                    @pointerleave="overlayMenuHoverHandler"
                >
                    <div v-tooltip.left="'Change Cell Type'" v-if="!shouldHideCellTypeAndExecuteButtons">
                        <Select
                            :name="`${cell.id}-celltype`"
                            class="cell-type-selector overlay-menu-button"
                            :model-value="cell.cell_type"
                            @update:model-value="(value) => {notebook.convertCellType(cell, value); hoverMenuRef.hide();}"
                            :options="Object.keys(typeof cellMap === 'function' ? cellMap(null) : cellMap || {})"
                            :dropdown-icon="cellIcon"
                            :label-style="{display: 'none'}"
                            append-to="self"
                        >
                            <template #value="slotProps">
                                <span :class="cellIconMap[slotProps.value]"></span>
                            </template>

                            <template #option="slotProps">
                                <div class="cell-type-dropdown-item">
                                    <span :class="cellIconMap[slotProps.option]"></span>
                                    <span>{{ slotProps.option }}</span>
                                </div>
                            </template>
                        </Select>
                    </div>
                    <Button
                        v-tooltip.left="'Execute cell'"
                        v-if="!shouldHideCellTypeAndExecuteButtons"
                        @click="beakerSession.findNotebookCellById(cell.id).execute(); hoverMenuRef.hide();"
                        icon="pi pi-play"
                        size="small"
                        text
                    />
                    <Button
                        v-tooltip.left="'Remove cell'"
                        @click="notebook.removeCell(beakerSession.findNotebookCellById(cell.id)); hoverMenuRef.hide();"
                        icon="pi pi-minus"
                        size="small"
                        text
                    />
                    <Button
                        v-tooltip.left="'Move cell up'"
                        @click="moveUp(); hoverMenuRef.hide();"
                        icon="pi pi-chevron-up"
                        size="small"
                        text
                    />
                    <Button
                        v-tooltip.left="'Move cell down'"
                        @click="moveDown(); hoverMenuRef.hide();"
                        icon="pi pi-chevron-down"
                        size="small"
                        text
                    />
                    <!-- <Button
                        v-tooltip="'Cut cell'"
                        @click="notebook.removeCell(beakerSession.findNotebookCellById(cell.id)); hoverMenuRef.hide();"
                        size="small"
                        text
                        label="✂"
                    /> -->
                </Popover>
            </div>
        </slot>
        </div>
        <div class="extra-area">
            <slot name="extra">
            </slot>
        </div>

    </div>
</template>


<script setup lang="ts">
import { ref, inject, computed } from "vue";
import Button from 'primevue/button';
import DraggableMarker from './DraggableMarker.vue';
import type { BeakerNotebookComponentType } from '../notebook/BeakerNotebook.vue';

import type { IBeakerCell } from "@jataware/beaker-client";
import Select from "primevue/select";
import Popover from "primevue/popover";
import type { BeakerSessionComponentType } from "../session/BeakerSession.vue";

interface BeakerCellProps {
    cell: IBeakerCell;
    index?: number;
    dragEnabled?: boolean;
}

const props = defineProps<BeakerCellProps>();
const emit = defineEmits([
    'move-cell',
]);

const beakerSession = inject<BeakerSessionComponentType>('beakerSession');
const notebook = inject<BeakerNotebookComponentType>("notebook");
const cellMap = inject("cell-component-mapping");

const clicked = (evt) => {
    if (!evt.defaultPrevented) {
        notebook.selectCell(props.cell as {id: string}, );
    }
};

const beakerCellRef = ref<HTMLDivElement|null>(null);
const hoverMenuRef = ref(null);
const cellMenuButton = ref(null);
const metadata = ref(props.cell.metadata);
const collapsed = computed(() => {
    return metadata.value?.collapsed || false;
});

const collapseHeight = computed(() => {
    if (!collapsed.value || !beakerCellRef.value) {
        return 'auto';
    }
    
    const cellElement = beakerCellRef.value;
    const naturalHeight = cellElement.scrollHeight;
    if (naturalHeight < 250) {
        return '3.5em';
    } else {
        return '250px';
    }
});

const cellIconMap = {
    "code": "pi pi-code",
    "markdown": "pi pi-pencil",
    "query": "pi pi-sparkles",
    "raw": "pi pi-question-circle",
};

const cellIcon = computed(() => cellIconMap[props.cell.cell_type]);

const isThoughtCell = computed(() => {
    return props.cell.cell_type === 'markdown' && 
           props.cell.metadata?.beaker_cell_type === 'thought';
});

const isResponseCell = computed(() => {
    return props.cell.cell_type === 'markdown' && 
           props.cell.metadata?.beaker_cell_type === 'response';
});

const isQuestionCell = computed(() => {
    return props.cell.cell_type === 'markdown' && 
           props.cell.metadata?.beaker_cell_type === 'user_question';
});

const isErrorCell = computed(() => {
    return props.cell.cell_type === 'markdown' && 
           props.cell.metadata?.beaker_cell_type === 'error';
});

const isAbortCell = computed(() => {
    return props.cell.cell_type === 'markdown' && 
           props.cell.metadata?.beaker_cell_type === 'abort';
});

const shouldHideCellTypeAndExecuteButtons = computed(() => {
    return isThoughtCell.value || isResponseCell.value || isQuestionCell.value || isErrorCell.value || isAbortCell.value || 
    props.cell.cell_type === 'query';
});

enum CellState {
    Success = 'success',
    Modified = 'modified',
    Error = 'error',
    Pending = 'pending',
}

const collapseCell = (evt) => {
    if (metadata.value) {
        metadata.value.collapsed = !collapsed.value;
    }
};

const moveUp = () => {
    if (props.index > 0) {
        emit("move-cell", props.index, props.index - 1);
    }
}

const moveDown = () => {
    if (props.index < notebook.cellCount - 1) {
        emit("move-cell", props.index, props.index + 1);
    }
}

const overlayMenuHoverHandler = (event: PointerEvent) => {
    // Trigger if we are entering, but not moving between elements with the specified classes
    if (!((event?.target instanceof HTMLElement) && (event?.relatedTarget instanceof HTMLElement))) {
        return;
    }
    const selectors = [
        `[cell-id="${props.cell.id}"] .menu-area`,
        `[cell-id="${props.cell.id}"] .hover-menu`,
        `.menu-overlay[cell-id="${props.cell.id}"]`,
    ];
    const selectorString = selectors.join(', ');
    const closest = event.relatedTarget.closest(selectorString);
    const ignore = closest !== null;
    if (!ignore) {
        if (event.type.toLowerCase().includes('enter')) {
            hoverMenuRef.value.show(event, cellMenuButton.value.$el);
        }
        else if (event.type.toLowerCase().includes('leave')) {
            hoverMenuRef.value.hide();
        }
    }
}

</script>

<style lang="scss">

.beaker-cell {
    display: grid;
    border-radius: 0;
    position: relative;
    background-color: var(--p-surface-a);
    --collapsed-height: 3.5em;
    --dynamic-collapse-height: var(--collapsed-height);
    min-height: 3.5em;

    grid:
        "collapse-box drag-handle cell-contents hover-menu" min-content
        "collapse-box drag-handle cell-contents extra" 1fr /
        10px 1.6rem 1fr 2.5em;

    &.selected .collapse-box {
        background-color: var(--p-primary-400);
    }

    &:focus {
        outline: none;
    }

    // Separators between cells
    &:not(.collapsed):after {
        content: "";
        position: absolute;
        height: 4px;
        left: 0;
        bottom: -2px;
        right: 0px;
        z-index: 0;
        background-color: var(--p-surface-border);
    }

    &.collapsed {
        overflow: hidden;

        .cm-editor {
            max-height: var(--dynamic-collapse-height);
        }
        max-height: var(--dynamic-collapse-height);
    }

    &.selected.collapsed .collapse-box {
        background-color: var(--p-primary-400);
    }

    &.collapsed .collapse-box {
        --wave-color: var(--p-surface-border);
        background-color: var(--wave-color);
        box-shadow: 0.3em 0 0.5em var(--p-surface-border);

        &:after {
            content: "";
            position: absolute;
            z-index: 200;
            height: 10px;
            bottom: -2px;
            left: 0;
            right: 0;
            background-color: var(--wave-color);
            --mask:
                radial-gradient(8.059999999999999px at 50% calc(100% + 4.25px),#0000 calc(99% - 3px),#000 calc(101% - 3px) 99%,#0000 101%) calc(50% - 10px) calc(50% - 4px + .5px)/20px 8px repeat-x,
                radial-gradient(8.059999999999999px at 50% -4.25px,#0000 calc(99% - 3px),#000 calc(101% - 3px) 99%,#0000 101%) 50% calc(50% + 4px)/20px 8px repeat-x;
            -webkit-mask: var(--mask);
            mask: var(--mask);
        }
    }

}

.collapse-box {
    grid-area: collapse-box;
    border: 1px inset var(--p-surface-border);
    border-top: unset;
    border-bottom: unset;
    cursor: pointer;

    &:hover {
        background-color: color(from var(--p-surface-border) srgb r g b / 0.5);
    }
}

.cell-contents {
  grid-area: cell-contents;
  margin: 0.5em 0;
}

.drag-handle {
    grid-area: drag-handle;
    align-content: center;
    justify-self: center;
    z-index: 10;

    .draggable-wrapper {
        height: 3rem;
        width: 1rem;
        background-position: 0.5rem 0.5rem;
        background-size: 0.5rem 0.5rem;

        &:hover {
            opacity: 0.9;
        }
    }
}

.drag-disabled {
    pointer-events: none;
    opacity: 0.2;
}

.drag-source {
    &:after {
        content: "";
        position: absolute;
        top: 0px;
        left: 0px;
        bottom: 0px;
        right: 0px;
        z-index: 0;
        background-color: rgba(128, 128, 128, 0.33);
    }
}

.drag-above {
    box-shadow: 0px -5px 1px var(--purple-200);

    &:first-child {
        margin-top: 5px;
        padding-top: calc(1rem - 5px);
    }
}

.drag-itself, .drag-itself.selected {
    background-color: var(--purple-200);
}

.drag-below {
    box-shadow: 0px 5px 0px var(--purple-200);
    margin-bottom: 5px;
    padding-bottom: calc(1rem - 5px);
}

.menu-area {
    grid-area: hover-menu;
    margin: 0.5em 0.25em 0 0;
    height: 2em;
    width: 100%;

    .cell-menu-button {
        height: 1.5em;
        width: 1.5em;
        aspect-ratio: 1 / 1;
        border-width: 0;
        padding: auto;
        border-radius: var(--p-surface-border-radius);

        .p-button-icon {
            font-size: smaller;
        }
    }
}

.hover-menu {
    height: 100%;
    width: 100%;
    padding: auto;
    text-align: center;
}

.menu-overlay {
    .p-popover-content{
        display: flex;
        flex-direction: column;
        padding: 0.8rem;
        row-gap: 0.5rem;
    }

    .p-button, .overlay-menu-button {
        background-color: var(--p-surface-a);
        color: var(--p-primary-color);
        --shadow: #777;
        aspect-ratio: 1 / 1;
        width: 1.75rem;
        padding: 0;
        border-color: var(--p-surface-border);
        box-shadow: 0px 3px 1px -2px color(from var(--shadow) srgb r g b / 0.5),
                    0px 2px 2px 0px color(from var(--shadow) srgb r g b / 0.25),
                    0px 1px 5px 0px color(from var(--shadow) srgb r g b / 0.22);
        .pi {
            color: var(--p-primary-color);
        }
    }

}

.cell-type-selector {
    grid-area: cell-type-dropdown;
    margin-left: auto;
    margin-right: auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    .p-dropdown-label {
        display: flex;
        align-items: center;
        justify-content: center;
        margin: auto;
        padding: 0;
        width: 100%;
        aspect-ratio: 1 / 1;
    }
    .p-dropdown-trigger {
        display: none;
        width: 0;
    }
}
.cell-type-dropdown-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    img {
        width: calc(2.5rem - 2px);
        aspect-ratio: 1 / 1;
    }
}

.extra-area {
    margin: 0.25em 0.25em 0.25em 0;
}
</style>
