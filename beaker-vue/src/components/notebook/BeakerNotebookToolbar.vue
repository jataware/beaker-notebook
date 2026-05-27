<template>
    <Toolbar class="notebook-toolbar">
        <template #start>
            <slot name="start">
                <SplitButton
                    @click="notebook.insertCellAfter()"
                    class="toolbar-splitbutton add-cell-button"
                    icon="pi pi-plus"
                    size="small"
                    :severity="props.defaultSeverity"
                    :model="addCellMenuItems"
                    text
                    :pt="{
                        pcButton: {
                            root: {
                                title: 'Add code cell after selection',
                                'aria-label': 'Add code cell after selection'
                            },
                        }
                    }"
                />
                <Button
                    @click="notebook.removeCell()"
                    icon="pi pi-minus"
                    size="small"
                    :severity="props.defaultSeverity"
                    text
                />
                <Button
                    @click="notebook.selectedCell().execute()"
                    icon="pi pi-play"
                    size="small"
                    :severity="props.defaultSeverity"
                    text
                />
                <Button
                    @click="session.interrupt()"
                    icon="pi pi-stop"
                    size="small"
                    :severity="props.defaultSeverity"
                    text
                />
                <div class="truncate-toggle-container"
                        v-tooltip.bottom="{value: 'Collapse agent code cells by default', showDelay: 300}"
                >
                    <ToggleSwitch
                        v-model="truncateAgentCodeCells"
                        inputId="auto-truncate-toggle"
                    />
                    <label for="auto-truncate-toggle" class="truncate-label">Collapse Agent Code</label>
                </div>
                <slot name="start-extra"></slot>
            </slot>
        </template>
        <template #end>
            <slot name="end">
                <AnnotationButton
                    :action="analyzeCells"
                    v-tooltip.bottom="{value: 'Analyze Codecells', showDelay: 300}"
                    size="small"
                    :severity="props.defaultSeverity"
                    text
                />
                <Button
                    @click="resetNotebook"
                    v-tooltip.bottom="{value: 'Reset notebook', showDelay: 300}"
                    icon="pi pi-refresh"
                    size="small"
                    :severity="props.defaultSeverity"
                    text
                />
                <div v-if="props.saveAvailable" class="p-splitbutton toolbar-splitbutton">
                    <Button
                        class="p-splitbutton-defaultbutton"
                        @click="saveNotebook"
                        v-tooltip.bottom="{
                            value: 'Save locally as ' + (saveAsFilename ? saveAsFilename : 'a .ipynb file') ,
                            showDelay: 300
                        }"
                        icon="pi pi-save"
                        size="small"
                        :severity="props.defaultSeverity"
                        text
                    />
                    <Button
                        class="p-splitbutton-menubutton"
                        size="small"
                        :severity="props.defaultSeverity"
                        text
                        @click="saveAsHoverMenuRef.toggle($event);"
                    >
                         <ChevronDownIcon/>
                    </Button>
                    <Popover
                        class="saveas-overlay"
                        ref="saveAsHoverMenuRef"
                        :popup="true"
                        @show="if (!saveAsFilename) {resetSaveAsFilename()};"
                    >
                        <div>Save as:</div>
                        <InputGroup>
                            <InputText
                                class="saveas-input"
                                ref="saveAsInputRef"
                                v-model="saveAsFilename"
                                @keydown.enter="saveAs()"
                                autofocus
                            />
                            <Button label="Save" @click="saveAs()"/>
                        </InputGroup>
                    </Popover>
                </div>
                <SplitButton
                    @click="downloadNotebook"
                    class="toolbar-splitbutton"
                    v-tooltip.bottom="{value: 'Export (download) as .ipynb', showDelay: 300}"
                    icon="pi pi-download"
                    size="small"
                    :model="exportAsTypes"
                    :severity="props.defaultSeverity"
                    text
                />
                <OpenNotebookButton :severity="$props.defaultSeverity" @open-file="loadNotebook"/>
                <slot name="end-extra"></slot>
            </slot>
        </template>
    </Toolbar>
</template>

<script setup lang="ts">
import { computed, inject, ref, capitalize, watch, onBeforeMount, toRaw } from "vue";
import { PageConfig } from '@jupyterlab/coreutils';
import { URLExt } from '@jupyterlab/coreutils';
import type { BeakerSession, BeakerBaseCell } from '@jataware/beaker-client';
import { BeakerNotebook, BeakerCodeCell, BeakerMarkdownCell, BeakerRawCell, BeakerQueryCell } from '@jataware/beaker-client';
import type { BeakerNotebookComponentType } from './BeakerNotebook.vue';
import contentDisposition from "content-disposition";

