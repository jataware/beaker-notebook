<template>
    <Card class="agent-input-card">
        <template #content>
            <InputGroup>
                <ContainedTextArea
                    class="agent-query-textarea"
                    @keydown.enter.exact.prevent="handleQuery"
                    @keydown.escape.prevent.stop="($event.target as HTMLElement).blur()"
                    v-model="query"
                    :placeholder="props.placeholder ?? 'How can the agent help?'"
                />
                <Button
                    icon="pi pi-send"
                    outlined
                    @click="handleQuery"
                />
            </InputGroup>

        </template>
    </Card>
</template>


<script setup lang="ts">
import { ref, nextTick, inject } from "vue";
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
const handleQuery = (e: any) => {
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
    const cell = session.addQueryCell(query.value);
    query.value = "";
    nextTick(() => {
        beakerSession.findNotebookCellById(cell.id).execute();
    });
}
</script>


<style lang="scss">
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
