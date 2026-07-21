<template>
    <div class="skill-resource-panel">
        <!-- List view -->
        <template v-if="viewState.view === 'list'">
            <div class="skill-resource-header">
                <i>{{ allResources.length }} resource{{ allResources.length === 1 ? '' : 's' }}</i>
                <div v-if="editable" class="skill-resource-add-buttons">
                    <Button icon="pi pi-plus" label="File" size="small" text @click="startNew('skill_file')" v-tooltip.bottom="'Add a reference/script/asset file'" />
                    <Button icon="pi pi-plus" label="Example" size="small" text @click="startNew('skill_example')" v-tooltip.bottom="'Add a code example'" />
                </div>
            </div>

            <p v-if="disabled && !isContext" class="skill-resource-hint">
                <i class="pi pi-info-circle"></i>
                <span>Save the skill before adding resources.</span>
            </p>
            <p v-else-if="!editable && !disabled" class="skill-resource-hint">
                <i class="pi pi-info-circle"></i>
                <span>This skill's resources are read-only.</span>
            </p>

            <div v-if="pendingResources.length" class="skill-resource-pending">
                <i class="skill-resource-pending-title">
                    {{ pendingResources.length }} file{{ pendingResources.length === 1 ? '' : 's' }} to import on save:
                </i>
                <div
                    class="skill-resource-card"
                    v-for="(resource, index) in pendingResources"
                    :key="`pending-${index}`"
                >
                    <Card>
                        <template #title>
                            <div class="skill-resource-card-title">
                                <i :class="resource.resource_type === 'skill_example' ? 'pi pi-code' : 'pi pi-file'"></i>
                                <span class="skill-resource-card-label">{{ pendingLabel(resource) }}</span>
                                <span class="skill-resource-pending-badge">pending</span>
                            </div>
                        </template>
                    </Card>
                </div>
            </div>

            <div class="skill-resource-list">
                <div
                    class="skill-resource-card"
                    v-for="resource in allResources"
                    :key="resource.resource_id"
                    @mouseenter="hoveredResource = resource.resource_id"
                    @mouseleave="hoveredResource = undefined"
                >
                    <Card
                        @click="openResource(resource)"
                        :pt="{ root: { style: 'transition: background-color 150ms linear;' + (hoveredResource === resource.resource_id ? 'background-color: var(--p-surface-100); cursor: pointer;' : '') } }"
                    >
                        <template #title>
                            <div class="skill-resource-card-title">
                                <i :class="resourceIcon(resource)"></i>
                                <span class="skill-resource-card-label">{{ resourceLabel(resource) }}</span>
                                <Button
                                    v-if="editable"
                                    icon="pi pi-trash"
                                    severity="danger"
                                    text
                                    size="small"
                                    @click.stop="removeResource(resource)"
                                    v-tooltip.left="'Delete'"
                                />
                                <i v-else class="pi pi-chevron-right skill-resource-arrow" :style="hoveredResource === resource.resource_id ? 'opacity: 1;' : 'opacity: 0;'" />
                            </div>
                        </template>
                    </Card>
                </div>
                <div v-if="allResources.length === 0 && pendingResources.length === 0" class="skill-resource-empty">
                    <i>No resource files yet.</i>
                </div>
            </div>
        </template>

        <!-- Focused / new view -->
        <template v-else>
            <div class="skill-resource-focused-header">
                <Button severity="secondary" icon="pi pi-arrow-left" label="Back" size="small" @click="backToList" style="width: fit-content;" />
                <span class="skill-resource-focused-title">{{ focusedLabel }}</span>
            </div>

            <div class="skill-resource-focused-form" v-if="viewState.view === 'new'">
                <div class="skill-resource-path-fields" v-if="viewState.resourceType === 'skill_file'">
                    <Select v-model="draftDir" :options="resourceDirs" placeholder="Directory" />
                    <InputText v-model="draftFilename" placeholder="filename.md" style="font-family: monospace; flex: 1 1 auto;" />
                </div>
                <div class="skill-resource-path-fields" v-else>
                    <span class="skill-resource-fixed-prefix">examples/</span>
                    <InputText v-model="draftFilename" placeholder="example.md" style="font-family: monospace; flex: 1 1 auto;" />
                </div>
            </div>

            <div class="skill-resource-focused-content">
                <div v-if="loadingContent" class="skill-resource-loading">
                    <ProgressSpinner style="width: 2rem; height: 2rem;" />
                    Loading resource...
                </div>
                <CodeEditor
                    v-else
                    :language="focusedLanguage"
                    :autocomplete-enabled="false"
                    :model-value="draftContent"
                    :disabled="!editable"
                    @update:model-value="(v) => { draftContent = v ?? ''; }"
                />
            </div>

            <div class="skill-resource-focused-actions" v-if="editable">
                <Button icon="pi pi-save" label="Save" severity="success" size="small" :disabled="!canSave" @click="saveFocused" />
            </div>
        </template>
    </div>
