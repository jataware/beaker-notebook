<template>
    <div v-if="config" class="config-panel">
        <div class="config-panel-container">
            <ConfigEntryComponent
                :key="nonce.toString()"
                :schema="schema"
                v-model="inputModel"
                key-value="config"
                :config-object="config.config"
            />
        </div>
        <div>
            <Button
                @click="save"
                label="Save"
                style="margin-right: 1rem;"
            />
            <Button
                @click="reset"
                label="Reset"
            />
        </div>
    </div>
    <div v-else class="loading">
        <h2>Loading...</h2>
        <ProgressSpinner/>

    </div>
</template>

<script setup lang="ts">
import { ref, onBeforeMount, inject, nextTick } from "vue";
import Button from "primevue/button";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import ConfigEntryComponent from '../misc/ConfigEntryComponent.vue'
import { useConfirm } from "primevue/useconfirm";
import ProgressSpinner from "primevue/progressspinner";
import { BeakerFetchClientKey } from '../../plugins/keys';

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const fetchClient = inject(BeakerFetchClientKey)!;


const config = ref<IConfig>();
const schema = ref<ISchema>();
const inputModel = ref<object>({});
const undoHistory = ref<string[]>();
const confirm = useConfirm();
const nonce = ref<number>(0);

const emit = defineEmits([
    "restartSession"
])

const save = async () => {
    const confirmationText = `You are about to update ${config.value.config_type} '${config.value.config_id}'.\nProceed?`;
    confirm.require({
        message: confirmationText,
        header: "Apply Changes",
        accept: async () => {
            const result = await saveConfig(beakerSession, fetchClient, schema.value, inputModel.value, config.value.config);
            const updatedConfig = await result.json();
            config.value = updatedConfig;
            inputModel.value = Object.assign({}, tablifyObjects(schema.value, updatedConfig.config));
            nextTick(() => {nonce.value++;})
            if (result.ok) {
                confirm.require({
                    header: "Restart Session",
                    message: "Restart kernel to apply changes?\n\nYour notebook contents will not be affected, \
but chat history will be lost and cells will need to be rerun.",
                    accept: () => {
                        emit("restartSession")
                    },
                });
            }
        },
    })
}

const reset = async () => {
    const {schema: schemaJson, config: configJson} = await getConfigAndSchema(beakerSession, fetchClient);
    schema.value = schemaJson;
    config.value = configJson;
    inputModel.value = Object.assign({}, tablifyObjects(schemaJson, configJson.config));
    undoHistory.value = [JSON.stringify(inputModel.value)];
    nextTick(() => {nonce.value++;})
}

onBeforeMount(() => {
    beakerSession.session.sessionReady.then(async () => {
        reset();
    });
})

</script>

<script lang="ts">

export interface IConfig {
    config_type: string;
    config_id: string;
    config: IConfigDefinitions
}

export interface ISchema {
    [key: string]: any;
    type_str: string;
}

export interface IConfigDefinitions {
    [key: string]: any;
}


export function objectifyTables(schema: ISchema, obj: unknown) {
    // Make sure to recurse through types that can hold other types
    if (schema.type_str.startsWith('Dataclass')) {
        const output = {};
        for (const key of Object.keys(schema.fields)) {
            const value = obj[key];
            const childSchema = schema.fields[key];
            output[key] = objectifyTables(childSchema, value);
        }
        return output
    }
    else if (schema.type_str.startsWith('Table') && Array.isArray(obj)) {
        return Object.fromEntries(
            obj.map((entryObj) => {
                return [entryObj.name, objectifyTables(schema.type_args[0], entryObj.value)]
            })
        );
    }
    else {
        return obj;
    }
}

export function tablifyObjects(schema: ISchema, obj: unknown) {
    if (schema.type_str.startsWith('Dataclass')) {
        const output = {};
        for (const key of Object.keys(schema.fields)) {
            const value = obj[key];
            const childSchema = schema.fields[key];
            output[key] = tablifyObjects(childSchema, value);
        }
        return output
    }
    else if (schema.type_str.startsWith('Table')) {
        return Object.entries(obj).map(
            ([k, v]) => {
                return {
                    name: k,
                    value: tablifyObjects(schema.type_args[0], v)
                }
            }
        );
    }
    else {
        return obj;
    }
}

export function dropUnchangedValues(schema: ISchema, currentConfig: IConfig, originalConfig: IConfig) {
    if (schema.type_str.startsWith('Dataclass')) {
        const output = {};
        for (const key of Object.keys(schema.fields)) {
            const value = currentConfig[key];
            const childSchema = schema.fields[key];
            const original = originalConfig && originalConfig[key];
            const newValue = dropUnchangedValues(childSchema, value, original);
            output[key] = newValue;
        }
        return output;
    }
    else if (schema.type_str.startsWith('Table')) {
        const output = {};
        for (const [key, value] of Object.entries(currentConfig)) {
            const newValue = dropUnchangedValues(schema.type_args[0], value, originalConfig[key]);
            output[key] = newValue;
        }
        return output;
    }
    else {
        return (currentConfig === originalConfig) ? null : currentConfig
    }

}

export async function getConfigAndSchema(beakerSession, fetchClient) {
    const serverSettings = beakerSession.session.services.serverSettings;
    const configUrl = `${serverSettings.baseUrl}config/control`;
    const schemaUrl = configUrl + '?schema';
    const configFuture = fetchClient.fetch(configUrl);
    const schemaFuture = fetchClient.fetch(schemaUrl);
    const configResponse = await configFuture
    const schemaResponse = await schemaFuture
    const config = await configResponse.json();
    const schema = await schemaResponse.json();
    return {config, schema}
}

export async function saveConfig(beakerSession, fetchClient, schema: ISchema, inputModel, config) {
    const serverSettings = beakerSession.session.services.serverSettings;
    const configUrl = `${serverSettings.baseUrl}config/control`;
    const updatedConfig = dropUnchangedValues(
        schema,
        objectifyTables(schema, inputModel),
        config,
    );
    if (updatedConfig === null) {
        return;
    }
    const configPostFuture = fetchClient.fetch(configUrl, {
        method: "POST",
        body: JSON.stringify(updatedConfig),
    })

    const result = await configPostFuture;
    return result;
}

</script>


<style lang="scss">

.config-panel {
    padding: 1rem;
}

.config-panel-container {
    padding-bottom: 0.5rem;
}

.loading {
    text-align: center;
    position: relative;
    top: 30%;
}

</style>
