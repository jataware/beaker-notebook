<template>
    <BaseInterface
        :title="$tmpl._('short_title', 'Beaker Notebook')"
        :title-extra="saveAsFilename"
        :header-nav="headerNav"
        ref="beakerInterfaceRef"
        :connectionSettings="props.config"
        defaultKernel="beaker_kernel"
        :sessionId="sessionIdFromProps || sessionIdFromUrl"
        :renderers="renderersFromProps || defaultRenderers"
        :savefile="saveAsFilename"
        @open-file="handleLoadNotebook"
        pageClass="next-notebook-interface"
    >
        <div class="next-notebook-container">
            <BeakerNotebook
                ref="beakerNotebookRef"
                :cell-map="cellComponentMapping"
                v-keybindings.top="notebookKeyBindings"
            >
                <BeakerNotebookToolbar
                    default-severity=""
                    :saveAvailable="true"
                    :save-as-filename="saveAsFilename"
                    :truncate-agent-code-cells="truncateAgentCodeCells"
                    @update-truncate-preference="(value) => { truncateAgentCodeCells = value; }"
                    @notebook-saved="handleNotebookSaved"
                    @open-file="handleLoadNotebook"
                >
                    <template #end-extra>
                        <Button
                            @click="isMaximized = !isMaximized; beakerInterfaceRef.setMaximized(isMaximized);"
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

                <div v-if="hasActiveQueryCells" class="follow-scroll-agent">
                    <Button
                        size="large"
                        icon="pi pi-arrow-down"
                        severity="secondary"
                        rounded
                        class="scroll-agent-button"
                        aria-label="Follow scroll as agent creates cells"
                        v-tooltip="'Select to toggle auto-scroll when the assistant is working and creating cells'"
                    />
                </div>

                <div class="agent-input-section">

                    <BeakerAgentQuery
                        ref="agentQueryRef"
                        class="agent-query-container"
                        :awaiting-input-cell="awaitingInputCell"
                        :awaiting-input-question="awaitingInputQuestion"
                    />
                </div>
            </BeakerNotebook>
        </div>

        <template #left-panel>
            <SideMenu
                ref="sideMenuRef"
                position="left"
                highlight="line"
                :expanded="true"
                initialWidth="25vi"
                :maximized="isMaximized"
            >
                <SideMenuPanel
                    id="workflow-steps"
                    label="Workflow Steps"
                    icon="pi pi-list-check"
                    v-if="attachedWorkflow"
                >
                    <WorkflowStepPanel>
                    </WorkflowStepPanel>
                </SideMenuPanel>

                <SideMenuPanel label="Context Info" icon="pi pi-home">
                    <InfoPanel/>
                </SideMenuPanel>
                <SideMenuPanel id="files" label="Files" icon="pi pi-folder" no-overflow :lazy="true">
                    <FilePanel
                        ref="filePanelRef"
                        @open-file="handleLoadNotebook"
                        @preview-file="(file, mimetype) => {
                            previewedFile = {url: file, mimetype: mimetype};
                            previewVisible = true;
                            rightSideMenuRef.selectPanel('file-contents');
                        }"
                    />
                </SideMenuPanel>
                <SideMenuPanel icon="pi pi-comments" label="Chat History">
                    <ChatHistoryPanel :chat-history="chatHistory"/>
                </SideMenuPanel>
                <SideMenuPanel
                    id="integrations" label="Integrations" icon="pi pi-database"
                    v-if="Object.keys(integrations).length > 0"
                >
                    <IntegrationPanel
                        v-model="integrations"
                    >
                    </IntegrationPanel>
                </SideMenuPanel>
                <SideMenuPanel
                    v-if="props.config.config_type !== 'server'"
                    id="config"
                    :label="`${$tmpl._('short_title', 'Beaker')} Config`"
                    icon="pi pi-cog"
                    :lazy="true"
                    position="bottom"
                >
                    <ConfigPanel
                        ref="configPanelRef"
                        @restart-session="restartSession"
                    />
                </SideMenuPanel>
            </SideMenu>
        </template>

        <template #right-panel>
            <SideMenu
                ref="rightSideMenuRef"
                position="right"
                highlight="line"
                :expanded="true"
                initialWidth="25vi"
                :maximized="isMaximized"
            >
                <SideMenuPanel
                    id="workflow-output"
                    label="Workflow Output"
                    icon="pi pi-list-check"
                    v-if="attachedWorkflow"
                >
                    <WorkflowOutputPanel>
                    </WorkflowOutputPanel>
                </SideMenuPanel>
                <SideMenuPanel label="Preview" icon="pi pi-eye" no-overflow>
                    <PreviewPanel :previewData="contextPreviewData"/>
                </SideMenuPanel>
                <SideMenuPanel
                    id="file-contents"
                    label="File Contents"
                    icon="pi pi-file beaker-zoom"
                    no-overflow
                >
                    <FileContentsPanel
                        :url="previewedFile?.url"
                        :mimetype="previewedFile?.mimetype"
                    />
                </SideMenuPanel>
                <SideMenuPanel id="media" label="Graphs and Images" icon="pi pi-chart-bar" no-overflow>
                    <MediaPanel />
                </SideMenuPanel>
                <SideMenuPanel id="kernel-state" label="Kernel State" icon="pi pi-server" no-overflow>
                    <KernelStatePanel :data="kernelStateInfo"/>
                </SideMenuPanel>
                <SideMenuPanel id="kernel-logs" label="Logs" icon="pi pi-list" position="bottom">
                    <DebugPanel :entries="debugLogs" @clear-logs="clearLogs" v-autoscroll />
                </SideMenuPanel>
            </SideMenu>
        </template>
    </BaseInterface>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeMount, provide, inject } from 'vue';
