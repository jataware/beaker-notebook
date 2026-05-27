<template>
    <div class="llm-query-event">
        <div v-if="waitForUserAnswer(event)">
            <span class="waiting-text">
                <i class="pi pi-spin pi-spinner" style="font-size: 1rem"></i> Waiting for user input in conversation.
            </span>
        </div>
        <div v-else-if="event.type === 'user_question' && props.shouldHideAnsweredQuestions">
        </div>
        <div
            v-else-if="isMarkdown(event) && isValidResponse(event)"
            v-html="markdownBody"
            class="md-inline"
        />

        <div v-if="props.event?.type === 'response' && parentEntries !== 0">
            <Accordion :multiple="true" :active-index="meaningfulOutputs">
                <AccordionTab
                    v-for="[index, child] in parentEntries"
                    :key="index"
                    :pt="{
                        header: {
                            class: [`agent-response-header`]
                        },
                        headerAction: {
                            class: [`agent-response-headeraction`]
                        },
                        content: {
                            class: [`agent-response-content`]
                        },
                        headerIcon: {
                            class: [`agent-response-icon`]
                        }
                    }"
                >
                    <template #header>
                        <span class="flex align-items-center gap-2 w-full">
                            <!-- <span :class="chooseOutputIcon(child?.outputs)"/>
                            <span class="font-bold white-space-nowrap">{{ formatOutputs(child?.outputs, ["execute_result"]) }}</span> -->
                            <span>Outputs</span>
                        </span>
                    </template>
                    <BeakerCodecellOutput :outputs="child?.outputs" />
                </AccordionTab>
            </Accordion>
        </div>
        <div v-else-if="props.event?.type === 'thought'">
            <div v-html="marked.parse(props.event.content.thought)" />
        </div>
        <div v-else-if="props.event?.type === 'code_cell'" style="position: relative;">
            <BeakerCodeCell
                @click="codeCellOnClick"
                :cell="getCellModelById(props?.event.content.cell_id)"
                :drag-enabled="false"
                :code-styles="props.codeStyles"
                :class="{
                    selected: isCodeCellSelected,
                    'query-event-code-cell': true
                }"
                :hide-output="false"
                ref="codeCellRef"
                v-keybindings="{
                    'keydown.enter.ctrl.prevent.capture.in-editor': (evt) => {
                        codeCellRef.execute();
                    },
                    'keydown.enter.shift.prevent.capture.in-editor': (evt) => {
                        codeCellRef.execute();
                    }
                }"
            />
            <slot name="code-cell-controls" />
            <!-- <span class="output-hide-text">(Output hidden -- shown in full response below.)</span> -->
        </div>
        <span v-else-if="props.event?.type === 'error' && props.event.content.ename === 'CancelledError'">
            <h4 class="p-error">Request cancelled.</h4>
        </span>
        <span v-else-if="props.event?.type === 'error'">
            <div>
                <pre class="pre" v-if="props?.event.content.ename">
                    {{props?.event.content.ename}}
                </pre>
                <pre class="pre" v-if="props?.event.content.evalue">
                    {{props?.event.content.evalue}}
                </pre>
                <Accordion>
                    <AccordionTab
                        :pt="{
                            header: {
                                class: [`agent-response-header`]
                            },
                            headerAction: {
                                class: [`agent-response-headeraction`]
                            },
                            content: {
                                class: [`agent-response-content`, 'agent-response-content-error']
                            },
                            headerIcon: {
                                class: [`agent-response-icon`]
                            }
                        }"
                    >
                        <template #header>
                            <span class="flex align-items-center gap-2 w-full">
                                <span class="font-bold white-space-nowrap">Traceback:</span>
                            </span>
                        </template>
                        <pre class="pre" v-if="props?.event.content.traceback">
                            {{props?.event.content.traceback?.join('\n')}}
                        </pre>
                    </AccordionTab>
                </Accordion>
            </div>
        </span>
    </div>
</template>

<script setup lang="ts">
import { inject, onBeforeMount, computed, ref, capitalize } from "vue";
import { type BeakerQueryEvent, type BeakerQueryEventType, type IBeakerCell } from "@jataware/beaker-client";
import { marked } from 'marked';
import BeakerCodeCell from "./BeakerCodeCell.vue";
import BeakerCodecellOutput from "./BeakerCodeCellOutput.vue";
import Accordion from "primevue/accordion";
import AccordionTab from "primevue/accordiontab";
import ansiHtml from "ansi-html-community";
import { formatOutputs, chooseOutputIcon } from './BeakerCodeCellOutputUtilities'
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import type { BeakerNotebookComponentType } from '../notebook/BeakerNotebook.vue';


// use session where possible - notebook may or may not exist, but matters for selection!
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const beakerNotebook = inject<BeakerNotebookComponentType>("notebook");
const codeCellRef = ref();

const props = defineProps([
    'event',
    'parentQueryCell',
    'codeStyles',
    'shouldHideAnsweredQuestions'
]);

onBeforeMount(() => {
    marked.setOptions({
    //    gfm: true,
    //    sanitize: false,
    //    langPrefix: `language-`,
    });
})

