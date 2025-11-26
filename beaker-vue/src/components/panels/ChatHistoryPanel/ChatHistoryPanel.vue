<template>
    <div class="chat-history-panel">
        <div class="chat-history-model">
            <div class="model-info">
                <h4>Current model</h4>
                <div class="model-specs" style="display: grid; grid-template-columns: max-content auto; column-gap: 1rem; row-gap: 0.5rem;">
                    <div class="model-spec-label">Model Provider:</div>
                    <div>{{ props.chatHistory?.model?.provider }}</div>
                    <div class="model-spec-label">Model Name:</div>
                    <div>{{ props.chatHistory?.model?.model_name }}</div>
                    <div v-if="props.chatHistory?.model?.context_window" class="model-spec-label">Context window:</div>
                    <div v-if="props.chatHistory?.model?.context_window">{{ props.chatHistory?.model?.context_window.toLocaleString() }} tokens</div>
                </div>
            </div>
        </div>
        <div class="context-window-usage">
            <h4 >Context window usage</h4>
            <div class="progress-bar-container">
                <div class="progress-bar">
                    <span class="progress-bar-usage overhead" :style="{width: `${overheadUsagePct}%`}"></span>
                    <span class="progress-bar-usage summary" :style="{width: `${summaryUsagePct}%`}"></span>
                    <span class="progress-bar-usage message" :style="{width: `${messageUsagePct}%`}"></span>
                </div>
                <div style="width: 2px; height: 100%; background-color: var(--p-orange-600); position: absolute; top: 0;" :style="{left:`${summarizationThresholdLowPct}%`}"></div>
                <div style="width: 2px; height: 100%; background-color: var(--p-red-600); position: absolute; top: 0;" :style="{left: `85%`}"></div>
                <div style="width: 100%; position: absolute; top: 1%; text-align: center;">
                    {{ usageLabel }}
                </div>
            </div>
            <div class="progress-bar-map">
                <div
                    class="progress-bar-map-row overhead"
                    v-tooltip="'Tokens used in tool definitions, subkernel state, etc. (estimated)'"
                >
                    <span class="progress-bar-map-circle overhead"></span>
                    Estimated token overhead:
                    <span>{{ displayNumber(roundToFiveHundred(chatHistory?.overhead_token_count)) }}</span>
                </div>
                <div
                    class="progress-bar-map-row summary"
                    v-tooltip="'Token used by summaries. (estimated)'"
                >
                    <span class="progress-bar-map-circle summary"></span>
                    Estimated summarized token usage:
                    <span>{{ displayNumber(roundToFiveHundred(chatHistory?.summary_token_count)) }}</span>
                </div>
                <div
                    class="progress-bar-map-row message"
                    v-tooltip="'Tokens used by all unsummarized messages. (estimated)'"
                >
                    <span class="progress-bar-map-circle message"></span>
                    Estimated message token usage:
                    <span>{{ displayNumber(roundToFiveHundred(chatHistory?.message_token_count)) }}</span>
                </div>
                <div
                    class="progress-bar-map-row total"
                    v-tooltip="'Total tokens of current conversational history, favoring summaries. (estimated)'"
                >
                    <span class="progress-bar-map-circle total"></span>
                    Estimated total token usage:
                    <span>{{ displayNumber(roundToFiveHundred(totalTokenCount)) }}</span>
                </div>
            </div>
            <!-- <div class="context-window-usage-config" style="display: inline-flex; gap: 1em">
                <span>
                    Soft limit:
                    <Knob v-model="summarizationThresholdLowPct" :size="60"/>
                </span>
                <span>
                    Hard limit:
                    <Knob :model-value="85" :size="60"/>
                </span>
            </div> -->
        </div>
        <h4>Messages</h4>
        <div class="add-message-section" v-if="showPreambleInput">
            <div class="add-message-input">
                <textarea
                    v-model="preambleText"
                    placeholder="Add a preamble message to chat history..."
                    rows="3"
                    class="message-textarea"
                ></textarea>
            </div>
            <div class="add-message-actions">
                <Button
                    @click="clearPreamble"
                    severity="danger"
                >
                    Clear Message
                </Button>
                <Button
                    @click="setPreamble"
                    :disabled="!preambleText.trim()"
                    class="save-message-btn"
                    severity="success"
                >
                    Save Message
                </Button>
            </div>
        </div>
        <div class="chat-history-records">
            <ChatHistoryMessage
                v-for="record, index in props.chatHistory?.records"
                :key="record.uuid"
                :record="record"
                :idx="index"
                :tool-call-message="getToolCallForRecord(record)"
            />
        </div>
    </div>
