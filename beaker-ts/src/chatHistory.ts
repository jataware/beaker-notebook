export interface IMessage {
    content: string | (string | {[key: string]: any})[];
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

export interface IChatHistory {
    records: RecordType[];
    systemMessage?: string;
    toolTokenUsageEstimate?: number;
    token_estimate?: number;
    message_token_count?: number;
    summary_token_count?: number;
    model: {
        provider: string;
        model_name: string;
        context_window?: number;
    };
    overhead_token_count?: number;
    summarization_threshold?: number;
}
