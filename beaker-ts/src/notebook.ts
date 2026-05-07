import * as nbformat from '@jupyterlab/nbformat';
import * as messages from '@jupyterlab/services/lib/kernel/messages';
import { JSONObject, PartialJSONValue, PartialJSONObject } from '@lumino/coreutils';
import { IShellFuture } from '@jupyterlab/services/lib/kernel/kernel';
import { v4 as uuidv4 } from 'uuid';

import { BeakerSession } from './session';
import { IBeakerFuture, BeakerCellFuture, BeakerCellFutures } from './util';


export interface IBeakerHeader extends messages.IHeader<messages.MessageType> {
    msg_type: any;
}

export interface IBeakerShellMessage extends messages.IShellMessage {
    header: IBeakerHeader;
    channel: "shell";
    content: any;
    parent_header: any;
}

export interface IBeakerIOPubMessage extends messages.IIOPubMessage {
    header: IBeakerHeader;
    channel: "iopub";
    content: any;
}

export interface IBeakerAnyMessage extends messages.IMessage {
    header: IBeakerHeader;
    content: any;
}

export type BeakerCellStatus = messages.Status | "awaiting_input";

export type BeakerCellExecutionStatus = IBeakerCellExecutionStatusPlain | IBeakerCellExecutionStatusPending | IBeakerCellExecutionStatusOk | IBeakerCellExecutionStatusError;

export interface IBeakerCellExecutionStatusPlain {
    status: "none" | "modified" | "abort";
}

export interface IBeakerCellExecutionStatusPending {
    status: "pending";
    checkpoint_index?: number;
}

export interface IBeakerCellExecutionStatusOk {
    status: "ok"
    checkpoint_index?: number;
}
export interface IBeakerCellExecutionStatusError {
    status: "error";
    ename: string;
    evalue: string;
    traceback: string[];
}

export type BeakerCellType = nbformat.CellType | string | 'query';

export class BeakerBaseCell implements nbformat.IBaseCell {
    // Override index type to allow methods to be defined on the class
    static IPYNB_KEYS = ["cell_type", "source", "metadata", "id", "attachments", "outputs", "execution_count"];

    [key: string]: any;
    id: string = BeakerBaseCell.generateId();
    declare cell_type: BeakerCellType;
    metadata: Partial<nbformat.ICellMetadata> = {};
    source: nbformat.MultilineString = "";
    status: BeakerCellStatus = "idle";
    children: BeakerBaseCell[] = [];

    constructor(content: Partial<nbformat.IBaseCell>) {
        Object.assign(this, content)
        if (content.id === undefined) {
            this.id = BeakerBaseCell.generateId();
        }
    }

    static generateId(): string {
        return uuidv4();
    }

    public fromJSON(obj: any) {
        Object.keys(obj).forEach((key) => {
            this[key] = obj[key];
        })
    }

    public toJSON() {
        return {...this};
    }

    public fromIPynb(obj: any) {
        Object.keys(obj).forEach((key) => {
            this[key] = obj[key];
        })
    }

    public toIPynb(): nbformat.IBaseCell|nbformat.IBaseCell[] {
        const output: JSONObject = {};
        for (const key of Object.keys(this)) {
            if (BeakerBaseCell.IPYNB_KEYS.includes(key)) {
                output[key] = this[key];
            }
        }
        return output as nbformat.IBaseCell;
    }
}

// Simple payload events

type BeakerQueryTextEventType =
    | "response"
    | "user_question"
    | "user_answer"
    | "abort";

export interface IBeakerQueryTextEvent extends PartialJSONObject {
    type: BeakerQueryTextEventType;
    content: string;
};

// Specific-payload types

type BeakerQueryCellEventType = "code_cell";

export interface IBeakerQueryCellEvent extends PartialJSONObject {
    type: BeakerQueryCellEventType;
    content: {
        cell_id: string;
        parent_id: string;
        metadata: PartialJSONObject;
    };
};

type BeakerQueryErrorEventType = "error";

export interface IBeakerQueryErrorEvent extends PartialJSONObject {
    type: BeakerQueryErrorEventType;
    content: {
        ename: string;
        evalue: string;
        traceback: string[];
    };
}

