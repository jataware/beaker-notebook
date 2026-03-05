<template>
    <BaseInterface
        title="Beaker Dev Interface"
        :title-extra="saveAsFilename"
        :connectionSettings="props.config"
        ref="beakerInterfaceRef"
        :sessionId="sessionId"
        defaultKernel="beaker_kernel"
        :renderers="renderers"
        @iopub-msg="iopubMessage"
        @unhandled-msg="unhandledMessage"
        @any-msg="anyMessage"
        @session-status-changed="statusChanged"
        @open-file="loadNotebook"
    >
        <div class="notebook-container">
            <BeakerNotebook
                ref="beakerNotebookRef"
                :cell-map="cellComponentMapping"
                v-keybindings.top="notebookKeyBindings"
            >
                <BeakerNotebookToolbar
                    default-severity=""
                    :saveAvailable="true"
                    :save-as-filename="saveAsFilename"
                    @notebook-saved="handleNotebookSaved"
                    @open-file="loadNotebook"
                >
                <template #end-extra>
                    <Button
                        @click="isMaximized = !isMaximized;"
                        :icon="`pi ${isMaximized ? 'pi-window-minimize' : 'pi-window-maximize'}`"
                        size="small"
                        text
                    />
                </template>
                </BeakerNotebookToolbar>
                <BeakerNotebookPanel
                    :selected-cell="beakerNotebookRef?.selectedCellId"
                    v-autoscroll
                >
                    <template #notebook-background>
                        <div class="welcome-placeholder">
                            <SvgPlaceholder />
                        </div>
                    </template>
                </BeakerNotebookPanel>
                <BeakerAgentQuery
                    class="agent-query-container"
                />
            </BeakerNotebook>
        </div>

        <template #left-panel>
            <SideMenu
                position="left"
                :show-label="true"
                highlight="line"
                :expanded="false"
                initialWidth="20vi"
                :maximized="isMaximized"
            >
                <SideMenuPanel label="Info" icon="pi pi-home">
                    <ContextPanel :context="activeContext?.info" @action-selected="selectAction"/>
                </SideMenuPanel>
                <SideMenuPanel id="files" label="Files" icon="pi pi-file-export" no-overflow>
                    <FilePanel
                        ref="filePanelRef"
                        @open-file="loadNotebook"
                    />
                </SideMenuPanel>
            </SideMenu>
        </template>

        <template #right-panel>
            <SideMenu
                position="right"
                ref="rightMenu"
                highlight="line"
                :show-label="true"
                :expanded="false"
                initialWidth="20vi"
                :maximized="isMaximized"
            >
                <SideMenuPanel tabId="preview" label="Preview" icon="pi pi-eye">
                    <PreviewPanel :previewData="previewData"/>
                </SideMenuPanel>

                <SideMenuPanel tabId="action" label="Actions" icon="pi pi-send">
                    <Card class="debug-card">
                        <template #title>Execute an Action</template>
                        <template #content>
                            <BeakerExecuteAction
                                ref="executeActionRef"
                                :rawMessages="rawMessages"
                            />
                        </template>
                    </Card>
                </SideMenuPanel>

                <SideMenuPanel tabId="logging" label="Logging" icon="pi pi-list" >
                    <DebugPanel :entries="debugLogs" @clear-logs="debugLogs.splice(0, debugLogs.length)" v-autoscroll />
                </SideMenuPanel>

                <SideMenuPanel label="Messages" icon="pi pi-comments">
                    <MessagesPanel :entries="rawMessages" @clear-logs="rawMessages.splice(0, rawMessages.length)" v-autoscroll />
                </SideMenuPanel>
            </SideMenu>
        </template>
    </BaseInterface>
</template>

<script setup lang="ts">
import { ref, watch, computed, inject, toRaw, nextTick } from 'vue';
import { JupyterMimeRenderer, type IBeakerCell, type IMimeRenderer } from 'beaker-kernel';
import BeakerNotebook from '../components/notebook/BeakerNotebook.vue';
import BaseInterface from './BaseInterface.vue';
import BeakerNotebookToolbar from '../components/notebook/BeakerNotebookToolbar.vue';
import BeakerNotebookPanel from '../components/notebook/BeakerNotebookPanel.vue';
import { JSONRenderer, LatexRenderer, wrapJupyterRenderer, type BeakerRenderOutput } from '../renderers';
import { standardRendererFactories } from '@jupyterlab/rendermime';
import * as messages from '@jupyterlab/services/lib/kernel/messages';

