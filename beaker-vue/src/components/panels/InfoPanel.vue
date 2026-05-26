<template>
    <div class="info-panel-container">
    <!-- <Accordion :multiple="true">
        <AccordionTab header="Kernel/System">
            <h3>Kernel</h3> -->
            <!-- <div><label>Display name</label>{{ activeContext.kernelInfo.display_name }}</div> -->
            <!-- <div><label>Language</label>{{ kernelInfo.language }}</div>
            <div><label>Metadata</label>{{ kernelInfo.metadata }}</div>
            <div><label>Extra</label>{{ kernelInfo.extra }}</div> -->



            <!-- <div>{{activeContext}}</div>

        </AccordionTab>
        <AccordionTab header="Context">

        </AccordionTab>
        <AccordionTab header="Agent">

        </AccordionTab>
    </Accordion> -->
    <Tree
        :value="contextNodes"
        :loading="!contextNodes"
        v-model:expandedKeys="contextExpandedKeys"
        :pt="{
            root: { class: 'context-tree', },
            nodeContent: { style: { padding: '0' } }
        }"
    >
        <template v-slot:loadingicon>
            <div class="loading-area">
                No Context Loaded.
            </div>
        </template>
        <template #action="slotProps">
            <div
                @mousedown="($event.detail > 1) && $event.preventDefault();"
                style="cursor: pointer; border-bottom: 1px dotted var(--p-text-color-secondary);"
                v-tooltip="{
                    value: `${slotProps.node.data}`,
                    pt: {
                        text: {
                            style: {
                                width: '20rem'
                            }
                        },
                        root: {
                            style: {
                                marginLeft: '1rem'
                            }
                        }
                    }
                    }"
                >
                {{ slotProps.node.label }}
            </div>
        </template>
        <template #tool="slotProps">
            <span
                style="cursor: help; border-bottom: 1px dotted var(--p-text-color-secondary);"
                v-tooltip="{
                    value: `${slotProps.node.data}`,
                    pt: {
                        text: {
                            style: {
                                width: '20rem'
                            }
                        },
                        root: {
                            style: {
                                marginLeft: '1rem'
                            }
                        }
                    }
                    }"
                >
                {{ slotProps.node.label }}
            </span>
        </template>
    </Tree>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch } from "vue";
import Tree from 'primevue/tree';
import type { TreeNode } from 'primevue/treenode';
import type { BeakerSessionComponentType } from '../session/BeakerSession.vue';

const contextPanelOpen = ref(true);
const toggleContextPanel = () => {
    contextPanelOpen.value = !contextPanelOpen.value;
};

const beakerSession = inject<BeakerSessionComponentType>("beakerSession");
const activeContext = computed(() => {
    const contextInfo = beakerSession?.activeContext;
    const kernelInfo = beakerSession?.session.kernelInfo;
    return {
        ...contextInfo,
        kernelInfo,
    };
});

const contextNodes = computed<TreeNode[]>(() => {

    const context = activeContext.value;

    if (!context) {
        return [];
    }

    const displayableNodes: TreeNode[] = [{
        key: "0",
        label: 'Kernel',
        icon: 'pi pi-fw pi-cog',
        expanded: true,
        children: [
            {
                key: '0-1',
                label: `${context?.info?.subkernel} (${context?.info?.language})`,
            },
            // ...Object.entries(context?.kernelInfo || {}).map(
            //     ([key, value]) => {
            //         return {
            //             key: `0-${key}`,
            //             label: `${key}: ${value}`,
            //         }
            //     }
            // ),
    ]
    }];

    if (context?.info?.workflow_info && Object.keys(context?.info?.workflow_info?.workflows ?? []).length > 0) {
        const { workflows, state } = context.info.workflow_info;
        displayableNodes.push({
            key: "5",
            label: 'Workflows',
            icon: 'pi pi-fw pi-list-check',
            expanded: true,
            children: Object.keys(workflows).map((workflow_id) => ({
                key: `5-${workflow_id}`,
                label: `${workflows[workflow_id].title}${state?.workflow_id === workflow_id ? " (Active)" : ""}`,
            }))
        });
    }

    displayableNodes.push({
        key: "3",
        label: 'Tools',
        icon: 'pi pi-fw pi-wrench',
        expanded: true,
        children: Object.keys(context?.info?.agent?.tools || {})
            .map((toolname, idx) => ({
                key: `3-${idx}`,
                label: toolname.replace('PyPackageAgent.', ''),
                data: context.info.agent.tools[toolname],
                type: 'tool'
            }))
    });

    return displayableNodes;

});

// Seeded from contextNodes' `expanded` flags so we don't hard-code numeric keys;
// kept as a ref (not computed) so the user can collapse/expand interactively.
const contextExpandedKeys = ref<Record<string, boolean>>({});
watch(contextNodes, (nodes) => {
    contextExpandedKeys.value = Object.fromEntries(
        nodes.filter(node => node.expanded).map(node => [node.key, true])
    );
}, { immediate: true });

</script>


<style lang="scss">

.context-heading {
  color: var(--p-text-color-secondary);
  margin: 1rem 1.25rem 0.25rem 1.25rem;
}

.context-tree {

  &.p-tree {
    border: none;
    padding: 0.5rem var(--p-tree-padding);

    .p-tree-root {
        overflow-x: hidden;
    }
  }
}

.context-toggle-button {
  position: absolute;
  right: -0.5rem;
  top: 40%;
  background: var(--p-surface-a);
  border-color: var(--p-surface-e);
  color: var(--p-primary-300);
  z-index: 2;
}

.button-rotate {
  transform: rotate(180deg);
}

.loading-area {
    background: var(--p-surface-a);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    right: 0;
}

.hidden {
    visibility: hidden;
}


</style>