import Button from "primevue/button";
import ToggleSwitch from "primevue/toggleswitch";
import ChevronDownIcon from '@primevue/icons/chevrondown'
import type { ButtonProps } from "primevue/button";
import SplitButton from 'primevue/splitbutton';
import InputGroup from "primevue/inputgroup";
import InputText from "primevue/inputtext";
import Popover from "primevue/popover";
import Toolbar from "primevue/toolbar";
import type { MenuItem } from "primevue/menuitem";
import { useDialog } from "primevue";

import AnnotationButton from "../misc/buttons/AnnotationButton.vue"
import OpenNotebookButton from "../misc/OpenNotebookButton.vue";
import { downloadFileDOM, getDateTimeString } from '../../util';
import StreamlineExportDialog from "../misc/StreamlineExportDialog.vue"
import { type BeakerSessionComponentType } from "../session/BeakerSession.vue";
import { fetch } from '@/util/fetch';

const session = inject<BeakerSession>('session');
const notebook = inject<BeakerNotebookComponentType>('notebook');
const cellMapping = inject<{[key: string]: {icon: string, modelClass: typeof BeakerBaseCell}} | ((cell: any) => {[key: string]: {icon: string, modelClass: typeof BeakerBaseCell}})>('cell-component-mapping');
const showOverlay = inject<(contents: string, header?: string) => void>('show_overlay');
const dialog = useDialog();

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

interface BeakerNotebookToolbarProps {
    defaultSeverity?: ButtonProps["badgeSeverity"];
    saveAvailable?: boolean;
    saveAsFilename?: string;
    truncateAgentCodeCells?: boolean;
}

const props = withDefaults(defineProps<BeakerNotebookToolbarProps>(), {
    defaultSeverity: "info",
    saveAvailable: false,
    truncateAgentCodeCells: false,
});

const emit = defineEmits([
    "notebook-saved",
    "open-file",
    "update-truncate-preference",
]);

const truncateAgentCodeCells = computed({
    get: () => props.truncateAgentCodeCells,
    set: (value) => {
        emit('update-truncate-preference', value);
    }
});


const addCellMenuItems = computed(() => {
    const cellMap = typeof cellMapping === 'function' ? cellMapping(null) : cellMapping;
    return Object.entries(cellMap).map(([name, obj]) => {
        return {
            label: `${capitalize(name)} Cell`,
            icon: obj.icon,
            command: () => {
                const cell = new obj.modelClass({
                    source: "",
                });
                notebook.insertCellAfter(notebook.selectedCell(), cell, true);
            },
        }
    })
});

const saveAsFilename = ref<string>(props.saveAsFilename);
const saveAsHoverMenuRef = ref();
const saveAsInputRef = ref();

const exportAsTypes = ref<MenuItem[]>([
    {
        label: "Loading...",
        disabled: true,
    }
]);

const handleExport = async (format: string, mimetype: string) => {

    const url = URLExt.join(PageConfig.getBaseUrl(), 'export', format);

    // process the notebook first by cloning and removing events from flattened query cells
    // then create a new BeakerNotebook instance and populate it with processed data
    const processedNotebookData = processNotebookForExport(notebook.notebook);
    const tempNotebook = new BeakerNotebook();
    tempNotebook.fromJSON(processedNotebookData);

    // ensure all cells are proper BeakerBaseCell instances before calling toIPynb
    if (tempNotebook.content.cells && Array.isArray(tempNotebook.content.cells)) {
        tempNotebook.content.cells = tempNotebook.content.cells.map((cell: any) => {
            if (cell.cell_type === 'raw') {
                return new BeakerRawCell(cell);
            } else if (cell.cell_type === 'code') {
                return new BeakerCodeCell(cell);
            } else if (cell.cell_type === 'query') {
                return new BeakerQueryCell(cell);
            } else if (cell.cell_type === 'markdown') {
                return new BeakerMarkdownCell(cell);
            } else {
                return new BeakerRawCell(cell);
            }
        });
    }

    if (format === "full_context_notebook") {
        const history = await session.executeAction("get_agent_history", {}).done;
        tempNotebook.content.metadata.chat_history = history.content.return;
    }

    const exportNotebook = tempNotebook.toIPynb();

    fetch(
        url,
        {
            "method": "POST",
            "body": JSON.stringify({
                name: saveAsFilename.value,
                content: exportNotebook
            }),
            "headers": {
                "Content-Type": "application/json;charset=UTF-8"
            },
        }
    ).then(async (result) => {
        if (result.status === 200) {
            const data = await result.blob();
            const dispositionHeader = result.headers.get("content-disposition")
            const disposition = contentDisposition.parse(dispositionHeader);
            const filename = disposition.parameters.filename;
            downloadFileDOM(data, filename, mimetype)
        }
        else {
            const errorInfo = await result.json();
            showOverlay(errorInfo, "Error converting notebook");
        }
    }).catch((reason) => console.error(reason));
}

