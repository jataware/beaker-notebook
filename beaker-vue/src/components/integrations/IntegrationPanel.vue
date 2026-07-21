<template>
    <div
        class="integrations-panel"
        :class="{ 'drag-over': isDragOver }"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop.prevent="onDrop"
    >
        <div class="integration-header">
            <InputGroup>
                <InputGroupAddon>
                    <i class="pi pi-search"></i>
                </InputGroupAddon>
                <InputText placeholder="Search Integrations..." v-model="searchText">
                </InputText>
                <Button
                    v-if="searchText !== undefined && searchText !== ''"
                    icon="pi pi-times"
                    severity="danger"
                    @click="() => {searchText = undefined}"
                    v-tooltip="'Clear Search'"
                />
            </InputGroup>
            <div
                v-if="!readOnly"
                class="integration-actions"
                style="
                    padding-top: 0.25rem;
                    width: 100%;
            ">
                <RouterLink
                    :to="(route.name == 'integrations' ? `/?session=${sessionId}` : `/integrations?session=${sessionId}`)"
                >
                    <Button
                        :label="(route.name == 'integrations' ? 'Back to session' : 'Manage Integrations') "
                    />
                </RouterLink>
                <span style="flex: 1"></span>
                <RouterLink
                    :to="`/integrations?selected=new${sessionIdParam}`"
                    aria-label="New Integration"
                >
                    <Button
                        icon="pi pi-plus"
                        label="New Integration"
                    />
                </RouterLink>
                <Button
                    icon="pi pi-upload"
                    label="Upload"
                    severity="secondary"
                    @click="triggerUpload"
                    v-tooltip.bottom="'Import a skill from a SKILL.md or .zip (or drop a file on this panel)'"
                />
                <input
                    ref="fileInputRef"
                    type="file"
                    accept=".zip,.md,text/markdown,application/zip"
                    style="display: none;"
                    @change="onFileSelected"
                />
            </div>
            <div
                style="
                    display: flex;
                    flex-direction: column;
                    padding-top: 0.25rem;
                    padding-bottom: 0.25rem;
                    gap: 0.5rem;
                    width: 100%;
            ">
                <div>
                    <i>{{ allIntegrations.length }} integrations available:</i>
                </div>
            </div>
        </div>
        <div class="integration-list">
            <div
                class="integration-provider"
            >
                <div
                    class="integration-card"
                    v-for="integration in processIntegrations(Object.values(integrations))"
                    :key="integration?.name"
                    @mouseleave="hoveredIntegration = undefined"
                    @mouseenter="hoveredIntegration = integration.uuid"
                >
                    <Card
                        :pt = "{
                            root: {
                                style:
                                    'transition: background-color 150ms linear;' +
                                    (hoveredIntegration === integration.uuid
                                        ? 'background-color: var(--p-surface-100); cursor: pointer;'
                                        : '')
                            }
                        }"
                        @click="expandedIntegration = (expandedIntegration === integration.uuid)
                            ? undefined
                            : integration.uuid;
                        "
                    >
                        <template #title>
                            <div class="integration-card-title">
                                <img
                                    v-if="getIntegrationIcon(integration)"
                                    class="integration-card-icon"
                                    :src="getIntegrationIcon(integration)"
                                    :alt="`${integration?.datatype ?? ''} icon`"
                                    v-tooltip.top="getIntegrationTypeLabel(integration)"
                                />
                                <span class="integration-card-title-text">
                                    {{ integration?.name }}
                                </span>

                                <span v-if="expandedIntegration === integration.uuid">
                                    <RouterLink
                                        :to="`/integrations?selected=${integration?.uuid}${sessionIdParam}`"
                                        :aria-label="(isEditableType(integration) ? 'Edit' : 'View') + ' ' + integration?.name"
                                    >
                                        <Button
                                            v-if="isEditableType(integration)"
                                            style="
                                                width: fit-content;
                                                height: 32px;
                                                margin-right: 0.5rem;
                                            "
                                            icon="pi pi-pencil"
                                            label="Edit"
                                        />
                                        <Button
                                            v-else
                                            style="
                                                width: fit-content;
                                                height: 32px;
                                                margin-right: 0.5rem;
                                            "
                                            icon="pi pi-eye"
                                            label="View"
                                            severity="secondary"
                                        />
                                    </RouterLink>
                                </span>
                            </div>
                        </template>
                        <template #content v-if="expandedIntegration === integration.uuid">
                            <div
                                class="integration-main-content"
                                style="overflow: hidden;"
                                v-html="integration.description"
                            >
                            </div>
                        </template>
                    </Card>
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch, inject } from "vue";
import Button from "primevue/button";
import InputGroup from "primevue/inputgroup";
import InputGroupAddon from "primevue/inputgroupaddon";
import InputText from "primevue/inputtext";
import Card from "primevue/card";
import { marked } from "marked";
import { type BeakerSessionComponentType } from "../session/BeakerSession.vue";
import { type IntegrationMap, type Integration, type IntegrationProviders, listIntegrations, getIntegrationProviderType, getIntegrationIcon, getIntegrationTypeLabel, isContextProvidedIntegration } from "@/util/integration";
import { useRoute, RouterLink } from "vue-router";
import { read } from "fs";

