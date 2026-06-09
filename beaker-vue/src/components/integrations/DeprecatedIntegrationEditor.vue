<template>
    <div class="integration-editor">
        <div class="integration-loading" v-if="beakerSession.status === 'connecting'">
            <ProgressSpinner></ProgressSpinner>
            Loading integrations...
            {{beakerSession?.status}}
        </div>
        <div class="integration-main-content" v-else>
            <div class="integration-header">
                <Select :options="
                    sortedIntegrations.map(integration => ({
                        label: integration.name,
                        value: integration.uuid
                    }))"
                    :option-label="(option) => option?.label ?? 'Select integration...'"
                    option-value="value"
                    placeholder="Select a integration..."
                    @click="(event) => {
                        if (!confirmUnsavedChanges()) {
                            event.preventDefault;
                        } else {
                            model.unsavedChanges = false;
                        }
                    }"
                    v-model="model.selected">
                </Select>

                <Button
                    @click="() => {
                        if (confirmUnsavedChanges()) {
                            newIntegration();
                        }
                    }"
                    label="New Integration"
                />
            </div>

            <Fieldset legend="Name">
                <InputText
                    v-if="selectedIntegration"
                    ref="nameInput"
                    v-model="selectedIntegration.name"
                    :placeholder="selectedIntegration?.name ? 'Name' : 'No integration selected.'"
                    @change="model.unsavedChanges = true;"
                />
                <InputText
                    v-else
                    disabled
                    placeholder="No integration selected."
                />
            </Fieldset>

            <Fieldset legend="Description">
                <p>
                    The description, used by both users and the agent, provides a brief summary of the purpose of this
                    integration. The agent will use this to select which integration best matches a user's request.
                </p>
                <div class="constrained-editor-height">
                    <CodeEditor
                        v-if="selectedIntegration"
                        language="markdown"
                        :autocomplete-enabled="false"
                        v-model="selectedIntegration.description"
                        @change="model.unsavedChanges = true"
                        ref="descriptionEditor"
                    />
                    <CodeEditor
                        v-else
                        language="markdown"
                        :autocompleteEnabled="false"
                        disabled
                        v-model="emptyText"
                        placeholder="No integration selected."
                    />
                </div>
            </Fieldset>

            <Fieldset legend="User Files">
                <p>
                    Uploaded files will be used by the agent in one of two ways: either included in the instruction body,
                    or when running code based on a user's request. For included documentation, these files should
                    be included in the body and will be used in determining what steps to take for the user's request.
                    For large datasets, these are used once the agent is executing a request.
                </p>
                <form ref="uploadForm">
                    <input
                        @change="onSelectFileForUpload"
                        ref="fileInput"
                        type="file"
                        style="display:none;"
                        name="uploadfiles"
                    />
                    <input
                        type="hidden"
                        name="_xsrf"
                        :value="xsrfCookie"
                    />
                </form>
                <form ref="uploadFormMultiple">
                    <input
                        @change="onSelectFilesForUpload"
                        ref="fileInputMultiple"
                        type="file"
                        style="display:none;"
                        name="uploadfilesMultiple"
                        multiple
                    />
                    <input
                        type="hidden"
                        name="_xsrf"
                        :value="xsrfCookie"
                    />
                </form>
                <Toolbar v-for="file, id in attachedFiles" :key="file?.filepath">
                    <template #start>
                        <Button
                            icon="pi pi-download"
                            v-tooltip="'Download'"
                            style="width: 32px; height: 32px"
                            @click="downloadFile(id)"
                        />
                    </template>
                    <template #center>
                        <InputText v-model="file.name" type="text"></InputText>
                    </template>
                    <template #end>
                        <Button
                            icon="pi pi-trash"
                            severity="danger"
                            style="width: 32px; height: 32px"
                            @click="removeFile(id)"
                            v-tooltip="'Remove File'"
                        />
                    </template>
                </Toolbar>
                <Toolbar v-for="file, index in uncommittedNewFileUploads" :key="file?.filepath">
                    <template #start>
                        <span>Pending Upload</span>
                    </template>
                    <template #center>
                        <InputText v-model="file.name" type="text"></InputText>
                    </template>
                    <template #end>
                        <Button
                            icon="pi pi-trash"
                            severity="danger"
                            style="width: 32px; height: 32px"
                            @click="uncommittedNewFileUploads.splice(index, 1)"
                            v-tooltip="'Remove File'"
                        />
                    </template>
                </Toolbar>
                <Button
                    @click="openFileSelectionMultiple"
                    style="width: fit-content; height: 32px;"
                    label="Add New Files"
                    icon="pi pi-plus"
                    :disabled="!selectedIntegration"
                />
            </Fieldset>

            <div
                style="display: flex;
                flex-direction: column;
                gap: 0.5rem"
                v-if="unincludedFiles.length > 0"
            >
                <Tag
                    icon="pi pi-exclamation-triangle"
                    severity="warning"
                    size="large"
                >
                    Some files are not included: {{ unincludedFiles.join(', ') }}; see the above documentation about how to reference these files.
                </Tag>
            </div>

            <Fieldset legend="Agent Instructions">
                <p>
                    Agent instructions will be given to the agent when it creates a plan to execute a user's request.
                </p>
                <span style="margin-bottom: 1rem">
                    Files uploaded above can be referenced in the below agent instructions with
                    <span style="font-family: monospace;">{filename}</span>,
                    such as if you uploaded a file named
                    <span style="font-family: monospace;">documentation.txt</span>
                    and it shows above with the name
                    <span style="font-family: monospace;">documentation</span>,
                    adding
                    <span style="font-family: monospace;">{documentation}</span> to the body below will ensure the agent
                    can read your uploaded file.
                </span>
                <div class="constrained-editor-height">
                    <CodeEditor
                        v-if="selectedIntegration"
                        language="markdown"
                        :autocompleteEnabled="true"
                        :autocomplete-options="Object.values(attachedFiles).map((file: IntegrationAttachedFile) => file.name)"
                        v-model="selectedIntegration.source"
                        @change="model.unsavedChanges = true"
                        ref="instructionEditor"
                    />
                    <CodeEditor
                        v-else
                        language="markdown"
                        :autocompleteEnabled="false"
                        disabled
                        v-model="emptyText"
                        placeholder="No integration selected."
                    />
                </div>
            </Fieldset>
        </div>
        <div style="flex: 1 0; margin: 0.2rem; display: flex; justify-content: flex-end;">
            <div v-if="model.unsavedChanges" style="flex-shrink: 0;">
                <Button
                    @click="save"
                    :disabled="!selectedIntegration"
                    icon="pi pi-save"
                    label="Save Changes"
                    severity="success"
                />
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">

