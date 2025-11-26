<template>
    <div id="agent-input">
        <div id="agent-prompt">
            {{ isAwaitingInput ? 'The agent has a question:' : 'How can the agent help?' }}
        </div>

        <div v-if="isAwaitingInput && awaitingInputQuestion" class="agent-question">
            <div class="question-text" v-html="questionMarkdown"></div>
        </div>

        <div id="agent-inner-input">
            <div class="query-input-container">
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
                />
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">
import { ref, nextTick, inject, computed, watch } from "vue";
import Card from 'primevue/card';
import Button from 'primevue/button';
import ContainedTextArea from '../misc/ContainedTextArea.vue';
import { useWorkflows } from '../../composables/useWorkflows';
import { BeakerSession } from 'beaker-kernel';
import { type BeakerSessionComponentType } from '../session/BeakerSession.vue';
import { type BeakerNotebookComponentType } from '../notebook/BeakerNotebook.vue';
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

const handleSubmit = (e: any) => {
    if (isAwaitingInput.value) {
        handleResponse();
    } else {
        handleQuery();
    }
}

const handleQuery = () => {
    if (!query.value.trim()) {
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
    const cell = session.addQueryCell(query.value);
    query.value = "";

    nextTick(() => {
        notebook.selectCell(cell.id);
        beakerSession.findNotebookCellById(cell.id).execute();
    });
}

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

</script>


<style lang="scss">
#agent-input {
    padding: 0.5rem 0.75rem;
    background: var(--p-toolbar-background);
    border: 1px solid var(--p-toolbar-border-color);
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
