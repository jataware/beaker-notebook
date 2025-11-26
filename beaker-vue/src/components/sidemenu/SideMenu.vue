<template>
    <div class="sidemenu-container" :class="[position]">
        <div class="sidemenu" :class="[position, (minimizeIndicator ? 'minimize' : undefined)]" :style="containerStyle" ref="panelRef">
            <div class="sidemenu-menu-selection" :class="[position]" ref="menuRef">
                <div
                    v-for="buttonPosition in ['top', 'middle', 'bottom']"
                    :key="buttonPosition"
                    :position="buttonPosition"
                    :class="['button-panel', `${buttonPosition}-buttons`]"
                >
                    <Button
                        v-for="{panel, idx} in panelsByPosition[buttonPosition]" :key="`button-${buttonPosition}-${idx}`"
                        :class="[
                            'menu-button',
                            props.highlight,
                            props.position,
                            (selectedTabIndex === idx ? 'selected' : undefined),
                            (props.showLabel ? 'show-label' : undefined),
                        ]"
                        :icon="panel.props?.icon"
                        :label="props.showLabel ? panel.props.label : undefined"
                        icon-pos="top"
                        @click="handleButtonClick(idx)"
                        v-tooltip:[toolTipArgs]="props.showTooltip ? panel.props.label : undefined"
                        text
                    ></Button>
                </div>
            </div>
            <div v-show="isExpanded" role="menu" class="sidemenu-panel-container">
                <component
                    v-for="(panel, index) in panels"
                    :key="`panel-${index}`"
                    :is="panel"
                    v-show="selectedTabIndex === index"
                    :selected="selectedTabIndex === index"
                />
            </div>
            <div v-if="isExpanded && !staticSize"
                class="sidemenu-gutter"
                @mousedown.prevent="startDragHandle"
                ref="gutterRef"
            >
                <div v-if="!staticSize" class="sidemenu-gutter-handle"></div>
            </div>
        </div>
    </div>
</template>

<script setup lang="tsx">
import { ref, watch, computed, getCurrentInstance, useSlots, defineSlots, isVNode, nextTick, onUnmounted, onMounted } from "vue";
import { type VNode } from "vue";

import Button from 'primevue/button';
import SideMenuPanel from "./SideMenuPanel.vue";

export type MenuPosition = "right" | "left";
export type HighlightType = "full" | "shadow" | "line";

export interface SideMenuProps {
    style?: {[key: string]: string};
    expanded?: boolean,
    position?: MenuPosition;
    highlight?: HighlightType;
    showLabel?: boolean;
    showTooltip?: boolean;
    staticSize?: boolean;
    initialWidth?: string;
    resizable?: boolean;
    maximized?: boolean;
}

const props = withDefaults(defineProps<SideMenuProps>(), {
    style: () => {return {}},
    expanded: true,
    highlight: "full",
    position: "right",
    showLabel: false,
    showTooltip: true,
    staticSize: false,
    initialWidth: '100%',
    resizable: true,
    maximized: false,
});

const emit = defineEmits([
    "panel-hide",
    "panel-show",
    "resize",
]);

const AUTO_CLOSE_MARGIN = 50;
const MINIMIZE_INDICATION_WIDTH = 8;

const slots = defineSlots<{
    default: () => any,
}>();

const selectedTabIndex = ref<number|null>(props.expanded ? 0 : null);
const panelWidth = ref<number|null>(null);
const listeners = ref({
    move: null,
    end: null,
});
const dragStartPos = ref<number|null>(null);
const dragStartWidth = ref<number|null>(null);
const dragDistance = ref<number|null>(null);
const panelRef = ref(null);
const menuRef = ref(null);
const gutterRef = ref(null);
const minimizeIndicator = ref<boolean>(false);
const resizeObserver = ref<ResizeObserver>();
const resizeHistory = ref<DOMRectReadOnly>();
const instance = getCurrentInstance();

let minWidth: number;
let menuWidth: number;
let closedWidth: number;

const isExpanded = computed(() => {
    return selectedTabIndex.value !== null;
});

const panels = computed(() => {
    const slotPanels = slots.default().filter((item) => {
        return (isVNode(item) && item.type === SideMenuPanel);
    });
    return slotPanels;
})

const panelsByPosition = computed(() => {
    const result: {[key: string]: {panel: VNode; idx: number}[]} = {
        top: [],
        middle: [],
        bottom: [],
    }
    panels.value?.forEach((panel, idx) => {
        const panelPos = panel.props.position || "top";
        result[panelPos].push({panel, idx});
    });
    return result;
});

