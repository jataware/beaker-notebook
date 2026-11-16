<template>
    <Card class="agent-input-card">
        <template #content>
            <div v-if="pending" class="pending-message">
                <div class="pending-label">{{ pending.state === 'deferred' ? 'Waiting to send' : 'Pending' }}</div>
                <InputGroup v-if="editingPending">
                    <ContainedTextArea v-model="pendingDraft" class="agent-query-textarea" />
                    <Button icon="pi pi-check" aria-label="Save pending message" :disabled="pendingBusy" @click="savePending" />
                    <Button icon="pi pi-undo" aria-label="Discard edits" :disabled="pendingBusy" @click="editingPending = false" />
                </InputGroup>
                <InputGroup v-else>
                    <div class="pending-text">{{ pending.text }}</div>
                    <Button v-if="pending.state === 'deferred'" icon="pi pi-send" aria-label="Send pending message" :disabled="pendingBusy" @click="sendDeferred" />
                    <Button icon="pi pi-pencil" aria-label="Edit pending message" :disabled="pendingBusy" @click="editPending" />
                    <Button icon="pi pi-times" aria-label="Cancel pending message" :disabled="pendingBusy" @click="cancelPending" />
                </InputGroup>
            </div>
            <InputGroup v-else>
                <ContainedTextArea
                    class="agent-query-textarea"
                    @keydown.enter.exact.prevent="handleQuery"
                    @keydown.escape.prevent.stop="($event.target as HTMLElement).blur()"
                    v-model="query"
                    :disabled="pendingBusy"
                    :placeholder="props.placeholder ?? 'How can the agent help?'"
                />
                <Button
                    icon="pi pi-send"
                    outlined
                    :disabled="pendingBusy"
                    @click="handleQuery"
                />
            </InputGroup>

        </template>
    </Card>
</template>


<script setup lang="ts">
import { ref, nextTick, inject } from "vue";
import { usePendingMessage } from '../../composables/usePendingMessage';
import Card from 'primevue/card';
import Button from 'primevue/button';
import { BeakerSession } from '@jataware/beaker-client';
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import ContainedTextArea from '../misc/ContainedTextArea.vue';

import InputGroup from 'primevue/inputgroup';

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

const query = ref("");
const emit = defineEmits([
    "select-cell",
    "run-cell",
]);

const props = defineProps([
    'placeholder'
])

const session: BeakerSession = inject("session");
const showToast: (...args: any[]) => void = inject("show_toast");

const submitCell = (text: string, pendingId?: string) => {
    const cell = session.addQueryCell(text);
    if (pendingId) cell.pending_message_id = pendingId;
    nextTick(() => {
        beakerSession.findNotebookCellById(cell.id).execute();
    });
};

const {
    pending, pendingDraft, editingPending, pendingBusy, queue,
    editPending, savePending, cancelPending, sendDeferred,
} = usePendingMessage(session, submitCell, showToast);

const handleQuery = async (e: any) => {
    const notebook = session.notebook;
    if (!query.value.trim()) {
        showToast?.({
            title: "Empty query",
            detail: "Please enter a question or instruction before submitting.",
            severity: "warn",
            life: 4000,
        });
        return;
    }
    // Remove the top cell if it is blank/not used.
    if (notebook.cells.length === 1) {
        const existingCell = notebook.cells[0];
        if (
            existingCell.cell_type === "code"
            && existingCell.source === ""
            && existingCell.execution_count === null
            && (existingCell.outputs as object[]).length === 0
        ) {
            notebook.removeCell(0);
        }
    }
    if (pendingBusy.value) return;
    const text = query.value;
    pendingBusy.value = true;
    try {
        const state = await queue(text);
        if (state === "inactive") {
            submitCell(text);
            query.value = "";
        } else if (state === "pending") {
            query.value = "";
        } else {
            showToast?.({title: "Message not queued", detail: "A message is already pending.", severity: "warn", life: 4000});
        }
    } catch (error) {
        showToast?.({title: "Message not sent", detail: String(error), severity: "error", life: 4000});
    } finally {
        pendingBusy.value = false;
    }
}
</script>


<style lang="scss">
.pending-label {
    font-size: 0.8rem;
    color: var(--p-text-muted-color);
}
.pending-text {
    flex: 1;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    padding: 0.5rem;
}
.agent-input-card {
    .p-card-body .p-card-content {
        padding: 0;
    }
}
.agent-query-container {
    background-color: var(--p-surface-b);
}
.agent-query-container div {
    padding: 0rem;
}
.agent-query-container-chat {
    width: 100%;
    align-self: flex-end;
    margin-top: 0.175rem;
    margin-bottom: 0.25rem;
    background-color: var(--p-surface-a);
}
.query-input-container {
    display: flex;
    align-items: flex-start;
    align-self: flex-end;
    margin-bottom: 0;
    padding: 0;
}
.query-input-container textarea {
    margin-bottom: 0;
}
.agent-submit-button {
    flex: 0 1 3rem;
    align-self: flex-end;
    height: 3rem;
}
.agent-query-textarea {
    flex: 1;
}
</style>
