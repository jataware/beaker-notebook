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
                <div class="integration-loading" v-if="beakerSession?.status === 'connecting'">
                    <ProgressSpinner></ProgressSpinner>
                    Loading integrations...
                </div>
                <div class="integration-page-content" v-else>
                    <div class="integration-content-header">
                        <Select
                            :options="sortedIntegrations.map(integration => ({
                                label: integration.name,
                                value: integration.uuid
                            }))"
                            :option-label="(option) => option?.label ?? 'Select integration...'"
                            option-value="value"
                            placeholder="Select an integration..."
                            @click="(event) => {
                                if (!confirmUnsavedChanges()) {
                                    event.preventDefault;
                                } else {
                                    integrations.unsavedChanges = false;
                                }
                            }"
                            v-model="integrations.selected"
                        />

                        <SplitButton
                            v-if="!readOnly"
                            label="New Integration"
                            :model="newIntegrationItems"
                            @click="() => {
                                if (confirmUnsavedChanges()) {
                                    newIntegration('adhoc');
                                }
                            }"
                        />
                    </div>

                    <div v-if="!integrations.selected" class="no-selection-placeholder" style="flex: 1">
                        <i class="pi pi-info-circle" style="font-size: 1.5rem;"></i>
                        <p>Select an integration to view or edit, or create a new one to get started.</p>
                    </div>

                    <component
                        v-else
                        :is="centerComponent"
                        v-model="integrations"
                        :deleteResource="deleteResourceOnSelectedIntegration"
                        :modifyResource="modifyResourceForSelectedIntegration"
                        :modifyIntegration="modifySelectedIntegration"
                        :fetchResources="fetchResourcesForSelectedIntegration"
                    />
                </div>
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
                        :read-only="readOnly"
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
                    :label="rightPanelLabel"
                    :icon="rightPanelIcon"
                    no-overflow
                >
                    <component
                        v-if="integrations.selected"
                        :is="rightPanelComponent"
                        v-model="integrations"
                        :disabled="!integrations.selected || integrations.selected === 'new'"
                        :deleteResource="deleteResourceOnSelectedIntegration"
                        :modifyResource="modifyResourceForSelectedIntegration"
                        :sessionId="sessionId"
                    />
                    <div v-else class="no-selection-placeholder" style="padding: 1rem;">
                        <i>Select an integration to view its resources.</i>
                    </div>
                </SideMenuPanel>
                <SideMenuPanel id="kernel-logs" label="Logs" icon="pi pi-list" position="bottom">
                    <DebugPanel :entries="debugLogs" @clear-logs="debugLogs.splice(0, debugLogs.length)" v-autoscroll />
                </SideMenuPanel>
            </SideMenu>
        </template>
    </BaseInterface>
</template>

<script setup lang="tsx">
import { ref, watch, computed, nextTick, onMounted, inject, h, type Component } from 'vue';
import { JupyterMimeRenderer, type IMimeRenderer } from '@jataware/beaker-client';
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

import Select from 'primevue/select';
import SplitButton from "primevue/splitbutton";
import ProgressSpinner from 'primevue/progressspinner';

import AdhocIntegrationEditor from '../components/integrations/AdhocIntegrationEditor.vue';
import SkillIntegrationViewer from '../components/integrations/SkillIntegrationViewer.vue';
import MCPIntegrationViewer from '../components/integrations/MCPIntegrationViewer.vue';
import MCPIntegrationEditor from '../components/integrations/MCPIntegrationEditor.vue';
import MCPToolsPanel from '../components/integrations/MCPToolsPanel.vue';
import IntegrationPanel from '../components/integrations/IntegrationPanel.vue';
import ExamplesPanel from '../components/integrations/ExamplesPanel.vue';
import ResourceViewer from '../components/integrations/ResourceViewer.vue';
import {
    listResources,
    listIntegrations,
    type IntegrationInterfaceState,
    type IntegrationMap,
    type Integration,
    getIntegrationProviderType,
    isContextProvidedIntegration,
    updateResource,
    addResource,
    updateIntegration,
    addIntegration,
    getIntegration,
    deleteResource,
} from '@/util/integration';
import { useRoute } from 'vue-router';

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

