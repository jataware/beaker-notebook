import type { Ref } from 'vue';
import type { BeakerSession, BeakerKernelStatus } from '@jataware/beaker-client';

// Interim flat shape — kernel-mirror state lives directly on the workspace
// (populated by the iopub handler in useWorkspacesStore.getOrCreate). The
// follow-up wrapper refactor will move these under workspace.session.state.*
// once a KernelSession wrapper type is introduced. Mirror-state field types
// are intentionally loose here; they get pinned down with the wrapper.
// See plans/beaker-ui-split.md "Deferred / out of scope" for the follow-up scope.

export interface BeakerWorkspace {
    /** Path-based identity (e.g. "user/workspace-name"); matches session.path. */
    name: string;

    /** The beaker-ts BeakerSession instance. */
    client: BeakerSession;

    // --- Kernel-mirror refs (populated by iopub handler) ---

    connectionStatus: Ref<BeakerKernelStatus>;
    chatHistory: Ref<unknown>;
    integrations: Ref<unknown[]>;
    kernelStateInfo: Ref<unknown>;
    contextPreviewData: Ref<unknown>;

    // --- Workspace-only UI state ---

    saveAsFilename: Ref<string | null>;
    dirty: Ref<boolean>;
    pendingPanelHint: Ref<string | null>;
}
