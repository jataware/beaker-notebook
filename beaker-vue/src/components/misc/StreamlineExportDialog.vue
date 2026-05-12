<template>
    <div class="streamline-dialog">
        <p>
            Streamline uses an AI agent to do a pass over the notebook for clarity,
            making agent interactions feel more like a comprehensive and cohesive notebook.
            This may take up to several minutes for longer notebooks.
        </p>
        <div class="streamline-name">
            <label for="notebookname">Notebook Name</label>
            <InputGroup>
                <InputText id="notebookname" style="display: flex; margin: auto" autocomplete="off" v-model="saveAsFilename"/>
                <InputGroupAddon>.ipynb</InputGroupAddon>
            </InputGroup>
        </div>
        <Divider></Divider>

        <div class="streamline-options">
            <div
                v-tooltip="`Enable additional options for streamlining, like collapsing outputs and code cells by default.`"
            >
                <label for="additionalStreamlineOptions">Additional Options</label>
                <ToggleSwitch inputId="additionalStreamlineOptions" v-model="additionalStreamlineOptions"/>
            </div>
            <div
                class="indented-option"
                v-if="additionalStreamlineOptions"
                v-tooltip="`Collapse code cells by default, which may be expanded using the toggle button on the left-hand side of the Jupyter pane.`"
            >
                <label for="hidecode">Collapse Code Cells</label>
                <ToggleSwitch inputId="hidecode" v-model="streamlineExportOptions.collapseCodeCells"/>
            </div>
            <div
                class="indented-option"
                v-if="additionalStreamlineOptions"
                v-tooltip="`Collapse outputs by default (excluding plots and figures), which may be expanded using the toggle button on the left-hand side of the Jupyter pane.`"
            >
                <label for="hidecharts">Collapse Outputs</label>
                <ToggleSwitch inputId="hidecharts" v-model="streamlineExportOptions.collapseOutputs"/>
            </div>
        </div>
        <Divider></Divider>

        <div v-if="streamlineExportRunning">
            <ProgressSpinner></ProgressSpinner>
            <span>Exporting...</span>
            <Divider></Divider>
        </div>


        <div class="streamline-buttons">
            <Button type="button" label="Cancel" severity="secondary" @click="dialogRef.close()"></Button>
            <Button type="button" label="Export Notebook" @click="
                streamlineExportRunning = true;
                handleStreamlineExport('streamline', 'application/json', streamlineExportOptions)"
            ></Button>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { onMounted, inject, ref, watch, type ComputedRef } from "vue";
import { ProgressSpinner, Button, Divider, ToggleSwitch, InputGroup, InputGroupAddon, InputText } from "primevue";
import { getDateTimeString, downloadFileDOM } from "../../util";
import { PageConfig, URLExt } from '@jupyterlab/coreutils';
import contentDisposition from "content-disposition";
import { BeakerFetchClientKey } from '../../plugins/keys';

const showOverlay = inject<(contents: string, header?: string) => void>('show_overlay');
const fetchClient = inject(BeakerFetchClientKey)!;

const dialogRef: ComputedRef = inject('dialogRef');

const streamlineExportRunning = ref<boolean>(false)
watch (streamlineExportRunning, value => {
    if (!value) {
        dialogRef.value.close();
    }
})

const additionalStreamlineOptions = ref<boolean>(false);
watch(additionalStreamlineOptions, value => {
    if (!value) {
        streamlineExportOptions.value = {
            collapseCodeCells: false,
            collapseOutputs: false,
        };
    }
})
const streamlineExportOptions = ref<{
    collapseCodeCells: boolean,
    collapseOutputs: boolean,
}>({
    collapseCodeCells: false,
    collapseOutputs: false,
});

const saveAsFilename = ref<string>("")
const notebook = ref();

onMounted(() => {
    saveAsFilename.value = dialogRef.value.data.saveAsFilename;
    notebook.value = dialogRef.value.data.notebook;
})

const resetSaveAsFilename = () => {
    saveAsFilename.value = `Beaker-Notebook_${getDateTimeString()}.ipynb`;
}

const handleStreamlineExport = (format: string, mimetype: string, options?: object) => {
    streamlineExportRunning.value = true;
    const url = URLExt.join(PageConfig.getBaseUrl(), 'export', format);
    if (!saveAsFilename.value) {
        resetSaveAsFilename();
    }
    fetch(
        url,
        {
            "method": "POST",
            "body": JSON.stringify({
                name: saveAsFilename.value,
                content: notebook.value,
                options: options ?? {}
            }),
            "headers": {
                "Content-Type": "application/json;charset=UTF-8"
            },
        }
    ).then(async (result) => {
        if (result.status === 200) {
            const data = new Blob([await result.text()]);
            const dispositionHeader = result.headers.get("content-disposition")
            const disposition = contentDisposition.parse(dispositionHeader);
            const filename = disposition.parameters.filename;
            downloadFileDOM(data, filename, mimetype)
        }
        else {
            const errorInfo = await result.json();
            showOverlay(errorInfo, "Error converting notebook");
        }
    }).catch((reason) => console.error(reason))
      .finally(() => {
        streamlineExportRunning.value = false;
        dialogRef.value.close();
    });
}

</script>

<style>
.streamline-dialog {
    width: 40rem;
    label {
        font-weight: 600;
        flex-shrink: 0;
    }
    .streamline-name {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-top: 1rem;
    }
    .streamline-options {
        display: flex;
        flex-direction: column;
        width: fit-content;
        gap: 1rem;
        > div {
            display: flex;
            justify-content: space-between;
            label {
                margin-right: 2rem;
            }
            .p-toggleswitch {
                margin: auto 0 auto auto;
            }
        }
    }
    .streamline-buttons {
        display: flex;
        justify-content: end;
        gap: 1rem;
    }
    .indented-option {
        margin-left: 2rem;
    }
}
</style>