import Button from "primevue/button";
import BaseInterface from './BaseInterface.vue';
import BeakerAgentQuery from '@/components/agent/BeakerAgentQuery.vue';
import InfoPanel from '@/components/panels/InfoPanel.vue';
import FilePanel from '@/components/panels/FilePanel.vue';
import ConfigPanel from '@/components/panels/ConfigPanel.vue';
import SvgPlaceholder from '@/components/misc/SvgPlaceholder.vue';
import SideMenu from '@/components/sidemenu/SideMenu.vue';
import SideMenuPanel from '@/components/sidemenu/SideMenuPanel.vue';
import FileContentsPanel from '@/components/panels/FileContentsPanel.vue';
import { ChatHistoryPanel, type IChatHistory } from '@/components/panels/ChatHistoryPanel';
import IntegrationPanel from '@/components/integrations/IntegrationPanel.vue';
import PreviewPanel from '@/components/panels/PreviewPanel.vue';
import BeakerNotebook from '@/components/notebook/BeakerNotebook.vue';
import BeakerNotebookToolbar from '@/components/notebook/BeakerNotebookToolbar.vue';
import BeakerNotebookPanel from '@/components/notebook/BeakerNotebookPanel.vue';
import DebugPanel from '@/components/panels/DebugPanel.vue';
import MediaPanel from '@/components/panels/MediaPanel.vue';
import KernelStatePanel from '@/components/panels/KernelStatePanel.vue';

import BeakerCodeCellComponent from '@/components/cell/BeakerCodeCell.vue';
import BeakerMarkdownCellComponent from '@/components/cell/BeakerMarkdownCell.vue';
import BeakerQueryCell from '@/components/cell/BeakerQueryCell.vue';
import BeakerRawCell from '@/components/cell/BeakerRawCell.vue';
import BeakerAgentCell from '@/components/cell/BeakerAgentCell.vue';

import { useQueryCellFlattening } from '@/composables/useQueryCellFlattening';
import { useWorkflows } from '@/composables/useWorkflows';
import { listIntegrations, type IntegrationMap } from '@/util/integration';
import { atStartOfInput, atEndOfInput } from '@/util';
import { defaultRenderers } from 'beaker-vue';
import { useWorkspacesStore, useUIStore } from '@/stores';