const containerStyle = computed(() => {
    if (isExpanded.value) {
        let width: string;
        if (panelWidth.value !== null) {
            width = `${panelWidth.value}px`;
        }
        else if (props.maximized) {
            width = props.initialWidth;
        }
        else {
            const currWidth = (instance?.vnode?.el as HTMLDivElement)?.clientWidth;
            if (currWidth) {
                width = `${currWidth}px`;
            }
            else {
                width = props.initialWidth;
            }
        }
        return {
            ...props.style,
            width: width,
        };
    }
    else {
        return {
            ...props.style,
        };
    }
});

watch(isExpanded, () => {
    nextTick(() => {
        const offsetParent = instance.vnode.el.offsetParent;
        const backoff = offsetParent.scrollWidth - offsetParent.offsetWidth;
        if (backoff > 0) {
            panelWidth.value -= backoff;
        }
    });
});

const toolTipArgs = computed(() => {
    return {position: ({left: "right", right: "left"}[props.position])};
});

const startDragHandle = (evt: MouseEvent) => {
    if (listeners.value.move !== null) {
        try {
            document.removeEventListener("mousemove", listeners.value.move);
        }
        catch (e) {}
        listeners.value.move = null;
    }
    if (listeners.value.end !== null) {
        try {
            document.removeEventListener("mouseup", listeners.value.end);
        }
        catch (e) {}
        listeners.value.end = null;
    }
    listeners.value.move = document.addEventListener("mousemove", moveDragHandle);
    listeners.value.end = document.addEventListener("mouseup", endDragHandle);

    dragStartPos.value = evt.x;
    dragStartWidth.value = panelWidth.value || panelRef.value.clientWidth;
    menuWidth = menuRef.value.clientWidth;
    closedWidth = menuWidth + MINIMIZE_INDICATION_WIDTH;
    minWidth = menuWidth + AUTO_CLOSE_MARGIN;
};

const moveDragHandle = (evt: MouseEvent) => {
    let width: number;
    let resize = true;
    dragDistance.value = evt.x - dragStartPos.value;
    if (props.position === "left") {
        width = dragStartWidth.value + dragDistance.value;
    }
    else {
        width = dragStartWidth.value - dragDistance.value;
    }
    if (width <= minWidth) {
        resize = false;
        // Will be minimizing
        if (panelWidth.value != closedWidth) {
            resize = true;
            width = closedWidth;
            minimizeIndicator.value = true;
        }
    }
    else {
        minimizeIndicator.value = false;
    }

    if (resize) {
        panelWidth.value = width;
    }

    nextTick(() => {
        const offsetParent = instance.vnode.el.offsetParent;
        const backoff = offsetParent.scrollWidth - offsetParent.offsetWidth;
        if (backoff > 0) {
            panelWidth.value -= backoff;
        }
    });
}

const endDragHandle = (evt: MouseEvent) => {
    document.removeEventListener("mousemove", moveDragHandle);
    document.removeEventListener("mouseup", endDragHandle);
    // Normalize position to closes full pixel. Prevent display errors for partial pixel sizes.
    panelWidth.value = Math.round(panelWidth.value);
    // If dragged closed, assume they want the panel to be hidden
    if (panelWidth.value <= minWidth) {
        selectedTabIndex.value = null;
        panelWidth.value = null;
    }
    dragStartPos.value = null;
    dragDistance.value = null;
    minimizeIndicator.value = false;

};

const handleButtonClick = (index: number) => {
    if (selectedTabIndex.value !== index) {
        selectedTabIndex.value = index;
        emit("panel-show");
    }
    else {
        selectedTabIndex.value = null;
        emit("panel-hide");
    }
}

const isPanelSelected = (index: number) => {
    return Boolean(
        selectedTabIndex.value !== null &&
        selectedTabIndex.value === index
    );
}

const hidePanel = () => {
    selectedTabIndex.value = null;
}

const selectPanel = (id_or_label: string) => {
    selectedTabIndex.value = panels.value.findIndex(
        (panel) => (panel.props?.label === id_or_label || panel.props?.id === id_or_label)
    );
    if (minimizeIndicator.value) {
        minimizeIndicator.value = false;
    }
}

onMounted(() => {
    const target: HTMLElement = document.body;
    // Observer to smoothly resize the side menu when the document size changes (maximizing/resizing a browser window)
    resizeObserver.value = new ResizeObserver((entries) => {
        for (const entry of entries) {
            if (!resizeHistory.value) {
                resizeHistory.value = entry.contentRect;

            }
            else if (entry.contentRect !== resizeHistory.value) {
                if (panelWidth.value) {
                    const resizeRatio = entry.contentRect.width / resizeHistory.value.width;
                    panelWidth.value = panelWidth.value * resizeRatio;
                }
                resizeHistory.value = entry.contentRect;
            }
        }

    });
    resizeObserver.value.observe(target);
    const currWidth = (instance?.vnode?.el as HTMLDivElement)?.clientWidth;
    if (currWidth) {
        panelWidth.value =  currWidth;
    }
})