const exportAction = async (format: string, mimetype: string) => {
    if (!saveAsFilename.value) {
        resetSaveAsFilename();
    }
    if (format === "streamline") {
        // process the notebook first by cloning and removing events from flattened query cells
        // then create a new BeakerNotebook instance and populate it with processed data
        const processedNotebookData = processNotebookForExport(notebook.notebook);
        const tempNotebook = new BeakerNotebook();
        tempNotebook.fromJSON(processedNotebookData);

        if (tempNotebook.content.cells && Array.isArray(tempNotebook.content.cells)) {
            tempNotebook.content.cells = tempNotebook.content.cells.map((cell: any) => {
                if (cell.cell_type === 'raw') {
                    return new BeakerRawCell(cell);
                } else if (cell.cell_type === 'code') {
                    return new BeakerCodeCell(cell);
                } else if (cell.cell_type === 'query') {
                    return new BeakerQueryCell(cell);
                } else if (cell.cell_type === 'markdown') {
                    return new BeakerMarkdownCell(cell);
                } else {
                    return new BeakerRawCell(cell);
                }
            });
        }

        const exportNotebook = tempNotebook.toIPynb();

        dialog.open(
            StreamlineExportDialog,
            {
                data: {
                    saveAsFilename: saveAsFilename.value,
                    notebook: exportNotebook,
                },
                props: {
                    modal: true,
                    header: "AI-Streamlined Notebook Export"
                }
            }
        );
    }
    else {
        await handleExport(format, mimetype);
    }
}

const processNotebookForExport = (notebookData: any) => {
    const clonedNotebook = JSON.parse(JSON.stringify(notebookData));

    if (clonedNotebook.cells && Array.isArray(clonedNotebook.cells)) {
        clonedNotebook.cells = clonedNotebook.cells.map((cell: any) => {
            // handle query cells with flattened=true metadata - remove events array
            if (cell.cell_type === 'query' && cell.metadata?.is_flattened === true) {
                const { events, ...cellWithoutEvents } = cell;
                return {
                    ...cellWithoutEvents,
                    metadata: {
                        ...cell.metadata,
                        events: undefined
                    }
                };
            }
            return cell;
        });
    }

    if (clonedNotebook.content && clonedNotebook.content.cells && Array.isArray(clonedNotebook.content.cells)) {
        clonedNotebook.content.cells = clonedNotebook.content.cells.map((cell: any) => {
            // handle query cells with flattened=true metadata - remove events array
            if (cell.cell_type === 'query' && cell.metadata?.is_flattened === true) {
                const { events, ...cellWithoutEvents } = cell;
                return {
                    ...cellWithoutEvents,
                    metadata: {
                        ...cell.metadata,
                        events: undefined
                    }
                };
            }
            return cell;
        });
    }

    return clonedNotebook;
};

const refreshExportTypes = async () => {
    const ignoredFormats = new Set(["custom", "qtpdf", "qtpng", "webpdf"]);
    const formats = await session.services.nbconvert.getExportFormats();
    exportAsTypes.value = Object.entries(formats).filter(([format]) => {
        if (ignoredFormats.has(format)) {
            return false;
        }
        return true
    }).map(([format, formatInfo]) => {
        const mimetype = formatInfo.output_mimetype;
        const labelMap: Record<string, string> = {
            asciidoc: "📄 AsciiDoc (.asciidoc)",
            chat: "🤖 Chat (.html)",
            html: "🌐 HTML (.html)",
            latex: "📐 LaTeX (.tex)",
            markdown: "📝 Markdown (.md)",
            notebook: "📓 Notebook (.ipynb)",
            pdf: "📕 PDF (.pdf)",
            python: "🐍 Python (.py)",
            rst: "📄 reStructuredText (.rst)",
            script: "📜 Script (.py)",
            slides: "🖥️ Slides (.html)",
            streamline: "✨ Notebook (AI streamlined)",
            full_context_notebook: "📓 Notebook (full agent context)",
        };
        const label = labelMap[format] ?? format;
        return {
            label,
            sortKey: format,
            tooltip: mimetype,
            command: () => {exportAction(format, mimetype)},
        };
    }).sort((a, b) => a.sortKey.localeCompare(b.sortKey));
};

