import { ref, nextTick, toValue, type Ref, type MaybeRefOrGetter } from 'vue';
import { fetch } from '../util/fetch';
import hashSum from 'hash-sum';
import type { BeakerSessionComponentType } from '../components/session/BeakerSession.vue';

export interface NotebookInfo {
    id: string;
    name: string;
    created: string;
    last_modified: string;
    size: number;
    session_id?: string;
    content?: any;
    checksum?: string;
    metadata?: {[key: string]: any};
}

export interface UseNotebookSnapshotOptions {
    /** Ref to the BeakerSession component instance. */
    beakerSession: Ref<BeakerSessionComponentType | undefined>;
    /** Default filename to associate with the notebook, if any. */
    savefile?: MaybeRefOrGetter<string | undefined>;
    /** Called when a loaded snapshot has content to open into the session. */
    onOpenFile: (content: any, name: string, options: { selectedCell?: string }) => void;
}

export interface UseNotebookSnapshotReturn {
    notebookInfo: Ref<NotebookInfo | null>;
    saveSnapshot: () => Promise<void>;
    loadSnapshot: () => Promise<void>;
    startAutosave: (intervalMs?: number) => void;
    stopAutosave: () => void;
}

/**
 * Persists the current session's notebook to the Beaker notebook storage API
 * (`/beaker/notebook/`) and restores it on load. Storage location and format
 * are entirely the backend's concern; this composable only ever talks to the
 * API endpoint.
 */
export function useNotebookSnapshot(options: UseNotebookSnapshotOptions): UseNotebookSnapshotReturn {
    const { beakerSession, savefile, onOpenFile } = options;

    const notebookInfo = ref<NotebookInfo | null>(null);
    const saveInterval = ref<ReturnType<typeof setInterval> | null>(null);

    const saveSnapshot = async () => {
        const session = beakerSession.value?.session;
        const sessionId = session?.sessionId;

        const notebookData: {[key: string]: any} = {
            ...(notebookInfo.value || {}),
        };
        if (notebookData.session_id && sessionId && notebookData.session_id !== sessionId) {
            console.warn(`saveSnapshot: session id mismatch (expected ${notebookData.session_id}, got ${sessionId}); skipping save.`);
            return;
        }
        notebookData.session_id = sessionId;

        // Only save state if there is state to save
        if (!session?.notebook) {
            return;
        }

        notebookData.content = session.toIPynb();

        const notebookChecksum: string = hashSum(notebookData.content);
        const notebookComponent = beakerSession.value.notebookComponent;

        if (notebookChecksum === notebookData.checksum) {
            // No changes since last save
            return;
        }
        notebookData.checksum = notebookChecksum;

        if (notebookComponent) {
            notebookData.selectedCell = notebookComponent.selectedCellId;
        }

        const savefileValue = toValue(savefile);
        if (!notebookData.filename && typeof savefileValue === "string") {
            notebookData.filename = savefileValue;
        }

        if (notebookData.selectedCell) {
            // Store selected cell in notebook metadata before saving
            notebookData.content.metadata = notebookData.content.metadata || {};
            notebookData.content.metadata.selected_cell = notebookData.selectedCell;
        }

        const saveRequest = await fetch(`/beaker/notebook/snapshot/${sessionId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(notebookData),
        });
        if (saveRequest.ok) {
            const response = await saveRequest.json();
            notebookInfo.value = {
                ...notebookInfo.value,
                metadata: response,
                checksum: notebookChecksum,
            };
        }
    };

    const loadSnapshot = async () => {
        const session = beakerSession.value.session;
        await session.sessionReady;  // Ensure content service is up
        const sessionId = session.sessionId;

        try {
            const notebookInfoResponse = await fetch(`/beaker/notebook/snapshot/${sessionId}`);
            if (notebookInfoResponse.ok) {
                const response = await notebookInfoResponse.json();
                const content = response.content;
                const metadata = {
                    ...response,
                    content: undefined,
                };
                const checksum = hashSum(content);
                notebookInfo.value = {
                    ...notebookInfo.value,
                    content,
                    metadata,
                    checksum,
                };
            }
        }
        catch (e) {
            console.error(e);
            notebookInfo.value = {
                id: sessionId,
                name: sessionId,
                created: "",
                last_modified: "",
                size: 0,
                session_id: sessionId,
            };
        }

        const notebookData: {[key: string]: any} = {
            ...(notebookInfo.value || {}),
        };

        // The selected cell is round-tripped through the notebook's metadata on save
        // (see saveSnapshot); restore it so the previously-selected cell is reselected.
        if (notebookData.selectedCell === undefined) {
            notebookData.selectedCell = notebookData.content?.metadata?.selected_cell;
        }

        if (notebookData.content) {
            onOpenFile(notebookData.content, notebookData.name, {selectedCell: notebookData.selectedCell});
        }

        if (notebookData.selectedCell !== undefined) {
            nextTick(() => {
                beakerSession.value.notebookComponent?.selectCell(notebookData.selectedCell);
            });
        }
    };

    const handleBeforeUnload = () => {
        saveSnapshot();
    };

    const startAutosave = (intervalMs: number = 10000) => {
        saveInterval.value = setInterval(saveSnapshot, intervalMs);
        window.addEventListener("beforeunload", handleBeforeUnload);
    };

    const stopAutosave = () => {
        if (saveInterval.value !== null) {
            clearInterval(saveInterval.value);
            saveInterval.value = null;
        }
        window.removeEventListener("beforeunload", handleBeforeUnload);
    };

    return {
        notebookInfo,
        saveSnapshot,
        loadSnapshot,
        startAutosave,
        stopAutosave,
    };
}
