import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent } from 'vue';
import AgentQuery from '../components/chat-interface/AgentQuery.vue';

const Textarea = defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
});
const Button = defineComponent({
    props: ['disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
});

function setup() {
    let state: any = {state: 'empty', revision: 0};
    let listener: ((sender: unknown, message: any) => void) | undefined;
    const signal = {
        connect: vi.fn((fn) => { listener = fn; }),
        disconnect: vi.fn(),
    };
    const broadcast = (next: any) => {
        state = next;
        listener?.(null, {header: {msg_type: 'llm_pending_update'}, content: next});
    };
    const session = {
        session: {ready: Promise.resolve(), iopubMessage: signal},
        notebook: {cells: []},
        addQueryCell: vi.fn(),
        sendBeakerMessage: vi.fn((_type, content) => {
            const future: any = {dispose: vi.fn()};
            queueMicrotask(() => {
                let result = state;
                if (content.operation === 'queue') {
                    result = {state: 'pending', id: content.id, text: content.text, revision: 1};
                    broadcast(result);
                } else if (content.operation === 'edit') {
                    result = {...state, text: content.text, revision: state.revision + 1};
                    broadcast(result);
                } else if (content.operation === 'cancel') {
                    result = {state: 'cancelled', id: content.id, revision: state.revision + 1};
                    broadcast(result);
                }
                future.onReply({content: {status: 'ok', return: result}});
            });
            return future;
        }),
    };
    const wrapper = mount(AgentQuery, {
        global: {
            provide: {session, beakerSession: {}, show_toast: vi.fn()},
            stubs: {
                Card: {template: '<div><slot name="content" /></div>'},
                InputGroup: {template: '<div><slot /></div>'},
                Button,
                ContainedTextArea: Textarea,
            },
        },
    });
    return {wrapper, session, broadcast};
}

describe('pending chat messages', () => {
    it('shows pending text, supports editing, and cancels without creating a query cell', async () => {
        const {wrapper, session} = setup();
        await flushPromises();
        await wrapper.get('textarea').setValue('first');
        await wrapper.get('button').trigger('click');
        await flushPromises();
        expect(wrapper.text()).toContain('Pending');
        expect(wrapper.text()).toContain('first');
        expect(session.addQueryCell).not.toHaveBeenCalled();

        await wrapper.get('[aria-label="Edit pending message"]').trigger('click');
        await wrapper.get('textarea').setValue('updated');
        await wrapper.get('[aria-label="Save pending message"]').trigger('click');
        await flushPromises();
        expect(wrapper.text()).toContain('updated');

        await wrapper.get('[aria-label="Cancel pending message"]').trigger('click');
        await flushPromises();
        expect(wrapper.find('textarea').exists()).toBe(true);
        expect(wrapper.text()).not.toContain('updated');
        wrapper.unmount();
    });

    it('restores an automatically cancelled pending message to the input', async () => {
        const {wrapper, session, broadcast} = setup();
        await flushPromises();
        await wrapper.get('textarea').setValue('follow up');
        await wrapper.get('button').trigger('click');
        await flushPromises();
        const queued = session.sendBeakerMessage.mock.calls.find((call) => call[1].operation === 'queue')![1];
        broadcast({state: 'restored', id: queued.id, text: 'edited follow up', revision: 2});
        await flushPromises();
        expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('edited follow up');
        expect(session.addQueryCell).not.toHaveBeenCalled();
        wrapper.unmount();
    });

    it('ignores an older pending acknowledgment after the sent event', async () => {
        const {wrapper, session, broadcast} = setup();
        await flushPromises();
        broadcast({state: 'sent', id: 'one', text: 'sent', revision: 3});
        broadcast({state: 'pending', id: 'one', text: 'sent', revision: 2});
        await flushPromises();
        expect(wrapper.find('textarea').exists()).toBe(true);
        expect(session.addQueryCell).not.toHaveBeenCalled();
        wrapper.unmount();
    });
});
