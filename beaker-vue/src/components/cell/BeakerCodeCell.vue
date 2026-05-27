<template>
        <div class="code-cell">
            <div class="code-cell-grid">
                <div
                    class="code-data"
                    :class="{
                        'dark-mode': theme.mode === 'dark',
                        [codeStyles]: props.codeStyles
                    }"
                >
                    <CodeEditor
                        display-mode="dark"
                        :language="language"
                        v-model="cell.source"
                        ref="codeEditorRef"
                        placeholder="Your code..."
                        :disabled="isBusy"
                        @change="handleCodeChange"
                        @click="clicked"
                        :annotations="lintAnnotations"
                        :annotation-provider="'linter'"
                    />
                </div>
                <div class="code-output">
                    <CodeCellOutput
                        :outputs="cell.outputs"
                        :busy="isBusy"
                        v-show="!hideOutput && cell.outputs.length"
                        :dropdown-layout="false"
                    />
                </div>
                <div class="state-info">
                    <div>
                        <Badge
                            class="execution-count-badge"
                            :class="{secondary: badgeSeverity === 'secondary'}"
                            :severity="badgeSeverity"
                            :value="cell.execution_count || '&nbsp;'">
                        </Badge>
                    </div>
                    <i
                        v-if="isBusy"
                        class="pi pi-spin pi-spinner busy-icon"
                    />
                    <AnnotationButton
                        :action="analyzeCell"
                        v-tooltip.bottom="{value: 'Analyze this code.', showDelay: 300}"
                        text
                    />
                    <Button
                        v-if="hasRollback"
                        class="rollback-button"
                        :severity="badgeSeverity"
                        icon="pi pi-undo"
                        size="small"
                        @click="rollback"
                    />
                </div>
            </div>
        </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, inject, getCurrentInstance, onBeforeMount, onBeforeUnmount, nextTick, watch } from "vue";
import CodeCellOutput from "./BeakerCodeCellOutput.vue";
import Badge from 'primevue/badge';
import Button from 'primevue/button';
import { findSelectableParent } from "../../util";
import { BeakerSession } from "@jataware/beaker-client";
import CodeEditor from "../misc/CodeEditor.vue";
import AnnotationButton from "../misc/buttons/AnnotationButton.vue";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import type { BeakerNotebookComponentType } from '../notebook/BeakerNotebook.vue';
import type { IBeakerTheme } from '../../plugins/theme';

const props = defineProps([
    "cell",
    "hideOutput",
    "codeStyles"
]);

const cell = ref(props.cell);
const { theme } = inject<IBeakerTheme>('theme');
const session = inject<BeakerSession>('session');
const codeEditorRef = ref<InstanceType<typeof CodeEditor>>();
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const notebook = inject<BeakerNotebookComponentType>("notebook");
const instance = getCurrentInstance();

const lintAnnotations = ref<{}[]>([]);

const emit = defineEmits([
    'blur',
])

enum ExecuteStatus {
  Success = 'ok',
  Modified = 'modified',
  Error = 'error',
  Pending = 'pending',
  None = 'none'
}

const hasRollback = computed(() => {
    return typeof(cell.value?.last_execution?.checkpoint_index) !== "undefined";
});

const rollback = () => cell.value.rollback(session);

const isBusy = computed(() => {
    return cell.value?.busy;
});

interface LinterCodeCell {
    [key: string]: string;
    cell_id: string;
    content: string;
}
interface LinterCodeCellPayload {
    [key: string]: string|LinterCodeCell[];
    notebook_id: string;
    cells: LinterCodeCell[];
}

const analyzeCell = async () => {
    const payload: LinterCodeCellPayload = {
        notebook_id: notebook.id,
        cells: [{
            cell_id: cell.value.id,
            content: cell.value.source,
        }],
    };
    const lintAction = session.executeAction("lint_code", payload)
    // Make sure to await completion so spinner does not disappear early.
    await lintAction.done;
};

const badgeSeverity = computed(() => {
    const defaultValue = "secondary";
    const mappings = {
        [ExecuteStatus.Success]: 'success',
        [ExecuteStatus.Modified]: 'warning',
        [ExecuteStatus.Error]: 'danger',
        [ExecuteStatus.Pending]: defaultValue,
        [ExecuteStatus.None]: defaultValue,
    };
    return mappings[cell.value?.last_execution?.status] || defaultValue;
});