onBeforeMount(async () => {
    refreshExportTypes();
})

watch(props, (oldValue, newValue) => {
    if (saveAsFilename.value !== newValue.saveAsFilename) {
        saveAsFilename.value = newValue.saveAsFilename;
    }
});

const resetSaveAsFilename = () => {
    saveAsFilename.value = `Beaker-Notebook_${getDateTimeString()}.ipynb`;
}

const analyzeCells = async () => {
    const payload = {
        notebook_id: notebook.id,
        cells: notebook.notebook.cells.map(cell => {return {cell_id: cell.id, content: cell.source}}),
    };
    const lintAction = session.executeAction("lint_code", payload)
    await lintAction.done;
}

const resetNotebook = async () => {
    if (window.confirm(`This will reset your entire session, clearing the notebook and removing any updates to the environment. Proceed?`)) {
        const currentContextPayload = {
            context: beakerSession.activeContext?.slug,
            language: beakerSession.activeContext?.language?.slug,
            context_info: beakerSession?.activeContext?.config ?? {},
            debug: beakerSession?.activeContext?.info?.debug,
            verbose: beakerSession?.activeContext?.info?.verbose,
        };

        toRaw(session).reset();

        await session.sessionReady;
        beakerSession.setContext(currentContextPayload)

        saveAsFilename.value = undefined;
        emit("notebook-saved", undefined);
        if (notebook.cellCount <= 0) {
            notebook.selectCell(session.addCodeCell("") as {id: string});
        }
    }
};

function loadNotebook(notebookJSON: any, filename: string) {
    emit("open-file", notebookJSON, filename);
}

async function saveNotebook() {
    const notebookContent = session.notebook.toIPynb();
    const contentsService = session.services.contents;
    if (!saveAsFilename.value) {
        resetSaveAsFilename();
    }
    const path = `./${saveAsFilename.value}`;
    const result = await contentsService.save(path, {
        type: "notebook",
        content: notebookContent,
        format: 'text',
    });
    emit("notebook-saved", result.path);
    saveAsFilename.value = result.path;
}

async function saveAs() {
    await saveNotebook();
    saveAsHoverMenuRef.value.hide();

}

function downloadNotebook() {
    const processedNotebookData = processNotebookForExport(notebook.notebook);
    const tempNotebook = new BeakerNotebook();
    tempNotebook.fromJSON(processedNotebookData);

    if (tempNotebook.content.cells && Array.isArray(tempNotebook.content.cells)) {
        tempNotebook.content.cells = tempNotebook.content.cells.map((cell: any) => {
            if (cell.cell_type === 'raw') {
                return new BeakerRawCell(cell);
            } else if (cell.cell_type === 'code') {
                return new BeakerCodeCell(cell);
            } else if (cell.cell_type === 'query') {
                return new BeakerQueryCell(cell);
            } else if (cell.cell_type === 'markdown') {
                return new BeakerMarkdownCell(cell);
            } else {
                return new BeakerRawCell(cell);
            }
        });
    }

    const exportNotebook = tempNotebook.toIPynb();

    const data = new Blob([JSON.stringify(exportNotebook, null, 2)]);

    const filename = `Beaker-Notebook_${getDateTimeString()}.ipynb`;
    const mimeType = 'application/x-ipynb+json';
    downloadFileDOM(data, filename, mimeType);
}

</script>


<style lang="scss">
.notebook-toolbar {
    margin: 0;
    padding: 0;
    *:focus {
        box-shadow: none !important;
    }

    .toolbar-splitbutton {
        .p-splitbutton-defaultbutton {
            padding-right: 0;
        }

        .p-splitbutton-dropdown {
            padding-left: 0;
            padding-top: 0;
            padding-bottom: 0.5rem;
            width: min-content;

            .p-icon, .p-button-icon {
                height: 0.7rem;
                font-size: 0.875rem;;
            }
        }
    }

    .truncate-toggle-container {
        display: none; // don't display in other interfaces
        align-items: center;
        gap: 0.5rem;
        margin-left: 0.75rem;

        .truncate-label {
            font-size: 0.875rem;
            color: var(--p-text-color);
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }
    }
}

.saveas-overlay {
    .p-overlaypanel-content {
        padding: 0.5rem;
    }
    .saveas-input {
        min-width: 25rem;
        padding: 0.25rem;
        font-size: small;
        font-family: 'Courier New', Courier, monospace;
    }
}
</style>