import Button from "primevue/button";
import Card from 'primevue/card';
import BeakerAgentQuery from '../components/agent/BeakerAgentQuery.vue';
import BeakerExecuteAction from "../components/dev-interface/BeakerExecuteAction.vue";
import ContextPanel from '../components/panels/ContextPanel.vue';
import FilePanel from '../components/panels/FilePanel.vue';
import PreviewPanel from '../components/panels/PreviewPanel.vue';
import SvgPlaceholder from '../components/misc/SvgPlaceholder.vue';
import SideMenu from "../components/sidemenu/SideMenu.vue";
import SideMenuPanel from "../components/sidemenu/SideMenuPanel.vue";

import BeakerCodeCell from '../components/cell/BeakerCodeCell.vue';
import BeakerMarkdownCell from '../components/cell/BeakerMarkdownCell.vue';
import BeakerQueryCell from '../components/cell/BeakerQueryCell.vue';
import BeakerRawCell from '../components/cell/BeakerRawCell.vue';
import type { IBeakerTheme } from '../plugins/theme';
import MessagesPanel from '../components/panels/MessagesPanel.vue';
import DebugPanel from '../components/panels/DebugPanel.vue';


const beakerApp = inject<any>("beakerAppConfig");
beakerApp.setPage("dev");

const activeContext = ref();
const beakerNotebookRef = ref();
const beakerInterfaceRef = ref();
const filePanelRef = ref();
const sideMenuRef = ref();


const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.has("session") ? urlParams.get("session") : "dev_session";

const props = defineProps([
    "config",
    "connectionSettings",
    "sessionName",
    "sessionId",
    "defaultKernel",
    "renderers",
]);

const renderers: IMimeRenderer<BeakerRenderOutput>[] = [
    ...standardRendererFactories.map((factory: any) => new JupyterMimeRenderer(factory)).map(wrapJupyterRenderer),
    JSONRenderer,
    LatexRenderer,
];

const cellComponentMapping = {
    'code': BeakerCodeCell,
    'markdown': BeakerMarkdownCell,
    'query': BeakerQueryCell,
    'raw': BeakerRawCell,
}

const connectionStatus = ref('connecting');
const debugLogs = ref<object[]>([]);
const rawMessages = ref<object[]>([])
const previewData = ref<any>();
const saveInterval = ref();
const copiedCell = ref<IBeakerCell | null>(null);
const notebookRef = ref<typeof BeakerNotebook>();
const saveAsFilename = ref<string>(null);

const isMaximized = ref(false);
const contextSelectionOpen = ref(false);
const activeContextPayload = ref<any>(null);
const rightMenu = ref<typeof SideMenuPanel>();
const executeActionRef = ref<typeof BeakerExecuteAction>();
const { theme, toggleDarkMode } = inject<IBeakerTheme>('theme');

const beakerSession = computed(() => {
    return beakerInterfaceRef?.value?.beakerSession;
});

const iopubMessage = (msg) => {
    if (msg.header.msg_type === "preview") {
        previewData.value = msg.content;
    }
    if (msg.header.msg_type === "debug_event") {
        debugLogs.value.push({
            type: msg.content.event,
            body: msg.content.body,
            timestamp: msg.header.date,
        });
    }
};

// Ensure we always have at least one cell
watch(
    () => beakerNotebookRef?.value?.notebook.cells,
    (cells) => {
        if (cells?.length === 0) {
            beakerNotebookRef.value.insertCellBefore();
        }
    },
    {deep: true},
)

const anyMessage = (msg: messages.IMessage, direction) => {
    // Ignore auto-completion messages as they add a lot of noise.
    if (/^complete_/.test(msg.header.msg_type)) {
        return
    }
    rawMessages.value.push({
        type: direction,
        body: msg,
        timestamp: msg.header.date,
    });
};

