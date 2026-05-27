<template>
    <div class="media-focus">
        <Toolbar class="media-toolbar">
            <template #start>
                <Button
                    icon="pi pi-arrow-left"
                    class="media-toolbar-button"
                    @click="() => {
                        currentOutput -= Math.min(currentOutput, 1)
                    }"
                />
                <Button
                    icon="pi pi-arrow-right"
                    class="media-toolbar-button"
                    @click="() => {
                        currentOutput += currentOutput >= notebookOutputs.length - 1 ? 0 : 1
                    }"
                />
            </template>
            <template #end>
                <InputGroup>
                    <InputGroupAddon class="media-dropdown-icon">
                        <i class="pi pi-chart-bar"></i>
                    </InputGroupAddon>
                    <Select
                        v-model="currentOutput"
                        :options="Array.from(notebookOutputs.map((_v, i) => {return {label: i + 1, value: i}}))"
                        option-label="label"
                        option-value="value"                    />

                    <InputGroupAddon>/ {{ notebookOutputs.length ?? 0 }}</InputGroupAddon>
                </InputGroup>
            </template>
        </Toolbar>
        <div class="media-mime-bundle">
            <BeakerMimeBundle
                v-if="currentMimeBundle !== undefined"
                :mime-bundle="currentMimeBundle"
                class="code-cell-output"
            />
        </div>
    </div>
</template>

<script lang="ts" setup>
import { ref, inject, computed } from "vue";
import type { BeakerQueryCell, BeakerCodeCell, BeakerSession, IBeakerCell } from '@jataware/beaker-client';
import Toolbar from "primevue/toolbar";
import Button from "primevue/button";
import InputGroup from "primevue/inputgroup";
import InputGroupAddon from "primevue/inputgroupaddon";
import Select from "primevue/select";
import BeakerMimeBundle from "../render/BeakerMimeBundle.vue";

const session = inject<BeakerSession>('session');

const currentOutput = ref(0);

const filteredMimetypes = [
    'image/png',
    'text/html',
]

const notebookOutputs = computed(() => {
    const outputs = [];
    const cells = session.notebook.cells;

    const getOutputs = (cell: IBeakerCell) => {
        const outputs = [];
        // The flattened check ensures we don't duplicate the outputs of the query cell children
        // on new notebook interface
        if (cell.cell_type === 'query' && !cell.metadata?.is_flattened) {
            for (const child of (cell as BeakerQueryCell)?.children ?? []) {
                outputs.push(...getOutputs(child));
            }
        }
        else if (cell.cell_type === 'code') {
            for (const output of (cell as BeakerCodeCell)?.outputs ?? []) {
                const data = output?.data ?? {};
                filteredMimetypes.forEach(mimetype => {
                    if (data[mimetype]) {
                        outputs.push(output);
                    }
                });
            }
        }
        return outputs;
    };

    for (const cell of cells) {
        outputs.push(...getOutputs(cell));
    }

    return outputs;
})

const currentMimeBundle = computed(() => {
    return notebookOutputs?.value?.[currentOutput?.value]?.data;
})

</script>

<style lang="scss">

div.media-toolbar {
    padding: 3px;
    background: var(--p-surface-d);
    border-radius: 0;
    border: none;
    margin-bottom: 0.5rem;
    button {
        width: 2em;
        height: 2em;
        margin-right: 0.5em;
    }
    .p-inputgroup {
        height: 2em;
        .media-dropdown-icon {
            min-width: 2em;
        }

        .p-dropdown-label {
            padding: 0;
            margin: auto;
            padding-left: 0.5rem;
        }

        .p-dropdown-trigger {
            width: 2rem;
        }
    }
}

.media-mime-bundle > div {
    background: none;
    overflow: auto;
    height: 100%;
    > .mime-payload img {
        width: 100%;
    }
}
</style>
