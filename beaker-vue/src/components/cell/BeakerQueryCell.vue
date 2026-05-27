<template>
    <div class="llm-query-cell">
        <div
            class="query"
            @dblclick="promptDoubleClick"
        >
            <div class="query-steps">User Query:</div>
            <div
                class="llm-prompt-container"
            >
                <div v-show="isEditing" class="prompt-input-container">
                    <ContainedTextArea
                        ref="textarea"
                        class="prompt-input"
                        v-model="promptText"
                        :style="{minHeight: `${promptEditorMinHeight}px`}"
                    />
                    <div class="prompt-controls" style="">
                        <Button label="Submit" @click="execute"/>
                        <Button label="Cancel" @click="promptText = cell.source; isEditing = false"/>
                    </div>
                </div>
                <div
                    v-show="!isEditing"
                    class="llm-prompt-text"
                >{{ cell.source }}</div>
            </div>
        </div>
        <div class="event-container"
            v-if="events.length > 0 || isLastEventTerminal(events)"
        >
            <div class="events">
                <div
                    class="query-steps"
                    v-if="events.length > 0"
                >
                    Agent actions:
                </div>
                <Accordion
                    v-if="events.length > 0"
                    :multiple="true"
                    :class="'query-accordion'"
                    v-model:active-index="selectedEvents"
                >
                    <AccordionTab
                        v-for="(event, eventIndex) in events"
                        :key="eventIndex"
                        :pt="{
                            header: {
                                class: [`query-tab`, `query-tab-${event.type}`]
                            },
                            headerAction: {
                                class: [`query-tab-headeraction`, `query-tab-headeraction-${event.type}`]
                            },
                            content: {
                                class: [`query-tab-content-${event.type}`]
                            },
                            headerIcon: {
                                class: [`query-tab-icon-${event.type}`]
                            }
                        }"
                    >
                        <template #header>
                            <span class="query-header-content">
                                <span :class="eventIconMap[event.type]">
                                    <ThinkingIcon v-if="event.type === 'thought'" class="thought-icon"/>
                                </span>
                                <span class="font-bold white-space-nowrap">{{ queryEventNameMap[event.type] }}</span>
                            </span>
                        </template>
                        <BeakerQueryCellEvent
                            :key="eventIndex"
                            :event="event"
                            :parent-query-cell="cell"
                        />
                    </AccordionTab>
                </Accordion>
                <div v-for="[messageEvent, messageClass] of messageEvents" v-bind:key="messageEvent.id">
                    <div style="display: flex; flex-direction: column;">
                        <BeakerQueryCellEvent
                            :event="messageEvent"
                            :parent-query-cell="cell"
                            :class="messageClass"
                        />
                    </div>
                </div>
                <div
                    class="query-answer"
                    v-if="isLastEventTerminal(events)"
                >
                    <h3 class="query-steps">Result</h3>
                    <BeakerQueryCellEvent
                        :event="cell?.events[cell?.events.length - 1]"
                        :parent-query-cell="cell"
                    />
                </div>
            </div>
        </div>
        <div class="thinking-indicator" v-if="cell.status === 'busy'">
            <span class="thought-icon" style="margin-right: 0.25rem;"><ThinkingIcon/></span> Thinking <span class="thinking-animation"></span>
        </div>
        <div
            class="input-request"
            v-focustrap
            v-if="cell.status === 'awaiting_input'"
        >
            <div
                class="input-request-wrapper"
            >
                <InputGroup>
                    <InputText
                        placeholder="Reply to the agent"
                        @keydown.enter.exact.prevent="respond"
                        @keydown.escape.prevent.stop="($event.target as HTMLElement).blur()"
                        @keydown.ctrl.enter.stop
                        @keydown.shift.enter.stop
                        autoFocus
                        v-model="response"
                    />
                    <Button
                        icon="pi pi-send"
                        @click="respond"
                    />
                </InputGroup>
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">
import { ref, inject, computed, onBeforeMount, getCurrentInstance, onBeforeUnmount } from "vue";
import Button from "primevue/button";
import Accordion from "primevue/accordion";
import AccordionTab from "primevue/accordiontab";
import BeakerQueryCellEvent from "./BeakerQueryCellEvent.vue";
import type { BeakerQueryEventType } from "@jataware/beaker-client";
import ContainedTextArea from '../misc/ContainedTextArea.vue';
import type { BeakerSessionComponentType } from "../session/BeakerSession.vue";
import ThinkingIcon from "../../assets/icon-components/BrainIcon.vue";
import InputGroup from 'primevue/inputgroup';
import InputText from 'primevue/inputtext';
import { isLastEventTerminal } from "./cellOperations";
import { useBaseQueryCell } from './BaseQueryCell';


