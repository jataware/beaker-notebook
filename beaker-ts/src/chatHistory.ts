import { SessionContext } from '@jupyterlab/apputils';
import { IBeakerIOPubMessage } from './notebook';

/**
 * The flattened message shape consumed by the UI.
 *
 * The serialized records carried in {@link INotebookChatHistory} store their
 * message in LangChain's `message_to_dict` form (`{type, data: {...}}`). The
 * UI, however, expects a flat message with a derived `text` field, so
 * {@link ChatHistory} adapts each record into this shape.
 */
export interface IMessage {
    content: string | (string | {[key: string]: any})[];
    text: string;
    responseMetadata: {[key: string]: any};
    type: string;
    name?: string;
    id?: string;
    additionalKwargs?: {[key: string]: any};
    tool_calls?: any[];
    tool_call_id?: string;
}

interface IRecordBase {
    message: IMessage;
    uuid: string;
    token_count?: number;
    metadata?: {[key: string]: any};
}

export interface IMessageRecord extends IRecordBase {
    reactLoopId?: number;
}

export interface ISummaryRecord extends IRecordBase {
    summarizedMessages: string[];
}

export type RecordType = IMessageRecord | ISummaryRecord;

export interface IChatModel {
    provider: string;
    model_name: string;
    context_window?: number;
}

export interface IChatHistory {
    records: RecordType[];
    systemMessage?: string;
    systemMessageRecord?: RecordType;
    systemPreambleRecord?: RecordType;
    userPreambleRecord?: RecordType;
    toolTokenUsageEstimate?: number;
    token_estimate?: number;
    message_token_count?: number;
    summary_token_count?: number;
    model?: IChatModel;
    overhead_token_count?: number;
    summarization_threshold?: number;
}

export interface IHistoryFormatVersion {
    schema: string;
    version: number;
}

/**
 * A serialized record as it arrives over the wire, before adaptation. The
 * `message` is in LangChain's `message_to_dict` envelope form.
 */
interface IRawRecord {
    message: ILangchainMessage;
    uuid: string;
    token_count?: number;
    metadata?: {[key: string]: any};
    react_loop_id?: number;
    summarized_messages?: string[];
}

interface ILangchainMessage {
    type: string;
    data: {
        content?: string | (string | {[key: string]: any})[];
        type?: string;
        name?: string;
        id?: string;
        tool_calls?: any[];
        tool_call_id?: string;
        additional_kwargs?: {[key: string]: any};
        response_metadata?: {[key: string]: any};
        [key: string]: any;
    };
}

interface INotebookChatHistoryModel {
    // The Archytas model metadata uses `class` as the provider/type identifier.
    class?: string;
    provider?: string;
    model_name?: string;
    context_window?: number;
}

export interface INotebookChatHistory {
    format: IHistoryFormatVersion;
    cell_links: {[key: string]: any};
    cell_links_format: IHistoryFormatVersion;
    history: {
        format: IHistoryFormatVersion;
        metadata?: {
            model?: INotebookChatHistoryModel;
            current_loop_id?: number;
            summarization_threshold?: number;
            tool_token_estimate?: number;
            token_estimate?: number;
            [key: string]: any;
        };
        raw_records: IRawRecord[];
        summaries?: IRawRecord[];
        system_message?: ILangchainMessage | IRawRecord;
        system_preamble?: ILangchainMessage | IRawRecord;
        user_preamble?: ILangchainMessage | IRawRecord;
    };
    history_encoding: string;
    metadata: {[key: string]: any};
}

const ENCODING_JSON = "json";

/**
 * Derive the displayable `text` for a message from its (possibly structured)
 * content. LangChain content may be a plain string or a list of content
 * blocks, each of which may itself be a string or an object carrying `text`.
 */
function deriveMessageText(content: ILangchainMessage["data"]["content"]): string {
    if (typeof content === "string") {
        return content;
    }
    if (Array.isArray(content)) {
        return content
            .map((part) => {
                if (typeof part === "string") {
                    return part;
                }
                return part?.text ?? "";
            })
            .join("");
    }
    return "";
}

/**
 * Flatten a LangChain `message_to_dict` envelope into the {@link IMessage}
 * shape the UI consumes.
 */
function adaptMessage(raw: ILangchainMessage | undefined): IMessage {
    const data = raw?.data ?? {};
    const content = data.content ?? "";
    return {
        content,
        text: deriveMessageText(content),
        type: data.type ?? raw?.type ?? "",
        name: data.name,
        id: data.id,
        tool_calls: data.tool_calls,
        tool_call_id: data.tool_call_id,
        additionalKwargs: data.additional_kwargs,
        responseMetadata: data.response_metadata ?? {},
    };
}

function adaptRecord(raw: IRawRecord): RecordType {
    const base: IRecordBase = {
        message: adaptMessage(raw.message),
        uuid: raw.uuid,
        token_count: raw.token_count,
        metadata: raw.metadata,
    };
    if (raw.summarized_messages !== undefined) {
        return {
            ...base,
            summarizedMessages: raw.summarized_messages,
        };
    }
    return {
        ...base,
        reactLoopId: raw.react_loop_id,
    };
}

/**
 * Adapt a system-message / preamble field, which may serialize either as a
 * record envelope (carrying its own `uuid`/`token_count`) or, defensively, as
 * a bare langchain message.
 */
