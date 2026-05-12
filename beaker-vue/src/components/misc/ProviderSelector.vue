<template>
    <div id="provider-select">
        <div v-if="props.configType !== 'server' && config?.config_type !== 'server'" id="provider-select-container" class="config-option">
            <div id="provider-select-selector">
                <Listbox v-model="inputModel.provider" :options="providerNames"/>
            </div>
            <div id="provider-select-providers">
                <ConfigEntryComponent
                    :schema="providerSchema"
                    v-model="selectedProviderValue"
                    key-value="config.providers"
                    :config-object="inputModel"
                />
            </div>
            <div class="list-buttons">
                <Button icon="pi pi-plus" @click="saveAsHoverMenuRef.toggle($event)" severity="info"/>
                <Popover
                    class="saveas-overlay"
                    ref="saveAsHoverMenuRef"
                    :popup="true"
                >
                    <div>Provider name</div>
                    <InputGroup>
                        <InputText
                            class="newProviderName-input"
                            ref="newProviderNameInputRef"
                            v-model="newProviderName"
                            @keydown.enter="addProvider()"
                            autofocus
                        />
                        <Button label="Save" @click="addProvider()"/>
                    </InputGroup>
                </Popover>
                <Button icon="pi pi-trash" :disabled="!inputModel.provider" @click="removeProvider" severity="danger"/>
            </div>
            <div class="dialog-buttons">
                <Button
                    @click="reset()"
                    label="Reset"
                    severity="warning"
                />
                <Button
                    @click="closeDialog()"
                    label="Cancel"
                    severity="danger"
                />
                <Button
                    @click="save(false)"
                    label="Save"
                    severity="success"
                />
            </div>
        </div>
        <div v-else>
            <h3>Please contact the system administrator to resolve the above issue(s) with the LLM provider or service.</h3>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onBeforeMount, inject, computed, nextTick } from "vue";
import Button from "primevue/button";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import ConfigEntryComponent from '../misc/ConfigEntryComponent.vue'
import Listbox from "primevue/listbox";
import { useConfirm } from "primevue/useconfirm";
import {
    getConfigAndSchema,
    tablifyObjects,
    saveConfig,
    type IConfig,
    type IConfigDefinitions,
    type ISchema,
} from "../panels/ConfigPanel.vue";
import InputGroup from "primevue/inputgroup";
import InputText from "primevue/inputtext";
import Popover from "primevue/popover";
import { BeakerFetchClientKey } from '../../plugins/keys';

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const fetchClient = inject(BeakerFetchClientKey)!;

const saveAsHoverMenuRef = ref()
const config = ref<IConfig>();
const schema = ref<ISchema>();
const inputModel = ref<IConfigDefinitions>({});
const undoHistory = ref<string[]>();
const confirm = useConfirm();
const newProviderName = ref<string>();
const newProviderNameInputRef = ref();

const props = defineProps([
    "configType",
])

const defaultProviderFactory = () => {
    if (providerSchema.value) {
        return Object.fromEntries(
            Object.entries(providerSchema.value.fields).map(([key, value]) => {return [key, (value as any).default_value]})
        )
    }
    else {
        return {};
    }
}

const selectedProviderName = computed((): string => (inputModel.value.provider as string));
const providerNames = computed((): string[] => {
    const providers: {name: string, value: object}[] = (Array.isArray(inputModel.value?.providers) ? inputModel.value.providers : []);
    if (selectedProviderName.value && !providers.map(obj => obj.name).includes(selectedProviderName.value)) {
        providers.splice(0, 0, {name: selectedProviderName.value, value: defaultProviderFactory()});
    }
    return inputModel.value?.providers?.map(obj => obj.name);
});
const providerSchema = computed<ISchema>(() => {
    return schema.value?.fields.providers.type_args[0];
});
const selectedProviderValue = computed({
    get() {
        if (!inputModel.value) {
            return defaultProviderFactory();
        }
        const providers = (
            Array.isArray(inputModel.value.providers)
            ? Object.fromEntries(inputModel.value?.providers?.map(obj => [obj.name, obj.value]))
            : {}
        );
        if (Object.hasOwn(providers, selectedProviderName.value)) {
            return providers[selectedProviderName.value];
        }
        else {
            return defaultProviderFactory();
        }
    },
    set(_newValue) {
        // pass
    }
});

