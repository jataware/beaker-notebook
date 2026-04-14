<template>
    <div class="integrations-panel">
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
                style="
                    display: flex;
                    flex-direction: column;
                    padding-top: 0.25rem;
                    padding-bottom: 0.25rem;
                    gap: 0.5rem;
                    width: 100%;
            ">
                <RouterLink
                    :to="`/integrations?selected=new${sessionIdParam}`"
                    aria-label="Edit {{ integration?.name }} "
                >
                    <Button
                        style="height: 32px"
                        icon="pi pi-plus"
                        label="New Integration"
                    />
                </RouterLink>
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
                                <span class="integration-card-title-text">
                                    {{ integration?.name }}
                                </span>

                                <span v-if="expandedIntegration === integration.uuid">
                                    <RouterLink
                                        :to="`/integrations?selected=${integration?.uuid}${sessionIdParam}`"
                                        :aria-label="(getIntegrationProviderType(integration) === 'adhoc' ? 'Edit' : 'View') + ' ' + integration?.name"
                                    >
                                        <Button
                                            v-if="getIntegrationProviderType(integration) === 'adhoc'"
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
import { type IntegrationMap, type Integration, type IntegrationProviders, listIntegrations, getIntegrationProviderType } from "@/util/integration";
import { RouterLink } from "vue-router";
import { read } from "fs";

const searchText = ref(undefined);

interface PropTypes {
    readOnly: boolean;
}

const props = withDefaults(defineProps<PropTypes>(), {
    readOnly: false,
});

const integrations = defineModel<IntegrationMap>()

const urlParams = new URLSearchParams(window.location.search);
const sessionIdParam = urlParams.has("session") ? `&session=${urlParams.get("session")}` : "";

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

const sortIntegrations = (integrations: Integration[]) =>
    integrations.toSorted((a, b) => a?.name.localeCompare(b?.name))

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
    .integration-show-more {
        aspect-ratio: 1/1;
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