import { ref, watch, computed, inject } from 'vue';
import { type IntegrationMap, type Integration, getIntegrationProviderType, type IntegrationAttachedFile, type IntegrationInterfaceState, filterByResourceType } from '../../util/integration';
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';

import Select from 'primevue/select';
import Fieldset from 'primevue/fieldset';
import Button from "primevue/button";
import Toolbar from 'primevue/toolbar';
import InputText from 'primevue/inputtext';
import ProgressSpinner from 'primevue/progressspinner';
import Tag from 'primevue/tag';

import * as cookie from 'cookie';

import CodeEditor from '../misc/CodeEditor.vue';

const showToast = inject<any>('show_toast');

// these are props rather than events due to awaiting async finishes;
// file uploads need to be done before the integration is changed.
const props = defineProps<{
    fetchResources: () => Promise<void>,
    deleteResource: (resourceId: string) => Promise<void>,
    modifyResource: (body: object, resourceId?: string) => Promise<void>,
    modifyIntegration: (body: object, integrationId?: string) => Promise<void>,
    /** Current value of the URL's "selected" query parameter; the page
     *  is responsible for sourcing this (typically via useRoute()) and
     *  passing it down. */
    selectedQuery?: string | null,
}>();

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

const model = defineModel<IntegrationInterfaceState>()

const sortIntegrations = (integrations: IntegrationMap): Integration[] =>
    Object.values(integrations).toSorted((a, b) => a?.name.localeCompare(b?.name))

const adhocIntegrations = computed<IntegrationMap>(() =>
    Object.fromEntries(Object.entries(model.value.integrations ?? {})
        .filter(([_name, integration]) => getIntegrationProviderType(integration) === "adhoc")))

const sortedIntegrations = computed<Integration[]>(() => sortIntegrations(adhocIntegrations.value))