type FilePreview = {
    url: string,
    mimetype?: string
}
const previewedFile = ref<FilePreview>();

onMounted(() => {
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

const integrationMapping: {[integrationType: string]: any} = {
    'agent-skill': {
        readOnly: true,
        centerComponent: SkillIntegrationViewer,
        rightPanelComponent: ResourceViewer,
        rightPanelLabel: 'Resources',
        rightPanelIcon: 'pi pi-folder-open',
    },
    adhoc: {
        readOnly: false,
        centerComponent: AdhocIntegrationEditor,
        rightPanelComponent: ExamplesPanel,
        rightPanelLabel: 'Example Editor',
        rightPanelIcon: 'pi pi-list-check',
    },
    mcp: {
        readOnly: false,
        centerComponent: MCPIntegrationViewer,
        rightPanelComponent: MCPToolsPanel,
        rightPanelLabel: 'Tools',
        rightPanelIcon: 'pi pi-wrench',
    },
    default: {
        readOnly: false,
        centerComponent: null,
        rightPanelComponent: null,
        rightPanelLabel: 'Resources',
        rightPanelIcon: 'pi pi-folder-check',
    },
}

const integrations = ref<IntegrationInterfaceState>({
    selected: selectedParam,
    integrations: {},
    unsavedChanges: false,
    finishedInitialLoad: false,
});

// --- Integration type detection ---

const selectedIntegration = computed<Integration | undefined>(() =>
    integrations.value.integrations?.[integrations.value?.selected]);

const selectedIntegrationType = computed<string | undefined>(() => {
    if (!selectedIntegration.value) return undefined;
    return getIntegrationProviderType(selectedIntegration.value);
});

// --- Dynamic component switching ---

const centerComponent = computed<Component>(() => {
    // MCP servers get a read-only viewer when provided by a context, and the
    // full editor otherwise; all other types use their fixed mapping entry.
    if (selectedIntegrationType.value === 'mcp') {
        return isContextProvidedIntegration(selectedIntegration.value)
            ? MCPIntegrationViewer
            : MCPIntegrationEditor;
    }
    return integrationMapping[selectedIntegrationType.value]?.centerComponent || integrationMapping.default?.centerComponent;
});

const rightPanelComponent = computed<Component>(() => {
    return integrationMapping[selectedIntegrationType.value]?.rightPanelComponent || integrationMapping.default?.rightPanelComponent;
});

const rightPanelLabel = computed<string>(() => {
    return integrationMapping[selectedIntegrationType.value]?.rightPanelLabel || integrationMapping.default?.rightPanelLabel;
});

const rightPanelIcon = computed<string>(() => {
    return integrationMapping[selectedIntegrationType.value]?.rightPanelIcon || integrationMapping.default?.rightPanelIcon;
});

const readOnly = computed<boolean>(() => {
    return integrationMapping[selectedIntegrationType.value]?.readOnly || integrationMapping.default?.readOnly;
})

// --- Integration selector logic (moved from IntegrationEditor) ---

const sortIntegrations = (integrations: IntegrationMap): Integration[] =>
    Object.values(integrations).toSorted((a, b) => a?.name.localeCompare(b?.name));

const sortedIntegrations = computed<Integration[]>(() =>
    sortIntegrations(integrations.value.integrations ?? {}));

const confirmUnsavedChanges = () => {
    if (integrations.value.unsavedChanges) {
        return confirm("You currently have unsaved changes that would be lost with this change. Are you sure?");
    }
    return true;
};

// Finds the provider string for an existing integration of the given type so
// new integrations attach to the same provider, falling back to a sensible
// default when none is loaded yet.
const providerForType = (providerType: string, fallback: string): string =>
    Object.values(integrations.value?.integrations ?? {})
        .find(i => getIntegrationProviderType(i) === providerType)?.provider ?? fallback;

const newIntegration = (providerType: string = 'adhoc') => {
    let integration: Integration;
    if (providerType === 'mcp') {
        integration = {
            name: "New MCP Server",
            source: "",
            description: "",
            provider: providerForType('mcp', "mcp:mcp"),
            datatype: "mcp",
            slug: "new_mcp_server",
            uuid: "new",
            url: "",
            server_config: {
                name: "new_mcp_server",
                transport: "stdio",
                command: "",
                args: [],
                env: {},
                headers: {},
                disabled: false,
            },
        } as Integration;
    } else {
        integration = {
            name: "New Integration",
            source: "This is the prompt information that the agent will consult when using the integration. Include API details or how to find datasets here.",
            description: "This is the description that the agent will use to determine when this integration should be used.",
            provider: providerForType('adhoc', "adhoc:specialist_agents"),
            slug: "new_integration",
            uuid: "new",
            url: ""
        };
    }
    integrations.value.integrations["new"] = integration;
    integrations.value.selected = "new";
    integrations.value.unsavedChanges = true;
};

// Menu items for the "New Integration" split button; each guards unsaved
// changes before starting a fresh integration of the chosen type.
const newIntegrationItems = computed(() => [
    {
        label: "Specialist Agent",
        icon: "pi pi-user",
        command: () => { if (confirmUnsavedChanges()) { newIntegration('adhoc'); } },
    },
//    {
//        label: "MCP Server",
//        icon: "pi pi-server",
//        command: () => { if (confirmUnsavedChanges()) { newIntegration('mcp'); } },
//    },
]);

const delayUntil = (condition, retryInterval) => {
    const poll = resolve => {
        if (condition()) {
            resolve();
        } else {
            setTimeout(() => poll(resolve), retryInterval);
        }
    };
    return new Promise(poll);
};

const route = useRoute();
watch(() => route, (newRoute) => {
    if (newRoute.query?.selected === "new") {
        const providerType = (newRoute.query?.type as string | undefined) ?? 'adhoc';
        if (integrations.value.finishedInitialLoad) {
            newIntegration(providerType);
        } else {
            delayUntil(() => integrations.value.finishedInitialLoad, 100)
                .then(() => newIntegration(providerType));
        }
    } else {
        integrations.value.selected = newRoute.query?.selected as string | undefined ?? integrations.value.selected;
    }
}, {immediate: true, deep: true});

// --- API operations ---

const fetchResourcesForSelectedIntegration = async () => {
    const selectedIntegration = integrations.value.integrations?.[integrations.value?.selected];
    if (selectedIntegration === undefined) {
        return;
    }
    if (integrations.value?.selected === "new") {
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

watch(
    [() => beakerSession?.value?.activeContext, () => beakerSession?.value?.session.kernelInfo],
    async () => await fetchIntegrations()
);

const modifySelectedIntegration = async (body: object, integrationId?: string) => {
    let savedId: string | undefined;
    if (integrationId) {
        await updateIntegration(sessionId, integrationId, body);
        savedId = integrationId;
    } else {
        const newIntegration = await addIntegration(sessionId, body);
        savedId = newIntegration?.uuid;
        if (savedId) {
            integrations.value.selected = savedId;
        }
    }
    // The POST response is not a reliable source of truth for the saved
    // integration -- some providers (e.g. MCP) return nothing on update, which
    // would otherwise clobber the local copy with an empty object. Re-fetch the
    // authoritative integration from the kernel so the local state reflects what
    // was actually persisted, preserving any resources already loaded for it.
    if (!savedId) {
        return;
    }
    const fresh = await getIntegration(sessionId, savedId);
    const existingResources = integrations.value.integrations[savedId]?.resources;
    if (fresh.resources === undefined && existingResources !== undefined) {
        fresh.resources = existingResources;
    }
    integrations.value.integrations[savedId] = fresh;
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
    await deleteResource(sessionId, integrations.value.selected, resourceId);
}

watch(beakerSession, async () => fetchIntegrations());

// --- Header nav ---

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

.integration-page-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 0 0.4rem;
}

.integration-content-header {
    display: flex;
    flex-direction: row;
    gap: 0.5rem;
    width: 100%;
    max-width: 100%;
    flex-shrink: 0;
    margin-bottom: 0.5rem;

    > div.p-select {
        flex: 1 1 auto;
        width: 100px;
        span.p-select-label {
            flex-shrink: 2;
            display: block;
            min-width: 0;
        }
    }
}

.integration-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 1rem;
}

.no-selection-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 3rem 1rem;
    color: var(--p-text-muted-color);
    text-align: center;
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