import WorkflowStepPanel from '@/components/panels/WorkflowStepPanel.vue';
import WorkflowOutputPanel from '@/components/panels/WorkflowOutputPanel.vue';

import type { NavOption } from '@/components/misc/BeakerHeader.vue';
import type { IBeakerTheme } from '@/plugins/theme';
import type { BeakerSession as BeakerSessionClass } from 'beaker-kernel';

import { contextService } from '@/services/context';

const props = defineProps([
    "config",
    "connectionSettings",
    "sessionName",
    "sessionId",
    "defaultKernel",
    "renderers",
]);

// --- Injections ---
const { theme, toggleDarkMode } = inject<IBeakerTheme>('theme');
const beakerApp = inject<any>("beakerAppConfig");

beakerApp.setPage("notebook");

// --- Identity / URL ---
const urlParams = new URLSearchParams(window.location.search);
const sessionIdFromUrl = urlParams.has("session") ? urlParams.get("session") : "nextgen_notebook_dev_session";
const sessionIdFromProps = computed(() => props.sessionId);
const renderersFromProps = computed(() => props.renderers);

const workspaceName = props.sessionName ?? props.sessionId ?? sessionIdFromUrl;

// --- Stores ---
const workspacesStore = useWorkspacesStore();
const uiStore = useUIStore();
const workspace = workspacesStore.getOrCreate(workspaceName);

// --- Template refs (page-local) ---
const beakerInterfaceRef = ref();
const beakerNotebookRef = ref();
const filePanelRef = ref();
const configPanelRef = ref();
const sideMenuRef = ref();
const rightSideMenuRef = ref();
const agentQueryRef = ref();

// --- Page-local UI state ---
const isMaximized = ref(false);
const truncateAgentCodeCells = ref<boolean>(false);
const integrations = ref<IntegrationMap>({});

// --- Computed access into store/session for template auto-unwrap ---
const beakerSession = computed(() => beakerInterfaceRef.value?.beakerSession);
const saveAsFilename = computed(() => workspace.saveAsFilename.value);
const chatHistory = computed(() => workspace.chatHistory.value as IChatHistory | null);
const contextPreviewData = computed<any>(() => workspace.contextPreviewData.value);
const kernelStateInfo = computed<any>(() => workspace.kernelStateInfo.value);
const debugLogs = computed(() => uiStore.debugLogs);

// --- Attach the underlying BeakerSession class instance to the workspace ---
// The workspace store wires the iopub handler on attach; until then, mirror state
// stays empty.
watch(
    () => beakerInterfaceRef.value?.beakerSession?.session as BeakerSessionClass | undefined,
    (session) => {
        if (session) {
            workspacesStore.attachSession(workspaceName, session);
        }
    },
    { immediate: true }
);

// Route the workspace's pendingPanelHint to actual panel switching side-effects.
// The store sets the hint when an iopub message wants the workflow panels open;
// routing the side-effect via template refs lives here so the store stays
// template-ref-free.
watch(
    () => workspace.pendingPanelHint.value,
    (hint) => {
        if (hint === 'workflow') {
            sideMenuRef.value?.selectPanel('workflow-steps');
            rightSideMenuRef.value?.selectPanel('workflow-output');
        }
        if (hint !== null) {
            workspace.pendingPanelHint.value = null;
        }
    }
);

// "At least one cell" invariant.
watch(
    () => beakerNotebookRef.value?.notebook.cells,
    (cells) => {
        if (cells?.length === 0) {
            beakerNotebookRef.value.insertCellBefore();
        }
    },
    { deep: true }
);

// --- Derived state from notebook cells ---
const awaitingInputCell = computed(() => {
    const cells = beakerSession.value?.session?.notebook?.cells ?? [];
    return cells.find(cell =>
        cell.cell_type === 'query' && cell.status === 'awaiting_input'
    ) || null;
});

