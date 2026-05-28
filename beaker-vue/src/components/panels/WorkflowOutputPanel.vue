<template>
    <div class="workflow-container">
        <p v-if="!attachedWorkflow">
            No workflow selected. Select one above or ask the agent about which workflow could work for your task.
        </p>

        <div v-if="hasContent" class="export-button-container">
            <button
                @click="exportToDocx"
                :disabled="isExporting"
                class="export-button"
                title="Export to DOCX"
            >
                <i v-if="!isExporting" class="pi pi-download"></i>
                <i v-else class="pi pi-spin pi-spinner"></i>
                <span class="export-button-text">{{ isExporting ? 'Exporting...' : 'Export DOCX' }}</span>
            </button>
        </div>

        <div ref="finalResponseElement" class="final-response p-steppanel" v-html="finalResponse" @click="handleImageClick">

        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from "vue";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import { useWorkflows } from '../../composables/useWorkflows';
import { marked } from "marked";
import { DocumentExporter } from '../../utils/exportUtils';
import { ImageZoomDialog } from "../render";
import { useDialog } from "primevue";

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const { attachedWorkflow, attachedWorkflowFinalResponse } = useWorkflows(beakerSession);

const finalResponseElement = ref<HTMLElement>();
const isExporting = ref(false);

const finalResponse = computed(() => {
    const workflow_response = attachedWorkflowFinalResponse.value;
    let response = `${workflow_response}`;
    if (response === "") {
        response = "### No workflow output yet\nThis panel will be populated as the workflow stages complete."
    }
    response = response.split('\n').filter(line => !line.match(/^[|\s]+$/)).join('\n');
    const parsedResponse = marked.parse(response);
    
    return parsedResponse;
});

const hasContent = computed(() => {
    const workflow_response = attachedWorkflowFinalResponse.value;
    return workflow_response && workflow_response.trim() !== "";
});

const exportToDocx = async () => {
    if (!finalResponseElement.value || !hasContent.value) {
        return;
    }

    isExporting.value = true;

    try {
        const exporter = new DocumentExporter();
        const title = attachedWorkflow.value?.title || 'Workflow Output';
        await exporter.exportToDocx(finalResponseElement.value, title);
    } catch (error) {
        console.error('Error exporting DOCX:', error);
    } finally {
        isExporting.value = false;
    }
};

const dialog = useDialog();
const overlay = ref();
const handleImageClick = (event: MouseEvent) => {
    const target = event.target as HTMLElement;
    if (target.tagName.toLowerCase() === 'img') {
        event.preventDefault();
        event.stopPropagation();
        const img = target as HTMLImageElement;
        overlay.value = dialog.open(
            ImageZoomDialog,
            {
                // Data used within the dialog to render the image.
                data: {
                    imageSrc: img.src,
                    imageAlt: img.alt || 'Zoomed image',
                },
                props: {
                    modal: true,
                    draggable: false,
                    showHeader: false,
                    closeButtonProps: {
                        class: "my-close-props",
                    },
                    style: {
                        width: "95vw",
                        maxHeight: "calc(95vh - 3rem)",
                        height: "100%",
                        position: "relative",
                        top: "1.5rem",
                    },
                    contentStyle: {
                        display: "flex",
                        flex: "1",
                        padding: "var(--p-overlay-modal-padding)",
                    }
                }
            }
        );
    }
};

</script>

<style lang="scss">

.export-button-container {
    position: absolute;
    top: 5px;
    right: 0.75rem;
    z-index: 10;
}

.export-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background-color: var(--p-primary-color);
    color: var(--p-primary-contrast-color);
    border: none;
    border-radius: var(--p-border-radius);
    cursor: pointer;
    transition: all 0.3s;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;

    &:hover:not(:disabled) {
        background-color: var(--p-primary-hover-color);
    }

    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    i {
        font-size: 1rem;
        flex-shrink: 0;
    }

    .export-button-text {
        display: inline;
        transition: opacity 0.3s;
    }
}

.workflow-container {
    container-type: inline-size;
    container-name: workflow-panel;
}

// Hide text when container is narrow (less space)
@container workflow-panel (max-width: 600px) {
    .export-button {
        padding: 0.5rem;
        
        .export-button-text {
            display: none;
        }
    }
}

// Keep text visible for all other sizes (medium and large)
@container workflow-panel (min-width: 601px) {
    .export-button {
        .export-button-text {
            display: inline;
        }
    }
}

.final-response {
    h1 { font-size: 1.3rem; }
    h2 { font-size: 1.2rem; }
    h3 { font-size: 1.10rem; }
    h4 { font-size: 1.05rem; }
    br,hr { width: 100%; }
    padding: 0.5rem;

    table {
        table-layout: fixed;
        margin: 0 auto;
        border-collapse: collapse;
        border: 1px solid var(--p-datatable-body-cell-border-color);
        tbody tr:nth-child(odd) {
            background-color: var(--p-datatable-row-background);
        }
        tbody tr:nth-child(odd) {
            background-color: var(--p-datatable-row-striped-background);
        }
    }

    th,
    td {
        padding: 0.2rem;
        border: 1px solid var(--p-datatable-body-cell-border-color);
    }

    img {
        border-radius: 0.25rem;
        max-width: 100%;
        cursor: pointer;
        transition: box-shadow 0.6s ease;
        padding: 1px;

        &:hover {
            box-sizing: border-box;
            box-shadow: inset 0 0 0 1px var(--p-surface-500);
        }
    }
}

</style>
