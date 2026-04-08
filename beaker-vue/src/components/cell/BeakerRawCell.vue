<template>
    <div class="raw-cell">
        <div class="raw-cell-header">
            <span class="raw-cell-title">Raw cell</span>
            <span v-if="props.cell.cell_type !== 'raw'"> - (Unrenderable cell type '{{ props.cell.cell_type }}')</span>
        </div>
        <CodeEditor
            display-mode="dark"
            language="julia"
            v-model="cell.source"
            ref="codeEditorRef"
            placeholder="Raw cell content..."
            :autofocus="false"
        />
    </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, getCurrentInstance, inject, onBeforeMount, onBeforeUnmount } from "vue";
import CodeEditor from "../misc/CodeEditor.vue";
import { findSelectableParent } from "../../util";
import { type BeakerSessionComponentType } from '../session/BeakerSession.vue';

const props = defineProps([
    "cell",
]);

const instance = getCurrentInstance();
const cell = ref(props.cell);
const codeEditorRef = ref<InstanceType<typeof CodeEditor>>(null);
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

enum ExecuteStatus {
  Success = 'success',
  Modified = 'modified',
  Error = 'error',
  Pending = 'pending',
}

const rawExtensions = computed(() => {
    const ext = [];
    // if (theme.value === 'dark') {
    //     ext.push(oneDark);
    // }
    return ext;

});


const execute = (evt: any) => {
    // Nothing to do but exit
    exit();
}

const enter = (position?: "start" | "end" | number) => {
    codeEditorRef.value?.focus();
    if (position === "start") {
        position = 0;
    }
    else if (position === "end") {
        position = codeEditorRef.value?.view?.state?.doc?.length;
    }
    if (position !== undefined) {
        codeEditorRef.value?.view?.dispatch({
            selection: {
                anchor: position,
                head: position,
            }
        });
    }
}

const exit = () => {
    // Be sure to blur editor even if we don't also refocus below.
    codeEditorRef.value.blur();
    const target: HTMLElement = (instance.vnode.el as HTMLElement);
    const selectableParent = findSelectableParent(target);
    selectableParent?.focus();
}

const clear = () => {
    cell.value.source = "";
}

defineExpose({
    execute,
    enter,
    exit,
    clear,
    model: cell,
    editor: codeEditorRef,
});

onBeforeMount(() => {
    if (cell.value?.id) {
        beakerSession.cellRegistry[cell.value.id] = instance.vnode;
    }
});

onBeforeUnmount(() => {
    if (cell.value?.id) {
        delete beakerSession.cellRegistry[cell.value.id];
    }
});
</script>

<script lang="ts">
import { BeakerRawCell } from "@jataware/beaker-client";
export default {
    modelClass: BeakerRawCell,
    icon: "pi pi-question-circle",
};
</script>


<style lang="scss">
.raw-cell {
    padding-right: 2em;

    .cm-editor {
        border: 1px solid var(--p-surface-d);
    }
    .cm-focused {
        outline: none;
        border: 1px solid var(--purple-200);
    }
    &.dark-mode {
        .cm-focused {
            border-color: #5b3c5b;
        }
    }
}

.raw-cell-header {
    margin-bottom: 0.5rem;
}

.raw-cell-title {
    font-weight: bold;
    font-size: large;
}
</style>