const awaitingInputQuestion = computed(() => {
    if (!awaitingInputCell.value) return null;
    const events = awaitingInputCell.value.events || [];
    const lastQuestionEvent = [...events].reverse().find(event => event.type === 'user_question');
    return lastQuestionEvent?.content || 'The agent is waiting for your response.';
});

const hasActiveQueryCells = computed(() => false);

// --- Truncate preference ---
onBeforeMount(() => {
    const saved = localStorage.getItem('beaker-truncate-agent-code-cells');
    if (saved !== null) {
        truncateAgentCodeCells.value = JSON.parse(saved);
    }
});

const updateTruncatePreference = () => {
    localStorage.setItem('beaker-truncate-agent-code-cells', JSON.stringify(truncateAgentCodeCells.value));
    if (beakerSession.value?.session?.notebook?.cells) {
        beakerSession.value.session.notebook.cells.forEach(cell => {
            if (cell.cell_type === 'query' && cell.metadata) {
                cell.metadata.auto_collapse_code_cells = truncateAgentCodeCells.value;
            }
        });
    }
};

watch(truncateAgentCodeCells, () => {
    updateTruncatePreference();
});

provide('truncateAgentCodeCells', truncateAgentCodeCells);

// ensures that attached workflow is kept current with the fact that beakerSession.value.activeContext might not be connected yet
const attachedWorkflow = computed(() => useWorkflows(beakerSession.value).attachedWorkflow.value);

// --- Cell component dispatch ---
const cellComponentMapping = (cell: any) => {
    const standardMap = {
        'code': BeakerCodeCellComponent,
        'markdown': BeakerMarkdownCellComponent,
        'raw': BeakerRawCell,
    };

    if (!cell) {
        return standardMap;
    }

    if (cell.cell_type === 'query') {
        return BeakerQueryCell;
    }

    if (cell.cell_type === 'markdown' && cell.metadata?.beaker_cell_type) {
        const agentCellType = cell.metadata.beaker_cell_type;
        if (['thought', 'response', 'user_question', 'error', 'abort'].includes(agentCellType)) {
            return BeakerAgentCell;
        }
    }

    return standardMap[cell.cell_type] || standardMap['code'];
};

// --- Header nav ---
const headerNav = computed<NavOption[]>(() => [
    {
        type: 'link',
        href: '/chat' + window.location.search,
        icon: 'comment',
        label: 'Navigate to chat view',
    },
    {
        type: 'button',
        icon: (theme.mode === 'dark' ? 'sun' : 'moon'),
        command: toggleDarkMode,
        label: `Switch to ${theme.mode === 'dark' ? 'light' : 'dark'} mode.`,
    },
    {
        type: 'link',
        href: `https://jataware.github.io/beaker-kernel`,
        label: 'Beaker Documentation',
        icon: "book",
        rel: "noopener",
        target: "_blank",
    },
    {
        type: 'link',
        href: `https://github.com/jataware/beaker-kernel`,
        label: 'Check us out on Github',
        icon: "github",
        rel: "noopener",
        target: "_blank",
    },
]);

// --- Keybindings ---
const keyBindingState: Record<string, any> = {};

const prevCellKey = () => {
    beakerNotebookRef.value?.selectPrevCell();
};

const nextCellKey = () => {
    const cells = beakerNotebookRef.value?.notebook.cells;
    if (!cells) return;
    const lastCell = cells[cells.length - 1];
    if (beakerNotebookRef.value.selectedCell().cell.id === lastCell.id) {
        agentQueryRef.value?.$el.querySelector('textarea')?.focus();
    } else {
        beakerNotebookRef.value.selectNextCell();
    }
};

