<template>
    <div class="resource-viewer">
        <div
            class="header-controls"
            v-if="viewState.view === 'list'"
        >
            <InputGroup>
                <InputGroupAddon>
                    <i class="pi pi-search"></i>
                </InputGroupAddon>
                <InputText placeholder="Search Resources..." v-model="searchText" />
                <Button
                    v-if="searchText"
                    icon="pi pi-times"
                    severity="danger"
                    @click="searchText = undefined"
                    v-tooltip.left="'Clear Search'"
                />
            </InputGroup>
            <div style="display: flex; flex-direction: column; padding: 0.25rem 0; gap: 0.5rem; width: 100%;">
                <i>{{ allResources.length }} resources available:</i>
            </div>
        </div>

        <div
            class="resource-list"
            v-if="viewState.view === 'list'"
        >
            <div
                class="resource-card"
                v-for="resource in filteredResources"
                :key="resource.resource_id"
                @mouseleave="hoveredResource = undefined"
                @mouseenter="hoveredResource = resource.resource_id"
            >
                <Card
                    @click="viewResource(resource)"
                    :pt="{
                        root: {
                            style:
                                'transition: background-color 150ms linear;' +
                                (hoveredResource === resource.resource_id
                                    ? 'background-color: var(--p-surface-100); cursor: pointer;'
                                    : '')
                        }
                    }"
                >
                    <template #title>
                        <div class="resource-card-title">
                            <i :class="resourceIcon(resource)"></i>
                            <span class="resource-card-title-text">
                                {{ resourceLabel(resource) }}
                            </span>
                            <i
                                class="pi pi-chevron-right resource-arrow"
                                :style="hoveredResource === resource.resource_id ? 'opacity: 1;' : 'opacity: 0;'"
                            />
                        </div>
                    </template>
                </Card>
            </div>
        </div>

        <div
            class="resource-focused"
            v-else-if="viewState.view === 'focused'"
        >
            <div class="resource-focused-header">
                <Button
                    severity="secondary"
                    icon="pi pi-arrow-left"
                    @click="viewState = { view: 'list' }"
                    label="Back"
                    style="width: fit-content;"
                />
                <span class="resource-focused-title">{{ viewState.label }}</span>
            </div>
            <div class="resource-focused-content">
                <div v-if="loadingContent" class="resource-loading">
                    <ProgressSpinner style="width: 2rem; height: 2rem;" />
                    Loading resource...
                </div>
                <CodeEditor
                    v-else-if="viewState.content !== undefined"
                    :language="viewState.language"
                    :autocomplete-enabled="false"
                    :model-value="viewState.content"
                    disabled
                />
                <div v-else class="resource-no-content">
                    <i>Failed to load resource content.</i>
                </div>
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">

import { ref, computed } from 'vue';
import Button from "primevue/button";
import Card from 'primevue/card';
import InputGroup from "primevue/inputgroup";
import InputGroupAddon from "primevue/inputgroupaddon";
import InputText from "primevue/inputtext";
import ProgressSpinner from 'primevue/progressspinner';
import CodeEditor from '../misc/CodeEditor.vue';
import {
    type IntegrationInterfaceState,
    type IntegrationResource,
    type SkillInstructionsResource,
    type SkillFileResource,
    type SkillExampleResource,
    getResource,
} from '../../util/integration';

const props = defineProps<{
    sessionId: string;
}>();

type ViewState =
    | { view: "list" }
    | { view: "focused"; resourceId: string; label: string; content: string | undefined; language: string };

const model = defineModel<IntegrationInterfaceState>();

const viewState = ref<ViewState>({ view: 'list' });
const searchText = ref<string | undefined>(undefined);
const hoveredResource = ref<string | undefined>(undefined);
const loadingContent = ref<boolean>(false);

const allResources = computed<IntegrationResource[]>(() => {
    const resources = model.value.integrations[model.value.selected]?.resources ?? {};
    console.log({resources});
    return Object.values(resources).filter(r => {
        console.log(r)
        return r.resource_type === 'skill_instructions' || r.resource_type === 'skill_file' || r.resource_type === 'skill_example';
    }
    );
});

