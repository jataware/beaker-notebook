<template>
    <div class="mcp-tools-panel">
        <div v-if="disabled" class="mcp-tools-placeholder">
            <i>Save this server to view the tools it advertises.</i>
        </div>

        <template v-else>
            <div class="mcp-tools-header" v-if="viewState.view === 'list'">
                <InputGroup>
                    <InputGroupAddon>
                        <i class="pi pi-search"></i>
                    </InputGroupAddon>
                    <InputText placeholder="Search Tools..." v-model="searchText" />
                    <Button
                        v-if="searchText"
                        icon="pi pi-times"
                        severity="danger"
                        @click="searchText = undefined"
                        v-tooltip.left="'Clear Search'"
                    />
                </InputGroup>
                <div class="mcp-tools-count">
                    <i>{{ allTools.length }} {{ allTools.length === 1 ? 'tool' : 'tools' }} advertised:</i>
                </div>
            </div>

            <div class="mcp-tools-list" v-if="viewState.view === 'list'">
                <div
                    class="mcp-tool-card"
                    v-for="tool in filteredTools"
                    :key="tool.resource_id"
                    @mouseleave="hoveredTool = undefined"
                    @mouseenter="hoveredTool = tool.resource_id"
                >
                    <Card
                        @click="viewTool(tool)"
                        :pt="{
                            root: {
                                style:
                                    'transition: background-color 150ms linear;' +
                                    (hoveredTool === tool.resource_id
                                        ? 'background-color: var(--p-surface-100); cursor: pointer;'
                                        : '')
                            }
                        }"
                    >
                        <template #title>
                            <div class="mcp-tool-card-title">
                                <i class="pi pi-wrench"></i>
                                <span class="mcp-tool-card-title-text">{{ tool.tool_name }}</span>
                                <i
                                    class="pi pi-chevron-right mcp-tool-arrow"
                                    :style="hoveredTool === tool.resource_id ? 'opacity: 1;' : 'opacity: 0;'"
                                />
                            </div>
                        </template>
                        <template #content v-if="tool.description">
                            <div class="mcp-tool-card-desc">{{ tool.description }}</div>
                        </template>
                    </Card>
                </div>

                <div v-if="allTools.length === 0" class="mcp-tools-placeholder">
                    <i class="pi pi-info-circle"></i>
                    <span>This server advertises no tools.</span>
                </div>
            </div>

            <div class="mcp-tool-focused" v-else-if="viewState.view === 'focused'">
                <div class="mcp-tool-focused-header">
                    <Button
                        severity="secondary"
                        icon="pi pi-arrow-left"
                        @click="viewState = { view: 'list' }"
                        label="Back"
                        style="width: fit-content;"
                    />
                    <span class="mcp-tool-focused-title">{{ viewState.tool.tool_name }}</span>
                </div>

                <div class="mcp-tool-focused-content">
                    <section v-if="renderedDescription">
                        <h4 class="mcp-tool-section-label">Description</h4>
                        <div class="mcp-tool-description" v-html="renderedDescription"></div>
                    </section>
                    <section v-else>
                        <div class="mcp-tool-blank-note"><i>This tool has no description.</i></div>
                    </section>

                    <section>
                        <h4 class="mcp-tool-section-label">Arguments</h4>
                        <div v-if="focusedArgs.length === 0" class="mcp-tool-blank-note">
                            <i>This tool takes no arguments.</i>
                        </div>
                        <div v-else class="mcp-tool-arg-list">
                            <div class="mcp-tool-arg" v-for="arg in focusedArgs" :key="arg.name">
                                <div class="mcp-tool-arg-signature">
                                    <span class="mcp-tool-arg-name">{{ arg.name }}</span>
                                    <span class="mcp-tool-arg-type">{{ arg.type }}</span>
                                    <Tag
                                        v-if="arg.required"
                                        value="required"
                                        severity="warn"
                                        class="mcp-tool-arg-required"
                                    />
                                </div>
                                <div class="mcp-tool-arg-desc" v-if="arg.description">{{ arg.description }}</div>
                            </div>
                        </div>
                    </section>
                </div>
            </div>
        </template>
    </div>
</template>


<script setup lang="ts">

import { ref, computed } from 'vue';
import Button from "primevue/button";
import Card from 'primevue/card';
import Tag from 'primevue/tag';
import InputGroup from "primevue/inputgroup";
import InputGroupAddon from "primevue/inputgroupaddon";
import InputText from "primevue/inputtext";
import { marked } from 'marked';
import {
    type IntegrationInterfaceState,
    type MCPToolResource,
    filterByResourceType,
} from '../../util/integration';

// The interface passes shared right-panel props (deleteResource, modifyResource,
// sessionId) to every right-panel component; this panel is read-only and uses
// only `disabled`, so discard the rest rather than let them fall through to the
// root element.
defineOptions({ inheritAttrs: false });

defineProps<{
    disabled?: boolean;
}>();

// A single argument surfaced from a tool's JSON-Schema `input_schema`.
interface ToolArgument {
    name: string;
    type: string;
    required: boolean;
    description?: string;
}

