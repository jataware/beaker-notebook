import { defineStore } from 'pinia';
import { ref, shallowRef, toRaw, type Ref } from 'vue';
import type { BeakerSession, BeakerKernelStatus } from '@jataware/beaker-client';
import type { BeakerWorkspace } from '@jataware/beaker-vue';
import { useUIStore } from './ui';

/**
 * Registry of user-perceived workspaces, keyed by session name (path-based,
 * e.g. "user/workspace-name").
 *
 * Each workspace holds:
 *   - A reference to its kernel-session (`workspace.client`, a BeakerSession
 *     instance that's typically created by the page's <BeakerSession>
 *     component and passed in via attachSession).
 *   - Mirror state populated by the iopub message handler (chatHistory,
 *     integrations, kernelStateInfo, contextPreviewData, connectionStatus).
 *   - UI-only workspace state (saveAsFilename, dirty, pendingPanelHint).
 *
 * Lifecycle: pages call `getOrCreate(name)` for the workspace ref; they
 * later call `attachSession(name, session)` once the underlying
 * BeakerSession exists, which is when iopub wiring kicks in.
 *
 * NOTE: Interim flat shape — kernel-mirror fields live directly on the
 * workspace. A future refactor will introduce a KernelSession wrapper and
 * move them under `workspace.session.state.*`. See
 * plans/beaker-ui-split.md "Deferred / out of scope".
 */
export const useWorkspacesStore = defineStore('beaker-workspaces', () => {
    // shallowRef around a plain Map: reactivity on the set of workspaces
    // but not deep reactivity that would mangle nested class types.
    const workspaces = shallowRef(new Map<string, BeakerWorkspace>());
    const wiredWorkspaces = new Set<string>();

    function makeWorkspace(name: string): BeakerWorkspace {
        // The workspace shape is the interim flat one. `client` starts as
        // a placeholder; pages call attachSession once <BeakerSession>
        // has constructed the real one.
        return {
            name,
            client: null as unknown as BeakerSession,
            connectionStatus: ref<BeakerKernelStatus>('connecting') as Ref<BeakerKernelStatus>,
            chatHistory: ref<unknown>(null),
            integrations: ref<unknown[]>([]),
            kernelStateInfo: ref<unknown>(null),
            contextPreviewData: ref<unknown>(null),
            saveAsFilename: ref<string | null>(null),
            dirty: ref<boolean>(false),
            pendingPanelHint: ref<string | null>(null),
        };
    }

    /** Get or create the workspace record for `name`. */
    function getOrCreate(name: string): BeakerWorkspace {
        const existing = workspaces.value.get(name);
        if (existing) return existing;
        const workspace = makeWorkspace(name);
        const next = new Map(workspaces.value);
        next.set(name, workspace);
        workspaces.value = next;
        return workspace;
    }

    /**
     * Attach a constructed BeakerSession to a workspace and wire iopub
     * handlers. Page calls this once <BeakerSession> has constructed its
     * session (typically in onMounted via the component ref).
     *
     * Idempotent — calling twice for the same workspace is a no-op for
     * the wiring.
     */
    function attachSession(name: string, session: BeakerSession): void {
        const raw = toRaw(session);
        const workspace = getOrCreate(name);
        workspace.client = session;
        if (wiredWorkspaces.has(name)) return;
        wiredWorkspaces.add(name);
        wireIopubHandler(workspace);
    }

    function wireIopubHandler(workspace: BeakerWorkspace): void {
        const uiStore = useUIStore();
        const client: any = toRaw(workspace.client);
        // const rawClient = toRaw(client)
        if (!client) return;

        client.services?.connectionFailure?.connect?.(() => {
            workspace.connectionStatus.value = 'disconnected';
        });

        client.sessionReady?.then?.(() => {
            const jupSession = toRaw(client.session);
            if (!jupSession) return;

            jupSession.iopubMessage?.connect?.((_: unknown, msg: any) => {
                handleIopubMessage(workspace, uiStore, msg);
            });

            jupSession.connectionStatusChanged?.connect?.(() => {
                workspace.connectionStatus.value = client.status;
            });

            jupSession.anyMessage?.connect?.((_: unknown, { msg, direction }: { msg: any; direction: string }) => {
                uiStore.recordRawMessage(msg, direction);
            });
        });
    }

    function handleIopubMessage(workspace: BeakerWorkspace, uiStore: ReturnType<typeof useUIStore>, msg: any): void {
        const msgType = msg?.header?.msg_type;
        switch (msgType) {
            case 'preview':
                workspace.contextPreviewData.value = msg.content;
                break;
            case 'kernel_state_info':
                workspace.kernelStateInfo.value = msg.content;
                break;
            case 'debug_event':
                uiStore.recordDebugLog({
                    type: msg.content.event,
                    body: msg.content.body,
                    timestamp: msg.header.date,
                });
                break;
            case 'update_workflow_state': {
                const ctx: any = (workspace.client as any).activeContext;
                if (ctx?.info?.workflow_info) {
                    ctx.info.workflow_info.state = msg.content;
                }
                workspace.pendingPanelHint.value = 'workflow';
                break;
            }
            case 'chat_history':
                workspace.chatHistory.value = msg.content;
                break;
            case 'context_setup_response':
            case 'context_info_response': {
                const incoming =
                    msgType === 'context_setup_response'
                        ? msg.content.integrations
                        : msg.content.info?.integrations;
                const list = incoming ?? [];
                const arr = Array.isArray(list) ? list : Object.values(list);
                workspace.integrations.value.splice(
                    0,
                    workspace.integrations.value.length,
                    ...arr,
                );
                break;
            }
            case 'lint_code_result':
                if (Array.isArray(msg.content)) {
                    msg.content.forEach((result: any) => {
                        const cell = (workspace.client as any).findNotebookCellById?.(result.cell_id);
                        cell?.lintAnnotations?.push?.(result);
                    });
                }
                break;
        }
    }

    function dispose(name: string): void {
        const next = new Map(workspaces.value);
        next.delete(name);
        workspaces.value = next;
        wiredWorkspaces.delete(name);
    }

    return { workspaces, getOrCreate, attachSession, dispose };
});
