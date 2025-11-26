<template>
    <BaseInterface
        :title="$tmpl._('short_title', 'Beaker Notebook')"
        :title-extra="saveAsFilename"
        :header-nav="headerNav"
        ref="beakerInterfaceRef"
        :connectionSettings="props.config"
        defaultKernel="beaker_kernel"
        :sessionId="sessionId"
        :renderers="renderers"
        :savefile="saveAsFilename"
        @iopub-msg="iopubMessage"
        @unhandled-msg="unhandledMessage"
        @any-msg="anyMessage"
        @session-status-changed="statusChanged"
    >
        <div class="integration-container">
            <div class="beaker-notebook">
                <IntegrationEditor
                    v-model="integrations"
                    :deleteResource="deleteResourceOnSelectedIntegration"
                    :modifyResource="modifyResourceForSelectedIntegration"
                    :modifyIntegration="modifySelectedIntegration"
                    :fetchResources="fetchResourcesForSelectedIntegration"
                />
            </div>
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
                <SideMenuPanel id="files" label="Files" icon="pi pi-folder" no-overflow :lazy="true">
                    <FilePanel
                        ref="filePanelRef"
                        @preview-file="(file, mimetype) => {
                            previewedFile = {url: file, mimetype: mimetype};
                            previewVisible = true;
                            rightSideMenuRef.selectPanel('file-contents');
                        }"
                    />
                </SideMenuPanel>
                <SideMenuPanel
                    id="integrations" label="Integrations" icon="pi pi-database"
                >
                    <IntegrationPanel
                        v-model="integrations.integrations"
                    ></IntegrationPanel>
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
                initialWidth="36vi"
                :maximized="isMaximized"
            >
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
                <SideMenuPanel
                    id="examples"
                    label="Example Editor"
                    icon="pi pi-list-check"
                    no-overflow
                >
                <ExamplesPanel
                    v-model="integrations"
                    :disabled="!integrations.selected || integrations.selected === 'new'"
                    :deleteResource="deleteResourceOnSelectedIntegration"
                    :modifyResource="modifyResourceForSelectedIntegration"
                />
                </SideMenuPanel>
                <SideMenuPanel id="kernel-logs" label="Logs" icon="pi pi-list" position="bottom">
                    <DebugPanel :entries="debugLogs" @clear-logs="debugLogs.splice(0, debugLogs.length)" v-autoscroll />
                </SideMenuPanel>
            </SideMenu>
        </template>
    </BaseInterface>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, inject } from 'vue';
import { JupyterMimeRenderer, type IMimeRenderer } from 'beaker-kernel';
import type { BeakerNotebookComponentType } from '../components/notebook/BeakerNotebook.vue';
import type { BeakerSessionComponentType } from '../components/session/BeakerSession.vue';
import { JSONRenderer, LatexRenderer, MarkdownRenderer, wrapJupyterRenderer, type BeakerRenderOutput, TableRenderer } from '../renderers';
import type { NavOption } from '../components/misc/BeakerHeader.vue';
import { standardRendererFactories } from '@jupyterlab/rendermime';

import BaseInterface from './BaseInterface.vue';
import FilePanel from '../components/panels/FilePanel.vue';
import ConfigPanel from '../components/panels/ConfigPanel.vue';
import SideMenu from "../components/sidemenu/SideMenu.vue";
import SideMenuPanel from "../components/sidemenu/SideMenuPanel.vue";
import FileContentsPanel from '../components/panels/FileContentsPanel.vue';
import NotebookSvg from '../assets/icon-components/NotebookSvg.vue';

import type { IBeakerTheme } from '../plugins/theme';
import DebugPanel from '../components/panels/DebugPanel.vue'

import IntegrationEditor from '../components/misc/IntegrationEditor.vue';
import IntegrationPanel from '../components/panels/IntegrationPanel.vue';
import { listResources, listIntegrations, type IntegrationInterfaceState, updateResource, addResource, updateIntegration, addIntegration, deleteResource } from '@/util/integration';
import ExamplesPanel from '../components/panels/ExamplesPanel.vue';

const beakerNotebookRef = ref<BeakerNotebookComponentType>();
const beakerInterfaceRef = ref();
const filePanelRef = ref();
const configPanelRef = ref();
const sideMenuRef = ref();
const rightSideMenuRef = ref();

const previewVisible = ref<boolean>(false);

const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.has("session") ? urlParams.get("session") : "notebook_dev_session";
const selectedParam = urlParams.has("selected") ? urlParams.get("selected") : undefined;

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
    MarkdownRenderer,
    TableRenderer
];

const connectionStatus = ref('connecting');
const debugLogs = ref<object[]>([]);
const rawMessages = ref<object[]>([])
const saveAsFilename = ref<string>(null);

const isMaximized = ref(false);
const { theme, toggleDarkMode } = inject<IBeakerTheme>('theme');
const beakerApp = inject<any>("beakerAppConfig");

beakerApp.setPage("integrations");

const contextPreviewData = ref<any>();
const kernelStateInfo = ref();

const hasOpenedPanelOnce = ref(false);

const selectedIntegration = ref();
const unsavedChanges = ref<boolean>(false);

type FilePreview = {
    url: string,
    mimetype?: string
}
const previewedFile = ref<FilePreview>();

onMounted(() => {
    // sideMenuRef.value.hidePanel()
    // rightSideMenuRef.value.hidePanel()
    if (!hasOpenedPanelOnce.value) {
        nextTick(() => sideMenuRef.value.selectPanel('integrations'));
        nextTick(() => rightSideMenuRef.value.selectPanel('examples'));
        (document.querySelector("div.sidemenu.right") as HTMLElement).style.width = '36vi';
        (document.querySelector("div.sidemenu.left") as HTMLElement).style.width = '25vi';
        hasOpenedPanelOnce.value = true;
    }
})

