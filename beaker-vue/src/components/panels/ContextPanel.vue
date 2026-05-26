<template>
    <Tree
        :value="contextNodes"
        :loading="!contextNodes"
        v-model:expandedKeys="contextExpandedKeys"
    >
        <template v-slot:loadingicon>
            <div class="loading-area">
                No Context Loaded.
            </div>
        </template>
        <template #action="slotProps">
            <div
                @mousedown="($event.detail > 1) && $event.preventDefault();"
                @dblclick.stop.prevent="selectAction(slotProps.node.label)"
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

const emits = defineEmits(['action-selected']);
const beakerSession = inject<BeakerSessionComponentType>("beakerSession");

const contextNodes = computed<TreeNode[]>(() => {

    const context = beakerSession?.activeContext?.info;

    if (!context) {
        return [];
    }

    const displayableNodes: TreeNode[] = [{
        key: "0",
        label: 'Kernel',
        icon: 'pi pi-fw pi-cog',
        expanded: true,
        children: [{
            key: '0-1',
            label: `${context.subkernel} (${context.language})`,
        }]
    }, {
        key: "1",
        label: 'Actions',
        icon: 'pi pi-fw pi-send',
        expanded: true,
        children: Object.keys(context.actions).map((action, idx) => {
            return ({
                dblClick: (data) => {
                    // emit("select_action", )
                },
                key: `1-${idx}`,
                label: action,
                data: context.actions[action].docs + "\n\nExample payload:\n" + context.actions[action].default_payload,
                type: 'action',
            })
        })
    }];

    if (context.procedures.length) {
        displayableNodes.push({
            key: "2",
            label: 'Procedures',
            icon: 'pi pi-fw pi-tablet',
            expanded: true,
            children: context.procedures.map((proc, idx) => ({
                key: `2-${idx}`,
                label: proc,
            }))
        });
    }

    displayableNodes.push({
        key: "3",
        label: 'Tools',
        icon: 'pi pi-fw pi-wrench',
        expanded: true,
        children: Object.keys(context?.agent?.tools || {})
            .map((toolname, idx) => ({
                key: `3-${idx}`,
                label: toolname.replace('PyPackageAgent.', ''),
                data: context.agent.tools[toolname],
                type: 'tool'
            }))
    });

    if (Object.keys(context.custom_messages).length) {
        displayableNodes.push({
            key: "4",
            label: 'Custom Messages',
            icon: 'pi pi-fw pi-comment',
            expanded: false,
            children: Object.keys(context.custom_messages).map((msg, idx) => ({
                key: `4-${idx}`,
                label: msg,
                data: context.custom_messages[msg].docs + "\n\nExample payload:\n" + context.custom_messages[msg].default_payload,
                type: 'tool'
            }))
        });
    }

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

const selectAction = (actionName: string) => {
    emits("action-selected", actionName);
}

</script>


<style lang="scss">

.context-heading {
  color: var(--p-text-color-secondary);
  margin: 1rem 1.25rem 0.25rem 1.25rem;
}

.context-tree {
  margin-top: 0.5rem;
  flex: 1;

  border: none;
  width: 21rem;
  position: relative;

  .p-tree {
    border: none;
  }

  .p-tree-wrapper {
    position: absolute;
    left: 1rem;
    top: 0;
    bottom: 0;
    right: 0;

    .p-treenode .p-treenode-content {
      padding: 0;
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
