import { onBeforeUnmount, onMounted, ref } from 'vue';
import { v4 as uuidv4 } from 'uuid';
import type { BeakerSession } from '@jataware/beaker-client';

type PendingState = {
    state: string;
    id?: string;
    text?: string;
    revision?: number;
    pending?: PendingState;
};

type Toast = (options: {title: string; detail: string; severity: string; life?: number}) => void;

/** Manage the kernel's single pending interjection for an agent input. */
export function usePendingMessage(
    session: BeakerSession,
    submitDeferred: (text: string, id: string) => void,
    showToast?: Toast,
) {
    const pending = ref<PendingState | null>(null);
    const pendingDraft = ref('');
    const editingPending = ref(false);
    const pendingBusy = ref(false);
    let pendingRevision = -1;
    let ownedPendingId: string | null = null;
    const deferredAttempts = new Set<string>();

    const sendDeferred = () => {
        if (pending.value?.id && pending.value.text) {
            submitDeferred(pending.value.text, pending.value.id);
        }
    };

    const applyPendingState = (state: PendingState) => {
        if (state.pending) {
            applyPendingState(state.pending);
            return;
        }
        if (state.revision === undefined || state.revision < pendingRevision) return;
        pendingRevision = state.revision;
        if (state.state === 'pending' || state.state === 'deferred') {
            pending.value = state;
            // Only the originating client automatically starts a deferred turn.
            if (state.state === 'deferred' && state.id === ownedPendingId && !deferredAttempts.has(state.id)) {
                deferredAttempts.add(state.id);
                queueMicrotask(() => {
                    if (pending.value?.id === state.id && pending.value.state === 'deferred') sendDeferred();
                });
            }
        } else if (['sent', 'cancelled', 'empty'].includes(state.state)) {
            if (state.id === ownedPendingId) ownedPendingId = null;
            pending.value = null;
            editingPending.value = false;
        }
    };

    const request = (content: Record<string, string | boolean>): Promise<PendingState> => {
        return new Promise((resolve, reject) => {
            const future = session.sendBeakerMessage('llm_pending_request', content);
            future.onReply = (reply) => {
                // Control requests do not publish an idle status.
                queueMicrotask(() => future.dispose());
                if (reply.content.status === 'error') {
                    reject(new Error(String(reply.content.evalue)));
                    return;
                }
                resolve(reply.content.return as PendingState);
            };
        });
    };

    const onPendingUpdate = (_sender: unknown, message: any) => {
        if (message.header.msg_type === 'llm_pending_update') applyPendingState(message.content);
    };

    let unmounted = false;
    onMounted(async () => {
        await session.session.ready;
        if (unmounted) return;
        session.session.iopubMessage.connect(onPendingUpdate);
        try {
            applyPendingState(await request({operation: 'status'}));
        } catch (error) {
            showToast?.({title: 'Pending message status unavailable', detail: String(error), severity: 'error', life: 4000});
        }
    });
    onBeforeUnmount(() => {
        unmounted = true;
        session.session.iopubMessage.disconnect(onPendingUpdate);
    });

    const queue = async (text: string, hasAttachments = false): Promise<string> => {
        ownedPendingId = uuidv4();
        const state = await request({operation: 'queue', id: ownedPendingId, text, has_attachments: hasAttachments});
        if (state.state !== 'pending') ownedPendingId = null;
        applyPendingState(state);
        return state.state;
    };

    const editPending = () => {
        pendingDraft.value = pending.value?.text ?? '';
        editingPending.value = true;
    };
    const updatePending = async (operation: string, text?: string) => {
        if (!pending.value?.id || pendingBusy.value) return;
        pendingBusy.value = true;
        try {
            const state = await request({operation, id: pending.value.id, ...(text === undefined ? {} : {text})});
            applyPendingState(state);
            if (state.state === 'pending' || state.state === 'deferred') editingPending.value = false;
        } catch (error) {
            showToast?.({title: 'Pending message update failed', detail: String(error), severity: 'error', life: 4000});
        } finally {
            pendingBusy.value = false;
        }
    };
    const savePending = () => {
        if (pendingDraft.value.trim()) void updatePending('edit', pendingDraft.value);
    };
    const cancelPending = () => void updatePending('cancel');

    return {pending, pendingDraft, editingPending, pendingBusy, queue, editPending, savePending, cancelPending, sendDeferred};
}