export type BeakerToolCallState =
    | "pending"
    | "running"
    | "done"
    | "error"
    | "cancelled";

export interface IBeakerToolCall extends PartialJSONObject {
    tool_call_id: string;
    tool_name: string;
    tool_input: any;
    state: BeakerToolCallState;
    started_at?: string;
    ended_at?: string;
    output_preview?: string;
    output_truncated?: boolean;
    error?: {
        ename: string;
        evalue: string;
        traceback?: string[];
    };
}

type BeakerQueryThoughtType = "thought";
export interface IBeakerQueryThoughtEvent extends PartialJSONObject {
    type: BeakerQueryThoughtType;
    content: {
        thought: string;
        thought_id: string;
        tool_calls: IBeakerToolCall[];
    };
}

// umbrella-type for events

export type BeakerQueryEventType =
    | BeakerQueryTextEventType
    | BeakerQueryCellEventType
    | BeakerQueryErrorEventType
    | BeakerQueryThoughtType
    ;

export type BeakerQueryEvent =
    | IBeakerQueryTextEvent
    | IBeakerQueryCellEvent
    | IBeakerQueryErrorEvent
    | IBeakerQueryThoughtEvent
    ;


export interface IQueryCell extends nbformat.IBaseCell {
    cell_type: 'query';
    events: BeakerQueryEvent[];
}

export class BeakerRawCell extends BeakerBaseCell implements nbformat.IRawCell {
    cell_type: "raw" = "raw";
    attachments?: nbformat.IAttachments;
    declare metadata: Partial<nbformat.IRawCellMetadata>;

    constructor(content: nbformat.ICell) {
        super(content);
        Object.assign(this, content)
    }

    public execute(session: BeakerSession): IBeakerFuture | null {
        return null
    };
}

export class BeakerCodeCell extends BeakerBaseCell implements nbformat.ICodeCell {
    cell_type: "code" = "code";
    outputs: nbformat.IOutput[] = [];
    execution_count: nbformat.ExecutionCount = null;
    declare metadata: Partial<nbformat.ICodeCellMetadata>;
    last_execution?: BeakerCellExecutionStatus = {status: "none"};
    busy?: boolean = false;

    constructor(content: Partial<nbformat.ICell>) {
        super({ ...content});
        Object.assign(this, content)
    }

    public execute(session: BeakerSession, syntheticFuture?: BeakerCellFuture): IBeakerFuture | null {
        this.busy = true;

        var future: BeakerCellFuture | IShellFuture;
        this.outputs.splice(0, this.outputs.length);
        if (syntheticFuture !== undefined) {
            future = syntheticFuture;
        }
        else {
            future = session.sendBeakerMessage(
                "execute_request",
                {
                    code: this.source,
                    silent: false,
                    store_history: true,
                    user_expressions: {},
                    allow_stdin: true,
                    stop_on_error: false,
                }
            );
            future.onIOPub = (msg: IBeakerIOPubMessage) => BeakerCellFutures.handleIOPub(msg, this);
            future.onReply = (msg: IBeakerShellMessage) => BeakerCellFutures.handleReply(msg, this);
        }
        return future;
    }

    public rollback(session: BeakerSession): IBeakerFuture | null {
        if (this?.last_execution?.status === "ok") {
            const future = session.executeAction(
                "rollback",
                {
                    checkpoint_index: this.last_execution.checkpoint_index || null
                }
            );
            // Treat rolling back like an execution as it may fail
            this.busy = true;

            // Clear outputs and children when rollback completes
            future.done.then((reply_msg: messages.IExecuteReplyMsg) => {
                if (reply_msg.content.status === "ok") {
                    this.busy = false;
                    this.last_execution = {"status": "none"};
                    this.execution_count = null;
                    this.outputs.splice(0, this.outputs.length);
                    this.children.splice(0, this.children.length);
                }
                else if (reply_msg.content.status === "error") {
                    this.last_execution = reply_msg.content;
                    this.outputs.push({...reply_msg.content, output_type: "error"})
                }
            });
            return future;
        }
        return null;
    };

    public reset_execution_state(): void {
        this.last_execution = {status: "modified"};
    }

