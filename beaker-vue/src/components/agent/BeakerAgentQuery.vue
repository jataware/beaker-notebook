<template>
    <div
        id="agent-input"
        :class="{'attachment-drop-active': isDraggingFiles}"
        @dragenter="handleDragEnter"
        @dragleave="handleDragLeave"
        @dragover="handleDragOver"
        @drop="handleDrop"
    >
        <div v-if="isDraggingFiles" class="attachment-drop-overlay">
            <i class="pi pi-cloud-upload"></i>
            <span>Drop files to attach them to this message</span>
        </div>
        <div id="agent-prompt">
            {{ isAwaitingInput ? 'The agent has a question:' : 'How can the agent help?' }}
        </div>

        <div v-if="isAwaitingInput && awaitingInputQuestion" class="agent-question">
            <div class="question-text" v-html="questionMarkdown"></div>
        </div>

        <div v-if="draftAttachments.length" class="attachment-drafts" aria-label="Message attachments">
            <div
                v-for="draft in draftAttachments"
                :key="draft.localId"
                class="attachment-draft"
                data-testid="attachment-draft"
                :class="`attachment-${draft.status}`"
                :title="draft.error || draft.attachment?.archive_error || draft.file.name"
            >
                <i
                    class="attachment-status-icon"
                    :class="draft.status === 'uploading'
                        ? 'pi pi-spin pi-spinner'
                        : draft.status === 'error'
                            ? 'pi pi-exclamation-triangle'
                            : draft.attachment?.kind === 'archive'
                                ? 'pi pi-box'
                                : 'pi pi-paperclip'"
                ></i>
                <span class="attachment-name">{{ draft.file.name }}</span>
                <small>{{ formatAttachmentSize(draft.file.size) }}</small>
                <small
                    v-if="draft.attachment?.kind === 'archive' && draft.attachment.archive_status === 'extracted'"
                    class="attachment-detail"
                >
                    {{ draft.attachment.file_count }} {{ draft.attachment.file_count === 1 ? 'file' : 'files' }}
                </small>
                <small v-if="draft.status === 'error'" class="attachment-error">Upload failed</small>
                <small
                    v-if="draft.attachment?.archive_status === 'failed'"
                    class="attachment-error"
                >
                    ZIP kept; extraction failed
                </small>
                <Button
                    type="button"
                    icon="pi pi-times"
                    text
                    rounded
                    size="small"
                    class="attachment-remove"
                    :aria-label="`Remove ${draft.file.name}`"
                    @click="removeAttachment(draft)"
                />
            </div>
        </div>

        <div id="agent-inner-input">
            <div class="query-input-container">
                <input
                    ref="fileInputRef"
                    type="file"
                    multiple
                    class="attachment-file-input"
                    data-testid="attachment-file-input"
                    @change="handleFileSelection"
                />
                <Button
                    v-if="!isAwaitingInput"
                    type="button"
                    icon="pi pi-paperclip"
                    text
                    rounded
                    class="attachment-picker"
                    aria-label="Attach files"
                    v-tooltip.top="'Attach temporary files'"
                    @click="fileInputRef?.click()"
                />
                <ContainedTextArea
                    ref="textAreaRef"
                    @submit="handleSubmit"
                    v-model="inputValue"
                    style="flex: 1; margin-right: 0.75rem"
                    :placeholder="isAwaitingInput ? 'Reply to the agent' : placeholder"
                />

                <Button
                    @click="handleSubmit"
                    class="agent-submit-button"
                    icon="pi pi-send"
                    :label="isAwaitingInput ? 'Reply' : $tmpl._('agent_submit_button_label', 'Submit')"
                    :foo="$tmpl"
                    :disabled="!isAwaitingInput && hasPendingUploads"
                />
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">
import { ref, reactive, nextTick, inject, computed, watch, onBeforeUnmount } from "vue";
import Button from 'primevue/button';
import { filesize } from 'filesize';
import ContainedTextArea from '../misc/ContainedTextArea.vue';
import { useWorkflows } from '../../composables/useWorkflows';
import { BeakerSession, type ISessionAttachment } from '@jataware/beaker-client';
import { type BeakerSessionComponentType } from '../session/BeakerSession.vue';
import { type BeakerNotebookComponentType } from '../notebook/BeakerNotebook.vue';
import { uploadSessionAttachment, deleteSessionAttachment } from '../../util/attachments';
import { marked } from "marked";

