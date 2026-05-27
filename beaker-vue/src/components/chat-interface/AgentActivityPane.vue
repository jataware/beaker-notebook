<template>
  <div class="thoughts-pane">
    <div v-if="!activeQueryCell">
      <span v-if="props.isChatEmpty">
         Start a conversation to view Beaker's activity as you interact with it.
      </span>
      <em v-else>Select <i class="pi pi-search magnifier-reference"></i> agent activity from the conversation to view details.</em>
    </div>
    <div v-else class="thoughts-pane-content">
      <div class="pane-actions">
        <Button
          icon="pi pi-arrow-circle-right"
          text
          @click="scrollToMessage"
          v-tooltip.bottom="'Scroll to related user message.'"
        />
      </div>
      <div class="events-scroll-container" v-autoscroll>
        <div v-if="shouldShowNoThoughtsPlaceholder" class="no-thoughts-message">
          <em>No agent activity from this query.</em>
        </div>
        <ChatQueryCellEvent
          v-else
          v-for="(event, eventIndex) in filteredCellEvents"
          :key="`${eventIndex}-${activeQueryCell.id}`"
          :event="event"
          :parent-query-cell="activeQueryCell"
        />
      </div>

      <div v-if="isActiveQueryCellInProgress" class="progress-area">
        <ProgressBar  mode="indeterminate" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue';
import ProgressBar from 'primevue/progressbar';
import Button from 'primevue/button';
import ChatQueryCellEvent from './ChatQueryCellEvent.vue';
import { type IBeakerCell } from "@jataware/beaker-client";
import { isLastEventTerminal } from "../cell/cellOperations";

const emit = defineEmits<{
  (e: 'scrollToMessage'): void
}>();

const props = defineProps<{
  isChatEmpty: boolean
}>();

const activeQueryCell = inject<IBeakerCell | null>('activeQueryCell');

const isActiveQueryCellInProgress = computed(() => {
  return !isLastEventTerminal(activeQueryCell.value?.events || []);
});

const activeQueryCellEvents = computed(() => {
  if (!activeQueryCell.value) {
    return null;
  }
  return activeQueryCell.value?.events || [];
});

const scrollToMessage = () => {
  emit('scrollToMessage');
}

const filteredCellEvents = computed(() => {
  if (!activeQueryCellEvents.value) return [];

  return activeQueryCellEvents.value.filter(event => {
    return !["user_answer", "response"].includes(event.type);
  })
  .map((event, index, all_events) => {
    const isLastEvent = index === all_events.length - 1;
    // if user_question event is last, add marker for unanswered question
    const unansweredQuestion = event.type === 'user_question' && isLastEvent;
    if (unansweredQuestion && isActiveQueryCellInProgress.value) {
      return {
        ...event,
        waitForUserInput: true
      }
    }
    return event;
  })
});

const shouldShowNoThoughtsPlaceholder = computed(() => {
  if (!activeQueryCellEvents.value || isActiveQueryCellInProgress.value) {
    return false;
  }

  // Check if query is complete (idle) and has only a response event
  const hasOnlyResponse = activeQueryCellEvents.value.length === 1 &&
    activeQueryCellEvents.value[0].type === 'response';

  return activeQueryCell.value?.status === 'idle' && hasOnlyResponse;
});

</script>

<style scoped lang="scss">
.thoughts-pane {
  padding: 1rem;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.thoughts-pane-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  position: relative;
  overflow: hidden;
}

.events-scroll-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  color: var(--p-text-color);

  overflow-y: auto;
  scrollbar-width: thin;
  // scrollbar-color: var(--p-surface-d) var(--p-surface-a);
  padding-right: 0.5rem;
  margin-right: 0.5rem;
  padding-top: 0.5rem;
}

.no-thoughts-message {
  text-align: center;
  padding: 1rem;
  color: var(--p-text-color-secondary);
}

.pane-actions {
  position: fixed;
  top: 2.5rem;
  right: 5rem;
  z-index: 100;
  & > .p-button {
    color: var(--p-text-color-secondary);
  }
}

.magnifier-reference {
  margin: 0 0.25rem;
  color: var(--p-text-color-secondary);
}

.progress-area {
  width: 100%;
  z-index: 100;
  .p-progressbar {
    height: 6px; width: 40%; margin: 1rem auto;
  }
}

</style>
