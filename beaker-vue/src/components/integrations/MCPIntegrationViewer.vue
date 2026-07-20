<template>
    <div class="mcp-integration-viewer">
        <div class="mcp-viewer-content">
            <Fieldset legend="Name">
                <InputText
                    :model-value="selectedIntegration?.name"
                    disabled
                />
            </Fieldset>

            <Fieldset legend="Server" v-if="hasServerInfo">
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
                    <div class="mcp-metadata-row" v-if="resolvedTransport">
                        <span class="mcp-metadata-label">Transport</span>
                        <span class="mcp-metadata-value" style="font-family: monospace;">{{ resolvedTransport }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="selectedIntegration?.url">
                        <span class="mcp-metadata-label">Website</span>
                        <span class="mcp-metadata-value">
                            <a :href="selectedIntegration.url" target="_blank" rel="noopener">{{ selectedIntegration.url }}</a>
                        </span>
                    </div>
                </div>
            </Fieldset>

            <Fieldset legend="Connection" v-if="serverConfig">
                <div class="mcp-metadata-grid">
                    <div class="mcp-metadata-row" v-if="serverConfig.command">
                        <span class="mcp-metadata-label">Command</span>
                        <span class="mcp-metadata-value mcp-command">{{ commandLine }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="serverConfig.url">
                        <span class="mcp-metadata-label">URL</span>
                        <span class="mcp-metadata-value" style="font-family: monospace;">{{ serverConfig.url }}</span>
                    </div>
                    <div class="mcp-metadata-row" v-if="envKeys.length > 0">
                        <span class="mcp-metadata-label">Environment</span>
                        <span class="mcp-metadata-value mcp-key-list">
                            <code v-for="key in envKeys" :key="key">{{ key }}</code>
                        </span>
                    </div>
                    <div class="mcp-metadata-row" v-if="headerKeys.length > 0">
                        <span class="mcp-metadata-label">Headers</span>
                        <span class="mcp-metadata-value mcp-key-list">
                            <code v-for="key in headerKeys" :key="key">{{ key }}</code>
                        </span>
                    </div>
                </div>
                <p v-if="envKeys.length > 0 || headerKeys.length > 0" class="mcp-secret-note">
                    <i>Values are hidden; only the configured keys are shown.</i>
                </p>
            </Fieldset>

            <Fieldset legend="Description" v-if="renderedDescription">
                <div class="mcp-description" v-html="renderedDescription"></div>
            </Fieldset>

            <Fieldset legend="Instructions">
                <p>
                    Usage instructions reported by the server during connection.
                </p>
                <div v-if="renderedInstructions" class="mcp-description" v-html="renderedInstructions"></div>
                <p v-else class="mcp-blank-note">
                    <i>This server does not provide any instructions.</i>
                </p>
            </Fieldset>

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
        </div>
    </div>
</template>


<script setup lang="ts">

import { computed, ref, watch } from 'vue';
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
import ProgressSpinner from 'primevue/progressspinner';

import { marked } from 'marked';

const props = defineProps<{
    fetchResources: () => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const selectedIntegration = computed<MCPIntegration>(() =>
    model.value.integrations[model.value.selected] as MCPIntegration);

const catalogLoading = ref<boolean>(false);
const catalogError = ref<boolean>(false);

// Ensure the catalog is populated when an MCP integration is selected. The
// backend lazily (re)loads it if the eager startup load failed; a load failure
// surfaces as a thrown error here, which we render as a warning.
const loadCatalog = async () => {
    if (!selectedIntegration.value) {
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

watch(() => model.value.selected, () => loadCatalog(), { immediate: true });

const serverConfig = computed<MCPServerConfig | undefined>(() =>
    selectedIntegration.value?.server_config);

const renderedDescription = computed<string>(() =>
    marked.parse(selectedIntegration.value?.description ?? "") as string);

const renderedInstructions = computed<string>(() => {
    const instructions = selectedIntegration.value?.instructions;
    return instructions ? marked.parse(instructions) as string : "";
});

const hasServerInfo = computed<boolean>(() =>
    !!(selectedIntegration.value?.server_title
        || selectedIntegration.value?.server_version
        || resolvedTransport.value
        || selectedIntegration.value?.url
        || selectedIntegration.value?.server_config));

// Mirrors MCPServerConfig.resolved_transport (a Python @property, so not
// serialized): explicit transport wins, else inferred from command/url.
const resolvedTransport = computed<string | undefined>(() => {
    const config = serverConfig.value;
    if (!config) return undefined;
    if (config.transport) return config.transport;
    if (config.command) return "stdio";
    if (config.url) return "http";
    return undefined;
});

const commandLine = computed<string>(() => {
    const config = serverConfig.value;
    if (!config?.command) return "";
    return [config.command, ...(config.args ?? [])].join(" ");
});

const envKeys = computed<string[]>(() => Object.keys(serverConfig.value?.env ?? {}));
const headerKeys = computed<string[]>(() => Object.keys(serverConfig.value?.headers ?? {}));

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

</script>

<style lang="scss">
.mcp-integration-viewer {
    display: flex;
    flex-direction: column;
    height: 100%;

    .mcp-viewer-content {
        overflow: auto;
        display: flex;
        flex-direction: column;
    }
}

.mcp-description {
    h1 { font-size: 1.25rem; margin-bottom: 1rem; }
    h2 { font-size: 1.2rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.8rem; margin-top: 0rem; }
    > *:first-child { margin-top: 0rem; }
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

.mcp-command {
    font-family: monospace;
}

.mcp-key-list {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.35rem;

    code {
        background-color: var(--p-surface-100);
        padding: 0.1rem 0.35rem;
        border-radius: 4px;
    }
}

.mcp-secret-note {
    color: var(--p-text-muted-color);
    margin-bottom: 0;
}

.mcp-blank-note {
    color: var(--p-text-muted-color);
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