const clicked = (evt) => {
    if (notebook) {
        notebook.selectCell(cell.value);
    }
    evt.stopPropagation();
};

function handleCodeChange() {
    cell.value.reset_execution_state();
}

const language = computed(() => (beakerSession.activeContext?.language?.slug || undefined));

const execute = (evt: any) => {
    const future = props.cell.execute(session);
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
    codeEditorRef.value?.blur();
    const target: HTMLElement = (instance.vnode.el as HTMLElement);
    const selectableParent = findSelectableParent(target);
    selectableParent?.focus();
}

const clear = () => {
    cell.value.source = "";
    cell.value.outputs.splice(0, cell.value.outputs.length);
}

defineExpose({
    execute,
    enter,
    exit,
    clear,
    cell,
    editor: codeEditorRef,
    lintAnnotations,
});

onBeforeMount(() => {
    beakerSession.cellRegistry[cell.value.id] = instance.vnode;
});

onBeforeUnmount(() => {
    delete beakerSession.cellRegistry[cell.value.id];
});

/* Sync execution_count for derived cells from query cell flattening
 * This is needed as cells may be created immediately and returned, while flattening,
 but the kernel may not be ready yet to report the source code cell execution results/count.
 The watcher is smart enough to break early if needsExecutionCountSync is falsey which will
 be a lot more efficient when that's the case.
 */
const isFlattenedCell = computed(() => {
    return cell.value.metadata?.source_cell_id && 
           cell.value.metadata?.beaker_cell_type === 'code';
});
const needsExecutionCountSync = computed(() => {
    return isFlattenedCell.value && 
           (cell.value.execution_count === null || cell.value.execution_count === undefined);
});
watch(
    () => {
        if (!needsExecutionCountSync.value) return null;

        const sourceCellId = cell.value.metadata?.source_cell_id;
        const parentQueryCellId = cell.value.metadata?.parent_query_cell;
        
        if (sourceCellId && parentQueryCellId) {
            const queryCell = beakerSession.session.notebook.cells.find(c => c.id === parentQueryCellId);
            if (queryCell && queryCell.children) {
                const sourceCell = queryCell.children.find(child => child.id === sourceCellId);
                return sourceCell?.execution_count;
            }
        }
        return null;
    },
    (newExecutionCount) => {
        if (newExecutionCount !== null && newExecutionCount !== undefined) {
            cell.value.execution_count = newExecutionCount;
        }
    }
);

</script>

<script lang="ts">
import { BeakerCodeCell } from "@jataware/beaker-client";
export default {
    modelClass: BeakerCodeCell,
    icon: "pi pi-code",
};
</script>

<style lang="scss">
.code-cell {
    // padding-left: 16px;
}

.code-cell-grid {
    display: grid;

    grid-template-areas:
        "code code code exec"
        "output output output output";

    grid-template-columns: 1fr 1fr 1fr auto;
}

.code-data {
    grid-area: code;
    background-color: var(--p-surface-a);

    .cm-editor {
        border: 1px solid var(--p-surface-d);
    }
    .cm-focused {
        outline: none;
        border: 1px solid var(--p-primary-200);
    }
    &.dark-mode {
        .cm-focused {
            border-color: #5b3c5b;
        }
    }
}

.code-output {
    grid-area: output;
}

.code-data-chat {
    background: none;
}


.state-info {
    grid-area: exec;
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-left: 0.5rem;
}

.execution-count-badge {
    font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
    font-size: 1rem;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 2em;
    aspect-ratio: 1/1;
    border-radius: 15%;
    &.secondary {
        background-color: var(--p-surface-e);
    }
}

button.rollback-button {
    margin-top: 0.25rem;
    margin-left: 0.5rem;
    width: 32px;
    height: 32px;
    padding: 0em;
    aspect-ratio: 1/1;
}

.busy-icon {
    color: var(--p-blue-500);
    font-weight: bold;
    font-size: 1.3rem;
    margin-top: 1rem;
}

</style>
