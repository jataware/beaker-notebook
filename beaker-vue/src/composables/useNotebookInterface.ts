import { ref, computed, watch, nextTick, inject, type Ref, type ComputedRef } from 'vue';
import { JupyterMimeRenderer } from 'beaker-kernel';
import type { IBeakerCell, IMimeRenderer } from 'beaker-kernel';
import type { BeakerNotebookComponentType } from '../components/notebook/BeakerNotebook.vue';
import type { BeakerSessionComponentType } from '../components/session/BeakerSession.vue';
import { JavascriptRenderer, JSONRenderer, LatexRenderer, MarkdownRenderer, wrapJupyterRenderer, TableRenderer, type BeakerRenderOutput } from '../renderers';
import { atStartOfInput, atEndOfInput } from '../util';
import type { NavOption } from '../components/misc/BeakerHeader.vue';
import { standardRendererFactories } from '@jupyterlab/rendermime';
import type { IBeakerTheme } from '../plugins/theme';
import type { IChatHistory } from '../components/panels/ChatHistoryPanel';

interface UseNotebookInterfaceReturn {
    // refs
    beakerNotebookRef: Ref<BeakerNotebookComponentType | undefined>;
    beakerInterfaceRef: Ref;
    filePanelRef: Ref<any>;
    configPanelRef: Ref<any>;
    sideMenuRef: Ref<any>;
    rightSideMenuRef: Ref<any>;
    agentQueryRef: Ref<any>;

    // state
    connectionStatus: Ref<string>;
    debugLogs: Ref<object[]>;
    rawMessages: Ref<object[]>;
    saveAsFilename: Ref<string | null>;
    isMaximized: Ref<boolean>;
    chatHistory: Ref<IChatHistory | undefined>;
    integrations: Ref<any[]>;
    contextPreviewData: Ref<any>;
    kernelStateInfo: Ref<any>;
    copiedCell: Ref<IBeakerCell | null>;

    // computed
    activeQueryCells: ComputedRef<Array<{
        id: string;
        source: string;
        status: string;
    }>>;
    awaitingInputCell: ComputedRef<any>;
    awaitingInputQuestion: ComputedRef<string | null>;
    beakerSession: ComputedRef<BeakerSessionComponentType>;
    defaultRenderers: IMimeRenderer<BeakerRenderOutput>[];

    // functions
    createHeaderNav: (currentPage: string) => NavOption[];
    createNotebookKeyBindings: Function;
    createIopubMessageHandler: () => (msg: any) => void;
    anyMessageHandler: (msg: any, direction: string) => void;
    unhandledMessageHandler: (msg: any) => void;
    statusChangedHandler: (newStatus: string) => void;
    loadNotebook: (notebookJSON: any, filename: string) => void;
    handleNotebookSaved: (path: string) => Promise<void>;
    scrollToCell: (cellId: string) => void;
    restartSession: () => Promise<void>;

    // injections
    theme: any;
    toggleDarkMode: () => void;
    beakerApp: any;
}