</template>


<script setup lang="ts">

import { ref, computed } from 'vue';
import Button from "primevue/button";
import Card from 'primevue/card';
import Select from "primevue/select";
import InputText from "primevue/inputtext";
import ProgressSpinner from 'primevue/progressspinner';
import CodeEditor from '../misc/CodeEditor.vue';
import {
    type IntegrationInterfaceState,
    type IntegrationResource,
    type SkillFileResource,
    type SkillExampleResource,
    isContextProvidedIntegration,
    getResource,
} from '../../util/integration';

const props = defineProps<{
    sessionId: string;
    disabled?: boolean;
    deleteResource: (resourceId: string) => Promise<void>,
    modifyResource: (body: object, resourceId?: string) => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const resourceDirs = ["references", "scripts", "assets"];

type ViewState =
    | { view: "list" }
    | { view: "focused"; resourceId: string }
    | { view: "new"; resourceType: "skill_file" | "skill_example" };

const viewState = ref<ViewState>({ view: 'list' });
const hoveredResource = ref<string | undefined>(undefined);
const loadingContent = ref<boolean>(false);

// Draft state for the focused editor (both new and existing resources).
const draftDir = ref<string>("references");
const draftFilename = ref<string>("");
const draftContent = ref<string>("");

const selectedIntegration = computed(() => model.value.integrations[model.value.selected]);

const isContext = computed<boolean>(() => isContextProvidedIntegration(selectedIntegration.value));

const editable = computed<boolean>(() =>
    (selectedIntegration.value as any)?.source_type === 'local'
    && !isContext.value
    && !props.disabled);

const allResources = computed<IntegrationResource[]>(() => {
    const resources = selectedIntegration.value?.resources ?? {};
    return Object.values(resources).filter(
        (r) => r.resource_type === 'skill_file' || r.resource_type === 'skill_example');
});

// Resources enumerated from an uploaded archive, shown read-only until the new
// skill is saved (at which point they are created and appear in allResources).
const pendingResources = computed<any[]>(() =>
    (selectedIntegration.value as any)?.pendingResources ?? []);

const pendingLabel = (resource: any): string =>
    resource.resource_type === 'skill_example'
        ? `examples/${resource.filename}`
        : resource.relative_path;

const resourceLabel = (resource: IntegrationResource): string => {
    if (resource.resource_type === 'skill_file') {
        return (resource as SkillFileResource).relative_path;
    }
    if (resource.resource_type === 'skill_example') {
        return `examples/${(resource as SkillExampleResource).filename}`;
    }
    return resource.resource_id;
};

const resourceIcon = (resource: IntegrationResource): string =>
    resource.resource_type === 'skill_example' ? 'pi pi-code' : 'pi pi-file';

const languageForPath = (path: string): string => {
    if (path.endsWith('.py')) return 'python';
    if (path.endsWith('.js') || path.endsWith('.ts')) return 'javascript';
    if (path.endsWith('.sh') || path.endsWith('.bash')) return 'shell';
    if (path.endsWith('.json')) return 'json';
    if (path.endsWith('.yaml') || path.endsWith('.yml')) return 'yaml';
    return 'markdown';
};

const focusedResource = computed<IntegrationResource | undefined>(() => {
    if (viewState.value.view !== 'focused') return undefined;
    return selectedIntegration.value?.resources?.[viewState.value.resourceId];
});

const focusedLabel = computed<string>(() => {
    if (viewState.value.view === 'new') {
        return viewState.value.resourceType === 'skill_file' ? 'New file' : 'New example';
    }
    return focusedResource.value ? resourceLabel(focusedResource.value) : '';
});

const focusedLanguage = computed<string>(() => {
    if (viewState.value.view === 'new') {
        return viewState.value.resourceType === 'skill_file'
            ? languageForPath(draftFilename.value)
            : 'markdown';
    }
    return focusedResource.value ? languageForPath(resourceLabel(focusedResource.value)) : 'markdown';
});

const canSave = computed<boolean>(() => {
    if (viewState.value.view === 'new') {
        return draftFilename.value.trim() !== "";
    }
    return true;
});

const backToList = () => {
    viewState.value = { view: 'list' };
    draftFilename.value = "";
    draftContent.value = "";
    draftDir.value = "references";
};

const startNew = (resourceType: "skill_file" | "skill_example") => {
    draftFilename.value = "";
    draftContent.value = "";
    draftDir.value = "references";
    viewState.value = { view: 'new', resourceType };
};

const openResource = async (resource: IntegrationResource) => {
    viewState.value = { view: 'focused', resourceId: resource.resource_id };
    const cached = (resource as SkillFileResource | SkillExampleResource).content;
    if (cached !== undefined && cached !== null) {
        draftContent.value = cached;
        return;
    }
    draftContent.value = "";
    loadingContent.value = true;
    try {
        const fetched = await getResource(props.sessionId, model.value.selected, resource.resource_type, resource.resource_id);
        const content = (fetched as any).content ?? "";
        (resource as any).content = content;
        draftContent.value = content;
    } catch (e) {
        console.error('Failed to load resource content:', e);
    } finally {
        loadingContent.value = false;
    }
};

const saveFocused = async () => {
    if (viewState.value.view === 'new') {
        const filename = draftFilename.value.trim();
        if (!filename) return;
        const body = viewState.value.resourceType === 'skill_file'
            ? {
                resource_type: 'skill_file',
                relative_path: `${draftDir.value}/${filename}`,
                name: filename,
                content: draftContent.value,
            }
            : {
                resource_type: 'skill_example',
                filename,
                content: draftContent.value,
            };
        await props.modifyResource(body);
    } else if (viewState.value.view === 'focused' && focusedResource.value) {
        await props.modifyResource(
            { ...focusedResource.value, content: draftContent.value },
            focusedResource.value.resource_id,
        );
    }
    backToList();
};

const removeResource = async (resource: IntegrationResource) => {
    if (!confirm(`Delete ${resourceLabel(resource)}?`)) return;
    await props.deleteResource(resource.resource_id);
    delete selectedIntegration.value.resources[resource.resource_id];
};

</script>

<style lang="scss">
.skill-resource-panel {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding-right: 0.5rem;
    height: 100%;
}

.skill-resource-header {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
}

.skill-resource-add-buttons {
    display: flex;
    gap: 0.25rem;
}

.skill-resource-hint {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--p-text-muted-color);
    margin: 0;
}

