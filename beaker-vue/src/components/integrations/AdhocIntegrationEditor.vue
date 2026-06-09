<template>
    <div class="adhoc-integration-editor">
        <div class="adhoc-editor-content">
            <Fieldset legend="Name">
                <InputText
                    ref="nameInput"
                    v-model="selectedIntegration.name"
                    placeholder="Name"
                    @change="model.unsavedChanges = true;"
                />
            </Fieldset>

            <Fieldset legend="Description">
                <p>
                    The description, used by both users and the agent, provides a brief summary of the purpose of this
                    integration. The agent will use this to select which integration best matches a user's request.
                </p>
                <div class="constrained-editor-height">
                    <CodeEditor
                        language="markdown"
                        :autocomplete-enabled="false"
                        v-model="selectedIntegration.description"
                        @change="model.unsavedChanges = true"
                        ref="descriptionEditor"
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
                        language="markdown"
                        :autocompleteEnabled="true"
                        :autocomplete-options="Object.values(attachedFiles).map((file: IntegrationAttachedFile) => file.name)"
                        v-model="selectedIntegration.source"
                        @change="model.unsavedChanges = true"
                        ref="instructionEditor"
                    />
                </div>
            </Fieldset>
        </div>
        <div style="flex: 1 0; margin: 0.2rem; display: flex; justify-content: flex-end;">
            <div v-if="model.unsavedChanges" style="flex-shrink: 0;">
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

import { ref, watch, computed, inject } from 'vue';
import { type Integration, type IntegrationAttachedFile, type IntegrationInterfaceState, filterByResourceType } from '../../util/integration';

import Fieldset from 'primevue/fieldset';
import Button from "primevue/button";
import Toolbar from 'primevue/toolbar';
import InputText from 'primevue/inputtext';
import Tag from 'primevue/tag';

import * as cookie from 'cookie';

import CodeEditor from '../misc/CodeEditor.vue';

const showToast = inject<any>('show_toast');

const props = defineProps<{
    fetchResources: () => Promise<void>,
    deleteResource: (resourceId: string) => Promise<void>,
    modifyResource: (body: object, resourceId?: string) => Promise<void>,
    modifyIntegration: (body: object, integrationId?: string) => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const selectedIntegration = computed<Integration>(() =>
    model.value.integrations[model.value.selected]);

const attachedFiles = computed<{[key: string]: IntegrationAttachedFile}>(() =>
    filterByResourceType<IntegrationAttachedFile>(
        selectedIntegration.value?.resources, "file")
);

const nameInput = ref();

const uncommittedDeletedResources = ref([]);
const uncommittedNewFileUploads = ref<IntegrationAttachedFile[]>([]);

watch(() => model.value.selected, () => {
    model.value.unsavedChanges = false;
    uncommittedNewFileUploads.value = [];
    uncommittedDeletedResources.value = [];
    props.fetchResources();
});

watch(model, ({unsavedChanges}) => {
    if (unsavedChanges) {
        onbeforeunload = () => true;
    } else {
        onbeforeunload = undefined;
    }
});

const descriptionEditor = ref();
watch(() => [selectedIntegration?.value?.description], (current) => {
    if (descriptionEditor.value) {
        descriptionEditor.value.model = current[0];
    }
});

const instructionEditor = ref();
watch(() => [selectedIntegration.value?.source], (current) => {
    if (instructionEditor.value) {
        instructionEditor.value.model = current[0];
    }
});

const fileInput = ref<HTMLInputElement|undefined>(undefined);
const fileInputMultiple = ref<HTMLInputElement|undefined>(undefined);
const uploadForm = ref<HTMLFormElement|undefined>(undefined);
const uploadFormMultiple = ref<HTMLFormElement|undefined>(undefined);

const unincludedFiles = computed<[string, IntegrationAttachedFile][]>(() => {
    const unincluded = [];
    for (const file of Object.values(attachedFiles.value)) {
        const pattern = RegExp(`{{\\s*${file?.name}\\s*}}`);
        if (!pattern.test(selectedIntegration?.value?.source)) {
            unincluded.push(file.name);
        }
    }
    return unincluded;
});

const removeFile = async (id) => {
    model.value.unsavedChanges = true;
    delete selectedIntegration.value.resources[id];
    uncommittedDeletedResources.value.push(id);
};

const fileTarget = ref();

const openFileSelectionMultiple = () => {
    fileTarget.value = undefined;
    fileInputMultiple.value?.click();
};

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

    if (model.value.selected === "new") {
        const source = selectedIntegration.value.source;
        const uncommittedUploads = [...uncommittedNewFileUploads.value];
        await props.modifyIntegration({...selectedIntegration.value, source: ""});
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

    delete model.value.integrations["new"];
    model.value.unsavedChanges = false;
};

const onSelectFileForUpload = async () => {
    const fileList = uploadForm.value['uploadfiles']?.files;
    await uploadFiles(fileList);
};

const onSelectFilesForUpload = async () => {
    const fileList = uploadFormMultiple.value['uploadfilesMultiple']?.files;
    await uploadFiles(fileList);
};

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
        };
        if (model.value.selected !== "new") {
            await props.modifyResource(fileResource);
        } else {
            uncommittedNewFileUploads.value.push(fileResource as IntegrationAttachedFile);
        }
    });
    await Promise.all(promises);
};

const downloadFile = async (id) => {
    const file: IntegrationAttachedFile = selectedIntegration.value.resources[id] as IntegrationAttachedFile;
    const blob = new Blob([file?.content], {type: "text/plain"});
    const url = window.URL.createObjectURL(blob);
    const temporaryElement = document.createElement("a");
    temporaryElement.href = url;
    temporaryElement.download = file.filepath;
    temporaryElement.click();

    window.URL.revokeObjectURL(url);
    temporaryElement.remove();
};

</script>

<style lang="scss">
.adhoc-integration-editor {
    display: flex;
    flex-direction: column;
    height: 100%;

    .adhoc-editor-content {
        overflow: auto;
        display: flex;
        flex-direction: column;
    }
}

.constrained-editor-height {
    max-height: 16rem;
    overflow-y: auto;
}
</style>