</template>

<script lang="ts" setup>

import { ref, computed, inject, watch } from "vue";
import ChatHistoryMessage from "./ChatHistoryMessage.vue";
import Button from "primevue/button";
import type { BeakerSessionComponentType } from "../../session/BeakerSession.vue";


export interface IMessage {
    content: string | (string | {[key: string]: any})[];
    responseMetadata: {[key: string]: any};
    type: string;
    name?: string;
    id?: string;
    additionalKwargs?: {[key: string]: any};
    tool_calls?: any[];
    tool_call_id?: string;
}

interface IRecordBase {
    message: IMessage;
    uuid: string;
    token_count?: number;
    metadata?: {[key: string]: any};
}

export interface IMessageRecord extends IRecordBase{
    reactLoopId?: number;

}
export interface ISummaryRecord extends IRecordBase {
    summarizedMessages: string[];
}

export type RecordType = IMessageRecord | ISummaryRecord;

export interface IChatHistory {
    records: RecordType[];
    systemMessage?: string;
    toolTokenUsageEstimate?: number;
    token_estimate?: number;
    message_token_count?: number;
    summary_token_count?: number;
    model: {
        provider: string;
        model_name: string;
        context_window?: number;

    };
    overhead_token_count?: number;
    summarization_threshold?: number;
}

export interface ChatHistoryProps {
    chatHistory: IChatHistory;
}

const props = defineProps<ChatHistoryProps>()

const showPreambleInput = ref<boolean>(false);
const preambleText = ref('');
const beakerSession = inject<BeakerSessionComponentType>('beakerSession');
const showToast: (...args) => void = inject('show_toast');

const clearPreamble = async () => {
    const action = beakerSession.session.executeAction(
        "set_user_preamble",
        { message_text: "" }
    );
    const reply = await action.done;
    if (reply?.content?.status === "ok") {
        preambleText.value = '';
        showToast({title: 'Upload complete', detail: "Preamble message cleared", severity: 'success', life: 4000});
    }
    else {
        showToast({title: 'Upload complete', detail: "Error clearing preamble message.", severity: 'error', life: 4000});
    }
};


const setPreamble = async () => {
    if (preambleText.value.trim() && beakerSession?.session) {
        const action = beakerSession.session.executeAction(
            "set_user_preamble",
            { message_text: preambleText.value.trim() }
        );
        const reply = await action.done;
        console.log({response: reply});
        if (reply?.content?.status === "ok") {
            preambleText.value = '';
            showToast({title: 'Upload complete', detail: "Preamble message set.", severity: 'success', life: 4000});
        }
        else {
            showToast({title: 'Upload complete', detail: "Error setting preamble message.", severity: 'error', life: 4000});
        }
    }
};


const contextWindowUsage = computed(() => {
    const contextWindow = props.chatHistory?.model?.context_window;
    const usageEstimate = props.chatHistory?.token_estimate;
    if(contextWindow && usageEstimate) {
        const pct = usageEstimate/contextWindow;
        // Round to 1 decimal spot
        return Math.round(pct * 1000) / 10;
    }
    else {
        return null;
    }
})

const contextWindowSize = computed(() => props.chatHistory?.model?.context_window);
const overheadUsagePct = computed(() => Math.round((props.chatHistory?.overhead_token_count / contextWindowSize.value) * 1000) / 10);
const messageUsagePct = computed(() => Math.round((props.chatHistory?.message_token_count / contextWindowSize.value) * 1000) / 10);
const summaryUsagePct = computed(() => Math.round((props.chatHistory?.summary_token_count / contextWindowSize.value) * 1000) / 10);
const summarizationThresholdLowPct = computed({
    get() { return Math.round((props.chatHistory?.summarization_threshold / contextWindowSize.value) * 1000) / 10},
    set(value) {console.log(value)},
});
const totalTokenCount = computed<number>(() => (
        props.chatHistory?.overhead_token_count
        + props.chatHistory?.message_token_count
        + props.chatHistory?.summary_token_count
));

const usageLabel = computed<string>(() => {
    const rawSum = totalTokenCount.value;
    const roundedSum = displayNumber(roundToFiveHundred(rawSum));
    const contextWindowSizeK = displayNumber(roundToFiveHundred(contextWindowSize.value));
    return `${ contextWindowUsage.value?.toLocaleString() }% (~ ${roundedSum} / ${contextWindowSizeK})`;
})