type ViewState =
    | { view: "list" }
    | { view: "focused"; tool: MCPToolResource };

const model = defineModel<IntegrationInterfaceState>();

const viewState = ref<ViewState>({ view: 'list' });
const searchText = ref<string | undefined>(undefined);
const hoveredTool = ref<string | undefined>(undefined);

const allTools = computed<MCPToolResource[]>(() =>
    Object.values(filterByResourceType<MCPToolResource>(
        model.value?.integrations?.[model.value?.selected]?.resources, "mcp_tool")));

const filteredTools = computed<MCPToolResource[]>(() => {
    if (!searchText.value) return allTools.value;
    const term = searchText.value.toLowerCase();
    return allTools.value.filter(t =>
        t.tool_name.toLowerCase().includes(term)
        || (t.description ?? "").toLowerCase().includes(term));
});

// Best-effort human-readable type for a JSON-Schema property; mirrors the
// backend's _json_schema_type (mcp.py) for the shapes MCP tools commonly use.
const jsonSchemaType = (spec: Record<string, any>): string => {
    if (spec?.type !== undefined) {
        return Array.isArray(spec.type) ? spec.type.join("|") : String(spec.type);
    }
    for (const unionKey of ["anyOf", "oneOf"]) {
        if (Array.isArray(spec?.[unionKey])) {
            return spec[unionKey]
                .map((s: any) => jsonSchemaType(typeof s === "object" && s !== null ? s : {}))
                .join("|");
        }
    }
    if (spec?.enum !== undefined) return "enum";
    return "any";
};

const argumentsFor = (tool: MCPToolResource): ToolArgument[] => {
    const schema = tool.input_schema ?? {};
    const properties = (schema.properties ?? {}) as Record<string, any>;
    const required = new Set<string>(schema.required ?? []);
    return Object.entries(properties).map(([name, rawSpec]) => {
        const spec = (typeof rawSpec === "object" && rawSpec !== null ? rawSpec : {}) as Record<string, any>;
        return {
            name,
            type: jsonSchemaType(spec),
            required: required.has(name),
            description: spec.description ? String(spec.description) : undefined,
        };
    });
};

const focusedArgs = computed<ToolArgument[]>(() =>
    viewState.value.view === 'focused' ? argumentsFor(viewState.value.tool) : []);

const renderedDescription = computed<string>(() => {
    if (viewState.value.view !== 'focused') return "";
    const description = viewState.value.tool.description;
    return description ? marked.parse(description) as string : "";
});

const viewTool = (tool: MCPToolResource) => {
    viewState.value = { view: 'focused', tool };
};

</script>

<style lang="scss">
.mcp-tools-panel {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding-right: 0.5rem;
    height: 100%;
}

.mcp-tools-header {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.mcp-tools-count {
    display: flex;
    flex-direction: column;
    padding: 0.25rem 0;
    width: 100%;
}

.mcp-tools-list {
    display: flex;
    flex-direction: column;
    overflow: auto;
    padding: 0.2rem;
    gap: 0.5rem;

    div.p-card .p-card-content { padding: 0; }
    div.p-card-body { padding: 0.75rem; }
    div.p-card .p-card-title { margin-bottom: 0; }
}

.mcp-tool-card-title {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;

    .mcp-tool-card-title-text {
        flex: 1 1;
        font-size: 0.95rem;
        font-weight: 500;
        font-family: monospace;
    }
}

.mcp-tool-arrow {
    transition: opacity 150ms linear;
}

.mcp-tool-card-desc {
    margin-top: 0.4rem;
    font-size: 0.85rem;
    color: var(--p-text-muted-color);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}

.mcp-tool-focused {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    height: 100%;
}

.mcp-tool-focused-header {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.75rem;

    .mcp-tool-focused-title {
        font-weight: 600;
        font-family: monospace;
        font-size: 0.95rem;
    }
}

.mcp-tool-focused-content {
    flex: 1 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
}

.mcp-tool-section-label {
    margin: 0 0 0.5rem 0;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--p-text-muted-color);
}

.mcp-tool-description {
    h1 { font-size: 1.2rem; margin-bottom: 0.8rem; }
    h2 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.1rem; margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.6rem; margin-top: 0; }
    code {
        background-color: var(--p-surface-100);
        padding: 0.1rem 0.35rem;
        border-radius: 4px;
    }
    > *:first-child { margin-top: 0; }
}

.mcp-tool-arg-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.mcp-tool-arg {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--p-surface-border);
    border-radius: 6px;
}

.mcp-tool-arg-signature {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;

    .mcp-tool-arg-name {
        font-family: monospace;
        font-weight: 600;
    }

    .mcp-tool-arg-type {
        font-family: monospace;
        font-size: 0.85rem;
        color: var(--p-primary-color);
    }

    .mcp-tool-arg-required {
        font-size: 0.7rem;
    }
}

.mcp-tool-arg-desc {
    font-size: 0.85rem;
    color: var(--p-text-muted-color);
}

.mcp-tools-placeholder {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
    color: var(--p-text-muted-color);
}

.mcp-tool-blank-note {
    color: var(--p-text-muted-color);
}
</style>
