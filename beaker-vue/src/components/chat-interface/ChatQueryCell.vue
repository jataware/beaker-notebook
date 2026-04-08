<template>
    <div class="llm-query-cell">
        <div
            class="query query-chat"
            @dblclick="promptDoubleClick"
        >
            <!-- renders user questions -->
            <div class="llm-prompt-container llm-prompt-container-chat">
                <div v-show="isEditing" class="prompt-input-container">
                    <ContainedTextArea
                        ref="textarea"
                        class="prompt-input"
                        v-model="promptText"
                        :style="{minHeight: `${promptEditorMinHeight}px`}"
                    />
                    <div class="prompt-controls">
                        <Button label="Submit" @click="execute"/>
                        <Button label="Cancel" @click="promptText = cell.source; isEditing = false"/>
                    </div>
                </div>
                <div
                    :style="{ visibility: isEditing ? 'hidden' : 'visible',
                              height: isEditing ? '0px' : 'auto',
                              padding: isEditing ? '0px' : '0.5rem'
                     }"
                    class="llm-prompt-text llm-prompt-text-chat"
                    :data-cell-id="cell.id"
                >{{ cell.source }}</div>
            </div>
        </div>

        <div class="event-container"
            v-if="events.length > 0 || isLastEventTerminal(events) || showChatEventsEarly(cell)"
        >
            <div class="events">
                <!-- initial position of expand-thoughts-button -->
                <div
                    v-if="!hasUserResponses"
                    class="expand-thoughts-button"
                    :class="{ 'expanded': activeQueryCell === cell }"
                    @click="expandThoughts"
                >
                    <div
                        class="white-space-nowrap"
                        style="
                            display: flex;
                            align-items: center;
                            font-weight: 400;
                            font-family: 'Courier New', Courier, monospace;
                            font-size: 0.8rem;
                            color: var(--p-text-color-secondary)
                        "
                    >
                        <i
                            class="pi pi-sparkles"
                            :class="{'animate-sparkles': queryStatus === QueryStatuses.Running}"
                            style="
                                color: var(--p-yellow-500);
                                font-size: 1.25rem;
                                margin-right: 0.6rem;
                            "
                        />
                        {{ lastEventThought }}
                    </div>
                    <Button
                        :icon="activeQueryCell === cell ? 'pi pi-times' : 'pi pi-search'"
                        text
                        rounded
                        style="background-color: var(--p-surface-c); color: var(--p-text-color-secondary); width: 2rem; height: 2rem; padding: 0;"
                    />
                </div>

                <!-- render messages with expand-thoughts-button after last user response -->
                <template v-for="([messageEvent, messageClass], index) in messageEvents" v-bind:key="messageEvent.id">
                    <div style="display: flex; flex-direction: column;">
                        <BeakerQueryCellEvent
                            :event="messageEvent"
                            :parent-query-cell="cell"
                            :class="messageClass"
                        />
                    </div>
                    <!-- show expand-thoughts-button after last user response -->
                    <div
                        v-if="isLastUserResponse(messageEvent, index)"
                        class="expand-thoughts-button"
                        :class="{ 'expanded': activeQueryCell === cell }"
                        @click="expandThoughts"
                    >
                        <div
                            class="white-space-nowrap"
                            style="
                                display: flex;
                                align-items: center;
                                font-weight: 400;
                                font-family: 'Courier New', Courier, monospace;
                                font-size: 0.8rem;
                                color: var(--p-text-color-secondary)
                            "
                        >
                            <i
                                class="pi pi-sparkles"
                                :class="{'animate-sparkles': queryStatus === QueryStatuses.Running}"
                                style="
                                    color: var(--p-yellow-500);
                                    font-size: 1.25rem;
                                    margin-right: 0.6rem;
                                "
                            />
                            {{ lastEventThought }}
                        </div>
                        <Button
                        :icon="activeQueryCell === cell ? 'pi pi-times' : 'pi pi-search'"
                        text
                        rounded
                        style="background-color: var(--p-surface-c); color: var(--p-text-color-secondary); width: 2rem; height: 2rem; padding: 0;"
                        />
                    </div>
                </template>

                <!-- show final agent response/answer to original user query -->
                <div
                    class="query-answer-chat-override"
                    v-if="isLastEventTerminal(events)"
                >
                    <BeakerQueryCellEvent
                        :event="cell?.events[cell?.events.length - 1]"
                        :parent-query-cell="cell"
                    />
                </div>
            </div>
        </div>


        <div
            class="input-request-chat-override"
            v-focustrap
            v-if="cell.status === 'awaiting_input'"
        >
            <div
                class="input-request-wrapper input-request-wrapper-chat"
            >
                <InputGroup>
                    <InputGroupAddon>
                        <i class="pi pi-exclamation-triangle"></i>
                    </InputGroupAddon>
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
import { defineProps, defineExpose, inject, computed, onBeforeMount, getCurrentInstance, onBeforeUnmount, watch, toRaw, nextTick, type Ref } from "vue";
import Button from "primevue/button";
import InputGroup from 'primevue/inputgroup';
import InputText from 'primevue/inputtext';
import InputGroupAddon from 'primevue/inputgroupaddon';
import { type IBeakerCell } from "@jataware/beaker-client";
import BeakerQueryCellEvent from "../cell/BeakerQueryCellEvent.vue";
import ContainedTextArea from '../misc/ContainedTextArea.vue';
import type { BeakerSessionComponentType } from "../session/BeakerSession.vue";
import { isLastEventTerminal } from "../cell/cellOperations";
import { useBaseQueryCell } from '../cell/BaseQueryCell';

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