    public toIPynb(): nbformat.ICodeCell {
        const result: nbformat.ICodeCell = {
            ...(super.toIPynb() as nbformat.IBaseCell),
            cell_type: "code",
            outputs: this.outputs.map(
                (output) => {
                    return {
                    ...output,
                    transient: undefined,
                    }

                }
            ),
            execution_count: this.execution_count,
        };
        return result;
    }
}

export class BeakerMarkdownCell extends BeakerBaseCell implements nbformat.IMarkdownCell {
    static IPYNB_KEYS = ["cell_type", "source", "metadata", "id", "attachments"];
    cell_type: "markdown" = "markdown";
    attachments?: nbformat.IAttachments;

    constructor(content: Partial<nbformat.ICell>) {
        super({ ...content});
        Object.assign(this, content)
    }


    public execute(session: BeakerSession): IBeakerFuture | null {
        // TODO: Replace this with code to render markdown.
        return null;
    };

    public toIPynb(): nbformat.IBaseCell|nbformat.IBaseCell[] {
        const output: JSONObject = {};
        for (const key of Object.keys(this)) {
            if (BeakerMarkdownCell.IPYNB_KEYS.includes(key)) {
                output[key] = this[key];
            }
        }
        return output as nbformat.IBaseCell;
    }
}

export class BeakerQueryCell extends BeakerBaseCell implements IQueryCell {
    cell_type: "query" = "query";
    events: BeakerQueryEvent[] = [];
    _current_input_request_message?: messages.IInputRequestMsg;
    _toolCallIndex: Map<string, {eventIndex: number; slot: number}> = new Map();

    constructor(content: Partial<nbformat.ICell>) {
        super({cell_type: 'query', ...content});
        Object.assign(this, content)
    }

