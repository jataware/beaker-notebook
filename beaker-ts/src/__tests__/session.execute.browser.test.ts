import { describe, it, expect, afterEach } from 'vitest';
import type { IOutput, IStream, IExecuteResult } from '@jupyterlab/nbformat';

import { BeakerSession } from '../session';
import { BeakerCodeCell } from '../notebook';
import { MockJupyterServer, type WireProtocol } from './mocks';

// Layer-2 integration tests: real beaker-ts + real jupyterlab connection code
// driving a scripted in-memory kernel over a mock websocket. These exercise the
// actual wire-protocol framing (both json and the v1 binary protocol Beaker
// uses in production), connection handshake, future/parent-header correlation,
// and the cell output-collection logic — without a live kernel.

let session: BeakerSession | undefined;

afterEach(() => {
  // Dispose the underlying services to stop the manager polls and close the
  // mock socket, so the run exits cleanly.
  session?.services?.dispose();
  session = undefined;
});

const executeAndCollect = async (wireProtocol: WireProtocol) => {
  const server = new MockJupyterServer({ wireProtocol });
  server.onExecute((ctx, count) => {
    ctx.io('stream', { name: 'stdout', text: 'hello\n' });
    ctx.io('execute_result', {
      execution_count: count,
      data: { 'text/plain': '136' },
      metadata: {},
    });
    ctx.reply('execute_reply', {
      status: 'ok',
      execution_count: count,
      user_expressions: {},
      payload: [],
    });
  });

  session = new BeakerSession({
    settings: server.serverSettings,
    name: 'mock-test',
    kernelName: 'python3',
    sessionId: 'mock-test-session',
  });
  await session.sessionReady;

  const cell = new BeakerCodeCell({
    cell_type: 'code',
    source: 'print("hello"); 21 + 115',
  });

  const future = cell.execute(session);
  expect(future).not.toBeNull();
  await future!.done;

  return cell;
};

describe.each<WireProtocol>(['v1', 'json'])(
  'BeakerSession code execution over mock websocket (%s protocol)',
  (wireProtocol) => {
    it('collects stream + execute_result outputs and ends idle', async () => {
      const cell = await executeAndCollect(wireProtocol);

      expect(cell.status).toBe('idle');
      expect(cell.busy).toBe(false);
      expect(cell.execution_count).toBe(1);

      const outputs = cell.outputs as IOutput[];
      const types = outputs.map((o) => o.output_type);
      expect(types).toContain('stream');
      expect(types).toContain('execute_result');

      const stream = outputs.find((o) => o.output_type === 'stream') as IStream;
      expect(stream.text).toBe('hello\n');

      const result = outputs.find((o) => o.output_type === 'execute_result') as IExecuteResult;
      expect(result.data['text/plain']).toBe('136');
    });
  },
);
