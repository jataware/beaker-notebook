<template>
    <div class="workflow-container">
        <p v-if="!attachedWorkflow">
            No workflow selected. Select one above or ask the agent about which workflow could work for your task.
        </p>
        <Tabs
            v-else
            v-model:value="activeTab"
            class="workflow-output-tabs"
        >
            <TabList>
                <Tab v-for="(stage, index) in stageViews" :key="stage.name" :value="index" :class="{ 'in-progress':  stage.state === 'in_progress'}">
                    <span class="tab-label" :class="{ 'tab-label-pending': !stage.filled}">
                        Stage {{ index + 1 }}
                    </span>
                    <ProgressSpinner
                        v-if="stage.state === 'in_progress'"
                        class="stage-pending-spinner"
                        aria-label="Stage in progress"
                    />
                </Tab>
                <Tab :key="'final-report'" :value="stageViews.length">
                    <span class="tab-label" :class="{ 'tab-label-pending': !hasFinalReport }">
                        Final Report
                    </span>
                </Tab>
            </TabList>
            <TabPanels>
                <TabPanel v-for="(stage, index) in stageViews" :key="stage.name" :value="index">
                    <div class="stage-section p-steppanel">
                        <h3 class="stage-section-header">{{ stage.name }}</h3>
                        <div
                            v-if="stage.filled"
                            class="stage-section-body"
                            v-html="stage.html"
                            @click="handleImageClick"
                        ></div>
                        <p v-else class="stage-pending">
                            <span>{{ stage.state === 'in_progress' ? 'In progress…' : 'Not yet started.' }}</span>
                        </p>
                    </div>
                </TabPanel>
                <TabPanel :key="'final-report'" :value="stageViews.length">
                    <div class="final-response p-steppanel" v-html="finalResponse" @click="handleImageClick">
                    </div>
                </TabPanel>
            </TabPanels>
        </Tabs>
    </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from "vue";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import { useWorkflows } from '../../composables/useWorkflows';
import { marked } from "marked";
import Tabs from "primevue/tabs";
import TabList from "primevue/tablist";
import Tab from "primevue/tab";
import TabPanels from "primevue/tabpanels";
import TabPanel from "primevue/tabpanel";
import ProgressSpinner from "primevue/progressspinner";
import { ImageZoomDialog } from "../render";
import { useDialog } from "primevue";

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const { attachedWorkflow, attachedWorkflowProgress, attachedWorkflowFinalResponse } = useWorkflows(beakerSession);

const activeTab = ref<number>(0);

// Strip lines that are only pipes/whitespace — keeps malformed markdown tables from
// rendering stray empty rows. Mirrors the cleanup the final report has always used.
const renderMarkdown = (source: string): string => {
    const cleaned = source.split('\n').filter(line => !line.match(/^[|\s]+$/)).join('\n');
    return marked.parse(cleaned) as string;
};

const hasFinalReport = computed(() => Boolean(attachedWorkflowFinalResponse.value?.trim()));

// One view-model per workflow stage, in definition order (matches the left panel's
// stepper numbering). Tabs are pre-generated; `filled`/`html` populate as results arrive.
const stageViews = computed(() => {
    const progress = attachedWorkflowProgress.value ?? {};
    return (attachedWorkflow.value?.stages ?? []).map((stage) => {
        const entry = progress[stage.name];
        const markdown = entry?.results_markdown ?? "";
        const filled = Boolean(markdown.trim());
        return {
            name: stage.name,
            state: entry?.state,
            filled,
            html: filled ? renderMarkdown(markdown) : "",
        };
    });
});

const finalResponse = computed(() => {
    let response = `${attachedWorkflowFinalResponse.value ?? ""}`;
    if (response.trim() === "") {
        response = "### No workflow output yet\nThis tab will show the final report once the workflow completes."
    }
    return renderMarkdown(response);
})

// Follow progress: jump to the Final Report once it arrives, otherwise to the latest
// stage that has filled-in output. Falls back to the first stage before anything lands.
watch([attachedWorkflowProgress, attachedWorkflowFinalResponse], () => {
    if (hasFinalReport.value) {
        activeTab.value = stageViews.value.length; // Final Report is the trailing tab.
        return;
    }
    const latestFilled = stageViews.value.reduce(
        (acc, stage, index) => (stage.filled ? index : acc),
        -1,
    );
    activeTab.value = latestFilled >= 0 ? latestFilled : 0;
}, { deep: true });

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

.workflow-output-tabs {
    // Pending (unfilled) stage tabs and the not-yet-ready Final Report tab read lighter
    // than completed ones.
    .p-tab {
        display: flex;
        align-items: end;
        gap: 0.25rem;

        &.in-progress {
            padding-right: .25rem;
            padding-left: 1rem;
        }

        .tab-label-pending {
            opacity: 0.75;
        }
        &:not(.p-tab-active) .tab-label-pending {
            color: var(--p-text-muted-color);
        }

        .stage-pending-spinner {
            width: 1rem;
            height: 1rem;
            margin: 0;
            opacity: 1;
        }
    }

    // Shared markdown styling for both the per-stage views and the final report.
    .final-response,
    .stage-section-body {
        h1 { font-size: 1.3rem; }
        h2 { font-size: 1.2rem; }
        h3 { font-size: 1.10rem; }
        h4 { font-size: 1.05rem; }
        br,hr { width: 100%; }

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

    .final-response,
    .stage-section {
        padding: 0.5rem;
    }

    .stage-section-header {
        font-size: 1.5rem;
        font-weight: bold;
        text-decoration: underline;
        margin: 0 0 0.5rem 0;
    }

    .stage-pending {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--p-text-muted-color);

        .stage-pending-spinner {
            width: 1.25rem;
            height: 1.25rem;
            margin: 0;
        }
    }
}

</style>
