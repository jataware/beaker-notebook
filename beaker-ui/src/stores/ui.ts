import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { IBeakerCell } from 'beaker-kernel';

/**
 * Cross-workspace UI ephemera. Holds state that is not tied to any
 * specific kernel session or workspace — clipboard buffers, debug logs
 * accumulated from all sessions, etc.
 *
 * Page-local UI state (isMaximized, panel selection within a single
 * notebook view) is not in this store — those live in the page refs.
 */
export const useUIStore = defineStore('beaker-ui', () => {
    // --- Clipboard ---
    const copiedCell = ref<IBeakerCell | null>(null);

    // --- Debug stream (originates from iopub but UI-owned; not mirrored
    // server-side) ---
    const debugLogs = ref<Array<{ type: string; body: any; timestamp: any }>>([]);
    const rawMessages = ref<Array<{ type: string; body: any; timestamp: any }>>([]);

    function recordDebugLog(entry: { type: string; body: any; timestamp: any }): void {
        debugLogs.value.push(entry);
    }

    function recordRawMessage(msg: any, direction: string): void {
        rawMessages.value.push({
            type: direction,
            body: msg,
            timestamp: msg?.header?.date,
        });
    }

    function clearDebugLogs(): void {
        debugLogs.value = [];
        rawMessages.value = [];
    }

    return {
        copiedCell,
        debugLogs,
        rawMessages,
        recordDebugLog,
        recordRawMessage,
        clearDebugLogs,
    };
});
