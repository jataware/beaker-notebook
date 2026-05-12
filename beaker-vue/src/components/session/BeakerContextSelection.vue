<template>

    <Panel class="context-selection-panel" header="Context selection">
        <InputGroup>
            <Select
                v-model="selectedContextSlug"
                :options="contextInfo"
                option-label="full_name"
                option-value="slug"
            />

            <Select
                v-model="selectedSubkernelSlug"
                :options="availableSubkernels"
                option-label="display_name"
                option-value="slug"
            />
        </InputGroup>

        <h4 class="h-less-pad">Context Info</h4>

        <div class="code-container">
            <CodeEditor
                :tab-size="2"
                language="javascript"
                v-model="contextPayloadData[selectedContextSlug]"
            />
        </div>

        <div>
            <h4 class="h-less-pad">Logging</h4>
            <div class="flex" style="align-items: center;">
                <div class="labeled-check">
                    <Checkbox v-model="logDebug" inputId="logging-debug-check" binary/>
                    <label for="logging-debug-check" class="ml-1">Debug</label>
                </div>
                <div class="labeled-check ml-2">
                    <Checkbox v-model="logVerbose" inputId="logging-verbose-check" binary />
                    <label for="logging-verbose-check" class="ml-1">Verbose</label>
                </div>
            </div>
        </div>

        <template #footer>
            <div style="width: 100%; text-align: center;">
                <Button
                    raised
                    @click="setContext"
                    label="Apply"
                    size="small"
                />
            </div>
        </template>

    </Panel>
</template>

<script setup lang="ts">

import { ref, onMounted, computed, watch, inject } from "vue";
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';
import Panel from 'primevue/panel';
import InputGroup from 'primevue/inputgroup';
import Select from 'primevue/select';
import Checkbox from 'primevue/checkbox';
import type { BeakerSessionComponentType } from './BeakerSession.vue';
import CodeEditor from '../misc/CodeEditor.vue';
import { type ISubkernelInfo, type IContextInfo } from '../../types/context';
import { BeakerContextServiceKey } from '../../plugins/keys';

const props = defineProps([
    "isOpen",
]);

const logDebug = ref(false);
const logVerbose = ref(false);
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const contextService = inject(BeakerContextServiceKey)!;

const contextInfo = contextService.contextList;
const contextMap = contextService.contextMap;

const emit = defineEmits([
    "update-context-info",
    "context-changed",
    "close-context-selection",
]);


const closeDialog = () => {
    emit("close-context-selection")
};

const activeContextSlug = computed<string | undefined>(() => {
    return beakerSession?.activeContext?.slug;
});

const activeSubkernelSlug = computed<string | undefined>(() => {
    return beakerSession?.activeContext?.info?.subkernel;
});

const activeContext = computed<IContextInfo | undefined>(() => {
    // return contextInfo.value?.find((context) => (context.slug == activeContextSlug.value));
    return contextMap.value[activeContextSlug.value];
});

const selectedContext = computed<IContextInfo | undefined>(() => {
    return contextMap.value?.[selectedContextSlug.value]
})

const activeSubkernel = computed<ISubkernelInfo | undefined>(() => {
    return activeContext.value?.subkernels[activeSubkernelSlug.value];
});

const availableSubkernels = computed<ISubkernelInfo[]>(() => {
    return selectedContext.value ? Object.values(selectedContext.value.subkernels) : [];
});

const selectedContextSlug = ref<string>(activeContextSlug.value);
const selectedSubkernelSlug = ref<string | undefined>(activeSubkernel.value?.slug);
const contextPayloadData = ref<{[key: string]: string}>({});


// When selectedContextSlug dropdown changes, the selected
// language might not be available in the new languageOptions/context
// Ensure to default the selected language for that context to 1st option available
watch(selectedContextSlug, (newSelectedContextSlug: string) => {
    const subkernelOptions = availableSubkernels.value;
    const currentSubkernelSlug = selectedSubkernelSlug.value;
    const availableCount = subkernelOptions.length;

    if(!currentSubkernelSlug || availableCount === 0) {
        return;
    }

    const isSelectedAvailable = subkernelOptions.map(subkernel => subkernel.slug).includes(currentSubkernelSlug);
    if (!isSelectedAvailable) {
        selectedSubkernelSlug.value = availableSubkernels.value?.[0].slug;
    }

        // When changing from active context slug to a different one, set default payload
        // if user has not modified it before (payload data is still empty)
        const existingContextPayload = contextPayloadData.value[newSelectedContextSlug];

        if (!existingContextPayload) {
            console.log("Need to fetch default payload");
        }
    // }
});

const setContext = async () => {
    const isDebug = logDebug.value;
    const isVerbose = logVerbose.value;

    const contextInfo = contextPayloadData.value[selectedContextSlug.value];

    const contextMessageContent = {
      context: selectedContextSlug.value,
      subkernel: selectedSubkernelSlug.value,
      context_info: JSON.parse(contextInfo || ''),
      debug: isDebug,
      verbose: isVerbose,
    };
    emit("context-changed", contextMessageContent);
    emit("close-context-selection")
}

</script>


<style lang="scss">

.context-selection-panel {
    min-width: 40rem;
}

.labeled-check {
    display: flex;
    align-items: center;
}

.ml-2 {
    margin-left: 1rem;
}

.ml-1 {
    margin-left: 0.25rem;
}

.flex {
    display: flex;
}

.h-less-pad {
    margin-block-end: 1rem;
}

.code-container {
    border: 1px solid var(--p-surface-ground);
    padding: 0.25rem;
    max-height: 15rem;
    overflow: auto;
}

</style>