const filteredResources = computed<IntegrationResource[]>(() => {
    if (!searchText.value) return allResources.value;
    const term = searchText.value.toLowerCase();
    return allResources.value.filter(r => resourceLabel(r).toLowerCase().includes(term));
});

const resourceLabel = (resource: IntegrationResource): string => {
    if (resource.resource_type === 'skill_instructions') {
        return 'Skill Instructions (SKILL.md)';
    }
    if (resource.resource_type === 'skill_file') {
        return (resource as SkillFileResource).relative_path;
    }
    if (resource.resource_type === 'skill_example') {
        const ex = resource as SkillExampleResource;
        return `examples/${ex.filename}`;
    }
    return resource.resource_id;
};

const resourceIcon = (resource: IntegrationResource): string => {
    if (resource.resource_type === 'skill_instructions') {
        return 'pi pi-book';
    }
    if (resource.resource_type === 'skill_file') {
        return 'pi pi-file';
    }
    if (resource.resource_type === 'skill_example') {
        return 'pi pi-code';
    }
    return 'pi pi-box';
};

const languageForPath = (path: string): string => {
    if (path.endsWith('.py')) return 'python';
    if (path.endsWith('.js') || path.endsWith('.ts')) return 'javascript';
    if (path.endsWith('.sh') || path.endsWith('.bash')) return 'shell';
    if (path.endsWith('.json')) return 'json';
    if (path.endsWith('.yaml') || path.endsWith('.yml')) return 'yaml';
    return 'markdown';
};

const viewResource = async (resource: IntegrationResource) => {
    const integrationId = model.value.selected;

    if (resource.resource_type === 'skill_instructions') {
        const instr = resource as SkillInstructionsResource;
        viewState.value = {
            view: 'focused',
            resourceId: resource.resource_id,
            label: 'Skill Instructions',
            content: instr.content,
            language: 'markdown',
        };
    } else if (resource.resource_type === 'skill_file' || resource.resource_type === 'skill_example') {
        const res = resource as SkillFileResource | SkillExampleResource;
        const label = resource.resource_type === 'skill_file'
            ? (res as SkillFileResource).relative_path
            : `examples/${(res as SkillExampleResource).filename}`;
        const language = languageForPath(label);

        // If content already cached, show immediately
        if (res.content) {
            viewState.value = {
                view: 'focused',
                resourceId: resource.resource_id,
                label,
                content: res.content,
                language,
            };
            return;
        }

        // Fetch content on demand
        viewState.value = { view: 'focused', resourceId: resource.resource_id, label, content: undefined, language };
        loadingContent.value = true;
        try {
            const fetched = await getResource(props.sessionId, integrationId, resource.resource_type, resource.resource_id);
            const fetchedContent = (fetched as any).content;
            // Cache on the resource object in the shared state
            res.content = fetchedContent;
            viewState.value = { ...viewState.value, content: fetchedContent ?? undefined } as ViewState;
        } catch (e) {
            console.error('Failed to load resource content:', e);
        } finally {
            loadingContent.value = false;
        }
    }
};

</script>

<style lang="scss">
.resource-viewer {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding-right: 0.5rem;
}

.header-controls {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.resource-list {
    display: flex;
    flex-direction: column;
    overflow: auto;
    padding: 0.2rem;

    div.p-card .p-card-content { padding: 0; }
    div.p-card-body { padding: 0.75rem; }
    div.p-card .p-card-title { margin-bottom: 0; }

    .resource-card > div { margin-bottom: 0.5rem; }
}

.resource-card-title {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;

    .resource-card-title-text {
        flex: 1 1;
        font-size: 0.95rem;
        font-weight: 500;
        font-family: monospace;
    }
}

.resource-arrow {
    transition: opacity 150ms linear;
}

.resource-focused {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    height: 100%;
}

.resource-focused-header {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.75rem;

    .resource-focused-title {
        font-weight: 600;
        font-family: monospace;
        font-size: 0.95rem;
    }
}

.resource-focused-content {
    flex: 1 1;
    overflow: auto;
}

.resource-no-content {
    padding: 1rem;
    color: var(--p-text-muted-color);
}
</style>