.skill-resource-list {
    display: flex;
    flex-direction: column;
    overflow: auto;
    padding: 0.2rem;

    div.p-card .p-card-content { padding: 0; }
    div.p-card-body { padding: 0.6rem; }
    div.p-card .p-card-title { margin-bottom: 0; }

    .skill-resource-card > div { margin-bottom: 0.5rem; }
}

.skill-resource-card-title {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;

    .skill-resource-card-label {
        flex: 1 1;
        font-size: 0.9rem;
        font-weight: 500;
        font-family: monospace;
        word-break: break-all;
    }
}

.skill-resource-arrow {
    transition: opacity 150ms linear;
}

.skill-resource-empty {
    padding: 1rem 0.2rem;
    color: var(--p-text-muted-color);
}

.skill-resource-pending {
    display: flex;
    flex-direction: column;
    padding: 0.2rem;

    .skill-resource-pending-title {
        color: var(--p-text-muted-color);
        margin-bottom: 0.25rem;
    }

    .skill-resource-card > div {
        margin-bottom: 0.5rem;
    }

    div.p-card .p-card-content { padding: 0; }
    div.p-card-body { padding: 0.6rem; }
    div.p-card .p-card-title { margin-bottom: 0; }
}

.skill-resource-pending-badge {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    background: var(--p-surface-200);
    color: var(--p-text-muted-color);
    flex-shrink: 0;
}

.skill-resource-focused-header {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.75rem;

    .skill-resource-focused-title {
        font-weight: 600;
        font-family: monospace;
        font-size: 0.9rem;
        word-break: break-all;
    }
}

.skill-resource-path-fields {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.35rem;

    .skill-resource-fixed-prefix {
        font-family: monospace;
        color: var(--p-text-muted-color);
    }
}

.skill-resource-focused-content {
    flex: 1 1;
    overflow: auto;
    min-height: 16rem;
    display: flex;
    flex-direction: column;
}

.skill-resource-focused-actions {
    display: flex;
    justify-content: flex-end;
}

.skill-resource-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 2rem;
    color: var(--p-text-muted-color);
}
</style>