    public execute(session: BeakerSession, includeNotebookState: boolean = true): IBeakerFuture | null {
        this.events.splice(0, this.events.length);
        this.children.splice(0, this.children.length);
        this._toolCallIndex.clear();

        const handleIOPub = async (msg: IBeakerIOPubMessage) => {
            const msg_type = msg.header.msg_type;
            const content = msg.content;
            if (msg_type === "status") {
                this.status = content.execution_state;
            }
            else if (msg_type === "llm_thought") {
                const tool_calls: IBeakerToolCall[] = (content.tool_calls || []).map(
                    (tc: any) => ({
                        tool_call_id: tc.tool_call_id,
                        tool_name: tc.tool_name,
                        tool_input: tc.tool_input,
                        state: (tc.state as BeakerToolCallState) || "pending",
                    })
                );
                if (!content.thought && tool_calls.length === 0) {
                    return;
                }
                const event: IBeakerQueryThoughtEvent = {
                    type: "thought",
                    content: {
                        thought: content.thought || "",
                        thought_id: content.thought_id,
                        tool_calls,
                    }
                };
                this.events.push(event);
                // Index by events-array position rather than by raw object reference.
                // Reactive consumers (Vue) only observe mutations made through the
                // proxy — i.e. through `this.events[idx]` — so we re-fetch the event
                // via index when applying updates.
                const eventIndex = this.events.length - 1;
                tool_calls.forEach((tc, slot) => {
                    if (tc.tool_call_id) {
                        this._toolCallIndex.set(tc.tool_call_id, {eventIndex, slot});
                    }
                });
            }
            else if (msg_type === "tool_call_update") {
                const entry = this._toolCallIndex.get(content.tool_call_id);
                if (entry === undefined) {
                    return;
                }
                const {eventIndex, slot} = entry;
                const event = this.events[eventIndex] as IBeakerQueryThoughtEvent;
                if (!event || event.type !== "thought") {
                    return;
                }
                const existing = event.content.tool_calls[slot];
                const {tool_call_id: _id, ...updateFields} = content;
                // Mutate via the proxy-wrapped event so Vue picks up the change.
                event.content.tool_calls = [
                    ...event.content.tool_calls.slice(0, slot),
                    {...existing, ...updateFields},
                    ...event.content.tool_calls.slice(slot + 1),
                ];
            }
            else if (msg_type === "llm_response" && content.name === "response_text") {
                this.events.push({
                    type: "response",
                    content: content.text,
                });
            }
            else if (msg_type === "code_cell") {
                const nb = session.notebook;
                const codeCell = new BeakerCodeCell({
                    cell_type: "code",
                    source: content.code,
                    metadata: {
                        parent_cell: this.id,
                    },
                    outputs: [],
                });

                const queryCellIndex = nb.cells.findIndex((cell) => (cell.id === this.id));
                if (queryCellIndex >= 0) {
                    session.notebook.cells.splice(queryCellIndex + 1, 0, codeCell);
                }
                else {
                    nb.addCell(codeCell);
                }
            }
            else if (msg_type === "add_child_codecell") {
                const autoexecute = content.autoexecute;
                const codeCell = new BeakerCodeCell({
                    cell_type: "code",
                    source: content.code,
                    metadata: {
                        parent_cell: this.id,
                    },
                    outputs: [],
                    busy: true,
                });
                codeCell.last_execution = {
                    status: "pending",
                    checkpoint_index: content.checkpoint_index,
                }
                // cell is stored in events - we point the children field to the same object
                // to make selection and execution work
                this.events.push({
                    type: "code_cell",
                    content: {
                        parent_id: this.id,
                        cell_id: codeCell.id,
                        metadata: {}
                    }
                });
                this.children.push(codeCell);

                const reactiveCell = this.children[this.children.length - 1] as BeakerCodeCell;
                if (autoexecute && content.execute_request_msg) {
                    const executeRequest = content.execute_request_msg;
                    const future = new BeakerCellFuture(
                        executeRequest,  // Message that is presumably sent
                        true,  // expectReply
                        true,  // disposeOnDone
                        session.kernel,  // kernel
                        reactiveCell,  // relatedCodecell
                    );
                }
            }
            else if (msg_type == "update_child_codecell") {
                const cellId = content.id;
                const cell = this.children.find((value) => (value.id === cellId));
                if (cell === undefined || cell === null) {
                    console.log("Can't find cell");
                    throw Error("Cell to be updated not found ")
                }

                cell.execution_count = content.execution_count;
                let status : BeakerCellExecutionStatus = {
                    status: content.execution_status
                }

                if (content.execution_status === "error") {
                    const error_details = {
                        ename: msg.content.ename,
                        evalue: msg.content.evalue,
                        traceback: msg.content.traceback,
                    };
                    cell.outputs.push({
                        output_type: "error",
                        ...error_details,
                    });
                    status = {...status, ...error_details};
                }
                else if (status.status === "ok") {
                    status = {...status, checkpoint_index: content.checkpoint_index};
                    cell.outputs.push({
                        output_type: "execute_result",
                        data: {
                            "text/plain": content.execution_return
                        }
                    });
                }
                cell.last_execution = status;
            }
        };

        const handleStdin = async (msg: messages.IStdinMessage) => {
            if (messages.isInputRequestMsg(msg)) {
                this.events.push({
                    type: "user_question",
                    content: msg.content.prompt,
                });
                this.status = "awaiting_input";
                this._current_input_request_message = msg;
            }
        }

        const handleReply = async (msg: messages.IExecuteReplyMsg) => {
            if (msg.content.status === "ok") {
                this.last_execution = {
                    status: "ok",
                };
            }
            else if (msg.content.status === "error") {
                const error_details = {
                    ename: msg.content.ename,
                    evalue: msg.content.evalue,
                    traceback: msg.content.traceback,
                };
                this.last_execution = {
                    status: "error",
                    ...error_details
                };
                this.events.push({
                    type: "error",
                    content: {...msg.content}
                });
            }
            else if (msg.content.status === "abort") {
                this.last_execution = {
                    status: "abort",
                };
                this.events.push({
                    type: "abort",
                    content: "Request aborted",
                });
            }
        };

        var metadata: PartialJSONObject = {};

        if (includeNotebookState) {
            const notebookState = session.notebook.toIPynb();
            notebookState.cells = notebookState.cells.filter(
                // Skip this cell and any children of this cell
                cell => cell.id !== this.id && cell.metadata?.parent_cell !== this.id
            );
            metadata["notebook_state"] = notebookState
        }

        const future = session.sendBeakerMessage(
            "llm_request",
            {
                request: this.source
            },
            undefined,
            metadata,
        );
        future.onIOPub = handleIOPub;
        future.onStdin = handleStdin;
        future.onReply = handleReply;
        return future;
    };

