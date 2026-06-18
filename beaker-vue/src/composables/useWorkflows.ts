import { computed } from 'vue';
import type { ComputedRef } from 'vue';
import type { BeakerSessionComponentType } from '../components/session/BeakerSession.vue';

export interface WorkflowStep {
    prompt: string;
    metadata?: { [key: string]: any };
}

export interface WorkflowStage {
    name: string;
    steps: WorkflowStep[];
    metadata?: { [key: string]: any };
    description?: string[] | null;
}

export interface BeakerWorkflow {
    title: string;
    agent_description: string;
    human_description: string;
    example_prompt: string;
    stages: WorkflowStage[];
    hidden?: boolean;
    is_context_default?: boolean;
    category?: string | null;
    metadata?: { [key: string]: any };
    output_prompt?: string | null;
}

interface UseWorkflowsReturn {
    workflows: ComputedRef<{[key: string]: BeakerWorkflow} | undefined>;
    attachedWorkflowId: ComputedRef<string | undefined>;
    attachedWorkflow: ComputedRef<BeakerWorkflow | undefined>;
    attachedWorkflowProgress: ComputedRef<{[key: string]: {
        state: 'in_progress' | 'finished',
        results_markdown: string
    }} | undefined>;
    attachedWorkflowFinalResponse: ComputedRef<string | undefined>;
}

export function useWorkflows(beakerSession: BeakerSessionComponentType): UseWorkflowsReturn {
    const workflows = computed(() => {
        return beakerSession?.activeContext?.info?.workflow_info?.workflows;
    });

    const attachedWorkflowId = computed(() => {
        return beakerSession?.activeContext?.info?.workflow_info?.state?.workflow_id;
    });

    const attachedWorkflow = computed(() => {
        return workflows.value?.[attachedWorkflowId.value];
    });

    const attachedWorkflowProgress = computed(() => {
        return beakerSession?.activeContext?.info?.workflow_info?.state?.progress;
    });

    const attachedWorkflowFinalResponse = computed(() => {
        return beakerSession?.activeContext?.info?.workflow_info?.state?.final_response;
    })

    return {
        workflows,
        attachedWorkflowId,
        attachedWorkflow,
        attachedWorkflowProgress,
        attachedWorkflowFinalResponse
    };
}