function adaptOptionalRecord(field: ILangchainMessage | IRawRecord | undefined): RecordType | undefined {
    if (!field) {
        return undefined;
    }
    if ((field as IRawRecord).message !== undefined) {
        return adaptRecord(field as IRawRecord);
    }
    return adaptRecord({ message: field as ILangchainMessage, uuid: "" });
}


export class ChatHistory implements IChatHistory {

    public constructor(history?: INotebookChatHistory) {
        if (history) {
            this.setChatHistory(history);
        }
    }

    public setChatHistory(notebook_history: INotebookChatHistory) {
        this._doc = notebook_history;
        this._recordsCache = undefined;
        if (notebook_history?.history_encoding && notebook_history.history_encoding !== ENCODING_JSON) {
            // The inner history was compressed (gzip+base64) on the wire. We do
            // not currently decompress in the browser, so the records/metadata
            // getters will read as empty until that is supported.
            console.warn(
                `ChatHistory received unsupported history_encoding "${notebook_history.history_encoding}"; ` +
                `chat history display will be unavailable until decompression is implemented.`
            );
        }
    }

    private get history() {
        const history = this._doc?.history;
        // Guard against a compressed (string) history payload.
        if (typeof history !== "object" || history === null) {
            return undefined;
        }
        return history;
    }

    private get historyMetadata() {
        return this.history?.metadata ?? {};
    }

    get records(): RecordType[] {
        if (this._recordsCache === undefined) {
            const rawRecords = this.history?.raw_records ?? [];
            this._recordsCache = rawRecords.map(adaptRecord);
        }
        return this._recordsCache;
    }

    get systemMessage(): string | undefined {
        return this.systemMessageRecord?.message.text || undefined;
    }

    get systemMessageRecord(): RecordType | undefined {
        return adaptOptionalRecord(this.history?.system_message);
    }

    get systemPreambleRecord(): RecordType | undefined {
        return adaptOptionalRecord(this.history?.system_preamble);
    }

    get userPreambleRecord(): RecordType | undefined {
        return adaptOptionalRecord(this.history?.user_preamble);
    }

    get toolTokenUsageEstimate(): number | undefined {
        return this.historyMetadata.tool_token_estimate;
    }

    get token_estimate(): number | undefined {
        return this.historyMetadata.token_estimate;
    }

    get message_token_count(): number {
        return this.records
            .filter((record) => !("summarizedMessages" in record))
            .reduce((sum, record) => sum + (record.token_count ?? 0), 0);
    }

    get summary_token_count(): number {
        return (this.history?.summaries ?? []).reduce(
            (sum, summary) => sum + (summary.token_count ?? 0),
            0,
        );
    }

    get model(): IChatModel | undefined {
        const model = this.historyMetadata.model;
        if (!model) {
            return undefined;
        }
        return {
            provider: model.provider ?? model.class ?? "",
            model_name: model.model_name ?? "",
            context_window: model.context_window,
        };
    }

    get overhead_token_count(): number {
        // Overhead (tool definitions, system/instruction tokens, subkernel
        // state, etc.) is not serialized directly. Derive it as the remainder
        // of the total estimate after accounting for message/summary tokens so
        // the usage breakdown still sums to the total estimate.
        const total = this.token_estimate;
        if (total === undefined) {
            return this.toolTokenUsageEstimate ?? 0;
        }
        return Math.max(0, total - this.message_token_count - this.summary_token_count);
    }

    get summarization_threshold(): number | undefined {
        return this.historyMetadata.summarization_threshold;
    }

    get initialized(): boolean {
        return Boolean(this.model) || Boolean(this.records.length);
    }

    /**
     * Produce a plain, immutable {@link IChatHistory} snapshot of the current
     * state. The UI consumes a snapshot rather than this instance directly so
     * that each update yields a fresh object reference, keeping framework
     * reactivity (and any derived computed state) correct.
     */
    public snapshot(): IChatHistory {
        return {
            records: this.records,
            systemMessage: this.systemMessage,
            systemMessageRecord: this.systemMessageRecord,
            systemPreambleRecord: this.systemPreambleRecord,
            userPreambleRecord: this.userPreambleRecord,
            toolTokenUsageEstimate: this.toolTokenUsageEstimate,
            token_estimate: this.token_estimate,
            message_token_count: this.message_token_count,
            summary_token_count: this.summary_token_count,
            model: this.model,
            overhead_token_count: this.overhead_token_count,
            summarization_threshold: this.summarization_threshold,
        };
    }

    /**
     * Serialize back to the on-the-wire {@link INotebookChatHistory} document
     * so the history round-trips when sent to the kernel (e.g. via
     * `context_setup_request`) or persisted into notebook metadata.
     */
    public toJSON(): INotebookChatHistory | undefined {
        return this._doc;
    }

    private async onAddChatRecord(record: IRawRecord) {
        if (this.history) {
            this.history.raw_records.push(record);
            this._recordsCache = undefined;
        }
    }

    private async onSetChatHistory(chatHistory: INotebookChatHistory) {
        this.setChatHistory(chatHistory);
    }

    public registerHandlers(sessionContext: SessionContext) {
        const onMessage = (sender: SessionContext, message: IBeakerIOPubMessage) => {
            if (message.header.msg_type == "add_chat_record") {
                this.onAddChatRecord(<IRawRecord>message.content);
            }
            else if (message.header.msg_type == "set_chat_history") {
                this.onSetChatHistory(<INotebookChatHistory>message.content);
            }
        }
        sessionContext.iopubMessage.connect(onMessage);
    }


    private _doc?: INotebookChatHistory;
    private _recordsCache?: RecordType[];
}