    public respond(response: string, session: BeakerSession) {
        // Only handle if we're awaiting input
        if (this.status !== "awaiting_input" || !this._current_input_request_message) {
            return;
        }

        this.events.push({
            type: "user_answer",
            content: response,
        });

        // Send the reply to the kernel
        session.kernel?.sendInputReply(
            {
                "value": response,
                "status": "ok",
            },
            this._current_input_request_message.header,
        );

        //cleanup
        this.status = "busy";
        this._current_input_request_message = undefined;
    }

    public toMultipleCells(): [BeakerMarkdownCell, ...BeakerBaseCell[]] {
        // break apart a query cell into a series of cells so that code is interspersed with markdown cells
        // and that in a jupyter notebook, loading and saving handles the redundant cells / query cell mapping

        // Transient classes for organizing strings.
        class JoinableMarkdown extends String {
            public prefix: string = "";
            public suffix: string = "";
        }
        class IndentedMarkdown extends JoinableMarkdown {
            public prefix = `
<div style="display: flex; width: 100%;">
<div style="padding: 0.2rem; margin: 0.2rem; margin-left: 4rem;">\n\n`;
            public suffix = `</div></div>\n\n`;
        }
        class AgentMarkdown extends JoinableMarkdown {
            public prefix = `
### Agent:
<div style="display: flex; width: 100%;">
<div style="padding: 0.2rem; margin: 0.2rem; margin-left: 4rem;">\n\n`;
            public suffix = `</div></div>\n\n`;
        }
        class FinalResponseMarkdown extends AgentMarkdown {}
        class UserMarkdown extends JoinableMarkdown {
            public prefix = `
### User:
<div style="display: flex; width: 100%;">
<div style="padding: 0.2rem; margin: 0.2rem; margin-left: 4rem;">\n\n`;
            public suffix = `</div></div>\n\n`;
        }

        // only tag first cell with all metadata to reconstruct, and let the rest get dropped on fromIPynb
        const parentMetadata = {
            ...this.metadata,
            beaker_cell_type: "query",
            prompt: this.source,
            events: this.events,
        };

        const eventElements: (JoinableMarkdown|IndentedMarkdown|BeakerBaseCell)[] = this.events.map((event) => {
            if (event.type === "thought") {
                const lines: string[] = [];
                if (event.content.thought) {
                    lines.push(`${event.content.thought}  `);
                }
                for (const tc of event.content.tool_calls || []) {
                    const argsBlob = JSON.stringify(tc.tool_input ?? {});
                    const stateLabel = tc.state ? ` [${tc.state}]` : "";
                    lines.push(`- \`${tc.tool_name}\`${stateLabel} — \`${argsBlob}\``);
                    if (tc.output_preview) {
                        const previewSuffix = tc.output_truncated ? "…" : "";
                        lines.push(`  - output: \`${tc.output_preview}${previewSuffix}\``);
                    }
                    if (tc.error) {
                        lines.push(`  - error: \`${tc.error.ename}: ${tc.error.evalue}\``);
                    }
                }
                return new AgentMarkdown(`${lines.join("\n")}\n`);
            }
            else if (event.type === "user_question") {
                return new AgentMarkdown(`**Agent Question:**  \n> ${event.content}\n`);
            }
            else if (event.type === "user_answer") {
                return new UserMarkdown(`**User Response:**  \n> ${event.content}\n`);
            }
            else if (event.type === "code_cell") {
                const childCell = this.children.find(child => child.id === event.content.cell_id);
                if (childCell === undefined) {
                    throw `Failed to find child cell ${event.content.cell_id} in children`
                }
                childCell.metadata.beaker_child_of = this.id;
                childCell.metadata.beakerQueryCellChild = true;
                return childCell;
            }
            else if (event.type === "response") {
                var output: string;
                if (typeof event.content === "string") {
                    const lines = event.content.split("\n")
                        .map(line => (/^\s*$/.test(line) ? "" : `${line}`))
                        // add an extra ## to shrink agent markdown output headers under notebook "agent" header
                        .map(line => /^#+\s+/.test(line) ? `###${line}` : line);
                    output = `\n${lines.join("\n")}`;
                }
                else {
                    output = `\n${event.content}`;
                }
                return new FinalResponseMarkdown(output);
            }
            else if (event.type === "abort") {
                return new JoinableMarkdown(event.content);
            }
            else if (event.type === "error") {
                return new BeakerMarkdownCell({
                    cell_type: 'markdown',
                    id: uuidv4(),
                    source: [JSON.stringify(event.content, undefined, 2)],
                    metadata: { ...parentMetadata, parentQueryCell: true, beakerQueryCellChild: true, },
                })
            }
            else {
                return new JoinableMarkdown(`Error: Unhandled query event type "${event.type}".`)
            }
        });

        let outputElements: (nbformat.IBaseCell|JoinableMarkdown)[] = [
            // new JoinableMarkdown('### User:'),
            new UserMarkdown(`${this.source}`),
            ...eventElements,
        ];

        let lastSeenElement = null;
        let cell = new BeakerMarkdownCell(
                {
                    cell_type: "markdown",
                    id: this.id,
                    source: [],
                    // contains all parent metadata
                    metadata: { ...parentMetadata, parentQueryCell: true },
                }
            );
        const outputCells: IBeakerCell[] = [
            cell,
        ];
        for (let element of outputElements) {
            if (element instanceof JoinableMarkdown) {
                if ((lastSeenElement === null && element.prefix)) {
                    if (element.prefix) {
                        (cell.source as string[]).push(element.prefix);
                    }
                }
                if ((lastSeenElement === null) || (lastSeenElement.constructor === element.constructor)) {
                    (cell.source as string[]).push(element as unknown as string)
                }
                else if (!(lastSeenElement instanceof JoinableMarkdown)) {
                    cell = new BeakerMarkdownCell({
                        cell_type: "markdown",
                        id: uuidv4(),
                        source: [],
                        metadata: { skipWhenLoading: true, beakerQueryCellChild: true },
                    })
                    if (element instanceof FinalResponseMarkdown) {
                        cell.metadata.finalResponse = true;
                    }
                    if (element.prefix) {
                        (cell.source as string[]).push(element.prefix);
                    }
                    (cell.source as string[]).push(element as unknown as string);
                    outputCells.push(cell);
                }
                else {
                    if (lastSeenElement.suffix) {
                        (cell.source as string[]).push(lastSeenElement.suffix);
                    }
                    if (element.prefix) {
                        (cell.source as string[]).push(element.prefix);
                    }
                    (cell.source as string[]).push(element as unknown as string);
                }
            }
            else {
                if (lastSeenElement instanceof JoinableMarkdown && lastSeenElement.suffix) {
                        (cell.source as string[]).push(lastSeenElement.suffix);
                }
                outputCells.push(element);
            }
            lastSeenElement = element;
        }
        return outputCells as [BeakerMarkdownCell, ...BeakerBaseCell[]];
    }

    // public fromJSON(obj: any) {
    //     if (this.metadata.beaker_cell_type !== "query") {
    //         throw TypeError("Cell is trying to be parsed as a query cell, but doesn't have the required metadata.")
    //     }
    //     this.source = obj.metadata.prompt;
    //     this.events = obj.metadata.events;
    // }

    // public toJSON() {
    //     return this.toMarkdownCell();
    // }

    public fromIPynb(obj: any) {
        if (this.metadata.beaker_cell_type !== "query") {
            throw TypeError("Cell is trying to be parsed as a query cell, but doesn't have the required metadata.")
        }
        this.source = obj.metadata.prompt;
        this.events = obj.metadata.events;

    }

    public toIPynb(): [nbformat.IMarkdownCell, ...nbformat.IBaseCell[]] {
        return this.toMultipleCells().flatMap(cell => cell.toIPynb()) as [nbformat.IMarkdownCell, ...nbformat.IBaseCell[]]
    }
}

export type IBeakerCell = BeakerCodeCell | BeakerMarkdownCell | BeakerRawCell | nbformat.IUnrecognizedCell;

export class BeakerNotebookContent implements nbformat.INotebookContent {