const getToolCallerMessage = (toolCallId: string) => {
    return props.chatHistory?.records?.map(record => record.message).find(message => {
        return message.type === "ai" && message.tool_calls?.map(tc => tc.id).includes(toolCallId);
    })
}

const getToolCallForRecord = (record: RecordType) => {
    if (record?.message?.tool_call_id) {
        return getToolCallerMessage(record.message.tool_call_id)
    }
}

const roundToFiveHundred = (rawValue: number): number => {
    return Math.round(rawValue / 500) * 0.5
}

const displayNumber = (rawValue: number): string => {
    let label = 'k';
    let value: string = rawValue.toLocaleString();
    if (rawValue >= 1000) {
        label = 'M';
        value = (rawValue / 1000).toFixed(2);
    }
    return `${value.toLocaleString()}${label}`
}

</script>

<style lang="scss">
.chat-history-panel {
    padding: 0 0.5rem;
    position: relative;
}

.context-window-usage {
    padding-left: 0.5rem;
}

.progress-bar-container {
    position: relative;
}

.overhead {
    --p-context-color: var(--p-gray-500);
}

.summary {
    --p-context-color: var(--p-blue-900);
}

.message {
    --p-context-color: var(--p-blue-600);
}

.total {
    --p-context-color: var(--p-primary-color);
}

.progress-bar-map {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;

    .progress-bar-map-row {
        display: inline-flex;
        flex-direction: row;
        align-items: center;
        gap: 0.5rem;
        width: fit-content;
        padding-right: 0.5rem;
    }

    .progress-bar-map-circle {
        display: inline-block;
        width: 1.5rem;
        height: 1.5rem;
        border-radius: 1.5rem;
        background-color: var(--p-context-color);
    }
}

.progress-bar {
    width: 100%;
    height: 1.5rem;
    border-radius: 0.5rem;
    background-color: var(--p-surface-d);
    overflow: hidden;
    margin-bottom: 0.5rem;

    .progress-bar-usage {
        display: inline-block;
        height: 100%;
        background-color: var(--p-context-color);
    }
}

.debug-panel-wrapper {
    // The internal class for the json viewer-
    // Change the hover color for better contrast
    .vjs-tree-node:hover {
        background-color: var(--p-surface-b);
    }
    height: 100%;
    width: 100%;
    overflow-y: auto;
}

.debug-flex-container {
    display: flex;
    align-items: center;
    margin-bottom: 0.5rem;
    justify-content: space-between;
    flex-wrap: wrap;
}

.debug-log-container {
    padding: 0.5rem;
}

.debug-bottom-actions {
    width: 100%;
    display: flex;
    margin-top: 0.5rem;
    justify-content: center;
    color: var(--p-text-color-secondary);
}

.debug-sort-actions {
    display: flex;
    flex-direction: row;
    .p-button {
        border-color: var(--p-surface-d);
    }
}

.model-info {
    padding-left: 0.5rem;

    & h4 {
        margin-top: 0.2rem;
    }
}

.model-specs {
    padding-left: 1rem;
}

.model-spec-label {
    text-decoration: underline;
}


.chat-history-panel h4 {
    font-size: 110%;
    margin-bottom: 0.5em;
}

.chat-history-records {
    margin-left: 0.5em;
}

.add-message-section {
    margin: 1rem 0.5rem;
    padding: 1rem;
    border: 1px solid var(--p-surface-d);
    border-radius: 0.5rem;
    background-color: var(--p-surface-a);
}

.add-message-input {
    margin-bottom: 0.75rem;
}

.message-textarea {
    width: 100%;
    min-height: 80px;
    padding: 0.75rem;
    border: 1px solid var(--p-surface-c);
    border-radius: 0.375rem;
    background-color: var(--p-surface-0);
    color: var(--p-text-color);
    font-family: inherit;
    font-size: 0.875rem;
    line-height: 1.4;
    resize: vertical;

    &:focus {
        outline: none;
        border-color: var(--p-primary-color);
        box-shadow: 0 0 0 1px var(--p-primary-color);
    }

    &::placeholder {
        color: var(--p-text-color-secondary);
    }
}

.add-message-actions {
    display: flex;
    justify-content: flex-end;
}

.save-message-btn {
    margin-left: 0.5rem;
}
</style>
