<template>
    <div class="skill-integration-editor">
        <div class="skill-editor-content">
            <div v-if="isNew && pendingResourceCount" class="skill-import-note">
                <i class="pi pi-inbox"></i>
                <span>
                    {{ pendingResourceCount }} resource file{{ pendingResourceCount === 1 ? '' : 's' }} will be
                    imported when you save.<template v-if="pendingSkippedCount"> {{ pendingSkippedCount }} non-text
                    file{{ pendingSkippedCount === 1 ? '' : 's' }} skipped.</template>
                </span>
            </div>

            <Fieldset legend="Source">
                <p>
                    A <code>local</code> skill lives on disk and is fully editable here. A
                    <code>remote</code> skill is fetched from a URL; only its location is editable and the
                    fetched content is read-only.
                </p>
                <div class="skill-form-row">
                    <label>Type</label>
                    <Select
                        :model-value="sourceType"
                        @update:model-value="onSourceTypeChange"
                        :options="sourceTypeOptions"
                        option-label="label"
                        option-value="value"
                        :disabled="!isNew"
                    />
                </div>
                <div class="skill-form-row" v-if="sourceType === 'remote'">
                    <label>URL</label>
                    <div class="skill-url-row">
                        <InputText
                            :model-value="url"
                            @update:model-value="(value) => { url = value ?? ''; remotePreviewed = false; markDirty(); }"
                            :disabled="!isNew"
                            placeholder="https://example.com/my-skill/ (containing SKILL.md)"
                            style="font-family: monospace; flex: 1 1 auto;"
                        />
                        <Button
                            v-if="isNew"
                            label="Fetch"
                            icon="pi pi-download"
                            :loading="fetching"
                            :disabled="!url.trim()"
                            @click="fetchFromUrl"
                            v-tooltip.bottom="'Fetch the skill from this URL to preview it before saving'"
                        />
                    </div>
                    <small>URL of the skill directory or its <code>SKILL.md</code>. Fetch to preview before saving.</small>
                </div>
            </Fieldset>

            <template v-if="sourceType === 'local' || !isNew || remotePreviewed">
                <Fieldset legend="Name">
                    <InputText
                        :model-value="name"
                        @update:model-value="(value) => { name = value ?? ''; markDirty(); }"
                        :disabled="!editable"
                        placeholder="Skill name"
                    />
                    <small v-if="!isNew && editable">The folder name (slug) is fixed after creation; renaming updates only the display name.</small>
                </Fieldset>

                <Fieldset legend="Description">
                    <p>A short summary the agent uses to decide when this skill is relevant.</p>
                    <InputText
                        :model-value="description"
                        @update:model-value="(value) => { description = value ?? ''; markDirty(); }"
                        :disabled="!editable"
                        placeholder="One-line description"
                    />
                </Fieldset>

                <Fieldset legend="Metadata">
                    <div class="skill-form-grid">
                        <div class="skill-form-row">
                            <label>License</label>
                            <InputText :model-value="license" @update:model-value="(v) => { license = v ?? ''; markDirty(); }" :disabled="!editable" placeholder="e.g. MIT" />
                        </div>
                        <div class="skill-form-row">
                            <label>Compatibility</label>
                            <InputText :model-value="compatibility" @update:model-value="(v) => { compatibility = v ?? ''; markDirty(); }" :disabled="!editable" placeholder="e.g. python>=3.11" />
                        </div>
                        <div class="skill-form-row">
                            <label>Allowed tools</label>
                            <InputChips
                                v-model="allowedToolsList"
                                @update:model-value="markDirty"
                                :disabled="!editable"
                                separator=","
                                :add-on-blur="true"
                                placeholder="Type a tool and press Enter"
                                class="skill-tools-chips"
                            />
                            <small v-if="editable">Press Enter (or comma) after each tool.</small>
                        </div>
                        <div class="skill-form-row">
                            <label>Custom metadata</label>
                            <div class="skill-kv-editor">
                                <div class="skill-kv-item" v-for="(row, index) in metadataRows" :key="index">
                                    <InputText v-model="row.key" @update:model-value="markDirty" :disabled="!editable" placeholder="key" style="font-family: monospace;" />
                                    <InputText v-model="row.value" @update:model-value="markDirty" :disabled="!editable" placeholder="value" />
                                    <Button v-if="editable" icon="pi pi-trash" severity="danger" text @click="() => { metadataRows.splice(index, 1); markDirty(); }" v-tooltip="'Remove'" />
                                </div>
                                <Button v-if="editable" class="skill-add-button" icon="pi pi-plus" label="Add metadata" text @click="() => { metadataRows.push({ key: '', value: '' }); markDirty(); }" />
                            </div>
                        </div>
                    </div>
                </Fieldset>

                <Fieldset legend="Instructions (SKILL.md)">
                    <p>The skill's full instructions, disclosed to the agent when it loads the skill.</p>
                    <div class="skill-editor-height" v-if="editable">
                        <CodeEditor
                            language="markdown"
                            :autocomplete-enabled="false"
                            :model-value="instructions"
                            @update:model-value="(v) => { instructions = v ?? ''; markDirty(); }"
                        />
                    </div>
                    <div v-else class="skill-description" v-html="renderedInstructions"></div>
                </Fieldset>
            </template>

            <p v-if="!editable && sourceType === 'remote' && !isNew" class="skill-readonly-note">
                <i class="pi pi-info-circle"></i>
                <span>This is a remote skill; its content is fetched from the URL above and is read-only.</span>
            </p>
        </div>

        <div class="skill-editor-actions">
            <Button
                v-if="deletable"
                @click="remove"
                icon="pi pi-trash"
                label="Delete"
                severity="danger"
                outlined
            />
            <Button
                v-if="canSave"
                @click="save"
                icon="pi pi-save"
                label="Save Changes"
                severity="success"
                :disabled="!model.unsavedChanges"
            />
        </div>
    </div>
