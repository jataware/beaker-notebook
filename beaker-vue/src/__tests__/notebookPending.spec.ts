import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, reactive, ref } from 'vue';
import { Signal } from '@lumino/signaling';
import BeakerAgentQuery from '../components/agent/BeakerAgentQuery.vue';

vi.mock('../composables/useWorkflows', () => ({
    useWorkflows: () => ({workflows: ref([]), attachedWorkflowId: ref(null), attachedWorkflow: ref(null)}),
}));
vi.mock('../util/attachments', () => ({
    uploadSessionAttachment: vi.fn(async () => ({id: 'attachment-one', kind: 'file'})),
    deleteSessionAttachment: vi.fn(),
}));

const Textarea = defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
});
const Button = defineComponent({
    props: ['disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
});

function setup(queueState: string) {
    let state: any = {state: 'empty', revision: 0};
    let listener: ((sender: unknown, message: any) => void) | undefined;
    const signal = {
        connect: vi.fn((fn) => { listener = fn; }),
        disconnect: vi.fn(),
    };
    const session = {
        sessionId: 'session',
        session: {ready: Promise.resolve(), iopubMessage: signal},
        addQueryCell: vi.fn(() => ({id: 'cell'})),
        sendBeakerMessage: vi.fn((_type, content) => {
            const future: any = {dispose: vi.fn()};
            queueMicrotask(() => {
                let result = state;
                if (content.operation === 'queue') {
                    result = queueState === 'pending'
                        ? {state: 'pending', id: content.id, text: content.text, revision: 1}
                        : {state: queueState};
                    if (queueState === 'pending') {
                        state = result;
                        listener?.(null, {header: {msg_type: 'llm_pending_update'}, content: result});
                    }
                } else if (content.operation === 'edit') {
                    result = {...state, text: content.text, revision: state.revision + 1};
                    state = result;
                    listener?.(null, {header: {msg_type: 'llm_pending_update'}, content: result});
                } else if (content.operation === 'cancel') {
                    result = {state: 'cancelled', id: content.id, revision: 2};
                    state = result;
                    listener?.(null, {header: {msg_type: 'llm_pending_update'}, content: result});
                }
                future.onReply({content: {status: 'ok', return: result}});
            });
            return future;
        }),
    };
    const showToast = vi.fn();
    const execute = vi.fn();
    const notebook = {notebook: {cells: []}, selectCell: vi.fn()};
    const wrapper = mount(BeakerAgentQuery, {
        global: {
            provide: {
                session, notebook, show_toast: showToast,
                beakerSession: {findNotebookCellById: () => ({execute})},
            },
            mocks: {$tmpl: {_: (_key: string, fallback: string) => fallback}},
            directives: {tooltip: {}},
            stubs: {Button, ContainedTextArea: Textarea},
        },
    });
    return {wrapper, session, showToast, execute};
}

describe('notebook pending messages', () => {
    it('queues and cancels text without creating a query cell', async () => {
        const {wrapper, session} = setup('pending');
        await flushPromises();
        await wrapper.get('textarea').setValue('change the plan');
        await wrapper.get('.agent-submit-button').trigger('click');
        await flushPromises();
        expect(wrapper.text()).toContain('change the plan');
        expect(session.addQueryCell).not.toHaveBeenCalled();
        await wrapper.get('[aria-label="Edit pending message"]').trigger('click');
        await wrapper.get('textarea').setValue('updated plan');
        await wrapper.get('[aria-label="Save pending message"]').trigger('click');
        await flushPromises();
        expect(wrapper.text()).toContain('updated plan');
        await wrapper.get('[aria-label="Cancel pending message"]').trigger('click');
        await flushPromises();
        expect(wrapper.find('textarea').exists()).toBe(true);
        wrapper.unmount();
    });

    it('clears the pending input when the raw Jupyter signal reports the message sent', async () => {
        const context: any = {ready: Promise.resolve()};
        context.iopubMessage = new Signal(context);
        let finishInitialization: () => void;
        const sessionReady = new Promise<void>((resolve) => { finishInitialization = resolve; });
        const session = reactive({
            session: undefined as any,
            sessionReady,
            addQueryCell: vi.fn(),
            sendBeakerMessage: vi.fn((_type, content) => {
                const future: any = {dispose: vi.fn()};
                queueMicrotask(() => {
                    const result = content.operation === 'queue'
                        ? {state: 'pending', id: content.id, text: content.text, revision: 1}
                        : {state: 'empty', revision: 0};
                    future.onReply({content: {status: 'ok', return: result}});
                });
                return future;
            }),
        });
        const wrapper = mount(BeakerAgentQuery, {
            global: {
                provide: {
                    session, notebook: {notebook: {cells: []}}, show_toast: vi.fn(),
                    beakerSession: {},
                },
                mocks: {$tmpl: {_: (_key: string, fallback: string) => fallback}},
                directives: {tooltip: {}},
                stubs: {Button, ContainedTextArea: Textarea},
            },
        });
        await flushPromises();
        expect(session.sendBeakerMessage).not.toHaveBeenCalled();
        session.session = context;
        finishInitialization();
        await flushPromises();
        await wrapper.get('textarea').setValue('during the loop');
        await wrapper.get('.agent-submit-button').trigger('click');
        await flushPromises();
        expect(wrapper.text()).toContain('Pending');
        const queueCall = session.sendBeakerMessage.mock.calls.find(([, content]) => content.operation === 'queue');
        context.iopubMessage.emit({
            header: {msg_type: 'llm_pending_update'},
            content: {state: 'sent', id: queueCall[1].id, text: 'during the loop', revision: 2},
        });
        await flushPromises();
        expect(wrapper.find('textarea').exists()).toBe(true);
        expect(wrapper.text()).not.toContain('Pending');
        wrapper.unmount();
    });

    it('does not subscribe if unmounted before session initialization', async () => {
        let finishInitialization: () => void;
        const sessionReady = new Promise<void>((resolve) => { finishInitialization = resolve; });
        const context = {iopubMessage: {connect: vi.fn(), disconnect: vi.fn()}};
        const session = reactive({sessionReady, session: undefined as any, sendBeakerMessage: vi.fn()});
        const wrapper = mount(BeakerAgentQuery, {
            global: {
                provide: {session, notebook: {notebook: {cells: []}}, show_toast: vi.fn(), beakerSession: {}},
                mocks: {$tmpl: {_: (_key: string, fallback: string) => fallback}},
                directives: {tooltip: {}},
                stubs: {Button, ContainedTextArea: Textarea},
            },
        });
        wrapper.unmount();
        session.session = context;
        finishInitialization();
        await flushPromises();
        expect(context.iopubMessage.connect).not.toHaveBeenCalled();
        expect(session.sendBeakerMessage).not.toHaveBeenCalled();
    });

    it('replies to an agent question without queuing a message', async () => {
        const {wrapper, session} = setup('pending');
        const respond = vi.fn();
        await flushPromises();
        await wrapper.setProps({awaitingInputCell: {respond}, awaitingInputQuestion: 'Question?'});
        await wrapper.get('textarea').setValue('answer');
        await wrapper.get('.agent-submit-button').trigger('click');
        expect(respond).toHaveBeenCalledWith('answer', session);
        expect(session.sendBeakerMessage).not.toHaveBeenCalledWith('llm_pending_request', expect.objectContaining({operation: 'queue'}));
        wrapper.unmount();
    });

    it('keeps text and attachments when a busy agent cannot accept them', async () => {
        const {wrapper, session, showToast} = setup('attachments_not_supported');
        await flushPromises();
        await wrapper.get('textarea').setValue('inspect this');
        const input = wrapper.get('[data-testid="attachment-file-input"]');
        Object.defineProperty(input.element, 'files', {value: [new File(['x'], 'data.txt')]});
        await input.trigger('change');
        await flushPromises();
        await wrapper.get('.agent-submit-button').trigger('click');
        await flushPromises();
        expect(session.sendBeakerMessage).toHaveBeenCalledWith('llm_pending_request', expect.objectContaining({
            operation: 'queue', has_attachments: true,
        }));
        expect(showToast).toHaveBeenCalledWith(expect.objectContaining({detail: expect.stringContaining('Please remove the attachment')}));
        expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('inspect this');
        expect(wrapper.text()).toContain('data.txt');
        expect(session.addQueryCell).not.toHaveBeenCalled();
        wrapper.unmount();
    });

    it('sends attachments normally when the agent is idle', async () => {
        const {wrapper, session, execute} = setup('inactive');
        await flushPromises();
        const input = wrapper.get('[data-testid="attachment-file-input"]');
        Object.defineProperty(input.element, 'files', {value: [new File(['x'], 'data.txt')]});
        await input.trigger('change');
        await flushPromises();
        await wrapper.get('.agent-submit-button').trigger('click');
        await flushPromises();
        expect(session.addQueryCell).toHaveBeenCalledWith('Please inspect the attached file(s).', {}, [expect.objectContaining({id: 'attachment-one'})]);
        expect(execute).toHaveBeenCalled();
        wrapper.unmount();
    });
});