const props = defineProps([
    'index',
    'cell',
]);

const {
  cell,
  isEditing,
  promptEditorMinHeight,
  promptText,
  response,
  textarea,
  events,
  execute,
  enter,
  exit,
  clear,
  respond
} = useBaseQueryCell(props);


const eventIconMap = {
    "code_cell": "pi pi-code",
    "thought": "thought-icon",
    "user_answer": "pi pi-reply",
    "user_question": "pi pi-question-circle"
}

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const instance = getCurrentInstance();

const messageEvents = computed(() => {
    return props.cell?.events?.filter(
        (event) => ["user_question", "user_answer"].includes(event.type)
    ).map(
        (event) => {
            let messageClass;
            if (event.type === "user_question") {
                messageClass = "query-answer-chat query-answer-chat-override";
            }
            else {
                messageClass = "llm-prompt-container llm-prompt-container-chat llm-prompt-text llm-prompt-text-chat";
            }
            return [event, messageClass];
        }
    );
})

// behavior: temporarily show last event and all code cells, until terminal, in which case,
// only show code cells
const selectedEvents = computed({
    get() {
        const eventCount = events.value.length;
        if (eventCount === 0) {
            return [];
        }
        else if (eventCount === 1) {
            return [0];
        }
        else {
            return [eventCount-2, eventCount-1];
        }
    },
    set(newValue) {
        // no operation,
    },

})

const queryEventNameMap: {[eventType in BeakerQueryEventType]: string} = {
    "thought": "Thought",
    "response": "Final Response",
    "code_cell": "Code",
    "user_answer": "Answer",
    "user_question": "Question",
    // "background_code": "Background Code",
    "error": "Error",
    "abort": "Abort"
}

const promptDoubleClick = (event) => {
    if (!isEditing.value) {
        promptEditorMinHeight.value = (event.target as HTMLElement).clientHeight;
        isEditing.value = true;
    }
}

defineExpose({
    execute,
    enter,
    exit,
    clear,
    cell,
    editor: textarea,
});

onBeforeMount(() => {
    beakerSession.cellRegistry[cell.value.id] = instance.vnode;
});

onBeforeUnmount(() => {
    delete beakerSession.cellRegistry[cell.value.id];
});

</script>

<script lang="ts">
import { BeakerQueryCell } from "@jataware/beaker-client";
export default {
    modelClass: BeakerQueryCell,
    icon: "pi pi-sparkles",
};
</script>


<style lang="scss">

.query-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.events {
    padding: 0.25rem 0;
    display: flex;
    flex-direction: column;
}

.query {
    display: flex;
    justify-content: space-between;
    flex-direction: column;
    margin-bottom: 0.25rem;
}

.input-request {
    padding: 0.5rem 0;
    display: flex;
    align-items: flex-start;
    width: 90%;
}

.input-request-wrapper {
    display: flex;
    width: 100%;
}

.input-request-chat-override {
    align-items: flex-end;
    width: 100%;
    .input-request-wrapper-chat {
        align-items: flex-end;
        flex-direction: column;
        margin-bottom: 0.5rem;
        .p-inputgroup {
            width: 100%;
            border: 1px solid var(--p-yellow-500);
            box-shadow: 0 0 4px var(--p-yellow-700);
            transition: box-shadow linear 1s;
            border-radius: var(--p-surface-border-radius);
            button {
                background-color: var(--p-surface-b);
                border-color: var(--p-surface-border);
                color: var(--p-text-color);
                border-left: 0px;
            }
            input {
                border-color: var(--p-yellow-500);
            }
        }
    }
}

.actions {
    display: flex;
    .p-button-icon {
        font-weight: bold;
        font-size: 1rem;
    }
}

.edit-actions {
    display: flex;
    align-items: flex-start;
    .p-button {
        margin-right: 0.5rem;
    }
}

.cancel-button {
    border-color: var(--p-surface-c);
    color: var(--p-primary-text-color);
}


.llm-prompt-container {
    display: flex;
    flex-direction: column;
    background-color: var(--p-surface-c);
    border-radius: var(--p-surface-border-radius);
}