const props = defineProps([
    "runCellCallback",
    "awaitingInputCell",
    "awaitingInputQuestion"
]);

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const notebook = inject<BeakerNotebookComponentType>("notebook");

const query = ref("");
const response = ref("");
type DraftStatus = 'uploading' | 'ready' | 'error';
type AttachmentDraft = {
    localId: string;
    file: File;
    status: DraftStatus;
    controller: AbortController;
    attachment?: ISessionAttachment;
    error?: string;
};
type ToastOptions = {
    title: string;
    detail: string;
    severity: string;
    life?: number;
};

const draftAttachments = ref<AttachmentDraft[]>([]);
const fileInputRef = ref<HTMLInputElement>();
const dragDepth = ref(0);
const isDraggingFiles = computed(() => dragDepth.value > 0 && !isAwaitingInput.value);
const hasPendingUploads = computed(() => draftAttachments.value.some((draft) => draft.status === 'uploading'));
const showToast = inject<(options: ToastOptions) => void>("show_toast");
defineEmits([
    "select-cell",
    "run-cell",
]);

const session: BeakerSession = inject("session");

const isAwaitingInput = computed(() => !!props.awaitingInputCell);

const inputValue = computed({
    get: () => isAwaitingInput.value ? response.value : query.value,
    set: (value) => {
        if (isAwaitingInput.value) {
            response.value = value;
        } else {
            query.value = value;
        }
    }
});

const textAreaRef = ref(null);

const handleSubmit = () => {
    if (isAwaitingInput.value) {
        handleResponse();
    } else {
        handleQuery();
    }
}

const handleQuery = () => {
    if (hasPendingUploads.value) {
        showToast?.({
            title: 'Attachments still uploading',
            detail: 'Wait for the uploads to finish before sending this message.',
            severity: 'info',
        });
        return;
    }
    if (draftAttachments.value.some((draft) => draft.status === 'error')) {
        showToast?.({
            title: 'Attachment upload failed',
            detail: 'Remove failed attachments or drop them again before sending.',
            severity: 'warn',
        });
        return;
    }
    const readyAttachments = draftAttachments.value
        .map((draft) => draft.attachment)
        .filter((attachment): attachment is ISessionAttachment => attachment !== undefined);
    if (!query.value.trim() && readyAttachments.length === 0) {
        return;
    }

    // remove the top cell if it is blank/not used.
    if (notebook.notebook.cells.length === 1) {
        const existingCell = notebook.notebook.cells[0];
        if (
            existingCell.cell_type === "code" && existingCell.source === ""
            && existingCell.execution_count === null && existingCell.outputs.length === 0
        ) {
            notebook.notebook.removeCell(0);
        }
    }
    const prompt = query.value.trim() || 'Please inspect the attached file(s).';
    const cell = session.addQueryCell(prompt, {}, readyAttachments);
    query.value = "";
    draftAttachments.value = [];

    nextTick(() => {
        notebook.selectCell(cell.id);
        beakerSession.findNotebookCellById(cell.id).execute();
    });
}

const formatAttachmentSize = (size: number) => filesize(size, {spacer: ' '});

const containsFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes('Files');

const handleDragEnter = (event: DragEvent) => {
    if (isAwaitingInput.value || !containsFiles(event)) return;
    event.preventDefault();
    dragDepth.value += 1;
};

const handleDragLeave = (event: DragEvent) => {
    if (dragDepth.value === 0) return;
    event.preventDefault();
    dragDepth.value = Math.max(0, dragDepth.value - 1);
};