const selectedIntegration = computed<Integration>(() => adhocIntegrations.value[model.value.selected])

const attachedFiles = computed<{[key in string]: IntegrationAttachedFile}>(() =>
    filterByResourceType<IntegrationAttachedFile>(
        model.value.integrations[model.value.selected]?.resources, "file")
    )

const nameInput = ref();

// storing deletes until save
const uncommittedDeletedResources = ref([]);
// storing new integration file uploads until pushed to
const uncommittedNewFileUploads = ref<IntegrationAttachedFile[]>([]);

const updateSelectedParam = () => {
    // keep URL in sync with focused integration after save
    const url = new URL(window.location.href);
    url.searchParams.set('selected', model.value.selected);
    window.history.pushState(null, '', url.toString());
}

watch(() => model.value.selected, () => {
    model.value.unsavedChanges = false;
    uncommittedNewFileUploads.value = [];
    uncommittedDeletedResources.value = [];
    props.fetchResources()
})

const newIntegration = () => {
    const defaultProvider = (Object.keys(model.value?.integrations).length ? Object.values(model.value.integrations).at(0)?.provider : "adhoc:specialist_agents");
    const integration: Integration = {
        name: "New Integration",
        source: "This is the prompt information that the agent will consult when using the integration. Include API details or how to find datasets here.",
        description: "This is the description that the agent will use to determine when this integration should be used.",
        provider: defaultProvider,
        slug: "new_integration",
        uuid: "new",
        url: ""
    }
    model.value.integrations["new"] = integration;
    model.value.selected = "new";
    model.value.unsavedChanges = true;
    // Select the contents of the name, focusing input to allow immediate editing
    const el = nameInput?.value?.$el
    el?.select();
    el?.focus();
}

const delayUntil = (condition, retryInterval) => {
    const poll = resolve => {
        if (condition()) {
            resolve();
        }
        else {
            setTimeout(() => poll(resolve), retryInterval)
        }
    }
    return new Promise(poll);
}

// in the case of non-remounting, where ?selected= is changed via other means, go with that
watch(() => props.selectedQuery, (newSelected) => {
    if (newSelected === "new") {
        // newIntegration sets model.value to a temp uuid - this handles non-pageload cases
        if (model.value.finishedInitialLoad) {
            newIntegration();
        }
        // when we're dealing with pageload, just wait until valid
        else {
            delayUntil(() => model.value.finishedInitialLoad, 100)
                .then(() => newIntegration());
        }
    } else {
        model.value.selected = (newSelected as string|undefined) ?? model.value.selected;
    }
}, {immediate: true, deep: true})

watch(model, ({unsavedChanges}) => {
    if (unsavedChanges) {
        onbeforeunload = () => true;
    } else {
        onbeforeunload = undefined;
    }
})

const descriptionEditor = ref();
watch(() => [selectedIntegration?.value?.description], (current) => {
    if (descriptionEditor.value) {
        descriptionEditor.value.model = current[0];
    }
})

const instructionEditor = ref();
watch(() => [selectedIntegration.value?.source], (current) => {
    if (instructionEditor.value) {
        instructionEditor.value.model = current[0];
    }
})

const emptyText = ref<string|undefined>(undefined);

const fileInput = ref<HTMLInputElement|undefined>(undefined);
const fileInputMultiple = ref<HTMLInputElement|undefined>(undefined);
const uploadForm = ref<HTMLFormElement|undefined>(undefined);
const uploadFormMultiple = ref<HTMLFormElement|undefined>(undefined);

const unincludedFiles = computed<[string, IntegrationAttachedFile][]>(() => {
    const unincluded = [];
    for (const file of Object.values(attachedFiles.value)) {
        // we want to match adhoc's handler for {% file path/to/file.ext %}
        const pattern = RegExp(`{{\\s*${file?.name}\\s*}}`);
        if (!pattern.test(selectedIntegration?.value?.source)) {
            unincluded.push(file.name);
        }
    }
    return unincluded;
})

const confirmUnsavedChanges = () => {
    if (model.value.unsavedChanges) {
        return confirm("You currently have unsaved changes that would be lost with this change. Are you sure?")
    }
    return true;
}

