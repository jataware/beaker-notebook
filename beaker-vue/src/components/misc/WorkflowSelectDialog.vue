<template>
    <div class="workflow-dialog">
        <p>
            Workflows are pre-configured approaches for the LLM agent to use for guidance
            on tackling larger problems using tried-and-true to-do lists of tasks. One workflow
            may be active at a time for framing the agent's thoughts towards a particular goal.
        </p>
        <Divider></Divider>
        <div class="attached-workflow">
            <div v-if="attachedWorkflow">
                <p class="attached-label">Currently Active:</p>
                <div class="attached-workflow-inner">
                    <Button
                        @click="clear"
                        label="Clear"
                        icon="pi pi-times"
                        small
                    >
                    </Button>
                    <span class="attached-label">
                        {{ attachedWorkflow.title }}
                    </span>
                </div>
            </div>
            <p v-else class="attached-label" style="margin: 0">No workflow active.</p>
            <InputGroup style="margin: auto 0 0 auto; width: 50%">
                <InputGroupAddon>
                    <i class="pi pi-search"></i>
                </InputGroupAddon>
                <InputText placeholder="Search Workflows..." v-model="searchText">
                </InputText>
                <Button
                    v-if="searchText !== undefined && searchText !== ''"
                    icon="pi pi-times"
                    severity="danger"
                    @click="() => {searchText = undefined}"
                    v-tooltip="'Clear Search'"
                />
            </InputGroup>
        </div>
        <Divider></Divider>

        <div class="workflow-content">
            <div class="workflow-list">
                <Card
                    v-for="workflow, id in searchResults"
                    class="workflow-card"
                    :class="{
                        'selected-card': selectedWorkflowId === id,
                        'current-card': id === attachedWorkflowId
                    }"
                    @click="selectWorkflow(id)"
                    @mouseleave="hoveredCard = undefined"
                    @mouseenter="hoveredCard = id"
                >
                    <template #title>{{ workflow.title }}</template>
                    <template #subtitle>
                        <div class="card-badges">
                            <Badge v-if="id === attachedWorkflowId" value="Current" severity="success" />
                            <Chip v-if="workflow.category" :label="workflow.category" class="p-chip-sm" />
                        </div>
                    </template>
                    <template #content>
                        <p>{{ workflow.human_description }}</p>
                        <small class="text-muted">{{ workflow.stages?.length || 0 }} stages</small>
                    </template>
                </Card>
            </div>

            <div class="workflow-preview" v-if="selectedWorkflow">
                <!-- Scrollable content area -->
                <div class="preview-content-scrollable">
                    <Card class="preview-card">
                        <template #title>{{ selectedWorkflow.title }}</template>
                        <template #subtitle>
                            <div class="flex gap-2 mt-2">
                                <Chip v-if="selectedWorkflow.category" :label="selectedWorkflow.category" />
                                <Badge :value="`${selectedWorkflow.stages?.length || 0} stages`" severity="info" />
                            </div>
                        </template>
                        <template #content>
                            <div class="preview-content">
                                <div class="section">
                                    <h4>Description</h4>
                                    <p>{{ selectedWorkflow.human_description }}</p>
                                </div>

                                <Divider v-if="selectedWorkflow.example_prompt" />
                                <div v-if="selectedWorkflow.example_prompt" class="mb-4">
                                    <h4 class="text-lg font-semibold mb-2">Example Usage</h4>
                                    <div class="bg-surface-100 border border-surface-200 rounded p-3 font-mono text-sm">
                                        {{ selectedWorkflow.example_prompt }}
                                    </div>
                                </div>

                                <Divider v-if="selectedWorkflow.stages?.length" />
                                <div v-if="selectedWorkflow.stages?.length" class="section">
                                    <h4>Workflow Stages</h4>
                                    <div class="stages-list">
                                        <div v-for="(stage, index) in selectedWorkflow.stages" :key="index" class="stage-item">
                                            <span class="stage-number">{{ index + 1 }}</span>
                                            <span class="stage-name">{{ stage.name }}</span>
                                        </div>
                                    </div>
                                </div>
                                <!-- Add some bottom padding to ensure content doesn't get hidden behind floating button -->
                                <div style="height: 80px;"></div>
                            </div>
                        </template>
                    </Card>
                </div>

                <!-- Floating action gutter - positioned absolutely within the preview panel -->
                <div class="floating-action-gutter">
                    <Button
                        :label="selectedWorkflowId === attachedWorkflowId ? 'Already Active' : `Start ${selectedWorkflow.title}`"
                        :disabled="selectedWorkflowId === attachedWorkflowId"
                        @click="confirmSelection"
                        icon="pi pi-play"
                        class="select-button"
                        size="large"
                    />
                </div>
            </div>

            <div class="workflow-preview empty-preview" v-else>
                <Card class="preview-card">
                    <template #content>
                        <div class="empty-state">
                            <i class="pi pi-arrow-left" style="font-size: 2rem; color: var(--p-surface-400);"></i>
                            <p>Select a workflow to see details</p>
                        </div>
                    </template>
                </Card>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { computed, inject, ref, watch, type ComputedRef } from "vue";
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';
import { Button, Divider, Card, InputGroup, InputGroupAddon, InputText, Chip, Badge } from "primevue";
import { type BeakerSession } from "beaker-kernel";
import { useWorkflows } from '../../composables/useWorkflows';

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const session = inject<BeakerSession>('session');
const dialogRef: ComputedRef = inject('dialogRef');

