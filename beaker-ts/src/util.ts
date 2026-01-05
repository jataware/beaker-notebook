import { v4 as uuidv4 } from 'uuid';
import { JSONObject } from '@lumino/coreutils';
import { KernelFutureHandler, KernelShellFutureHandler } from '@jupyterlab/services/lib/kernel/future';
import * as nbformat from '@jupyterlab/nbformat';
import * as Kernel from '@jupyterlab/services/lib/kernel/kernel';
import * as messages from '@jupyterlab/services/lib/kernel/messages';
import { IBeakerShellMessage, BeakerCodeCell, IBeakerIOPubMessage, IBeakerCell, BeakerNotebook, BeakerNotebookContent, BeakerBaseCell } from './notebook';


// Lower case states to match the naming in the messages.
export enum KernelState {
	unknown = 'unknown',
	starting = 'starting',
	idle = 'idle',
	busy = 'busy',
	terminating = 'terminating',
	restarting = 'restarting',
	autorestarting = 'autorestarting',
	dead = 'dead'
}


export const createMessageId = (msgType: string): string => {
	const uuid = uuidv4().replaceAll('-', '').slice(0, 16);
	return `beaker-${uuid}-${msgType}`;
};

// export type IBeakerFutureMessage = IBeakerShellMessage | messages.IShellMessage;

export interface IBeakerFuture<REQUEST extends IBeakerShellMessage = IBeakerShellMessage, REPLY extends IBeakerShellMessage = IBeakerShellMessage> extends Kernel.IShellFuture<REQUEST, REPLY> {
    msgId?: string;
    onResponse?: (msg: any) => void | PromiseLike<void>;
}

export interface IBeakerAvailableContexts {
    [key: string]: {
        languages: {
            slug: string,
            kernel: string,
        },
        defaultPayload: string,
    };
}

export interface IActiveContextInfo {
    slug: string;
    class: string;
    config: JSONObject;
    language: {
        slug: string;
        subkernel: string;
    }
    kernelInfo?: any
}


export class BeakerCellFuture extends KernelFutureHandler<IBeakerShellMessage, IBeakerShellMessage> {
    /**
     * Construct a new KernelFutureHandler.
     */

    constructor(
        msg: IBeakerShellMessage,
        expectReply: boolean,
        disposeOnDone: boolean,
        kernel?: Kernel.IKernelConnection | null,
        cell?: BeakerCodeCell,
    ) {

        if (!kernel) {
            throw Error("Unable to send message. Not connected to kernel.");
        }
        if (!cell) {
            throw Error("Cannot execute in cell as cell is undefined or invalid.");
        }


        const msgId = msg.header.msg_id;
        // Ensure channel is set if created via alternate means
        if (msg.channel === undefined) {
            msg.channel = "shell";
        }
        // Clean up from kernel future list when complete.
        const disposalCallback: (() => void) = () => {
            // @ts-ignore -- Deregister future via private member for cleanup
            kernel._futures.delete(msgId);
        };
        super(disposalCallback, msg, expectReply, disposeOnDone, kernel)
        // @ts-ignore -- Register future via private member
        kernel._futures?.set(msgId, this);
        this.cell = cell;
        this.onIOPub = (msg: IBeakerIOPubMessage) => BeakerCellFutures.handleIOPub(msg, this.cell);
        this.onReply = (msg: IBeakerShellMessage) => BeakerCellFutures.handleReply(msg, this.cell);
    }


    private cell: BeakerCodeCell;
}

export namespace BeakerCellFutures {

    export const handleIOPub = (msg: IBeakerIOPubMessage, cell: IBeakerCell): void => {
        const msg_type = msg.header.msg_type;
        const content = msg.content;
        if (msg_type === "status") {
            cell.status = content.execution_state;
        }
        else if (msg_type === "execute_result") {
            cell.busy = false;
            if (content.execution_count) {
                cell.execution_count = content.execution_count;
            }
            cell.outputs.push({
                output_type: "execute_result",
                ...content
            });
        }
        else if (msg_type === "stream") {
            cell.outputs.push({
                output_type: "stream",
                ...content
            });
        }
        else if (msg_type === "display_data") {
            cell.outputs.push({
                output_type: "display_data",
                ...content
            });
        }
    };

    export const handleReply = (msg: IBeakerShellMessage, cell: IBeakerCell) => {
        cell.busy = false;
        if (msg.content.status === "ok") {
            cell.last_execution = {...cell.last_execution, status: "ok"};
            cell.execution_count = Number(msg.content.execution_count);
        }
        else if (msg.content.status === "error") {
            cell.execution_count = Number(msg.content.execution_count);
            const error_details = {
                ename: msg.content.ename,
                evalue: msg.content.evalue,
                traceback: msg.content.traceback,
            };
            cell.last_execution = {
                status: "error",
                ...error_details
            };
            cell.outputs.push({
                output_type: "error",
                ...error_details
            });
        }
        else if (msg.content.status === "abort") {
            cell.execution_count = msg.content.execution_count;
            const error_details = {
                ename: "Execution aborted",
                evalue: "Execution aborted",
                traceback: [],
            };
            cell.last_execution = {
                status: "error",
                ...error_details,
            };
            cell.outputs.push({
                output_type: "error",
                content: error_details,
            });
        }
    };

}

const maxNotebookElementSize = 1024 * 2;

export function truncateNotebookForAgent(notebook: BeakerNotebook): nbformat.INotebookContent {
    const content = notebook.toIPynb();
    const cells: nbformat.ICell[] = content.cells;
    content.cells = [];
    for (const cell of cells) {
        if (nbformat.isCode(cell)) {
            for (const output of cell.outputs) {
                if (nbformat.isDisplayData(output) || nbformat.isDisplayUpdate(output)) {
                    // For display data, only include any textual descriptions, if included
                    for (const mimetype of Object.keys(output.data)) {
                        if (!mimetype.startsWith("text")) {
                            delete output.data[mimetype];
                        }
                    }
                }
                else if (nbformat.isExecuteResult(output)) {
                    for (const mimetype of Object.keys(output.data)) {
                        var mimeData = output.data[mimetype];
                        const dataLength = JSON.stringify(mimeData).length;
                        if (dataLength > maxNotebookElementSize) {
                            if (Array.isArray(mimeData) && mimeData.every((value) => {return typeof(value) === "string"})) {
                                mimeData = mimeData.join("\n");
                            }
                            if (typeof(mimeData) === "string") {
                                mimeData = mimeData.substring(0, maxNotebookElementSize) + " ... <truncated>"
                            }
                            else {
                                mimeData = `<item of type ${typeof(mimeData)} removed due to size>`;
                            }
                            output.data[mimetype] = mimeData;
                        }
                    }

                }
                else if (nbformat.isStream(output)) {
                    var streamData = output.text;
                    const dataLength = JSON.stringify(streamData).length;
                    if (dataLength > maxNotebookElementSize) {
                        if (Array.isArray(streamData) && streamData.every((value) => {return typeof(value) === "string"})) {
                            mimeData = streamData.join("\n");
                        }
                        if (typeof(streamData) === "string") {
                            streamData = streamData.substring(0, maxNotebookElementSize) + " ... <truncated>"
                        }
                        else {
                            streamData = `<item of type ${typeof(streamData)} removed due to size>`;
                        }
                        output.text = streamData;
                    }
                }
            }
        }
        content.cells.push({...cell});
    }
    return content;
}
