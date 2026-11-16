import { describe, expect, it } from 'vitest';
import { nextTick, reactive, ref } from 'vue';
import { useQueryCellFlattening } from '../composables/useQueryCellFlattening';

describe('notebook query interjections', () => {
    it('creates a separate cell even when a prior agent question was answered', async () => {
        const query = reactive({
            id: 'query', cell_type: 'query', metadata: {query_status: 'in-progress'},
            events: [
                {type: 'user_question', content: 'First question'},
                {type: 'user_answer', content: 'First answer'},
                {type: 'user_answer', content: 'New instruction', interjection: true},
            ],
        });
        const notebook = reactive({
            cells: [query] as any[],
            moveCell(from: number, to: number) {
                this.cells.splice(to, 0, this.cells.splice(from, 1)[0]);
            },
        });
        const session = {
            notebook,
            addMarkdownCell(source: string, metadata: any) {
                const cell = {id: String(notebook.cells.length), cell_type: 'markdown', source, metadata};
                notebook.cells.push(cell);
                return cell;
            },
        };
        const {setupQueryCellFlattening} = useQueryCellFlattening(() => ({session}) as any, ref(false));
        setupQueryCellFlattening(() => notebook.cells);
        await nextTick();
        const question = notebook.cells.find(cell => cell.metadata?.beaker_cell_type === 'user_question');
        const interjection = notebook.cells.find(cell => cell.metadata?.query_event_index === 2);
        expect(question.source).toContain('First answer');
        expect(question.source).not.toContain('New instruction');
        expect(interjection.source).toContain('New instruction');
    });
});