const notebookKeyBindings = {
    "keydown.enter.ctrl.prevent.capture.in-cell": () => {
        beakerNotebookRef.value?.selectedCell().execute();
        beakerNotebookRef.value?.selectedCell().exit();
    },
    "keydown.enter.shift.prevent.capture.in-cell": () => {
        const targetCell = beakerNotebookRef.value?.selectedCell();
        targetCell.execute();
        if (!beakerNotebookRef.value?.selectNextCell()) {
            beakerNotebookRef.value?.insertCellAfter(targetCell, undefined, true);
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
    "keydown.up.in-editor.capture": (event: KeyboardEvent) => {
        const eventTarget = event.target as HTMLElement;
        const parentCellElement = eventTarget.closest('.beaker-cell');
        const targetCellId = parentCellElement?.getAttribute('cell-id');

        if (targetCellId !== undefined && targetCellId !== null) {
            const curCell = beakerSession.value.findNotebookCellById(targetCellId);
            if (atStartOfInput(curCell.editor)) {
                const prevCell = beakerNotebookRef.value.prevCell();
                if (prevCell) {
                    curCell.exit();
                    beakerNotebookRef.value.selectCell(prevCell.cell.id, true, "end");
                    event.preventDefault();
                    event.stopImmediatePropagation();
                }
            }
        } else if (eventTarget.closest('.agent-query-container')) {
            eventTarget.blur();
            beakerNotebookRef.value.selectCell(
                beakerNotebookRef.value.notebook.cells[beakerNotebookRef.value.notebook.cells.length - 1].id,
                true,
                "end",
            );
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    },
    "keydown.down.in-editor.capture": (event: KeyboardEvent) => {
        const eventTarget = event.target as HTMLElement;
        const parentCellElement = eventTarget.closest('.beaker-cell');
        const targetCellId = parentCellElement?.getAttribute('cell-id');

        if (targetCellId !== undefined && targetCellId !== null) {
            const curCell = beakerSession.value.findNotebookCellById(targetCellId);
            if (atEndOfInput(curCell.editor)) {
                const nextCell = beakerNotebookRef.value.nextCell();
                if (nextCell) {
                    curCell.exit();
                    beakerNotebookRef.value.selectCell(nextCell.cell.id, true, "start");
                    event.preventDefault();
                    event.stopImmediatePropagation();
                } else {
                    const lastCell = beakerNotebookRef.value.notebook.cells[beakerNotebookRef.value.notebook.cells.length - 1];
                    if (beakerNotebookRef.value.selectedCell().cell.id === lastCell.id) {
                        curCell.exit();
                        agentQueryRef.value?.$el.querySelector('textarea')?.focus();
                        event.preventDefault();
                        event.stopImmediatePropagation();
                    }
                }
            }
        }
    },
    "keydown.k.!in-editor": prevCellKey,
    "keydown.down.!in-editor.prevent": nextCellKey,
    "keydown.j.!in-editor": nextCellKey,
    "keydown.a.prevent.!in-editor": () => {
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
            keyBindingState['d'] = { cell_id: cell.id, timeout: timeoutId };
        } else {
            const { cell_id, timeout } = keyBindingState['d'];
            if (cell_id === cell.id) {
                notebook?.removeCell(cell);
                uiStore.copiedCell = cell.cell;
                delete keyBindingState['d'];
            }
            if (timeout) {
                window.clearTimeout(timeout);
            }
        }
    },
};

// --- Notebook operations ---
const loadNotebook = (notebookJSON: any, filename: string) => {
    console.log("Loading notebook", filename);
    const notebook = beakerNotebookRef.value;
    beakerSession.value?.session.loadNotebook(notebookJSON);
    if (notebookJSON?.metadata?.chat_history) {
        beakerSession.value?.session.executeAction(
            "set_agent_history",
            notebookJSON?.metadata?.chat_history,
        );
    }
    workspace.saveAsFilename.value = filename;

    const cellIds = notebook.notebook.cells.map((cell: any) => cell.id);
    if (!cellIds.includes(notebook.selectedCellId)) {
        nextTick(() => {
            notebook.selectCell(cellIds[0]);
        });
    }
};

const handleNotebookSaved = async (path: string) => {
    workspace.saveAsFilename.value = path;
    if (path) {
        sideMenuRef.value?.selectPanel("Files");
        await filePanelRef.value.refresh();
        await filePanelRef.value.flashFile(path);
    }
};

const restartSession = async () => {
    const resetFuture = beakerSession.value.session.sendBeakerMessage("reset_request", {});
    await resetFuture;
};

const clearLogs = () => uiStore.clearDebugLogs();

// --- Query cell flattening ---
const { setupQueryCellFlattening, resetProcessedEvents } = useQueryCellFlattening(
    () => beakerSession.value,
    truncateAgentCodeCells,
);

setupQueryCellFlattening(() => beakerSession.value?.session?.notebook?.cells);

const handleLoadNotebook = (notebookJSON: any, filename: string) => {
    console.log("Loading notebook:", filename);
    resetProcessedEvents();
    loadNotebook(notebookJSON, filename);
};

// --- Integrations (HTTP-driven, separate from workspace.integrations) ---
type FilePreview = {
    url: string,
    mimetype?: string
};
const previewedFile = ref<FilePreview>();
const previewVisible = ref<boolean>(false);

watch(
    [() => beakerSession?.value?.activeContext, () => beakerSession?.value?.session.kernelInfo],
    async () => { integrations.value = await listIntegrations(sessionIdFromUrl); },
);

</script>

<style lang="scss">

.next-notebook-container {
    display: flex;
    height: 100%;
    max-width: 100%;
    position: relative;
}

.next-notebook-interface {
    .truncate-toggle-container {
        display: flex;
    }

    .cell-container {

        .beaker-cell {
            padding-top: 0;
        }

        .cell-contents {
            margin-left: 0.5rem;
            margin-top: 0.5rem;
            margin-bottom: 0.65rem;

            .state-info {
                margin-left: 0;
            }

            .markdown-cell {
                padding-right: 0;

                &>div {

                    p {
                        word-break: break-word;
                        margin-block-start: 0.5rem;
                        margin-block-end: 0.25rem;
                    }

                    p:first-child {
                        margin-block-start: 0;
                        margin-block-end: 0;
                    }

                    p:last-child {
                        margin-block-start: 0.5rem;
                        margin-block-end: 0.25rem;
                    }
                }
            }
        }
    }

    .beaker-notebook {
        flex: 2 0 calc(50vw - 2px);
        border: 2px solid var(--p-surface-border);
        border-radius: 0;
        border-top: 0;
        max-width: 100%;
    }

    .agent-input-section {
        background-color: var(--p-surface-b);
    }

    .spacer {
        &.left {
            flex: 1 1000 25vw;
        }

        &.right {
            flex: 1 1 25vw;
        }
    }

    .notebook-toolbar {
        border-style: inset;
        border-radius: 0;
        border-top: unset;
        border-left: unset;
        border-right: unset;
    }

    .title-extra {
        vertical-align: baseline;
        display: inline-block;
        height: 100%;
        font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
    }

    .agent-thinking-indicator-container {
        background-color: var(--p-surface-b);
        border-bottom: 1px solid var(--p-surface-border);
    }

    .execution-badge,
    .execution-count-badge {
        // font-size: 0.8rem;
        height: 1.75rem;
    }
}

.follow-scroll-agent {
    position: absolute;
    bottom: 7rem;
    right: 1rem;
    // z-index: 100;

    // padding-left: 1rem;
    // background-color: var(--p-surface-b);
    // border-radius: 17.5%;
    // padding: 0.75rem;
    // border: 1px solid var(--p-purple-300);

    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.scroll-agent-button {
    background-color: var(--p-surface-c);
    // border-radius: 17.5%;
    // padding: 0.75rem;
    // border: 1px solid var(--p-purple-300);
    border-color: var(--p-purple-300);
    border-width: 2px;
    height: 3rem;
    width: 3rem;

    & > span {
        font-weight: bold;
        font-size: 1.25rem;
    }
}
</style>
