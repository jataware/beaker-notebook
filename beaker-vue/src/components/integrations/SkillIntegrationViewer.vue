<template>
    <div class="skill-integration-viewer">
        <div class="skill-viewer-content">
            <Fieldset legend="Name">
                <InputText
                    :model-value="selectedIntegration?.name"
                    disabled
                />
            </Fieldset>

            <Fieldset legend="Description">
                <div class="skill-description" v-html="renderedDescription"></div>
            </Fieldset>

            <Fieldset legend="Metadata" v-if="metadata">
                <div class="skill-metadata-grid">
                    <div class="skill-metadata-row" v-if="metadata.license">
                        <span class="skill-metadata-label">License</span>
                        <span class="skill-metadata-value">{{ metadata.license }}</span>
                    </div>
                    <div class="skill-metadata-row" v-if="metadata.compatibility">
                        <span class="skill-metadata-label">Compatibility</span>
                        <span class="skill-metadata-value">{{ metadata.compatibility }}</span>
                    </div>
                    <div class="skill-metadata-row" v-if="metadata.allowed_tools">
                        <span class="skill-metadata-label">Allowed Tools</span>
                        <span class="skill-metadata-value" style="font-family: monospace;">{{ metadata.allowed_tools }}</span>
                    </div>
                    <template v-for="(value, key) in (metadata.skill_metadata ?? {})" :key="key">
                        <div class="skill-metadata-row">
                            <span class="skill-metadata-label">{{ key }}</span>
                            <span class="skill-metadata-value">{{ value }}</span>
                        </div>
                    </template>
                </div>
                <div v-if="!hasMetadata" class="skill-no-metadata">
                    <i>No metadata available for this skill.</i>
                </div>
            </Fieldset>

            <Fieldset legend="Available Resources" v-if="fileResources.length > 0">
                <p>
                    These resources are available to the agent and will be loaded on demand when the skill is active.
                </p>
                <div class="skill-resource-list">
                    <div
                        class="skill-resource-item"
                        v-for="resource in fileResources"
                        :key="resource.resource_id"
                    >
                        <i class="pi pi-file"></i>
                        <span class="skill-resource-path">{{ resource.relative_path }}</span>
                    </div>
                </div>
            </Fieldset>

            <Fieldset legend="Code Examples" v-if="exampleResources.length > 0">
                <p>
                    Code examples demonstrating usage patterns for this skill.
                </p>
                <div class="skill-resource-list">
                    <div
                        class="skill-resource-item"
                        v-for="example in exampleResources"
                        :key="example.resource_id"
                    >
                        <i class="pi pi-code"></i>
                        <div class="skill-example-info">
                            <span class="skill-resource-path">{{ example.filename }}</span>
                            <span class="skill-example-title">{{ example.title }}</span>
                        </div>
                    </div>
                </div>
            </Fieldset>
        </div>
    </div>
</template>


<script setup lang="ts">

import { computed } from 'vue';
import {
    type Integration,
    type IntegrationInterfaceState,
    type IntegrationResource,
    type SkillMetadataResource,
    type SkillFileResource,
    type SkillExampleResource,
    filterByResourceType,
} from '../../util/integration';

import Fieldset from 'primevue/fieldset';
import InputText from 'primevue/inputtext';

import { marked } from 'marked';

const props = defineProps<{
    fetchResources: () => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const selectedIntegration = computed<Integration>(() =>
    model.value.integrations[model.value.selected]);

const renderedDescription = computed<string>(() =>
    marked.parse(selectedIntegration.value?.description ?? "") as string);

const metadata = computed<SkillMetadataResource | undefined>(() => {
    const resources = filterByResourceType<SkillMetadataResource>(
        selectedIntegration.value?.resources, "skill_metadata");
    return Object.values(resources)[0];
});

const hasMetadata = computed<boolean>(() => {
    if (!metadata.value) return false;
    return !!(metadata.value.license
        || metadata.value.compatibility
        || metadata.value.allowed_tools
        || Object.keys(metadata.value.skill_metadata ?? {}).length > 0);
});

const fileResources = computed<SkillFileResource[]>(() => {
    const resources = filterByResourceType<SkillFileResource>(
        selectedIntegration.value?.resources, "skill_file");
    return Object.values(resources);
});

const exampleResources = computed<SkillExampleResource[]>(() => {
    const resources = filterByResourceType<SkillExampleResource>(
        selectedIntegration.value?.resources, "skill_example");
    return Object.values(resources);
});

</script>

<style lang="scss">
.skill-integration-viewer {
    display: flex;
    flex-direction: column;
    height: 100%;

    .skill-viewer-content {
        overflow: auto;
        display: flex;
        flex-direction: column;
    }
}

.skill-description {
    h1 { font-size: 1.25rem; margin-bottom: 1rem; }
    h2 { font-size: 1.2rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.8rem; margin-top: 0rem; }
    > *:first-child { margin-top: 0rem; }
}

.skill-metadata-grid {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.skill-metadata-row {
    display: flex;
    flex-direction: row;
    gap: 1rem;
    align-items: baseline;

    .skill-metadata-label {
        font-weight: 600;
        min-width: 8rem;
        flex-shrink: 0;
    }

    .skill-metadata-value {
        flex: 1;
    }
}

.skill-no-metadata {
    color: var(--p-text-muted-color);
}

.skill-resource-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.skill-resource-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;

    &:hover {
        background-color: var(--p-surface-100);
    }
}

.skill-resource-path {
    font-family: monospace;
}

.skill-example-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.skill-example-title {
    font-size: 0.85rem;
    color: var(--p-text-muted-color);
}
</style>