</template>


<script setup lang="ts">

import { computed, ref, watch, inject } from 'vue';
import {
    type IntegrationInterfaceState,
    type SkillIntegration,
    type SkillMetadataResource,
    type SkillInstructionsResource,
    isContextProvidedIntegration,
    filterByResourceType,
    previewRemoteSkill,
} from '../../util/integration';

import Fieldset from 'primevue/fieldset';
import InputText from 'primevue/inputtext';
import InputChips from 'primevue/inputchips';
import Select from 'primevue/select';
import Button from 'primevue/button';

import { marked } from 'marked';

import CodeEditor from '../misc/CodeEditor.vue';

const showToast = inject<any>('show_toast');

const props = defineProps<{
    sessionId: string,
    fetchResources: () => Promise<void>,
    deleteResource: (resourceId: string) => Promise<void>,
    modifyResource: (body: object, resourceId?: string) => Promise<void>,
    modifyIntegration: (body: object, integrationId?: string) => Promise<void>,
    deleteIntegration: (integrationId: string) => Promise<void>,
}>();

const model = defineModel<IntegrationInterfaceState>();

const selectedIntegration = computed<SkillIntegration>(() =>
    model.value.integrations[model.value.selected] as SkillIntegration);

const isNew = computed<boolean>(() => model.value.selected === "new");

// A skill is editable here when it is local and not provided by a context
// (context-bundled skills render through the read-only viewer instead).
const editable = computed<boolean>(() =>
    sourceType.value === 'local' && !isContextProvidedIntegration(selectedIntegration.value));

// A saved, non-context skill (local or remote) can be deleted.
const deletable = computed<boolean>(() =>
    !isNew.value && !isContextProvidedIntegration(selectedIntegration.value));

// The editor can persist changes for editable (local) skills, and for a new
// remote skill (whose URL is still editable). An existing remote skill has no
// editable fields, so it shows no Save button.
const canSave = computed<boolean>(() =>
    editable.value || (sourceType.value === 'remote' && isNew.value));

// Resources enumerated from an uploaded archive, awaiting the initial save.
const pendingResourceCount = computed<number>(() =>
    ((selectedIntegration.value as any)?.pendingResources ?? []).length);
const pendingSkippedCount = computed<number>(() =>
    ((selectedIntegration.value as any)?.pendingSkipped ?? []).length);

const sourceTypeOptions = [
    { label: "Local (on disk)", value: "local" },
    { label: "Remote (URL)", value: "remote" },
];