const unhandledMessage = (msg) => {
    console.log("Unhandled message recieved", msg);
}

const statusChanged = (newStatus) => {
    connectionStatus.value = newStatus == 'idle' ? 'connected' : newStatus;
};

const toggleContextSelection = () => {
    contextSelectionOpen.value = !contextSelectionOpen.value;
};

const selectAction = (actionName: string) => {
    rightMenu.value?.selectPanel("action");
    executeActionRef.value?.selectAction(actionName);
};

const loadNotebook = (notebookJSON: any, filename: string) => {
    const notebook = beakerNotebookRef.value;
    beakerSession.value?.session.loadNotebook(notebookJSON);
    saveAsFilename.value = filename;
    const cellIds = notebook.notebook.cells.map((cell) => cell.id);
    if (!cellIds.includes(notebook.selectedCellId)) {
        nextTick(() => {
            // Force the notebook to select one of cells in the current notebook.
            notebook.selectCell(cellIds[0]);
        });
    }
}

const handleNotebookSaved = async (path: string) => {
    saveAsFilename.value = path;
    if (path) {
        sideMenuRef.value?.selectPanel("Files");
        await filePanelRef.value.refresh();
        await filePanelRef.value.flashFile(path);
    }
}
;

// onBeforeMount(() => {
//     var notebookData: {[key: string]: any};
//     try {
//         notebookData = JSON.parse(localStorage.getItem("notebookData")) || {};
//     }
//     catch (e) {
//         console.error(e);
//         notebookData = {};
//     }

//     if (notebookData[sessionId]?.data) {
//         nextTick(() => {
//             if (beakerNotebookRef.value?.notebook) {
//                 beakerNotebookRef.value?.notebook.loadFromIPynb(notebookData[sessionId].data);
//                 nextTick(() => {
//                     beakerNotebookRef.value?.selectCell(notebookData[sessionId].selectedCell);
//                 });
//             }
//         });
//     }
// });

const prevCellKey = () => {
    beakerNotebookRef.value?.selectPrevCell();
};

const nextCellKey = () => {
    beakerNotebookRef.value?.selectNextCell();
};