// these need to be no-ops if notebook doesn't exist in the parent UI.
const codeCellOnClick = () => {
    if (beakerNotebook) {
        beakerNotebook.selectCell(props.event?.content.cell_id)
    }
}

// see above
const parentIndex = computed(() =>
    beakerSession.session.notebook.cells.indexOf(props.parentQueryCell.value));

const isCodeCellSelected = computed(() => {
    if (beakerNotebook) {
        return parentIndex.value.toString() === beakerNotebook.selectedCellId;
    }
    return false;
});

const parentEntries = computed(() => {
    const isAllTextPlain = props.parentQueryCell?.children?.map((child =>
        child?.outputs?.every(output => {
            if (output?.data !== undefined) {
                const mimetypes = Object.keys(output?.data);
                // if only text/plain is returned
                return output?.output_type === 'execute_result'
                    && mimetypes.length === 1
                    && mimetypes[0] === 'text/plain';
            }
            else {
                return true;
            }
        // only handle cases where every single loop iteration returns only all text/plain
        // to not greedily handle longer agent requests
        }))).every(x => x);
    // omit the list going to vue to hide it
    return isAllTextPlain ? [] : props.parentQueryCell?.children?.entries();
});

const meaningfulOutputs = computed(() => {
    const outputs = [];
    props.parentQueryCell?.children?.entries()?.forEach(([index, child]) => {
        child?.outputs?.forEach(output => {
            const desiredOutputs = ['image/png', 'text/html'];
            const desiredTypes = ['execute_result', 'display_data'];
            if (
                desiredTypes.includes(output?.output_type)
                && desiredOutputs.map(value =>
                    (Object.keys(output?.data ?? [])).includes(value)).some(found => found))
            {
                outputs.push(index);
            }
        });
    });
    return outputs;
})

const getCellModelById = (id): IBeakerCell | undefined => {
    const notebook = beakerSession.session.notebook;
    for (const cell of notebook.cells) {
        const target = (cell.children as IBeakerCell | undefined)?.find(
            child => child.id === id
        );
        if (typeof target !== "undefined") {
            return target;
        }
    }
    return undefined;
}

const isMarkdown = (event: BeakerQueryEvent) => {
    const markdownTypes: BeakerQueryEventType[] = ["response", "user_answer", "user_question"];
    return markdownTypes.includes(event.type);
}

// if the agent response is 'None' rather than any plain text,
// we can assume that was the result of LOOP_SUCCESS returning None,
// in which case the side effect was the main desired output,
// and the agent 'None' can safely be ignored and hidden from the user.
const isValidResponse = (event: BeakerQueryEvent) => {
    if (event.type === "response" && event.content === "None") {
        return false;
    }
    return true;
}

const waitForUserAnswer = (event: BeakerQueryEvent) => {
    return event.type === 'user_question' && event.waitForUserInput;
}

const markdownBody = computed(() =>
    isMarkdown(props.event) ? marked.parse(props.event.content, {async: false}).trim() : "");

function execute() {
    //const future = props.cell.execute(session);
}

defineExpose({
    execute,
});

</script>

<style lang="scss">

.llm-query-event {
    & p {
        margin-bottom: 0rem;
        margin-top: 0rem;
        padding-bottom: 0rem;
        padding-top: 0rem;
    }
}

.query-event-code-cell {
    font-size: 0.75rem;
    padding-top: 1rem;
    padding-bottom: 0.25rem;
}

.output-hide-text {
    font-size: 0.9rem;
    font-style: italic;
}

.agent-response-header {
    padding-left: 0px;
    background: none;
    border: none;
    padding-bottom: 0.5rem;
}

.p-accordion .p-accordion-header a.p-accordion-header-link.agent-response-headeraction  {
    padding-left: 0px;
    background: none;
    border: none;
    padding-top: 1rem;
    padding-bottom: 0;
    svg {
        flex-shrink: 0;
    }
}

a.agent-response-headeraction > span > span.pi {
    align-items: center;
    margin: auto;
    padding-right: 0.25rem;
}

.agent-response-content {
    padding-top: 0rem;
    background: none;
    border: none;
    div.mime-select-container {
        display:none;
    }
}

.agent-response-content-error pre {
    font-size: 0.7rem;
}


.agent-response-content .code-cell-output {
    background: none;
    border: none;
    padding: 0;
}

/* specifically within query cell outputs, make the width hand off to overflow */
/* note - this selector specifically matches the jupyter div, from inside the output,
   only in query cells. not needed anywhere else. preserves highlighting, etc. */
div.agent-response-content
div.code-cell-output
div
div.error
div
div
div
div.lm-Widget.jp-RenderedText.jp-mod-trusted {
    width: 1px;
    font-size: 0.7rem;
}


.agent-outputs {
    font-weight: 400;
    margin-bottom: 0rem;
    font-size: 1.1rem;
}

.md-inline {
    pre {
        overflow-x: auto;
        code {
            display: inline-block;
            font-size: 0.75rem;
        }
    }

    p:first-child {
        padding-top: 0.5rem;
    }
    p:last-child {
        padding-bottom: 0.5rem;
    }
}

.waiting-text {
    display: flex;
    align-items: center;
    gap: 0.25rem;
}

</style>