const route = useRoute();
const searchText = ref(undefined);

interface PropTypes {
    readOnly?: boolean;
}

const props = withDefaults(defineProps<PropTypes>(), {
    readOnly: false,
});

const emit = defineEmits<{
    (e: 'upload', file: File): void;
}>();

const integrations = defineModel<IntegrationMap>()

// --- Skill upload (button + drag-and-drop) ---
const fileInputRef = ref<HTMLInputElement>();
const isDragOver = ref(false);

const triggerUpload = () => fileInputRef.value?.click();

const onFileSelected = (event: Event) => {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
        emit('upload', file);
    }
    // Reset so selecting the same file again re-triggers change.
    input.value = '';
};

const onDragOver = () => {
    if (!props.readOnly) {
        isDragOver.value = true;
    }
};

const onDragLeave = () => {
    isDragOver.value = false;
};

const onDrop = (event: DragEvent) => {
    isDragOver.value = false;
    if (props.readOnly) {
        return;
    }
    const file = event.dataTransfer?.files?.[0];
    if (file) {
        emit('upload', file);
    }
};

const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.get("session") ?? "";
const sessionIdParam = sessionId ? `&session=${sessionId}` : "";


const sortIntegrations = (integrations: Integration[]) =>
    integrations.toSorted((a, b) => (a?.name ?? '').localeCompare(b?.name ?? ''))

const filterIntegrations = (integrations: Integration[]) =>
    integrations.filter(integration =>
        (searchText?.value === undefined)
        || integration?.name?.toLowerCase()?.includes(searchText?.value?.toLowerCase()))

const renderIntegrations = (integrations: Integration[]) =>
    integrations.map(integration =>
        ({...integration, description: marked.parse(integration?.description ?? "") as string}))

const processIntegrations = (integrations: Integration[]) =>
    renderIntegrations(filterIntegrations(sortIntegrations(integrations)))

// const relevantProviders = (providers: IntegrationProviders): IntegrationProviders =>
//     Object.keys(providers)
//         .filter((name) => processIntegrations(providers[name].integrations).length >= 1)
//         .reduce((result, key) => (result[key] = providers[key], result), {})

// Whether a card opens into an editor ("Edit") rather than a read-only viewer
// ("View"). MCP servers and skills are editable unless provided by a context
// (see isContextProvidedIntegration); every other type is view-only.
const isEditableType = (integration: Integration): boolean => {
    const type = getIntegrationProviderType(integration);
    if (type === 'mcp' || type === 'agent-skill') {
        return !isContextProvidedIntegration(integration);
    }
    return false;
};

const allIntegrations = computed<Integration[]>(() => Object.values(integrations.value))

const expandedIntegration = ref<string|undefined>(undefined);
const hoveredIntegration = ref<string|undefined>(undefined);

watch(searchText, () => {
    const filtered = filterIntegrations(allIntegrations.value);
    if (filtered.length === 1) {
        expandedIntegration.value = filtered[0].slug;
        return;
    }
    expandedIntegration.value = undefined;
})

</script>

<style lang="scss">
.integrations-panel {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding-left: 0.25rem;
    padding-right: 0.25rem;
    gap: 0.5rem;

    &.drag-over {
        outline: 2px dashed var(--p-primary-color);
        outline-offset: -4px;
        border-radius: 4px;
    }

    .integration-actions {
        display: flex;
        flex-direction: row;
        gap: 0.5rem;
        align-items: center;
    }
    div.p-card .p-card-content {
        padding: 0;
    }
    div.p-card .p-card-title {
        margin-bottom: 0;
    }
    div.p-card-body {
        padding: 0.75rem 0.75rem;
    }
}

.integration-header {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.integration-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    overflow: auto;
    padding: 0.2rem;
}

.integration-provider {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0rem;
}

.integration-card-title {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    .integration-show-more {
        aspect-ratio: 1/1;
    }
    .integration-card-icon {
        width: 1.25rem;
        height: 1.25rem;
        object-fit: contain;
        flex-shrink: 0;
    }
    .integration-card-title-text {
        flex: 1 1;
        font-size: 1rem;
        font-weight: 500;
        margin: auto;
    }
}

.clickable-table-of-contents {
    &:hover, *:hover { cursor: pointer; color: var(--p-surface-h) }
    &:active, *:active { cursor: pointer; color: var(--p-surface-i) }
    * { margin-right: 0.2rem; }
}

// for inner h1 being larger than header; rescale to make sensible whitespace
.integration-main-content {
    margin-top: 0.5rem;
    h1 { font-size: 1.25rem; margin-bottom: 1rem;   }
    h2 { font-size: 1.2rem;  margin-bottom: 0.8rem; }
    h3 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    h4 { font-size: 1.1rem;  margin-bottom: 0.8rem; }
    h5 { font-size: 1.05rem; margin-bottom: 0.8rem; }
    h6 { font-size: 1.0rem;  margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.8rem; margin-top: 0rem; }
    h1, h2, h3, h4, h5, h6 {
        margin-top: 0.25rem;
    }
    > *:nth-child(1) {
        margin-top: 0rem;
    }

}
</style>