const handleDragOver = (event: DragEvent) => {
    if (isAwaitingInput.value || !containsFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
};

const handleDrop = (event: DragEvent) => {
    dragDepth.value = 0;
    if (isAwaitingInput.value || !containsFiles(event)) return;
    event.preventDefault();
    void addFiles(event.dataTransfer?.files);
};

const handleFileSelection = (event: Event) => {
    const input = event.target as HTMLInputElement;
    void addFiles(input.files);
    input.value = '';
};

const addFiles = async (files?: FileList | null) => {
    if (!files?.length) return;
    for (const file of Array.from(files)) {
        const draft = reactive<AttachmentDraft>({
            localId: crypto.randomUUID(),
            file,
            status: 'uploading',
            controller: new AbortController(),
        });
        draftAttachments.value.push(draft);
        void uploadDraft(draft);
    }
};

const uploadDraft = async (draft: AttachmentDraft) => {
    try {
        if (draft.controller.signal.aborted) return;
        draft.attachment = await uploadSessionAttachment(
            session.sessionId,
            draft.file,
            draft.controller.signal,
        );
        draft.status = 'ready';
        if (draft.attachment.archive_status === 'failed') {
            showToast?.({
                title: 'ZIP extraction failed',
                detail: `${draft.file.name} was kept as an attachment. The agent can inspect the original ZIP. ${draft.attachment.archive_error || ''}`,
                severity: 'warn',
                life: 8000,
            });
        }
    } catch (error) {
        if (draft.controller.signal.aborted) return;
        draft.status = 'error';
        draft.error = error instanceof Error ? error.message : String(error);
        showToast?.({
            title: 'Attachment upload failed',
            detail: `${draft.file.name}: ${draft.error}`,
            severity: 'error',
            life: 8000,
        });
    }
};

const removeAttachment = async (draft: AttachmentDraft) => {
    draft.controller.abort();
    const index = draftAttachments.value.findIndex((item) => item.localId === draft.localId);
    if (index >= 0) draftAttachments.value.splice(index, 1);
    if (draft.attachment) {
        try {
            await deleteSessionAttachment(session.sessionId, draft.attachment.id);
        } catch (error) {
            showToast?.({
                title: 'Unable to remove attachment',
                detail: error instanceof Error ? error.message : String(error),
                severity: 'error',
            });
        }
    }
};

const handleResponse = () => {
    if (!response.value.trim() || !props.awaitingInputCell) {
        return;
    }

    props.awaitingInputCell.respond(response.value, session);
    response.value = "";
}

const focusTextArea = () => {
    // auto-focus textarea when awaiting user input from an agent question
    if (!textAreaRef.value) {
        return false;
    }

    const target = textAreaRef.value.$el;
    if (target && target.tagName === 'TEXTAREA') {
        target.focus();
        return true;
    }

    return false;
};

// tries twice to focus to give vue a change to process rendering
watch(isAwaitingInput, (newValue) => {
    if (newValue) {
        setTimeout(() => {
            if (!focusTextArea()) {
                setTimeout(focusTextArea, 200);
            }
        }, 50);
    }
});
const { workflows, attachedWorkflowId, attachedWorkflow } = useWorkflows(beakerSession);

const placeholder = computed(() => attachedWorkflow?.value?.example_prompt ? attachedWorkflow.value.example_prompt : "Ask the AI or request an operation.")

const questionMarkdown = computed(() => marked.parse(props?.awaitingInputQuestion ?? ""))

onBeforeUnmount(() => {
    draftAttachments.value.forEach((draft) => draft.controller.abort());
});

</script>


<style lang="scss">
#agent-input {
    padding: 0.5rem 0.75rem;
    background: var(--p-toolbar-background);
    border: 1px solid var(--p-toolbar-border-color);
    position: relative;
}

.attachment-drop-overlay {
    position: absolute;
    inset: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    border: 2px dashed var(--p-primary-color);
    border-radius: var(--p-content-border-radius);
    background: color-mix(in srgb, var(--p-primary-color) 12%, var(--p-content-background));
    color: var(--p-primary-color);
    font-weight: 600;
    pointer-events: none;
}

.attachment-drafts {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.4rem 0;
}

.attachment-draft {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    min-width: 0;
    padding: 0.2rem 0.25rem 0.2rem 0.55rem;
    border: 1px solid var(--p-content-border-color);
    border-radius: 999px;
    background: var(--p-content-background);
    font-size: 0.85rem;

    small {
        color: var(--p-text-muted-color);
    }
}

.attachment-name {
    max-width: 15rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.attachment-error,
.attachment-error .attachment-status-icon {
    color: var(--p-red-500) !important;
}

.attachment-detail {
    white-space: nowrap;
}

.attachment-remove {
    width: 1.75rem;
    height: 1.75rem;
}

.attachment-file-input {
    display: none;
}

.attachment-picker {
    flex: 0 0 auto;
    align-self: flex-end;
    width: 2.5rem;
    height: 3rem;
}

#agent-prompt {
    margin-bottom: 0.25rem;
    opacity: 0.8;
    filter: saturate(0.7);
    font-size: 1.1rem;
    margin-left: 1px;
}

.agent-question {
    margin-bottom: 0.5rem;
    padding: 0 0.5rem;
    background: var(--p-surface-b);
    border-left: 3px solid var(--p-primary-color);
}

.question-text {
    font-weight: 500;
    color: var(--p-text-color);
}

.query-input-container {
    display: flex;
}

.agent-submit-button {
    flex: 0 1 7rem;
}
</style>