const emit = defineEmits([
    "setAgentModel",
    "closeDialog",
])

const save = async (override = false) => {
    if (!inputModel.value.provider && !override) {
        confirm.require({
            message: "Without a provider selected, you will\nnot be able to use the Beaker Agent.",
            header: "Warning: No provider selected",
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Proceed',
            rejectLabel: 'Cancel',
            accept: () => {
                nextTick(() => save(true));
            },
        });
    }
    else {
        let confirmationText: string;
        let callback;
        if (config.value.config_type === "file") {
            confirmationText = `You are about to update file '${config.value.config_id}'.\nProceed?`;
            callback = async () => {
                const result = await saveConfig(beakerSession, fetchClient, schema.value, inputModel.value, config.value.config);
                if (result.ok) {
                    emit("setAgentModel", selectedProviderValue.value, true);
                    emit("closeDialog");
                }
            }
        }
        else if (config.value.config_type === "session") {
            confirmationText = `You are about to set the configuration for this session only. No values will be saved.\nProceed?`;
            callback = async () => {
                emit("setAgentModel", {
                    provider_id: selectedProviderName.value,
                    model_config: selectedProviderValue.value,
                }, true);
                emit("closeDialog");
            }
        }
        confirm.require({
            message: confirmationText,
            header: "Apply Changes",
            accept: callback,
        })
    }
}

const reset = async () => {
    const {schema: schemaJson, config: configJson} = await getConfigAndSchema(beakerSession, fetchClient);
    schema.value = schemaJson;
    config.value = configJson;
    inputModel.value = Object.assign({}, tablifyObjects(schemaJson, configJson.config));
    undoHistory.value = [JSON.stringify(inputModel.value)];
}

const addProvider = () => {
    const providerName = newProviderName.value;
    if (!inputModel.value.providers.map(obj => obj.name).includes(providerName)) {
        inputModel.value.providers.push({
            name: providerName,
            value: defaultProviderFactory(),
        });
        saveAsHoverMenuRef.value.hide();
        newProviderName.value = "";
        nextTick(() => {
            inputModel.value.provider = providerName;
        })
    }
}

const removeProvider = () => {
    const idx = (inputModel.value.providers as any[]).findIndex((value) => {
        return value.name === inputModel.value.provider;
    });
    inputModel.value.provider = "";
    inputModel.value.providers.splice(idx, 1);
}

const closeDialog = () => {
    emit("closeDialog");
}

onBeforeMount(() => {
    beakerSession.session.sessionReady.then(async () => {
        reset();
    });
})

</script>


<style lang="scss">

#provider-select {
    height: 40vh;
    width: 50vw;
}

#provider-select-container {
    width: 100%;
    height: 100%;
    display: grid;
    grid: "selector provider" calc(100% - 3rem)
          "selector-buttons dialog-buttons" 3rem /
            minmax(30%, max-content) 1fr;
}

#provider-select-selector {
    grid-area: selector;
    padding-bottom: 1rem;

    & .p-listbox {
        height: 100%;
    }

    & .p-listbox-list-wrapper {
        height: 100%;
        overflow-y: auto;
    }
}

#config-panel-provider {
    grid-area: provider;
    background-color: blue;
}

.p-listbox-item {
    position: relative;
    padding-left: 2rem;

    &.p-highlight::before {
       position: absolute;
       left: 0.75rem;
       content: "✔";
    }
}

.list-buttons {
    grid-area: selector-buttons;
    & Button:not(:last-of-type) {
        margin-right: 0.5rem;
    }
}

.dialog-buttons {
    grid-area: dialog-buttons;
    text-align: right;
    & Button:not(:first-of-type) {
        margin-left: 1rem;
    }
}

</style>