const beakerSession = computed<BeakerSessionComponentType>(() => {
    return beakerInterfaceRef?.value?.beakerSession;
});

const integrations = ref<IntegrationInterfaceState>({
    selected: selectedParam,
    integrations: {},
    unsavedChanges: false,
    finishedInitialLoad: false,
})

const fetchResourcesForSelectedIntegration = async () => {
    const selectedIntegration = integrations.value.integrations?.[integrations.value?.selected];
    if (selectedIntegration === undefined) {
        return;
    }
    if (integrations.value?.selected === "new") {
        // in the case of first-load opening a new, local-only integration, assume an empty resources object
        if (selectedIntegration?.resources === undefined || selectedIntegration?.resources === null ) {
            selectedIntegration.resources = {};
        }
        return;
    }
    selectedIntegration.resources = Object.fromEntries(
        (await listResources(sessionId, integrations.value.selected))
            ?.map(resource => [resource.resource_id, resource]) ?? []);
}

const fetchIntegrations = async () => {
    integrations.value.integrations = await listIntegrations(sessionId);
    integrations.value.finishedInitialLoad = true;
}

const modifySelectedIntegration = async (body: object, integrationId?: string) => {
    if (integrationId) {
        integrations.value.integrations[integrationId] = await updateIntegration(
            sessionId,
            integrationId,
            body
        )
    } else {
        const newIntegration = await addIntegration(sessionId, body);
        integrations.value.integrations[newIntegration.uuid] = newIntegration;
        integrations.value.selected = newIntegration.uuid;
    }
}

const modifyResourceForSelectedIntegration = async (body: object, resourceId?: string) => {
    const selectedIntegration = integrations.value.integrations?.[integrations.value?.selected];
    if (resourceId) {
        selectedIntegration.resources[resourceId] = await updateResource(
            sessionId,
            integrations.value.selected,
            resourceId,
            body
        );
    } else {
        const newResource = await addResource(
            sessionId,
            integrations.value.selected,
            body
        );
        selectedIntegration.resources[newResource.resource_id] = newResource;
    }
}

const deleteResourceOnSelectedIntegration = async (resourceId: string) => {
    await deleteResource(sessionId, integrations.value.selected, resourceId)
}

// on connection, send message with retries: see integrations.py:call_in_context()
watch(beakerSession, async () => fetchIntegrations());

const headerNav = computed((): NavOption[] => {
    const nav = [];
    if (!(beakerApp?.config?.pages) || (Object.hasOwn(beakerApp.config.pages, "notebook"))) {
        const href = "/" + (beakerApp?.config?.pages?.notebook?.default ? '' : 'notebook') + window.location.search;
        nav.push(
            {
                type: 'link',
                href: href,
                label: 'Navigate to notebook view',
                component: NotebookSvg,
                componentStyle: {
                    fill: 'currentColor',
                    stroke: 'currentColor',
                    height: '1rem',
                    width: '1rem',
                },
            }
        );
    }
    if (!(beakerApp?.config?.pages) || (Object.hasOwn(beakerApp.config.pages, "chat"))) {
        const href = "/" + (beakerApp?.config?.pages?.chat?.default ? '' : 'chat') + window.location.search;
        nav.push(
            {
                type: 'link',
                href: href,
                icon: 'comment',
                label: 'Navigate to chat view',
            }
        );
    }
    nav.push(...[
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
    return nav;
});

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

const iopubMessage = (msg) => {
    if (msg.header.msg_type === "preview") {
        contextPreviewData.value = msg.content;
    }
    else if (msg.header.msg_type === "kernel_state_info") {
        kernelStateInfo.value = msg.content;
    }
    else if (msg.header.msg_type === "debug_event") {
        debugLogs.value.push({
            type: msg.content.event,
            body: msg.content.body,
            timestamp: msg.header.date,
        });
    }
};

const anyMessage = (msg, direction) => {
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

const restartSession = async () => {
    const resetFuture = beakerSession.value.session.sendBeakerMessage(
        "reset_request",
        {}
    )
    await resetFuture;
}

</script>

<style lang="scss">

.integration-container {
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
    padding-top: 1rem;
    overflow: auto;

    .p-fieldset {
        input {
            max-width: 100%;
            width: 100%;
        }
        textarea {
            max-width: 100%;
            width: 100%;
        }

        max-width: 100%;
        .p-fieldset-legend {
            max-width: 100%;
            background: none;
            padding: 0.5rem;
            .p-dropdown {
                margin-right: 0.5rem;
            }
        }
        margin-bottom: 1rem;

        .p-fieldset-content {
            max-width: 100%;
            padding: 0.5rem;
            display: flex;
            flex-direction: column;
            div.p-toolbar {
                max-width: 100%;
                padding: 0.5rem;
                margin-bottom: 0.5rem;
                // &:nth-child(1) {
                //     margin-bottom: 0rem;
                // }
                .p-toolbar-group-start {
                    button {
                        margin-right: 0.5rem
                    }
                }
            }
            > .p-inputtextarea.p-inputtext {
                height: 10rem;
            }
            > p {
                margin-top: 0rem;
            }
        }
    }
}

.spacer {
    &.left {
        flex: 1 1000 25vw;
    }
    &.right {
        flex: 1 1 36vw;
    }
}

.title-extra {
    vertical-align: baseline;
    display: inline-block;
    height: 100%;
    font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
}

</style>