const hoveredCard = ref<undefined|string>(undefined);
const selectedWorkflowId = ref<undefined|string>(undefined);
const searchText = ref<undefined|string>(undefined);

const setWorkflow = (id?: string) => {
    // convert undefined to null as well so undefined doesn't get in json body
    session.executeAction('set_workflow', {workflow: id ? id : null});
    dialogRef.value.close();
}

const selectWorkflow = (id: string) => {
    selectedWorkflowId.value = id;
}

const confirmSelection = () => {
    if (selectedWorkflowId.value) {
        setWorkflow(selectedWorkflowId.value);
    }
}

const clear = () => setWorkflow(null);

const { workflows, attachedWorkflowId, attachedWorkflow } = useWorkflows(beakerSession);

const selectedWorkflow = computed(() => {
    if (!selectedWorkflowId.value || !workflows.value) return null;
    return workflows.value[selectedWorkflowId.value];
});

const searchResults = computed<{[key in string]: any}>(() => {
    if (!workflows.value) return {};
    return Object.fromEntries(
        Object.entries(workflows.value).filter(([_, workflow]) =>
            searchText.value === ""
            || searchText.value === undefined
            || [
                workflow.human_description,
                workflow.title,
                workflow.category
            ].join(' ').toLocaleLowerCase().includes(searchText.value.toLocaleLowerCase()))
    );
});

</script>

<style scoped>
.workflow-dialog {
    display: flex;
    flex-direction: column;
    width: 80vw;
    max-width: 1200px;
    height: 80vh;
    max-height: 800px;
}

.attached-workflow {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.attached-workflow-inner {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.attached-label {
    font-weight: 600;
}

.workflow-content {
    display: flex;
    flex: 1;
    gap: 1.5rem;
    min-height: 0;
}

.workflow-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    overflow-y: auto;
    padding-right: 0.5rem;
}

.workflow-card {
    cursor: pointer;
    transition: all 0.15s ease;
    border: 2px solid transparent;
    margin-top: 0.25rem;
}

.workflow-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.workflow-card.selected-card {
    border-color: var(--p-primary-color);
    background: var(--p-primary-50);
}

.workflow-card.current-card {
    border-color: var(--p-green-500);
    background: var(--p-green-50);
}

.card-badges {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-top: 0.25rem;
}

.workflow-preview {
    flex: 1.2;
    min-width: 400px;
    position: relative;
}

.preview-content-scrollable {
    height: 100%;
    overflow-y: auto;
}

.preview-card {
    height: auto;
    margin: 0.25rem;
}

.floating-action-gutter {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    z-index: 1000;
    background: var(--p-surface-0);
    padding: 1rem;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    border: 1px solid var(--p-surface-200);
}

.select-button {
    min-width: 200px;
}

.empty-state {
    text-align: center;
    color: var(--p-text-color-secondary);
}

.section {
    margin-bottom: 1.5rem;
}

.section h4 {
    margin: 0 0 0.5rem 0;
    color: var(--p-text-color);
    font-size: 1rem;
    font-weight: 600;
}

.section p {
    margin: 0;
    line-height: 1.5;
    color: var(--p-text-color-secondary);
}

.stages-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.stage-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem;
    background: var(--p-surface-50);
    border-radius: 4px;
    border-left: 3px solid var(--p-primary-300);
}

.stage-number {
    background: var(--p-primary-color);
    color: white;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    font-weight: 600;
    flex-shrink: 0;
}

.stage-name {
    font-weight: 500;
    color: var(--p-text-color);
}

/* Responsive */
@media (max-width: 1000px) {
    .workflow-dialog {
        width: 95vw;
        height: 90vh;
    }

    .workflow-content {
        flex-direction: column;
    }

    .workflow-list {
        max-height: 40vh;
    }

    .workflow-preview {
        min-width: unset;
        flex: 1;
    }

    .sticky-footer-absolute {
        padding: 0.75rem;
    }
}

/* Utility classes (if not available in PrimeVue) */
.flex { display: flex; }
.flex-col { flex-direction: column; }
.gap-2 { gap: 0.5rem; }
.gap-3 { gap: 0.75rem; }
.items-center { align-items: center; }
.mt-2 { margin-top: 0.5rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-3 { margin-bottom: 0.75rem; }
.mb-4 { margin-bottom: 1rem; }
.p-2 { padding: 0.5rem; }
.p-3 { padding: 0.75rem; }
.rounded { border-radius: 0.375rem; }
.border { border-width: 1px; }
.border-l-4 { border-left-width: 4px; }
.font-mono { font-family: monospace; }
.font-medium { font-weight: 500; }
.font-semibold { font-weight: 600; }
.text-sm { font-size: 0.875rem; }
.text-lg { font-size: 1.125rem; }
.text-muted { color: var(--p-text-color-secondary); }
.w-6 { width: 1.5rem; }
.h-6 { height: 1.5rem; }
.rounded-full { border-radius: 9999px; }
.bg-surface-50 { background-color: var(--p-surface-50); }
.bg-surface-100 { background-color: var(--p-surface-100); }
.border-surface-200 { border-color: var(--p-surface-200); }
.border-primary-300 { border-color: var(--p-primary-300); }
</style>
