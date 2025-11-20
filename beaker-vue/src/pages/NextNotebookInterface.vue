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
        @iopub-msg="iopubMessageHandler"
        @unhandled-msg="unhandledMessageHandler"
        @any-msg="anyMessageHandler"
        @session-status-changed="statusChangedHandler"
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
                    <DebugPanel :entries="debugLogs" @clear-logs="debugLogs.splice(0, debugLogs.length)" v-autoscroll />
                </SideMenuPanel>
            </SideMenu>
        </template>
    </BaseInterface>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeMount, provide } from 'vue';
import Button from "primevue/button";
import BaseInterface from './BaseInterface.vue';
import BeakerAgentQuery from '../components/agent/BeakerAgentQuery.vue';
import InfoPanel from '../components/panels/InfoPanel.vue';
import FilePanel from '../components/panels/FilePanel.vue';
import ConfigPanel from '../components/panels/ConfigPanel.vue';
import SvgPlaceholder from '../components/misc/SvgPlaceholder.vue';
import SideMenu from "../components/sidemenu/SideMenu.vue";
import SideMenuPanel from "../components/sidemenu/SideMenuPanel.vue";
import FileContentsPanel from '../components/panels/FileContentsPanel.vue';
import { ChatHistoryPanel, type IChatHistory } from '../components/panels/ChatHistoryPanel';
import IntegrationPanel from '../components/panels/IntegrationPanel.vue';
import PreviewPanel from '../components/panels/PreviewPanel.vue';
import BeakerNotebook from '../components/notebook/BeakerNotebook.vue';
import BeakerNotebookToolbar from '../components/notebook/BeakerNotebookToolbar.vue';
import BeakerNotebookPanel from '../components/notebook/BeakerNotebookPanel.vue';
import DebugPanel from '../components/panels/DebugPanel.vue';
import MediaPanel from '../components/panels/MediaPanel.vue';
import KernelStatePanel from '../components/panels/KernelStatePanel.vue';

import BeakerCodeCellComponent from '../components/cell/BeakerCodeCell.vue';
import BeakerMarkdownCellComponent from '../components/cell/BeakerMarkdownCell.vue';
import NextGenBeakerQueryCell from '../components/cell/NextBeakerQueryCell.vue';
import BeakerRawCell from '../components/cell/BeakerRawCell.vue';
import BeakerAgentCell from '../components/cell/BeakerAgentCell.vue';

import { useNotebookInterface } from '../composables/useNotebookInterface';
import { useQueryCellFlattening } from '../composables/useQueryCellFlattening';
import { listIntegrations, type IntegrationMap } from '../util/integration';

import WorkflowStepPanel from '@/components/panels/WorkflowStepPanel.vue';
import WorkflowOutputPanel from '@/components/panels/WorkflowOutputPanel.vue';
import { useWorkflows } from '@/composables/useWorkflows';

const props = defineProps([
    "config",
    "connectionSettings",
    "sessionName",
    "sessionId",
    "defaultKernel",
    "renderers",
]);

const {
    beakerNotebookRef,
    beakerInterfaceRef,
    filePanelRef,
    configPanelRef,
    sideMenuRef,
    rightSideMenuRef,
    agentQueryRef,
    saveAsFilename,
    isMaximized,
    debugLogs,
    contextPreviewData,
    kernelStateInfo,
    beakerSession,
    defaultRenderers,
    awaitingInputCell,
    awaitingInputQuestion,
    createHeaderNav,
    createNotebookKeyBindings,
    createIopubMessageHandler,
    anyMessageHandler,
    unhandledMessageHandler,
    statusChangedHandler,
    loadNotebook,
    handleNotebookSaved,
    beakerApp,
    restartSession,
    chatHistory,
} = useNotebookInterface();

beakerApp.setPage("notebook");

const urlParams = new URLSearchParams(window.location.search);
const sessionIdFromUrl = urlParams.has("session") ? urlParams.get("session") : "nextgen_notebook_dev_session";
const sessionIdFromProps = computed(() => props.sessionId);
const renderersFromProps = computed(() => props.renderers);

const truncateAgentCodeCells = ref<boolean>(false);

// ensures that attached workflow is kept current with the fact that beakerSession.value.activeContext might not be connected yet
const attachedWorkflow = computed(() => useWorkflows(beakerSession.value).attachedWorkflow.value)

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
        return NextGenBeakerQueryCell;
    }

    if (cell.cell_type === 'markdown' && cell.metadata?.beaker_cell_type) {
        const agentCellType = cell.metadata.beaker_cell_type;
        if (['thought', 'response', 'user_question', 'error', 'abort'].includes(agentCellType)) {
            return BeakerAgentCell;
        }
    }

    return standardMap[cell.cell_type] || standardMap['code'];
};

const headerNav = computed(() => createHeaderNav('notebook'));

const notebookKeyBindings = createNotebookKeyBindings();

const iopubMessageHandler = createIopubMessageHandler();

const hasActiveQueryCells = computed(() => {
    return false;
    if (!beakerSession.value?.session?.notebook?.cells) return false;

    return beakerSession.value.session.notebook.cells.some(cell => {
        if (cell.cell_type !== 'query') return false;
        const queryStatus = cell.metadata?.query_status;
        return queryStatus === 'in-progress' || queryStatus === 'pending';
    });
});

const { setupQueryCellFlattening, resetProcessedEvents } = useQueryCellFlattening(
    () => beakerSession.value,
    truncateAgentCodeCells
);

setupQueryCellFlattening(() => beakerSession.value?.session?.notebook?.cells);

const handleLoadNotebook = (notebookJSON: any, filename: string) => {
    console.log("Loading notebook:", notebookJSON, filename);
    resetProcessedEvents();
    loadNotebook(notebookJSON, filename);
};

const integrations = ref<IntegrationMap>({});
const previewVisible = ref<boolean>(false);

type FilePreview = {
    url: string,
    mimetype?: string
}
const previewedFile = ref<FilePreview>();

watch(beakerSession, async () => {
    integrations.value = await listIntegrations(sessionIdFromUrl);
});

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