    [key: string]: PartialJSONValue;
    nbformat: number = 4;
    nbformat_minor: number = 5;
    metadata: nbformat.INotebookMetadata = {};
    cells: BeakerBaseCell[] = [];
}

export class BeakerNotebook {

    constructor() {

        this.content = {
            nbformat: 4,
            nbformat_minor: 5,
            cells: [],
            metadata: {
                "kernelspec": {
                    "display_name": "Beaker Kernel",
                    "name": "beaker",
                    "language": "beaker",
                   },
                   "language_info": this.subkernelInfo,
            },
        }

        // Using a Proxy to get around issues with reactivity in getters/setters
        this.cells = new Proxy(this.content.cells, {});
    }

    public toJSON() {
        this.content.metadata.language_info = this.subkernelInfo;
        return {...this.content};
    }

    public fromJSON(obj: any) {
        Object.keys(obj).forEach((key) => {
            this.content[key] = obj[key];
        })
        this.cells = new Proxy(this.content.cells, {});
    }

    public loadFromIPynb(obj: any) {
        this.content.nbformat = obj.nbformat;
        this.content.nbformat_minor = obj.nbformat_minor;
        const cellList = obj.cells
            .map((cell: IBeakerCell) => {
                if (cell.cell_type === "raw") {
                    return new BeakerRawCell(cell);
                }
                else if (cell.cell_type === "code") {
                    return new BeakerCodeCell(cell);
                }
                else if (cell.metadata.beaker_cell_type === "query") {
                    return new BeakerQueryCell({
                        cell_type: "query",
                        id: cell.id,
                        source: cell.metadata.prompt as nbformat.MultilineString,
                        events: cell.metadata.events,
                        metadata: cell.metadata,
                    });
                }
                else if (cell.cell_type === "markdown") {
                    if (cell.metadata?.skipWhenLoading === true) {
                        return;
                    }
                    return new BeakerMarkdownCell(cell);
                }
                else {
                    return new BeakerRawCell(cell);
                }
            })
            .filter((cell: BeakerBaseCell | undefined) => cell);

        let cellMap: {[uuid: string]: BeakerBaseCell} = {};
        cellList.forEach((cell: BeakerBaseCell) => {
            cellMap[cell.id] = cell;
        });

        let i = 0;
        while (i < cellList.length) {
            const cell = cellList[i];
            if (typeof(cell.metadata.beaker_child_of) !== "undefined") {
                cellMap[cell.metadata.beaker_child_of].children.push(cellList.splice(i, 1)[0]);
            }
            else {
                i++;
            }
        }

        this.cells.splice(
            0,
            this.cells.length,
            ...cellList
        );
        this.content.metadata = obj.metadata;
    }

