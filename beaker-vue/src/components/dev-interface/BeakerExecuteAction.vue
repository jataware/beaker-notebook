<template>
    <div class="execute-action-container">
        <AutoComplete
            class="action-name-input"
            placeholder="Action Name"
            dropdown
            v-model="actionType"
            :suggestions="actionOptions"
            @complete="search"
            @item-select="actionSelected"
            dropdownClass="ac-button"
        />

        <div class="docs">
            <div v-if="selectedActionName">
                <span style="font-weight: bold">{{ selectedActionName }}</span><br/><br/><span>{{ actionDocs }}</span>
            </div>
            <div v-else>
                Select an action to see the docstring...
            </div>
        </div>

        <div class="code">
            Action Payload
            <CodeEditor
                :tab-size="2"
                language="javascript"
                v-model="actionPayload"
            />
        </div>

        <Button
            icon="pi pi-bolt"
            size="small"
            @click="executeAction"
            label="Send"
            iconPos="right"
        />
        <h3>Results:</h3>

        <Fieldset
            legend="Reply"
            :toggleable="true"
        >
            <VueJsonPretty v-if="reply" :data="reply"/>
        </Fieldset>

        <Fieldset
            legend="Response (Optional)"
            :toggleable="true"
        >
            <VueJsonPretty v-if="response" :data="response"/>
        </Fieldset>

        <Fieldset
            legend="Raw Messages (Debug)"
            :toggleable="true"
            :collapsed="true"
        >
            <Panel
                class="log-panel"
                :class="{odd: ((index as number) % 2) !== 0}"
                :data-index="logEntry.timestamp"
                v-for="(logEntry,index) in logEntries" :key="`${logEntry.type}-${logEntry.timestamp}`"
                :header="logEntry.type"
                >
                <vue-json-pretty
                    :data="logEntry.body"
                    :deep="2"
                    showLength
                    showIcon
                    :showDoubleQuotes="true"
                    :showLineNumber="false"
                />
            </Panel>
        </Fieldset>

    </div>

</template>

<script setup lang="ts">
import { ref, computed, inject, watch } from "vue";
import * as messages from '@jupyterlab/services/lib/kernel/messages';
import Button from 'primevue/button';
import AutoComplete from 'primevue/autocomplete';
import Fieldset from 'primevue/fieldset';
import VueJsonPretty from 'vue-json-pretty';
import 'vue-json-pretty/lib/styles.css';
import Panel from 'primevue/panel';

import { BeakerSession } from '@jataware/beaker-client';
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import CodeEditor from '../misc/CodeEditor.vue';

const props = defineProps([
    "actions",
    "rawMessages",
    "selectedAction",
]);

const emit = defineEmits([
    "clearSelection",
])

const session = inject<BeakerSession>('session');
const beakerSession = inject<BeakerSessionComponentType>('beakerSession');
const showToast = inject<any>('show_toast');

const actionType = ref<string>();
const actionPayload = ref<string>("{\n}");
const actionOptions = ref([]);
const actionDocs = ref<string|undefined>();
const selectedActionName = ref<string|undefined>()
const messageNum = ref<number>(1)
const messageId = ref<string|undefined>(undefined);
const response = ref<any>();
const result = ref<any>();
const reply = ref<any>();


const executeAction = () => {
    messageId.value = `beaker-custom-${actionType.value}-${messageNum.value}`;
    messageNum.value += 1;
    const future = session.executeAction(
        actionType.value,
        JSON.parse(actionPayload.value),
        messageId.value,
    );
    future.onResponse = async (msg: messages.IIOPubMessage) => {
        response.value = msg;
    };
    future.onReply = async (msg: messages.IExecuteReplyMsg) => {
        reply.value = msg;
    }
    future.done.then(() => {
        showToast({title: 'Success', detail: 'Message processed.'});
    });
};

const actions = computed(() => {
    if (props.actions !== undefined) {
        return props.actions;
    }
    else {
        return beakerSession.activeContext?.info.actions;
    }
});

const allMessageOptions = computed(() => Object.keys(actions.value));

const search = (event: any) => {
    actionOptions.value = event.query ?
        allMessageOptions.value.filter((item) => item.includes(event.query)) :
        allMessageOptions.value;
};

const actionSelected = (event: any) => {
    selectAction(event.value);
}

const selectAction = (actionName: string) => {
    selectedActionName.value = actionName;
    const selectedAction = actions.value[actionName];
    if (selectedAction === undefined) {
        return;
    }
    if (actionType.value !== actionName) {
        actionType.value = actionName;
    }
    actionPayload.value = selectedAction.default_payload;
    actionDocs.value = selectedAction.docs;
}

const logEntries = computed(() => {
    if (!messageId.value) {
        return [];
    }
    return props.rawMessages.filter((item) => {return (item.body.header?.msg_id === messageId.value || item.body.parent_header?.msg_id === messageId.value)});
});

watch(() => props.selectedAction, async (newValue: string) => {
    if (newValue !== undefined) {
        selectAction(newValue);
        emit("clearSelection");
    }
});

defineExpose({
    selectAction,
});

</script>


<style lang="scss">

.execute-action-container {
    & > *{
        margin-bottom: 1rem;
    }
}

.p-autocomplete-items {
    .p-autocomplete-empty-message {
        padding-left: 1rem;
    }
}

.custom-message {
    .p-fieldset-content {
        width: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-evenly;
        align-items: center;
    }
    .p-autocomplete-input {
        height: 2rem;
    }
}

.action-name-input {
    width: 100%;
}

.code {
    border: 1px solid var(--p-surface-b);
    flex: 1;
    width: 100%;
}

.docs {
    white-space: pre-wrap;

}

</style>