div.query-steps {
    margin-bottom: 1rem;
}

h3.query-steps {
    margin-bottom: 0rem;
}

.llm-prompt-text {
    margin-left: 1rem;
    padding: 0.5rem;
    white-space: pre-wrap;
    width: fit-content;
}

.event-container {
    padding: 0rem;
    border-radius: 6px;
}

.query-events-header {
    background-color: var(--p-surface-b);
    border-radius: 6px 6px 0 0;
}

.query-events-header {
    font-weight: 600;
}

.query-accordion .p-accordion-content {
    padding-top: 0.25rem;
    padding-bottom: 0rem;
}

.query-accordion-chat {
    margin-bottom: 0.5rem;
    width: 100%;
    > .p-accordion-tab {
        width: 100%;
        display: flex;
        align-items: center;
        flex-direction: column;
        > * {
            max-width: 80%;
            width: 100%;
        }
        > .p-toggleable-content > .p-accordion-content {
            border: 2px solid var(--p-surface-d);
            border-radius: var(--p-surface-border-radius);
            padding: 0.25rem;
            padding-left: 1.5rem;
            margin: 1rem;
            margin-bottom: 0rem;
            > * {
                border-bottom: 2px solid var(--p-surface-d);
                margin-right: 1rem;
            }
            > *:last-child {
                border-bottom: none;
            }
        }
        .p-accordion-header {
            border-radius: var(--p-surface-border-radius);
            margin: 1rem;
            margin-bottom: 0rem;
            transition: background-color 0.2s;

            &:hover {
                background-color: var(--p-surface-a);
            }
        }
    }

}

.query-tab-title-chat {
    font-weight: 400;
}

.query-tab-thought-chat {
    .p-accordion-header-link svg {
        flex-shrink: 0;
    }
}

.query-steps {
    font-size: large;
}

.query-tab-background_code {
    font-size: 6pt;
    color: #777;

    + a {
        margin: 0;
        padding: 0;
    }
}


div.query-tab a.p-accordion-header-link.p-accordion-header-action{
    padding: 0.5rem;
    background: none;
    border: none;
}

div.query-tab-thought a.p-accordion-header-link.p-accordion-header-action,
div.query-tab-user_question a.p-accordion-header-link.p-accordion-header-action,
div.query-tab-user_answer a.p-accordion-header-link.p-accordion-header-action {
    background: none;
    border: none;
}

div.p-accordion-content.query-tab-content-thought,
div.p-accordion-content.query-tab-content-user_question,
div.p-accordion-content.query-tab-content-user_answer {
    background: none;
    border: none;
    font-size: 0.9rem;
    padding-left: 2.5rem;
}

div.p-accordion-content.query-tab-content-code_cell {
    background: none;
    border: none;
    padding-left: 2.5rem;
}

div.code-cell.query-event-code-cell {
    padding-left: 0;
}


a.query-tab-headeraction > span > span.pi {
    align-items: center;
    margin: auto;
    padding-right: 0.5rem;
}

.query-answer {
    background-color: var(--p-surface-c);
    padding-left: 1rem;
    padding-bottom: 1rem;
    border-radius: var(--p-surface-border-radius);
    margin-top: 1rem;
}

.prompt-input-container {
    display: flex;
    flex-direction: row;
}

.prompt-input {
    flex: 1;
}

.prompt-controls {
    display: flex;
    align-self: end;
    flex-direction: column;
    gap: 0.5em;
    margin: 0.5em;
}

.thought-icon {
    display: inline-block;
    height: 1rem;
    margin: auto;

    svg {
        fill: currentColor;
        stroke: currentColor;
        width: 1rem;
        margin: 0;
    }
}

.thinking-indicator {
    opacity: 0.7;
    vertical-align: middle;
}

.thinking-animation {
    font-size: x-large;
    clip-path: view-box;
}

.thinking-animation:after {
    overflow: hidden;
    display: inline-block;
    vertical-align: bottom;
    position: relative;
    animation: thinking-ellipsis 2000ms steps(48, end) infinite;
    content: "\2026\2026\2026\2026"; /* ascii code for the ellipsis character */
    width: 4em;
}


@keyframes thinking-ellipsis {
  from {
    right: 4em;
  }
  to {
    right: -4em;
  }
}

.query-header-content {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

</style>