const enum QueryStatuses {
    NotExecuted,
    Running,
    Done,
}

const activeQueryCell = inject<IBeakerCell | null>("activeQueryCell");
const userClickedQueryCell = inject<Ref<boolean> | null>("userClickedQueryCell", null);
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const instance = getCurrentInstance();

const lastEventThought = computed(() => {
    const fallback = "Thinking";
    // initial state
    if (events.value.length < 1) {
        return fallback;
    }
    // grab the text from the last thought.
    const lastEvent = events.value[events.value.length - 1];
    if (lastEvent.type === 'thought') {
        return lastEvent.content.thought;
    }
    else {
        // walk backwards through events to determine the last thought
        let offset = 2;
        let eventCursor = events.value[events.value.length - offset];
        if (eventCursor === undefined) {
            return fallback;
        }
        while (eventCursor.type !== 'thought' && events.value.length >= offset) {
            offset += 1;
            eventCursor = events.value[events.value.length - offset];
        }
        if (eventCursor.type === 'thought') {
            if (eventCursor.content.thought === "Thinking..." && lastEvent.type === "response") {
                // TODO eventually summarize the previous work
                return "Thinking...";
            }
            const endTags = {
                'user_question': "(awaiting user input)",
                'user_answer': "(answer received, thinking)",
                'code_cell': "(code is now running)",
            }
            if (endTags[lastEvent.type]) {
                return `${eventCursor.content.thought} ${endTags[lastEvent.type]}`;
            }
            else {
                return eventCursor.content.thought;
            }
        // no thought, end of stack
        } else {
            return fallback;
        }
    }
})

const expandThoughts = (event: Event, forceOpen = false) => {
    const currentCell = toRaw(cell.value);

    if (forceOpen) {
        // Auto-expand (agent started running) — don't signal user click
        activeQueryCell.value = currentCell;
        return;
    }

    // Explicit user click on magnifying glass — always signal as user click
    if (userClickedQueryCell) userClickedQueryCell.value = true;

    const currentActiveCell = toRaw(activeQueryCell.value);
    if (currentActiveCell?.id === currentCell?.id) {
        // Same cell re-clicked — trigger reactivity so the watch fires again
        activeQueryCell.value = null;
        nextTick(() => {
            if (userClickedQueryCell) userClickedQueryCell.value = true;
            activeQueryCell.value = currentCell;
        });
    } else {
        activeQueryCell.value = currentCell;
    }
};

const queryStatus = computed<QueryStatuses>(() => {
    const eventCount = events.value.length;
    if (props.cell.status === 'busy') {
        return QueryStatuses.Running;
    }
    if (eventCount === 0) {
        return QueryStatuses.NotExecuted;
    }
    else if (isLastEventTerminal(events.value)) {
        return QueryStatuses.Done;
    }
    else {
        return QueryStatuses.Running;
    }
})