export function useNotebookInterface(): UseNotebookInterfaceReturn {
    const beakerNotebookRef = ref<BeakerNotebookComponentType>();
    const beakerInterfaceRef = ref();
    const filePanelRef = ref();
    const configPanelRef = ref();
    const sideMenuRef = ref();
    const rightSideMenuRef = ref();
    const agentQueryRef = ref();
    const kernelStateInfo = ref();

    const connectionStatus = ref('connecting');
    const debugLogs = ref<object[]>([]);
    const rawMessages = ref<object[]>([]);
    const saveAsFilename = ref<string>(null);
    const isMaximized = ref(false);
    const chatHistory = ref<IChatHistory>();
    const integrations = ref([]);
    const contextPreviewData = ref<any>();
    const keyBindingState = {};
    const copiedCell = ref<IBeakerCell | null>(null);

    const { theme, toggleDarkMode } = inject<IBeakerTheme>('theme');
    const beakerApp = inject<any>("beakerAppConfig");

    const beakerSession = computed<BeakerSessionComponentType>(() => {
        return beakerInterfaceRef?.value?.beakerSession;
    });

    const activeQueryCells = computed(() => {
        if (!beakerSession.value?.session?.notebook?.cells) return [];

        return beakerSession.value.session.notebook.cells
            .filter(cell => cell.cell_type === 'query')
            .map(cell => ({
                id: cell.id,
                source: cell.source,
                status: cell.status
            }));
    });

    const awaitingInputCell = computed(() => {
        const cells = beakerSession.value?.session?.notebook?.cells ?? [];
        return cells.find(cell =>
            cell.cell_type === 'query' && cell.status === 'awaiting_input'
        ) || null;
    });

    const awaitingInputQuestion = computed(() => {
        if (!awaitingInputCell.value) return null;

        // find the last user_question event to get the question text
        const events = awaitingInputCell.value.events || [];
        const lastQuestionEvent = [...events].reverse().find(event => event.type === 'user_question');

        return lastQuestionEvent?.content || 'The agent is waiting for your response.';
    });

    const defaultRenderers: IMimeRenderer<BeakerRenderOutput>[] = [
        ...standardRendererFactories.map((factory: any) => new JupyterMimeRenderer(factory)).map(wrapJupyterRenderer),
        JavascriptRenderer,
        JSONRenderer,
        LatexRenderer,
        MarkdownRenderer,
        TableRenderer
    ];

    const createHeaderNav = (currentPage: string): NavOption[] => {
        const nav = [];

        if (currentPage !== 'chat') {
            nav.push({
                type: 'link',
                href: '/chat' + window.location.search,
                icon: 'comment',
                label: 'Navigate to chat view',
            });
        }

        if (currentPage !== 'notebook') {
            nav.push({
                type: 'link',
                href: '/notebook' + window.location.search,
                icon: 'sparkles',
                label: 'Navigate to notebook view',
            });
        }

        nav.push(...[
            {
                type: 'button',
                icon: (theme.mode === 'dark' ? 'sun' : 'moon'),
                command: toggleDarkMode,
                label: `Switch to ${theme.mode === 'dark' ? 'light' : 'dark'} mode.`,
            },
            {
                type: 'link',
                href: `https://jataware.github.io/beaker-kernel`,
                label: 'Beaker Documentation',
                icon: "book",
                rel: "noopener",
                target: "_blank",
            },
            {
                type: 'link',
                href: `https://github.com/jataware/beaker-kernel`,
                label: 'Check us out on Github',
                icon: "github",
                rel: "noopener",
                target: "_blank",
            },
        ]);
        return nav;
    };

    const prevCellKey = () => {
        beakerNotebookRef.value?.selectPrevCell();
    };

    const nextCellKey = () => {
        const lastCell = beakerNotebookRef.value.notebook.cells[beakerNotebookRef.value.notebook.cells.length-1];
        if (beakerNotebookRef.value.selectedCell().cell.id === lastCell.id) {
            agentQueryRef.value.$el.querySelector('textarea')?.focus()
        }
        else {
            beakerNotebookRef.value?.selectNextCell();
        }
    };

    const scrollToCell = (cellId: string) => {
        const cellElement = document.querySelector(`[cell-id="${cellId}"]`);
        if (cellElement) {
            cellElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            beakerNotebookRef.value?.selectCell(cellId);
        }
    };

    const createNotebookKeyBindings = () => ({
        "keydown.enter.ctrl.prevent.capture.in-cell": () => {
            beakerNotebookRef.value?.selectedCell().execute();
            beakerNotebookRef.value?.selectedCell().exit();
        },
        "keydown.enter.shift.prevent.capture.in-cell": () => {
            const targetCell = beakerNotebookRef.value?.selectedCell();
            targetCell.execute();
            if (!beakerNotebookRef.value?.selectNextCell()) {
                beakerNotebookRef.value?.insertCellAfter(
                    targetCell,
                    undefined,
                    true,
                );
                nextTick(() => {
                    beakerNotebookRef.value?.selectedCell().enter();
                });
            }
        },
        "keydown.enter.exact.prevent.stop.!in-editor": () => {
            beakerNotebookRef.value?.selectedCell().enter();
        },
        "keydown.esc.exact.prevent": () => {
            beakerNotebookRef.value?.selectedCell().exit();
        },
        "keydown.up.!in-editor.prevent": prevCellKey,
        "keydown.up.in-editor.capture": (event: KeyboardEvent) => {
            const eventTarget = event.target as HTMLElement;
            const parentCellElement = eventTarget.closest('.beaker-cell');
            const targetCellId = parentCellElement?.getAttribute('cell-id');

            if (targetCellId !== undefined) {
                const curCell = beakerSession.value.findNotebookCellById(targetCellId);
                if (atStartOfInput(curCell.editor)) {
                    const prevCell = beakerNotebookRef.value.prevCell();
                    if (prevCell) {
                        curCell.exit();
                        beakerNotebookRef.value.selectCell(prevCell.cell.id, true, "end");
                        event.preventDefault();
                        event.stopImmediatePropagation();
                    }
                }
            }
            else if (eventTarget.closest('.agent-query-container')) {
                eventTarget.blur();
                beakerNotebookRef.value.selectCell(
                    beakerNotebookRef.value.notebook.cells[beakerNotebookRef.value.notebook.cells.length-1].id,
                    true,
                    "end",
                );
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        },
        "keydown.down.in-editor.capture": (event: KeyboardEvent) => {
            const eventTarget = event.target as HTMLElement;
            const parentCellElement = eventTarget.closest('.beaker-cell');
            const targetCellId = parentCellElement?.getAttribute('cell-id');

            if (targetCellId !== undefined) {
                const curCell = beakerSession.value.findNotebookCellById(targetCellId);
                if (atEndOfInput(curCell.editor)) {
                    const nextCell = beakerNotebookRef.value.nextCell();
                    if (nextCell) {
                        curCell.exit();
                        beakerNotebookRef.value.selectCell(nextCell.cell.id, true, "start");
                        event.preventDefault();
                        event.stopImmediatePropagation();
                    }
                    else {
                        const lastCell = beakerNotebookRef.value.notebook.cells[beakerNotebookRef.value.notebook.cells.length-1];
                        if (beakerNotebookRef.value.selectedCell().cell.id === lastCell.id) {
                            curCell.exit();
                            agentQueryRef.value.$el.querySelector('textarea')?.focus()
                            event.preventDefault();
                            event.stopImmediatePropagation();
                        }
                    }
                }
            }
        },
        "keydown.k.!in-editor": prevCellKey,
        "keydown.down.!in-editor.prevent": nextCellKey,
        "keydown.j.!in-editor": nextCellKey,
        "keydown.a.prevent.!in-editor": () => {
            const notebook = beakerNotebookRef.value;
            notebook?.selectedCell().exit();
            notebook?.insertCellBefore();
        },
        "keydown.b.prevent.!in-editor": () => {
            const notebook = beakerNotebookRef.value;
            notebook?.selectedCell().exit();
            notebook?.insertCellAfter();
        },
        "keydown.d.!in-editor": () => {
            const notebook = beakerNotebookRef.value;
            const cell = notebook.selectedCell();
            const deleteCallback = () => {
                delete keyBindingState['d'];
            };
            const state = keyBindingState['d'];

            if (state === undefined) {
                const timeoutId = setTimeout(deleteCallback, 1000);
                keyBindingState['d'] = {
                    cell_id: cell.id,
                    timeout: timeoutId,
                }
            }
            else {
                const {cell_id, timeout} = keyBindingState['d'];
                if (cell_id === cell.id) {
                    notebook?.removeCell(cell);
                    copiedCell.value = cell.cell;
                    delete keyBindingState['d'];
                }
                if (timeout) {
                    window.clearTimeout(timeout);
                }
            }
        },
    });

    const createIopubMessageHandler = () => (msg) => {
        if (msg.header.msg_type === "preview") {
            contextPreviewData.value = msg.content;
        }
        else if (msg.header.msg_type === "kernel_state_info") {
            kernelStateInfo.value = msg.content;
        }
        else if (msg.header.msg_type === "debug_event") {
            debugLogs.value.push({
                type: msg.content.event,
                body: msg.content.body,
                timestamp: msg.header.date,
            });
        } else if (msg.header.msg_type === "update_workflow_state") {
            const workflows = beakerSession?.value?.activeContext?.info?.workflow_info;
            if (workflows) {
                workflows.state = msg.content;
                sideMenuRef.value.selectPanel('workflow-steps');
                rightSideMenuRef.value.selectPanel('workflow-output');
            }
        } else if (msg.header.msg_type === "chat_history") {
            chatHistory.value = msg.content;
            console.log(msg.content);
        } else if (msg.header.msg_type === "context_setup_response" || msg.header.msg_type === "context_info_response") {
            let incomingIntegrations;
            if (msg.header.msg_type === "context_setup_response") {
                incomingIntegrations = msg.content.integrations;
            }
            else if (msg.header.msg_type === "context_info_response") {
                incomingIntegrations = msg.content.info.integrations;
            }
            if (incomingIntegrations === undefined) {
                incomingIntegrations = [];
            }
            integrations.value.splice(0, integrations.value.length, ...incomingIntegrations);
        } else if (msg.header.msg_type === "lint_code_result") {
            msg.content.forEach((result) => {
                const cell = beakerSession.value.findNotebookCellById(result.cell_id);
                cell.lintAnnotations.push(result);
            })
        }
    };

    const anyMessageHandler = (msg, direction) => {
        rawMessages.value.push({
            type: direction,
            body: msg,
            timestamp: msg.header.date,
        });
    };

    const unhandledMessageHandler = (msg) => {
        console.log("Unhandled message received", msg);
    };

    const statusChangedHandler = (newStatus) => {
        connectionStatus.value = newStatus == 'idle' ? 'connected' : newStatus;
    };

    const loadNotebook = (notebookJSON: any, filename: string) => {
        console.log("Loading notebook", notebookJSON);

        const notebook = beakerNotebookRef.value;
        beakerSession.value?.session.loadNotebook(notebookJSON);
        if (notebookJSON?.metadata?.chat_history) {
            beakerSession.value?.session.executeAction(
                "set_agent_history",
                notebookJSON?.metadata?.chat_history
            );
        }
        saveAsFilename.value = filename;

        const cellIds = notebook.notebook.cells.map((cell) => cell.id);
        if (!cellIds.includes(notebook.selectedCellId)) {
            nextTick(() => {
                notebook.selectCell(cellIds[0]);
            });
        }
    };

    const handleNotebookSaved = async (path: string) => {
        saveAsFilename.value = path;
        if (path) {
            sideMenuRef.value?.selectPanel("Files");
            await filePanelRef.value.refresh();
            await filePanelRef.value.flashFile(path);
        }
    };

    const restartSession = async () => {
        const resetFuture = beakerSession.value.session.sendBeakerMessage(
            "reset_request",
            {}
        )
        await resetFuture;
    };

    // at least one cell
    watch(
        () => beakerNotebookRef?.value?.notebook.cells,
        (cells) => {
            if (cells?.length === 0) {
                beakerNotebookRef.value.insertCellBefore();
            }
        },
        {deep: true},
    );

    return {
        // refs
        beakerNotebookRef,
        beakerInterfaceRef,
        filePanelRef,
        configPanelRef,
        sideMenuRef,
        rightSideMenuRef,
        agentQueryRef,

        // state
        connectionStatus,
        debugLogs,
        rawMessages,
        saveAsFilename,
        isMaximized,
        chatHistory,
        integrations,
        contextPreviewData,
        kernelStateInfo,
        copiedCell,
        activeQueryCells,
        awaitingInputCell,
        awaitingInputQuestion,

        // computed
        beakerSession,
        defaultRenderers,

        // functions
        createHeaderNav,
        createNotebookKeyBindings,
        createIopubMessageHandler,
        anyMessageHandler,
        unhandledMessageHandler,
        statusChangedHandler,
        loadNotebook,
        handleNotebookSaved,
        scrollToCell,
        restartSession,

        // injections
        theme,
        toggleDarkMode,
        beakerApp,
    };
}