const keyBindingState = {};
const notebookKeyBindings = {
    "keydown.enter.ctrl.prevent.capture.in-cell": () => {
        beakerNotebookRef.value?.selectedCell().execute();
        beakerNotebookRef.value?.selectedCell().exit();
    },
    "keydown.enter.shift.prevent.capture.in-cell": () => {
        const targetCell = beakerNotebookRef.value?.selectedCell();
        targetCell.execute();
        if (!beakerNotebookRef.value?.selectNextCell()) {
            // Create a new cell after the current cell if one doesn't exist.
            beakerNotebookRef.value?.insertCellAfter(
                targetCell,
                undefined,
                true,
            );
            // Focus the editor only if we are creating a new cell.
            nextTick(() => {
                beakerNotebookRef.value?.selectedCell().enter();
            });
        }
    },
    "keydown.enter.exact.prevent.stop.!in-editor": () => {
        beakerNotebookRef.value?.selectedCell().enter();
    },
    "keydown.esc.exact.prevent": () => {
        beakerNotebookRef.value?.selectedCell().exit();
    },
    "keydown.up.!in-editor.prevent": prevCellKey,
    "keydown.k.!in-editor": prevCellKey,
    "keydown.down.!in-editor.prevent": nextCellKey,
    "keydown.j.!in-editor": nextCellKey,
    "keydown.a.prevent.!in-editor": (evt) => {
        const notebook = beakerNotebookRef.value;
        notebook?.selectedCell().exit();
        notebook?.insertCellBefore();
    },
    "keydown.b.prevent.!in-editor": () => {
        const notebook = beakerNotebookRef.value;
        notebook?.selectedCell().exit();
        notebook?.insertCellAfter();
    },
    "keydown.d.!in-editor": () => {
        const notebook = beakerNotebookRef.value;
        const cell = notebook.selectedCell();
        const deleteCallback = () => {
            delete keyBindingState['d'];
        };
        const state = keyBindingState['d'];

        if (state === undefined) {
            const timeoutId = setTimeout(deleteCallback, 1000);
            keyBindingState['d'] = {
                cell_id: cell.id,
                timeout: timeoutId,
            }
        }
        else {
            const {cell_id, timeout} = keyBindingState['d'];
            if (cell_id === cell.id) {
                notebook?.removeCell(cell);
                copiedCell.value = cell.cell;
                delete keyBindingState['d'];
            }
            if (timeout) {
                window.clearTimeout(timeout);
            }
        }
    },
    "keydown.y.!in-editor": () => {
        const notebook = beakerNotebookRef.value;
        const cell = notebook.selectedCell();
        const copyCallback = () => {
            delete keyBindingState['y'];
        };
        const state = keyBindingState['y'];

        if (state === undefined) {
            const timeoutId = setTimeout(copyCallback, 1000);
            keyBindingState['y'] = {
                cell_id: cell.id,
                timeout: timeoutId,
            }
        }
        else {
            const {cell_id, timeout} = keyBindingState['y'];
            if (cell_id === cell.id) {
                copiedCell.value = cell.cell;
                delete keyBindingState['y'];
            }
            if (timeout) {
                window.clearTimeout(timeout);
            }
        }
    },
    "keydown.p.!in-editor": (evt: KeyboardEvent) => {
        const notebook = beakerNotebookRef.value;
        let copiedCellValue = toRaw(copiedCell.value);
        if (copiedCellValue !== null) {
            var newCell: IBeakerCell;


            // If a cell with the to-be-pasted cell's id already exists in the notebook, set the copied cell's id to
            // undefined so that it is regenerated when added.
            const notebookIds = notebook.notebook.cells.map((cell) => cell.id);
            if (notebookIds.includes(copiedCellValue.id)) {
                const cls = copiedCellValue.constructor as (data: IBeakerCell) => void;
                const data = {
                    ...copiedCellValue,
                    // Set non-transferable attributes to undefined.
                    id: undefined,
                    executionCount: undefined,
                    busy: undefined,
                    last_execution: undefined,
                } as IBeakerCell;
                copiedCellValue = new cls(data);
            }

            // Lowercase `p` pastes after, uppercase `P` pastes before. Checking the actual is key better than checking
            // for shift, etc as it includes caps lock, etc.
            if (evt.key === 'p') {
                 newCell = notebook?.insertCellAfter(notebook.selectedCell(), copiedCellValue);
            }
            else if (evt.key === 'P') {
                 newCell = notebook?.insertCellBefore(notebook.selectedCell(), copiedCellValue);
            }
            copiedCellValue.value = null;
        }
    },
}

</script>

<style lang="scss">

.notebook-container {
    display:flex;
    height: 100%;
    max-width: 100%;
}

.beaker-notebook {
    flex: 2 0 calc(50vw - 2px);
    border: 2px solid var(--p-surface-border);
    border-radius: 0;
    border-top: 0;
    max-width: 100%;
}


.notebook-toolbar {
    border-style: inset;
    border-radius: 0;
    border-top: unset;
    border-left: unset;
    border-right: unset;
}

// #app {
//     margin: 0;
//     padding: 0;
//     overflow: hidden;
//     background-color: var(--p-surface-b);
// }

// header {
//     grid-area: header;
//     display: flex;
//     justify-content: space-between;
//     align-items: center;
// }

// main {
//     grid-area: main;
//     padding-top: 2px;
//     padding-bottom: 2px;
// }

// footer {
//     grid-area: footer;
// }

// .main-panel {
//     display: flex;
//     flex-direction: column;
//     &:focus {
//         outline: none;
//     }
// }


// .central-panel {
//     flex: 1000;
//     display: flex;
//     flex-direction: column;
// }

// .beaker-dev-interface {
//     padding-bottom: 2px;
//     height: 100vh;
//     width: 100vw;
//     display: grid;
//     grid-gap: 1px;

//     grid-template-areas:
//         "header header header header"
//         "main main main main"
//         "footer footer footer footer";

//     grid-template-columns: 1fr 1fr 1fr 1fr;
//     grid-template-rows: auto 1fr auto;
// }

// .beaker-dev-interface .p-toolbar {
//     border: none;
// }

</style>