// --- Editable form state, synced from the selected integration ---
const sourceType = ref<'local' | 'remote'>('local');
const url = ref<string>('');
const name = ref<string>('');
const description = ref<string>('');
const instructions = ref<string>('');
const license = ref<string>('');
const compatibility = ref<string>('');
const allowedToolsList = ref<string[]>([]);
const metadataRows = ref<{ key: string, value: string }[]>([]);

// Whether a new remote skill's SKILL.md has been fetched to populate the form.
const remotePreviewed = ref<boolean>(false);
const fetching = ref<boolean>(false);

const metadataResource = computed<SkillMetadataResource | undefined>(() =>
    Object.values(filterByResourceType<SkillMetadataResource>(
        selectedIntegration.value?.resources, "skill_metadata"))[0]);

const instructionsResource = computed<SkillInstructionsResource | undefined>(() =>
    Object.values(filterByResourceType<SkillInstructionsResource>(
        selectedIntegration.value?.resources, "skill_instructions"))[0]);

const syncFromIntegration = () => {
    const integration = selectedIntegration.value;
    if (!integration) return;
    sourceType.value = integration.source_type ?? 'local';
    url.value = integration.url ?? '';
    name.value = integration.name ?? '';
    description.value = integration.description ?? '';
    instructions.value = instructionsResource.value?.content ?? '';
    const metadata = metadataResource.value;
    license.value = metadata?.license ?? '';
    compatibility.value = metadata?.compatibility ?? '';
    allowedToolsList.value = (metadata?.allowed_tools ?? '')
        .split(',').map((tool) => tool.trim()).filter((tool) => tool !== '');
    metadataRows.value = Object.entries(metadata?.skill_metadata ?? {})
        .map(([key, value]) => ({ key, value: String(value) }));
};

const markDirty = () => {
    model.value.unsavedChanges = true;
};

const onSourceTypeChange = (value: 'local' | 'remote') => {
    sourceType.value = value;
    remotePreviewed.value = false;
    markDirty();
};

// Fetch and parse the remote SKILL.md so the form shows the skill's actual
// content before the user commits. The fetched values are merged into the
// working "new" integration (which keeps its uuid "new" so save still adds).
const fetchFromUrl = async () => {
    if (!url.value.trim()) return;
    fetching.value = true;
    try {
        const preview = await previewRemoteSkill(props.sessionId, {
            provider: selectedIntegration.value.provider,
            url: url.value,
        });
        const working = selectedIntegration.value;
        working.name = preview.name;
        working.description = preview.description;
        working.resources = preview.resources ?? {};
        syncFromIntegration();
        // syncFromIntegration resets url from the (urless) working copy; restore it.
        url.value = (preview.url || url.value);
        remotePreviewed.value = true;
    } catch (e) {
        console.error('Failed to fetch remote skill:', e);
        showToast({
            title: 'Fetch failed',
            detail: `Could not load a skill from that URL. ${(e as Error)?.message ?? ''}`.trim(),
            severity: 'error',
            life: 5000,
        });
    } finally {
        fetching.value = false;
    }
};

const renderedInstructions = computed<string>(() =>
    instructions.value ? marked.parse(instructions.value) as string : "");

watch(() => model.value.selected, () => {
    remotePreviewed.value = false;
    syncFromIntegration();
    // A freshly created skill arrives pre-dirtied so its Save button shows
    // immediately; only clear the flag when landing on an existing one.
    if (!isNew.value) {
        model.value.unsavedChanges = false;
    }
}, { immediate: true });

// Re-sync when an existing integration's resources arrive/refresh (e.g. after a
// save re-fetches the authoritative copy), unless the user has edits pending.
watch(() => selectedIntegration.value?.resources, () => {
    if (!model.value.unsavedChanges) {
        syncFromIntegration();
    }
});

watch(model, ({ unsavedChanges }) => {
    onbeforeunload = unsavedChanges ? () => true : undefined;
}, { deep: true });

