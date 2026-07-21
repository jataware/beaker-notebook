<template>
    <div class="mcp-integration-editor">
        <div class="mcp-editor-content">
            <Fieldset legend="Display Name">
                <p>
                    The display name shown for this MCP server throughout the UI and used by the agent to refer to it.
                    Overrides the server's own reported title.
                </p>
                <InputText
                    :model-value="selectedIntegration?.name"
                    @update:model-value="(value) => { selectedIntegration.name = value; markDirty(); }"
                    placeholder="Display name"
                />
                <template v-if="isNew">
                    <p style="margin-top: 1rem;">
                        A unique key identifying this server in the config file. Lower-case, no spaces.
                    </p>
                    <InputText
                        :model-value="serverConfig.name"
                        @update:model-value="(value) => { serverConfig.name = value; markDirty(); }"
                        placeholder="server-key"
                        style="font-family: monospace;"
                    />
                </template>
            </Fieldset>

            <Fieldset legend="Server" v-if="hasServerInfo && !isNew">
                <div class="mcp-metadata-grid">
                    <div class="mcp-metadata-row" v-if="selectedIntegration?.slug">
                        <span class="mcp-metadata-label">Key</span>
                        <span class="mcp-metadata-value" style="font-family: monospace;">{{ selectedIntegration.slug }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="selectedIntegration?.server_title">
                        <span class="mcp-metadata-label">Reported title</span>
                        <span class="mcp-metadata-value">{{ selectedIntegration.server_title }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="selectedIntegration?.server_version">
                        <span class="mcp-metadata-label">Version</span>
                        <span class="mcp-metadata-value">{{ selectedIntegration.server_version }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="selectedIntegration?.url">
                        <span class="mcp-metadata-label">Website</span>
                        <span class="mcp-metadata-value">
                            <a :href="selectedIntegration.url" target="_blank" rel="noopener">{{ selectedIntegration.url }}</a>
                        </span>
                    </div>
                </div>
            </Fieldset>

            <Fieldset legend="Connection">
                <p>
                    How Beaker connects to this server. A <code>stdio</code> server runs as a local process; an
                    <code>http</code> or <code>sse</code> server is reached over the network.
                </p>
                <div class="mcp-form-grid">
                    <div class="mcp-form-row">
                        <label>Transport</label>
                        <Select
                            :model-value="activeTransport"
                            @update:model-value="(value) => { serverConfig.transport = value; markDirty(); }"
                            :options="transportOptions"
                            option-label="label"
                            option-value="value"
                            placeholder="Select transport..."
                        />
                    </div>

                    <template v-if="activeTransport === 'stdio'">
                        <div class="mcp-form-row">
                            <label>Command</label>
                            <InputText
                                :model-value="serverConfig.command"
                                @update:model-value="(value) => { serverConfig.command = value; markDirty(); }"
                                placeholder="e.g. npx"
                                style="font-family: monospace;"
                            />
                        </div>

                        <div class="mcp-form-row">
                            <label>Arguments</label>
                            <div class="mcp-list-editor">
                                <div class="mcp-list-item" v-for="(_, index) in argRows" :key="index">
                                    <InputText
                                        v-model="argRows[index]"
                                        @update:model-value="markDirty"
                                        placeholder="argument"
                                        style="font-family: monospace;"
                                    />
                                    <Button
                                        icon="pi pi-trash"
                                        severity="danger"
                                        text
                                        @click="() => { argRows.splice(index, 1); markDirty(); }"
                                        v-tooltip="'Remove argument'"
                                    />
                                </div>
                                <Button
                                    class="mcp-add-button"
                                    icon="pi pi-plus"
                                    label="Add argument"
                                    text
                                    @click="() => { argRows.push(''); markDirty(); }"
                                />
                            </div>
                        </div>

                        <div class="mcp-form-row">
                            <label>Environment</label>
                            <div class="mcp-list-editor">
                                <div class="mcp-kv-item" v-for="(row, index) in envRows" :key="index">
                                    <InputText
                                        v-model="row.key"
                                        @update:model-value="markDirty"
                                        placeholder="KEY"
                                        style="font-family: monospace;"
                                    />
                                    <InputText
                                        v-model="row.value"
                                        @update:model-value="markDirty"
                                        placeholder="value"
                                    />
                                    <Button
                                        icon="pi pi-trash"
                                        severity="danger"
                                        text
                                        @click="() => { envRows.splice(index, 1); markDirty(); }"
                                        v-tooltip="'Remove variable'"
                                    />
                                </div>
                                <Button
                                    class="mcp-add-button"
                                    icon="pi pi-plus"
                                    label="Add variable"
                                    text
                                    @click="() => { envRows.push({ key: '', value: '' }); markDirty(); }"
                                />
                            </div>
                        </div>
                    </template>

                    <template v-else>
                        <div class="mcp-form-row">
                            <label>URL</label>
                            <InputText
                                :model-value="serverConfig.url"
                                @update:model-value="(value) => { serverConfig.url = value; markDirty(); }"
                                placeholder="https://example.com/mcp"
                                style="font-family: monospace;"
                            />
                        </div>

                        <div class="mcp-form-row">
                            <label>Headers</label>
                            <div class="mcp-list-editor">
                                <div class="mcp-kv-item" v-for="(row, index) in headerRows" :key="index">
                                    <InputText
                                        v-model="row.key"
                                        @update:model-value="markDirty"
                                        placeholder="Header-Name"
                                        style="font-family: monospace;"
                                    />
                                    <InputText
                                        v-model="row.value"
                                        @update:model-value="markDirty"
                                        placeholder="value"
                                    />
                                    <Button
                                        icon="pi pi-trash"
                                        severity="danger"
                                        text
                                        @click="() => { headerRows.splice(index, 1); markDirty(); }"
                                        v-tooltip="'Remove header'"
                                    />
                                </div>
                                <Button
                                    class="mcp-add-button"
                                    icon="pi pi-plus"
                                    label="Add header"
                                    text
                                    @click="() => { headerRows.push({ key: '', value: '' }); markDirty(); }"
                                />
                            </div>
                        </div>
                    </template>

                    <div class="mcp-form-row mcp-form-row-inline">
                        <Checkbox
                            :model-value="serverConfig.disabled"
                            @update:model-value="(value) => { serverConfig.disabled = value; markDirty(); }"
                            :binary="true"
                            input-id="mcp-disabled"
                        />
                        <label for="mcp-disabled">Disabled (do not load this server)</label>
                    </div>
                </div>
                <p class="mcp-secret-note">
                    <i>Environment and header values are stored in the config file in plain text.</i>
                </p>
            </Fieldset>

            <Fieldset legend="Description">
                <p>
                    A brief summary of this server's purpose. Used by the agent to decide when this server is relevant.
                </p>
                <div class="constrained-editor-height">
                    <CodeEditor
                        language="markdown"
                        :autocomplete-enabled="false"
                        v-model="selectedIntegration.description"
                        @change="markDirty"
                        ref="descriptionEditor"
                    />
                </div>
            </Fieldset>

            <Fieldset legend="Instructions">
                <p>
                    Usage instructions reported by the server during connection. These are provided by the server and
                    cannot be edited here.
                </p>
                <div v-if="renderedInstructions" class="mcp-description" v-html="renderedInstructions"></div>
                <p v-else class="mcp-blank-note">
                    <i>This server does not provide any instructions.</i>
                </p>
            </Fieldset>

            <template v-if="!isNew">
                <div v-if="catalogLoading" class="mcp-catalog-status mcp-catalog-loading">
                    <ProgressSpinner style="width: 1.5rem; height: 1.5rem;" />
                    <span>Loading this server's catalog&hellip;</span>
                </div>

                <div v-else-if="catalogError" class="mcp-catalog-status mcp-catalog-warning">
                    <i class="pi pi-exclamation-triangle"></i>
                    <span>Unable to load this server's catalog. The server may be unavailable or misconfigured.</span>
                </div>

                <p class="mcp-catalog-hint" v-if="!catalogLoading && !catalogError && toolResources.length > 0">
                    <i class="pi pi-wrench"></i>
                    <span>
                        This server advertises {{ toolResources.length }}
                        {{ toolResources.length === 1 ? 'tool' : 'tools' }}; see the
                        <b>Tools</b> panel for details.
                    </span>
                </p>

                <Fieldset :legend="`Resources (${resourceResources.length})`" v-if="!catalogLoading && !catalogError && resourceResources.length > 0">
                    <p>
                        Readable resources advertised by this server, addressed by URI and fetched on demand.
                    </p>
                    <div class="mcp-resource-list">
                        <div
                            class="mcp-resource-item"
                            v-for="resource in resourceResources"
                            :key="resource.resource_id"
                        >
                            <i class="pi pi-file"></i>
                            <div class="mcp-resource-info">
                                <span class="mcp-resource-name">{{ resource.name || resource.uri }}</span>
                                <span class="mcp-resource-desc" v-if="resource.uri && resource.name">{{ resource.uri }}</span>
                            </div>
                        </div>
                    </div>
                </Fieldset>

                <Fieldset :legend="`Prompts (${promptResources.length})`" v-if="!catalogLoading && !catalogError && promptResources.length > 0">
                    <p>
                        Prompt templates advertised by this server.
                    </p>
                    <div class="mcp-resource-list">
                        <div
                            class="mcp-resource-item"
                            v-for="prompt in promptResources"
                            :key="prompt.resource_id"
                        >
                            <i class="pi pi-comment"></i>
                            <div class="mcp-resource-info">
                                <span class="mcp-resource-name">{{ prompt.prompt_name }}</span>
                                <span class="mcp-resource-desc" v-if="prompt.description">{{ prompt.description }}</span>
                            </div>
                        </div>
                    </div>
                </Fieldset>

                <div v-if="!catalogLoading && !catalogError && catalogEmpty" class="mcp-catalog-status mcp-catalog-empty">
                    <i class="pi pi-info-circle"></i>
                    <span>This server advertises no tools, resources, or prompts.</span>
                </div>
            </template>
        </div>

        <div class="mcp-editor-actions">
            <div v-if="model.unsavedChanges">
                <Button
                    @click="save"
                    icon="pi pi-save"
                    label="Save Changes"
                    severity="success"
                />
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">

import { computed, ref, watch, inject } from 'vue';
import {
    type IntegrationInterfaceState,
    type MCPIntegration,
    type MCPServerConfig,
    type MCPToolResource,
    type MCPResourceResource,
    type MCPPromptResource,
    filterByResourceType,
} from '../../util/integration';

import Fieldset from 'primevue/fieldset';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import Button from 'primevue/button';
import ProgressSpinner from 'primevue/progressspinner';

import { marked } from 'marked';

import CodeEditor from '../misc/CodeEditor.vue';

const showToast = inject<any>('show_toast');

const props = defineProps<{
    fetchResources: () => Promise<void>,
    deleteResource: (resourceId: string) => Promise<void>,
    modifyResource: (body: object, resourceId?: string) => Promise<void>,
    modifyIntegration: (body: object, integrationId?: string) => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const selectedIntegration = computed<MCPIntegration>(() =>
    model.value.integrations[model.value.selected] as MCPIntegration);

const isNew = computed<boolean>(() => model.value.selected === "new");

// The server_config is always present on discovered integrations and on the
// "new" shell created by the interface; guard defensively regardless.
const serverConfig = computed<MCPServerConfig>(() => {
    if (selectedIntegration.value && !selectedIntegration.value.server_config) {
        selectedIntegration.value.server_config = { name: selectedIntegration.value.slug };
    }
    return selectedIntegration.value?.server_config ?? { name: "" };
});

const transportOptions = [
    { label: "stdio (local process)", value: "stdio" },
    { label: "http", value: "http" },
    { label: "sse", value: "sse" },
];

// Mirrors MCPServerConfig.resolved_transport: an explicit transport wins,
// otherwise it is inferred from command/url, defaulting to stdio for a fresh
// server that has neither set yet.
const activeTransport = computed<string>(() => {
    const config = serverConfig.value;
    if (config?.transport) return config.transport;
    if (config?.command) return "stdio";
    if (config?.url) return "http";
    return "stdio";
});

// Editable connection collections. Backed by local rows so that adding,
// removing, or renaming keys behaves naturally; flushed into server_config on
// save. Re-initialized whenever the selected integration changes.
const argRows = ref<string[]>([]);
const envRows = ref<{ key: string, value: string }[]>([]);
const headerRows = ref<{ key: string, value: string }[]>([]);

const syncRowsFromConfig = () => {
    const config: Partial<MCPServerConfig> = selectedIntegration.value?.server_config ?? {};
    argRows.value = [...(config.args ?? [])];
    envRows.value = Object.entries(config.env ?? {}).map(([key, value]) => ({ key, value: String(value) }));
    headerRows.value = Object.entries(config.headers ?? {}).map(([key, value]) => ({ key, value: String(value) }));
};

const markDirty = () => {
    model.value.unsavedChanges = true;
};

const catalogLoading = ref<boolean>(false);
const catalogError = ref<boolean>(false);

// Ensure the catalog is populated when an existing MCP integration is selected.
// The backend lazily (re)loads it if the eager startup load failed; a load
// failure surfaces as a thrown error here, which we render as a warning.
const loadCatalog = async () => {
    if (!selectedIntegration.value || isNew.value) {
        return;
    }
    catalogError.value = false;
    catalogLoading.value = true;
    try {
        await props.fetchResources();
    } catch (e) {
        console.error('Failed to load MCP catalog:', e);
        catalogError.value = true;
    } finally {
        catalogLoading.value = false;
    }
};

watch(() => model.value.selected, () => {
    // A freshly created server arrives pre-dirtied so its Save button shows
    // immediately; only clear the flag when landing on an existing one.
    if (!isNew.value) {
        model.value.unsavedChanges = false;
    }
    syncRowsFromConfig();
    loadCatalog();
}, { immediate: true });

watch(model, ({ unsavedChanges }) => {
    onbeforeunload = unsavedChanges ? () => true : undefined;
});

const descriptionEditor = ref();
watch(() => selectedIntegration.value?.description, (current) => {
    if (descriptionEditor.value) {
        descriptionEditor.value.model = current;
    }
});

// Instructions are reported by the server during connection; rendered
// read-only here (see the Instructions fieldset). Not persisted to config.
const renderedInstructions = computed<string>(() => {
    const instructions = selectedIntegration.value?.instructions;
    return instructions ? marked.parse(instructions) as string : "";
});

const hasServerInfo = computed<boolean>(() =>
    !!(selectedIntegration.value?.server_title
        || selectedIntegration.value?.server_version
        || selectedIntegration.value?.slug
        || selectedIntegration.value?.url));

const toolResources = computed<MCPToolResource[]>(() =>
    Object.values(filterByResourceType<MCPToolResource>(
        selectedIntegration.value?.resources, "mcp_tool")));

const resourceResources = computed<MCPResourceResource[]>(() =>
    Object.values(filterByResourceType<MCPResourceResource>(
        selectedIntegration.value?.resources, "mcp_resource")));

const promptResources = computed<MCPPromptResource[]>(() =>
    Object.values(filterByResourceType<MCPPromptResource>(
        selectedIntegration.value?.resources, "mcp_prompt")));

const catalogEmpty = computed<boolean>(() =>
    toolResources.value.length === 0
    && resourceResources.value.length === 0
    && promptResources.value.length === 0);

const save = async () => {
    const integration = selectedIntegration.value;
    if (integration === undefined) {
        return;
    }

    // Flush the editable connection collections back into server_config, then
    // mirror the display name/description onto it so the backend has an
    // unambiguous source when writing the config file.
    const config: MCPServerConfig = { ...(integration.server_config ?? { name: integration.slug }) };
    config.args = [...argRows.value];
    config.env = Object.fromEntries(envRows.value.filter((r) => r.key !== "").map((r) => [r.key, r.value]));
    config.headers = Object.fromEntries(headerRows.value.filter((r) => r.key !== "").map((r) => [r.key, r.value]));
    config.transport = activeTransport.value as MCPServerConfig["transport"];
    config.title = integration.name;
    config.description = integration.description;
    if (!config.name) {
        config.name = integration.slug || integration.name;
    }
    integration.server_config = config;

    await props.modifyIntegration(integration, isNew.value ? undefined : model.value.selected);

    showToast({
        title: 'Saved!',
        detail: `The session will now reconnect and load the new definition.`,
        severity: 'success',
        life: 4000,
    });

    if (isNew.value) {
        delete model.value.integrations["new"];
    }
    model.value.unsavedChanges = false;
};

</script>

<style lang="scss">
.mcp-integration-editor {
    display: flex;
    flex-direction: column;
    height: 100%;

    .mcp-editor-content {
        flex: 1 1 auto;
        min-height: 0;
        overflow: auto;
        display: flex;
        flex-direction: column;
    }
}

.mcp-editor-actions {
    flex: 1 0;
    margin: 0.2rem;
    display: flex;
    justify-content: flex-end;

    > div {
        flex-shrink: 0;
    }
}

.mcp-form-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.mcp-form-row {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;

    > label {
        font-weight: 600;
    }
}

.mcp-form-row-inline {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;

    > label {
        font-weight: 400;
    }
}

.mcp-list-editor {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

.mcp-list-item {
    display: flex;
    flex-direction: row;
    gap: 0.35rem;
    align-items: center;

    > .p-inputtext {
        flex: 1 1 auto;
    }
}

.mcp-kv-item {
    display: flex;
    flex-direction: row;
    gap: 0.35rem;
    align-items: center;

    > .p-inputtext:first-of-type {
        flex: 1 1 30%;
    }
    > .p-inputtext:nth-of-type(2) {
        flex: 2 1 60%;
    }
}

.mcp-add-button {
    width: fit-content;
}

.mcp-description {
    h1 { font-size: 1.25rem; margin-bottom: 1rem; }
    h2 { font-size: 1.2rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.8rem; margin-top: 0rem; }
    > *:first-child { margin-top: 0rem; }
}

.mcp-blank-note {
    color: var(--p-text-muted-color);
}

.mcp-metadata-grid {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.mcp-metadata-row {
    display: flex;
    flex-direction: row;
    gap: 1rem;
    align-items: baseline;

    .mcp-metadata-label {
        font-weight: 600;
        min-width: 8rem;
        flex-shrink: 0;
    }

    .mcp-metadata-value {
        flex: 1;
        min-width: 0;
        word-break: break-word;
    }
}

.mcp-secret-note {
    color: var(--p-text-muted-color);
    margin-bottom: 0;
}

.mcp-resource-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.mcp-resource-item {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;

    &:hover {
        background-color: var(--p-surface-100);
    }
}

.mcp-resource-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
}

.mcp-resource-name {
    font-family: monospace;
}

.mcp-resource-desc {
    font-size: 0.85rem;
    color: var(--p-text-muted-color);
}

.mcp-catalog-hint {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--p-text-muted-color);
    margin: 0 0 1rem 0;
}

.mcp-catalog-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
}

.mcp-catalog-loading,
.mcp-catalog-empty {
    color: var(--p-text-muted-color);
}

.mcp-catalog-warning {
    color: var(--p-orange-600, #c05621);

    i {
        font-size: 1.1rem;
    }
}
</style>