    public toIPynb() {
        this.content.metadata.language_info = this.subkernelInfo;
        return {
            nbformat: this.content.nbformat,
            nbformat_minor: this.content.nbformat_minor,
            cells: this.content.cells.flatMap((cell: BeakerBaseCell): nbformat.IBaseCell | nbformat.IBaseCell[] => cell.toIPynb()),
            metadata: this.content.metadata,
        }
    }

    public addCell(cell: IBeakerCell | nbformat.ICell) {
        this.cells.push(cell);
    }

    public insertCell(cell: IBeakerCell | nbformat.ICell, position: number) {
        this.cells.splice(position, 0, cell);
    }

    public removeCell(index: number) {
        this.cells.splice(index, 1);
    }

    public cutCell(index: number) {
        const removedValues = this.cells.splice(index, 1);
        if (removedValues.length > 0) {
            return removedValues[0];
        }
        return null;
    }

    public moveCell(fromIndex: number, toIndex: number) {
        if (fromIndex !== toIndex) {
            const cell = this.cutCell(fromIndex);
            if (cell) {
                this.insertCell(cell, toIndex);
            }
        }
    }

    public setSubkernelInfo(sessionInfo: any) {
        this.subkernelInfo = {
            "name": sessionInfo.subkernel,
            "display_name": sessionInfo.language,
        }
    };

    public content: BeakerNotebookContent;
    public cells: IBeakerCell[];
    private subkernelInfo?: nbformat.ILanguageInfoMetadata;
}