const save = async () => {
    const integration = selectedIntegration.value;
    if (!integration) return;

    // Capture before the save flips the selection from "new" to the saved id.
    const wasNew = isNew.value;
    const pending = wasNew ? ((integration as any).pendingResources ?? []) as object[] : [];

    const payload: Record<string, any> = {
        ...integration,
        source_type: sourceType.value,
        url: url.value,
    };
    // Resources are persisted through their own CRUD path; drop the (possibly
    // large) resource payloads from the integration body.
    delete payload.resources;
    delete payload.pendingResources;
    delete payload.pendingSkipped;

    if (sourceType.value === 'remote') {
        if (!url.value.trim()) {
            showToast({ title: 'URL required', detail: 'Enter the URL of the remote skill.', severity: 'warn', life: 4000 });
            return;
        }
    } else {
        if (!name.value.trim()) {
            showToast({ title: 'Name required', detail: 'Enter a name for the skill.', severity: 'warn', life: 4000 });
            return;
        }
        payload.name = name.value;
        payload.description = description.value;
        payload.instructions = instructions.value;
        payload.license = license.value;
        payload.compatibility = compatibility.value;
        payload.allowed_tools = allowedToolsList.value.join(", ");
        payload.skill_metadata = Object.fromEntries(
            metadataRows.value.filter((row) => row.key.trim() !== "").map((row) => [row.key, row.value]));
    }

    await props.modifyIntegration(payload, wasNew ? undefined : model.value.selected);

    // For a newly-created skill, upload any resources enumerated from an
    // uploaded archive now that the skill exists on disk. modifyResource targets
    // the just-saved integration (selection was updated by modifyIntegration).
    let failed = 0;
    for (const resource of pending) {
        try {
            await props.modifyResource(resource);
        } catch (e) {
            failed += 1;
            console.error('Failed to add uploaded resource', resource, e);
        }
    }

    showToast({
        title: failed ? 'Saved with errors' : 'Saved!',
        detail: pending.length
            ? `Saved with ${pending.length - failed} of ${pending.length} resource(s) imported${failed ? `; ${failed} failed (see console).` : '.'}`
            : 'The skill has been saved and will be available to the agent.',
        severity: failed ? 'warn' : 'success',
        life: 4000,
    });

    if (wasNew) {
        delete model.value.integrations["new"];
    }
    model.value.unsavedChanges = false;
};

const remove = async () => {
    const integration = selectedIntegration.value;
    if (!integration || isNew.value) return;
    const detail = sourceType.value === 'local'
        ? ' and its files from disk'
        : ' from your skills list';
    if (!confirm(`Delete skill "${integration.name}"? This permanently removes it${detail}.`)) {
        return;
    }
    await props.deleteIntegration(model.value.selected);
    model.value.unsavedChanges = false;
    showToast({
        title: 'Deleted',
        detail: `Removed "${integration.name}".`,
        severity: 'success',
        life: 4000,
    });
};

</script>

<style lang="scss">
.skill-integration-editor {
    display: flex;
    flex-direction: column;
    height: 100%;

    .skill-editor-content {
        flex: 1 1 auto;
        min-height: 0;
        overflow: auto;
        display: flex;
        flex-direction: column;
    }
}

.skill-editor-actions {
    flex: 1 0;
    margin: 0.2rem;
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;

    > * {
        flex-shrink: 0;
    }
}

.skill-form-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.skill-form-row {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;

    > label {
        font-weight: 600;
    }
    > small {
        color: var(--p-text-muted-color);
    }
}

.skill-kv-editor {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

.skill-kv-item {
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

.skill-add-button {
    width: fit-content;
}

.skill-url-row {
    display: flex;
    flex-direction: row;
    gap: 0.35rem;
    align-items: center;
}

.skill-tools-chips {
    width: 100%;
}

.skill-editor-height {
    height: 20rem;
    display: flex;
    flex-direction: column;
}

.skill-description {
    h1 { font-size: 1.25rem; margin-bottom: 1rem; }
    h2 { font-size: 1.2rem; margin-bottom: 0.8rem; }
    h3 { font-size: 1.15rem; margin-bottom: 0.8rem; }
    p, ul, li { margin-bottom: 0.8rem; margin-top: 0rem; }
    > *:first-child { margin-top: 0rem; }
}

.skill-readonly-note {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--p-text-muted-color);
}

.skill-import-note {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem;
    margin-bottom: 1rem;
    border-radius: 4px;
    background: var(--p-surface-100);
    color: var(--p-text-color);

    > i {
        color: var(--p-primary-color);
    }
}
</style>