onUnmounted(() => {
    resizeObserver.value.disconnect();
    resizeObserver.value = null;
})

defineExpose({
    selectPanel,
    getSelectedPanelInfo: () => {
        if (selectedTabIndex.value === null) return null;
        const panel = panels.value[selectedTabIndex.value];
        return {
            index: selectedTabIndex.value,
            label: panel?.props?.label,
            id: panel?.props?.id,
        };
    },
    hidePanel
});

</script>


<style lang="scss">
.sidemenu-container {
    height: 100%;
    width: 100%;
    display: grid;
    &.right {
        grid:
            "spacer sidemenu" 100% /
            1fr max-content;

    }
    &.left {
        grid:
            "sidemenu spacer" 100% /
            max-content 1fr;
    }
}

.spacer {
    grid-area: spacer;
    flex-grow: 1;
    flex-shrink: 1000;
}

.sidemenu {
    grid-area: sidemenu;
    height: 100%;
    display: grid;
    box-sizing: border-box;
    width: 100%;

    &.right {
        grid:
            "gutter content menu" 100% /
            4px minmax(0px, 1fr) max-content;

        .sidemenu-panel-container {
            margin-left: 6px;
        }
    }

    &.left {
        grid:
            "menu content gutter" 100% /
            max-content minmax(0px, 1fr) 4px;

        .sidemenu-panel-container {
            margin-right: 6px;
        }
    }

    &.minimize {
        .sidemenu-gutter {
            width: 8px;
            background-color: var(--p-primary-color);
            .sidemenu-gutter-handle {
                right: -4px;
            }

        }
        .sidemenu-panel-container, .side-panel {
            width: 0;
            overflow: hidden;
            margin: 0;
        }
    }
}

.sidemenu-panel-container {
    grid-area: content;
    box-sizing: border-box;
    height: 100%;
    width: 100%;
    overflow: hidden;
}

.sidemenu-menu-selection {
    position: sticky;
    border: 1px solid var(--p-surface-border);
    grid-area: menu;
    background-color: var(--p-surface-b);
    display: flex;
    flex-direction: column;
    min-width: 3.5rem;

    > div {
        display: flex;
        flex-direction: column;

        &.button-panel {
            flex: 1;
        }
        &.bottom-buttons {
            flex-direction: column;
            justify-content: end;
        }
    }
}

.sidemenu-gutter {
    grid-area: gutter;
    position: relative;
    display: grid;
    flex-direction: row;
    align-items: center;
    background-color: var(--p-surface-border);
    z-index: 30;

    &:hover {
        cursor: col-resize;
        background-color: var(--p-surface-e);
    }
}

.sidemenu-gutter-handle {
    display: flex;
    position: absolute;
    width: 6px;
    left: -1px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 50;
    height: 40px;
    background-color: var(--p-primary-500);
    border-radius: 2px;
    transition: all 0.2s ease;
    filter: saturate(1.1);

    &::before {
        content: '';
        position: absolute;
        width: 12px;
        height: 46px;
        left: -3px;
        top: -3px;
        background: transparent;
        z-index: -1;
    }

    // expand handle when hovering over the larger area
    &:hover {
        width: 12px;
        height: 46px;
        left: -4px;
        top: 50%;
        transform: translateY(-50%);
    }
}

button.menu-button {
    background-color: transparent;
    border-color: transparent;
    aspect-ratio: 1;
    width: 100%;

    &.p-button-icon-only .p-button-icon{
        font-size: 1.15rem;
    }

    &:focus {
        box-shadow: none;
    }

    &:hover {
        color: var(--p-primary-700);
        background-color: var(--p-surface-c);
        border-color: var(--p-primary-700);
    }

    &.disabled {
        color: var(--p-surface-d);
        cursor: default;
        &:hover {
            background-color: var(--p-surface-c);
            border-color: var(--p-surface-d);
        }
    }
    &.line {
        border-radius: 0;
    }
    &.line.right {
        border-width: 0 6px 0 0;
    }
    &.line.left {
        border-width: 0 0 0 6px;
    }
    &.full {
        border-radius: 0;
        border-color: transparent;

        &.selected {
            background-color: var(--p-primary-600);
            border-radius: 0;
            border-color: transparent;
            color: var(--p-surface-b);
        }
        &:hover {
            border: none;
            border-color: transparent;
            box-shadow: none;
        }
    }
    &.selected {
        border-color: var(--p-primary-color);
    }

    &.shadow:hover {
        box-shadow: inset 0 0 15px var(--p-primary-800);
    }
    &.shadow.selected {
        box-shadow: inset 0 0 15px var(--p-primary-color);
    }
}

</style>