watch(queryStatus, (newStatus, oldStatus) => {
     // Auto-expand thoughts the first time a cell transitions to Running
     if (newStatus === QueryStatuses.Running && oldStatus !== QueryStatuses.Running) {
        expandThoughts(null, true);
     }
});


const messageEvents = computed(() => {
    return props.cell?.events?.filter(
        (event) => ["user_question", "user_answer"].includes(event.type)
    ).map(
        (event) => {
            var messageClass;
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

const showChatEventsEarly = (cell) => cell.status === 'busy';

const promptDoubleClick = (event) => {
    if (!isEditing.value) {
        promptEditorMinHeight.value = (event.target as HTMLElement).clientHeight;
        isEditing.value = true;
    }
}

const hasUserResponses = computed(() => {
    return messageEvents.value.some(([event]) => event.type === 'user_answer');
});

const isLastUserResponse = (event, index) => {
    if (event.type !== 'user_answer') return false;
    // last user response in the seq?
    const remainingEvents = messageEvents.value.slice(index + 1);
    return !remainingEvents.some(([e]) => e.type === 'user_answer');
};

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
.events {
    padding: 0.25rem 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.query {
    display: flex;
    justify-content: space-between;
    flex-direction: column;
}

.query-chat {
    align-items: flex-end;
    margin: 0.5rem 0;
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
        margin-bottom: 0.5rem;
    }
}

.llm-prompt-container {
    display: flex;
    flex-direction: column;
    background-color: var(--p-surface-c);
    border-radius: var(--p-surface-border-radius);
}

.llm-prompt-container-chat {
    width: fit-content;
    max-width: 80%;
    align-self: flex-end;
    background-color: var(--p-surface-d);
}

.llm-prompt-text {
    margin-left: 1rem;
    padding: 0.5rem;
    white-space: pre-wrap;
    width: fit-content;
}

.llm-prompt-text-chat {
    margin-left: 0.5rem;
    margin-right: 0.5rem;
}

.event-container {
    padding: 0rem;
    border-radius: 6px;
    margin-bottom: 0.25rem;
}

.query-answer-chat-override {
    padding-left: 1rem;
    padding-right: 1rem;
    border-radius: var(--p-surface-border-radius);
    max-width: 80%;
    width: fit-content;
    background-color: var(--p-surface-c);
}

.prompt-input-container {
    display: flex;
    flex-direction: row;
    margin: 0.25rem 0 0.25rem 0.25rem
}

.prompt-input {
    flex: 1;
    width: 100%;
}

.prompt-controls {
    display: flex;
    flex-direction: column;
    gap: 0.5em;
    margin: 0.5em;
}

.expand-thoughts-button {
    display: flex;
    gap: 0.15rem;
    cursor: pointer;
    margin: auto;
    justify-content: space-between;
    padding: 0.75rem;
    width: 100%;
    max-width: 80%;
    border: 1px solid var(--p-surface-b);
    border-radius: var(--p-surface-border-radius);

    &:hover {
        background-color: var(--p-surface-b);
    }

    &.expanded {
        background-color: var(--p-surface-b);
    }

    [data-theme="dark"] & {
        border: 1px solid var(--p-surface-a);
        &:hover, &.expanded {
            background-color: var(--p-surface-a);
        }
    }

    & > div {
        flex: 1;
    }

    &>button {
        align-self: center;
    }
}

@keyframes sparkle-spin-bounce {
  0% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(360deg);
  }
  60% {
    transform: rotate(360deg) translateY(-5px);
  }
  70% {
    transform: rotate(360deg) translateY(0px);
  }
  80% {
    transform: rotate(360deg) translateY(-3px);
  }
  90% {
    transform: rotate(360deg) translateY(0px);
  }
  100% {
    transform: rotate(360deg);
  }
}

.animate-sparkles {
  display: inline-block;
  animation: sparkle-spin-bounce 2s ease-in-out infinite;
  transform-origin: center;
}

</style>
