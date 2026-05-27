import { ref, watch, nextTick, type Ref } from 'vue';
import type { BeakerSessionComponentType } from '../components/session/BeakerSession.vue';
import type { IBeakerQueryThoughtEvent } from '@jataware/beaker-client';

export function useQueryCellFlattening(
    beakerSession: () => BeakerSessionComponentType,
    truncateAgentCodeCells: Ref<boolean>
) {
    const processedQueryEvents = ref<Map<string, Set<number>>>(new Map());

    const findCellByMetadata = (parentQueryId: string, eventIndex: number, cellType: 'thought' | 'response' | 'code' | 'user_question' | 'user_answer' | 'error' | 'abort') => {
        const notebook = beakerSession().session.notebook;
        return notebook.cells.find(cell =>
            cell.metadata?.parent_query_cell === parentQueryId &&
            cell.metadata?.query_event_index === eventIndex &&
            cell.metadata?.beaker_cell_type === cellType
        );
    };

    // scan existing cells
    const initializeProcessedEvents = () => {
        const notebook = beakerSession()?.session?.notebook;
        if (!notebook) return;

        processedQueryEvents.value.clear();

        for (const cell of notebook.cells) {
            if (cell.metadata?.parent_query_cell && cell.metadata?.query_event_index !== undefined) {
                const parentQueryId = cell.metadata.parent_query_cell;
                const eventIndex = cell.metadata.query_event_index;

                if (!processedQueryEvents.value.has(parentQueryId)) {
                    processedQueryEvents.value.set(parentQueryId, new Set());
                }
                processedQueryEvents.value.get(parentQueryId).add(eventIndex);
            }
        }
    };

    // insert position after a query cell
    const findInsertionPosition = (queryCellId: string): number => {
        const notebook = beakerSession().session.notebook;
        const queryCellIndex = notebook.cells.findIndex(cell => cell.id === queryCellId);
        if (queryCellIndex === -1) return notebook.cells.length; // append at end if not found

        // last cell that's related the query
        let insertIndex = queryCellIndex + 1;
        while (insertIndex < notebook.cells.length &&
               notebook.cells[insertIndex].metadata?.parent_query_cell === queryCellId) {
            insertIndex++;
        }

        return insertIndex;
    };

    const createCellMetadata = (cellType: string, queryCellId: string, eventIndex: number, additionalMetadata = {}) => {
        return {
            beaker_cell_type: cellType,
            parent_query_cell: queryCellId,
            query_event_index: eventIndex,
            ...additionalMetadata
        };
    };

    function moveCellToPosition(currentIndex: number, insertPosition: number) {
        if (currentIndex !== insertPosition) {
            beakerSession().session.notebook.moveCell(currentIndex, insertPosition);
        }
    }

    const createAndPositionMarkdownCell = (source: string, queryCellId: string, metadata: any) => {
        const insertPosition = findInsertionPosition(queryCellId);
        const markdownCell = beakerSession().session.addMarkdownCell(source, metadata);

        moveCellToPosition(beakerSession().session.notebook.cells.length - 1, insertPosition);
        return markdownCell;
    };

    const createAndPositionCodeCell = (source: string, queryCellId: string, metadata: any, outputs: any[] = []) => {
        const insertPosition = findInsertionPosition(queryCellId);
        const codeCell = beakerSession().session.addCodeCell(source, metadata, outputs);

        moveCellToPosition(beakerSession().session.notebook.cells.length - 1, insertPosition);
        return codeCell;
    };

    const createThoughtCell = (thoughtContent: IBeakerQueryThoughtEvent["content"], queryCellId: string, eventIndex: number) => {
        if (findCellByMetadata(queryCellId, eventIndex, 'thought')) {
            return;
        }

        if(thoughtContent?.thought === null || thoughtContent?.thought.length === 0 || thoughtContent.thought === "Thinking...") {
            return;
        }

        const metadata = createCellMetadata('thought', queryCellId, eventIndex, {thought: thoughtContent});
        const markdownContent = `**Beaker Agent:**\n\n${thoughtContent.thought}`;
        return createAndPositionMarkdownCell(markdownContent, queryCellId, metadata);
    };

    const createResponseCell = (responseContent: string, queryCellId: string, eventIndex: number) => {
        if (findCellByMetadata(queryCellId, eventIndex, 'response')) {
            return;
        }

        let markdownContent = '';
        if (typeof responseContent === 'string') {
            markdownContent = `**Beaker Agent:**\n\n${responseContent}`;
        } else if (responseContent && typeof responseContent === 'object') {
            markdownContent = `\`\`\`json\n${JSON.stringify(responseContent, null, 2)}\n\`\`\``;
        }

        const metadata = createCellMetadata('response', queryCellId, eventIndex);

        return createAndPositionMarkdownCell(markdownContent, queryCellId, metadata);
    };

    const createCodeCell = (codeCellId: string, queryCell: any, queryCellId: string, eventIndex: number) => {
        const currentTruncateValue = truncateAgentCodeCells.value;

        if (findCellByMetadata(queryCellId, eventIndex, 'code')) {
            return;
        }

        const childCell = queryCell.children?.find(child => child.id === codeCellId);
        if (!childCell) {
            return;
        }

        const shouldCollapse = currentTruncateValue === true;

        const metadata = createCellMetadata('code', queryCellId, eventIndex, {
            source_cell_id: codeCellId,
            collapsed: shouldCollapse
        });

        const newCodeCell = createAndPositionCodeCell(
            childCell.source,
            queryCellId,
            metadata,
            childCell.outputs || []
        );

        newCodeCell.execution_count = childCell.execution_count;
        if (childCell.last_execution) {
            newCodeCell.last_execution = {
                ...childCell.last_execution,
                status: 'ok'
            };
        } else if (childCell.outputs && childCell.outputs.length > 0) {
            newCodeCell.last_execution = {
                status: 'ok',
                checkpoint_index: undefined
            };
        }

        return newCodeCell;
    };

    const createErrorCell = (errorContent: any, queryCellId: string, eventIndex: number) => {
        if (findCellByMetadata(queryCellId, eventIndex, 'error')) {
            return;
        }

        let markdownContent = '';
        if (typeof errorContent === 'string') {
            markdownContent = `**Error:**\n\n${errorContent}`;
        } else if (errorContent && typeof errorContent === 'object') {
            if (errorContent.ename && errorContent.evalue) {
                markdownContent = `**Error:**\n\n**${errorContent.ename}:** ${errorContent.evalue}`;
                if (errorContent.traceback && errorContent.traceback.length > 0) {
                    markdownContent += `\n\n\`\`\`\n${errorContent.traceback.join('\n')}\n\`\`\``;
                }
            } else {
                markdownContent = `**Error:**\n\n\`\`\`json\n${JSON.stringify(errorContent, null, 2)}\n\`\`\``;
            }
        }

        const metadata = createCellMetadata('error', queryCellId, eventIndex);

        return createAndPositionMarkdownCell(markdownContent, queryCellId, metadata);
    };

    const createQuestionCell = (questionContent: string, queryCellId: string, eventIndex: number) => {
        if (findCellByMetadata(queryCellId, eventIndex, 'user_question')) {
            return;
        }

        const markdownContent = `**Agent Question:**\n\n${questionContent}`;
        const metadata = createCellMetadata('user_question', queryCellId, eventIndex);

        return createAndPositionMarkdownCell(markdownContent, queryCellId, metadata);
    };

    const updateQuestionCellWithReply = (replyContent: string, queryCellId: string, eventIndex: number) => {
        // the question should be in a previous event index
        let questionCell = null;
        let questionEventIndex = eventIndex - 1;

        // look backwards for the most recent question cell
        while (questionEventIndex >= 0 && !questionCell) {
            questionCell = findCellByMetadata(queryCellId, questionEventIndex, 'user_question');
            questionEventIndex--;
        }

        if (questionCell) {
            const currentContent = questionCell.source;
            const alreadyContainsReply = currentContent.includes(`**User Response:**`);
            // prevents responses from being added twice when reloading the page on intermediate states:
            if (!alreadyContainsReply) {
                const updatedContent = `${currentContent}\n\n**User Response:**\n\n${replyContent}`;
                questionCell.source = updatedContent;
            }
            return questionCell;
        } else {
            return createReplyCell(replyContent, queryCellId, eventIndex);
        }
    };

    const createReplyCell = (replyContent: string, queryCellId: string, eventIndex: number) => {
        if (findCellByMetadata(queryCellId, eventIndex, 'user_answer')) {
            return;
        }

        const markdownContent = `**User Response:**\n\n${replyContent}`;
        const metadata = createCellMetadata('user_answer', queryCellId, eventIndex);

        return createAndPositionMarkdownCell(markdownContent, queryCellId, metadata);
    };

    const setupQueryCellFlattening = (cells: () => any[]) => {
        watch(
            cells,
            (cellsArray) => {
                if (!cellsArray) return;

                if (processedQueryEvents.value.size === 0) {
                    initializeProcessedEvents();
                }

                for (const cell of cellsArray) {
                    if (cell.cell_type === 'query') {
                        const queryStatus = cell.metadata?.query_status;
                        const isInProgress = queryStatus === 'in-progress' || queryStatus === 'pending';
                        const isCompleted = queryStatus === 'success' || queryStatus === 'failed' || queryStatus === 'aborted';

                        if (isCompleted) {
                            continue;
                        }

                        if (isInProgress) {
                            if (!cell.metadata) {
                                cell.metadata = {};
                            }
                            cell.metadata.is_flattened = true;

                            if (!processedQueryEvents.value.has(cell.id)) {
                                processedQueryEvents.value.set(cell.id, new Set());
                            }

                            watch(
                                () => cell.events,
                                (events) => {
                                    if (!events || events.length === 0) return;

                                    const processedEvents = processedQueryEvents.value.get(cell.id);

                                    const isCompleted = events.length > 0 &&
                                        ['response', 'error', 'abort'].includes(events[events.length - 1].type);

                                    if (isCompleted && processedEvents.size === events.length) {
                                        return;
                                    }

                                    events.forEach((event, eventIndex) => {
                                        if (processedEvents.has(eventIndex)) {
                                            return;
                                        }

                                        processedEvents.add(eventIndex);

                                        if (event.type === 'thought' && event.content?.thought) {
                                            createThoughtCell(event.content, cell.id, eventIndex);
                                        } else if (event.type === 'code_cell' && event.content?.cell_id) {
                                            nextTick(() => {
                                                createCodeCell(event.content.cell_id, cell, cell.id, eventIndex);
                                            });
                                        } else if (event.type === 'response') {
                                            createResponseCell(event.content, cell.id, eventIndex);
                                        } else if (event.type === 'error') {
                                            createErrorCell(event.content, cell.id, eventIndex);
                                        } else if (event.type === 'user_question') {
                                            createQuestionCell(event.content, cell.id, eventIndex);
                                        } else if (event.type === 'user_answer') {
                                            updateQuestionCellWithReply(event.content, cell.id, eventIndex);
                                        }
                                    });
                                },
                                { deep: true, immediate: true }
                            );
                        } else {
                        }
                    }
                }
            },
            { deep: true, immediate: true }
        );
    };

    const resetProcessedEvents = () => {
        processedQueryEvents.value.clear();
    };

    return {
        processedQueryEvents,
        setupQueryCellFlattening,
        resetProcessedEvents,
        initializeProcessedEvents,
        // createErrorCell,
        // createQuestionCell,
        // createReplyCell,
        // createThoughtCell,
        // createResponseCell,
        // createCodeCell,
    };
}