const removeFile = async (id) => {
    model.value.unsavedChanges = true;
    delete selectedIntegration.value.resources[id];
    // if exists remote -- if it's only a local unsaved change, the request here is a no-op
    uncommittedDeletedResources.value.push(id);
}

const fileTarget = ref();

const openFileSelectionMultiple = () => {
    fileTarget.value = undefined;
    fileInputMultiple.value?.click();
}

const cookies = cookie.parse(document.cookie);
const xsrfCookie = cookies._xsrf;

const save = async () => {
    if (selectedIntegration?.value === undefined) {
        return;
    }

    for (const id of uncommittedDeletedResources.value) {
        await props.deleteResource(id);
    }
    uncommittedDeletedResources.value = [];

    // if local only, sync minimal details to get a uuid from the server, then update after files are pushed
    if (model.value.selected === "new") {
        const source = selectedIntegration.value.source;
        const uncommittedUploads = [...uncommittedNewFileUploads.value];
        // sets selected with new uuid
        await props.modifyIntegration({...selectedIntegration.value, source: ""})
        for (const file of uncommittedUploads) {
            await props.modifyResource(file);
        }
        selectedIntegration.value.source = source;
    } else {
        for (const [file_id, file] of Object.entries(attachedFiles.value)) {
            await props.modifyResource(file, file_id);
        }
    }
    await props.modifyIntegration(selectedIntegration.value, model.value.selected);

    showToast({
        title: 'Saved!',
        detail: `The session will now reconnect and load the new definition.`,
        severity: 'success',
        life: 4000
    });

    // if exists
    delete model.value.integrations["new"];

    model.value.unsavedChanges = false;
    // if ?selected=new, assign it to the new uuid for clarity
    // updateSelectedParam();
}

const onSelectFileForUpload = async () => {
    const fileList = uploadForm.value['uploadfiles']?.files;
    await uploadFiles(fileList);
}

const onSelectFilesForUpload = async () => {
    const fileList = uploadFormMultiple.value['uploadfilesMultiple']?.files;
    await uploadFiles(fileList);
}

const uploadFiles = async (files: FileList) => {
    model.value.unsavedChanges = true;
    const promises = Array.from(files).map(async (file) => {
        const bytes = [];
        const reader = file.stream().getReader();
        var chunk = (await reader.read()).value;
        while (chunk?.length > 0) {
            bytes.push(Array.from(chunk, (byte) => String.fromCharCode(byte)).join(""));
            chunk = (await reader.read()).value;
        }
        const fileResource = {
            resource_type: "file",
            integration: model.value.selected,
            content: String(bytes),
            filepath: file.name,
            name: file.name.split('.')[0]
        }
        // keep local until save on new temporary integration
        if (model.value.selected !== "new") {
            await props.modifyResource(fileResource);
        } else {
            uncommittedNewFileUploads.value.push(fileResource as IntegrationAttachedFile);
        }
    });
    await Promise.all(promises);
}

const downloadFile = async (id) => {
    const file: IntegrationAttachedFile = selectedIntegration.value.resources[id] as IntegrationAttachedFile
    const blob = new Blob([file?.content], {type: "text/plain"})
    const url = window.URL.createObjectURL(blob);
    const temporaryElement  = document.createElement("a");
    temporaryElement.href = url;
    temporaryElement.download = file.filepath;
    temporaryElement.click();

    window.URL.revokeObjectURL(url)
    temporaryElement.remove()
};

</script>

<style lang="scss">
.integration-editor {
    display: flex;
    flex-direction: column;
    .integration-main-content {
        overflow: auto;
        display: flex;
        flex-direction: column;
        .integration-header {
            display: flex;
            flex-direction: row;
            gap: 0.5rem;
            width: 100%;
            max-width: 100%;
            flex-shrink: 0;
            > div.p-select {
                flex: 1 1 auto;
                width: 100px;
                span.p-select-label {
                    flex-shrink: 2;
                    display: block;
                    min-width: 0;
                }
            }
            > div.p-splitbutton {
                flex-shrink: 0;
            }
        }
    }
    padding: 0 0.4rem;
    height: 100%
}

.constrained-editor-height {
    max-height: 16rem;
    overflow-y: auto;
}

.integration-editor > fieldset.p-fieldset legend.p-fieldset-legend {
    display: flex;
}
</style>
