import { defineStore } from 'pinia';
import { ref, shallowRef } from 'vue';
import { BeakerSession, type IBeakerSessionOptions } from '@jataware/beaker-client';

/**
 * Registry of live BeakerSession (kernel connection) instances, keyed by
 * session name. Pure transport-layer concern — no app state. Workspaces
 * hold references to entries here.
 *
 * Lifecycle: getOrCreate constructs new sessions; dispose tears down.
 * Server-side kernel persistence is independent (the kernel may outlive
 * the BeakerSession on the UI side).
 */
export type KernelSessionInit = Omit<IBeakerSessionOptions, 'sessionId'>;

export const useKernelSessionsStore = defineStore('beaker-kernel-sessions', () => {
    // shallowRef around a plain Map: we want reactivity on "set of keys"
    // changes (so list-views update) but NOT on the class instances inside
    // (deep reactive would mangle the BeakerSession class identity).
    const sessions = shallowRef(new Map<string, BeakerSession>());

    function get(name: string): BeakerSession | undefined {
        return sessions.value.get(name);
    }

    function getOrCreate(name: string, opts: KernelSessionInit): BeakerSession {
        const existing = sessions.value.get(name);
        if (existing) return existing;

        const session = new BeakerSession({ ...opts, sessionId: name });
        // Trigger reactivity: replace the Map with a new one containing the
        // added entry. (Map.set on a shallowRef'd Map doesn't notify.)
        const next = new Map(sessions.value);
        next.set(name, session);
        sessions.value = next;
        return session;
    }

    function dispose(name: string): void {
        const session = sessions.value.get(name);
        if (!session) return;
        try {
            // Best-effort cleanup; the BeakerSession class doesn't have a
            // documented dispose API yet (see Kernel-mirror wrapper deferral
            // in plans/beaker-ui-split.md).
            (session as any).services?.dispose?.();
        } catch (err) {
            console.debug('Error disposing kernel session', name, err);
        }
        const next = new Map(sessions.value);
        next.delete(name);
        sessions.value = next;
    }

    return { sessions, get, getOrCreate, dispose };
});
