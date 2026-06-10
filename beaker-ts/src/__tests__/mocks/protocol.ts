// Jupyter wire-protocol helpers for the in-memory kernel fixture.
//
// We deliberately reuse jupyterlab's own `serialize`/`deserialize` rather than
// reimplementing the frame layouts. Both the default ("") and the binary
// `v1.kernel.websocket.jupyter.org` protocols are symmetric (the server frames
// messages the same way the client does), so the mock "kernel" side can encode
// replies and decode requests with the exact same functions beaker-ts uses on
// the client side. This means the fixture exercises the real framing code and
// surfaces any drift in either protocol.
import { v4 as uuidv4 } from 'uuid';
import { serialize, deserialize } from '@jupyterlab/services/lib/kernel/serialize';
import { supportedKernelWebSocketProtocols } from '@jupyterlab/services/lib/kernel/messages';

/** The binary protocol subprotocol token jupyterlab negotiates by default. */
export const V1_PROTOCOL = supportedKernelWebSocketProtocols.v1KernelWebsocketJupyterOrg;

/** Which wire protocol the mock kernel should speak. */
export type WireProtocol = 'json' | 'v1';

/**
 * The subprotocol string a real server would echo back on the websocket
 * handshake. jupyterlab keys serialization off `socket.protocol`: an empty
 * string selects the default (JSON-or-binary) codec; the v1 token selects the
 * binary codec.
 */
export const wireProtocolHeader = (protocol: WireProtocol): string =>
  protocol === 'v1' ? V1_PROTOCOL : '';

/** Kernel message protocol version we advertise. */
export const PROTOCOL_VERSION = '5.3';

export interface MessageHeader {
  msg_id: string;
  session: string;
  username: string;
  date: string;
  msg_type: string;
  version: string;
}

export interface KernelMessage {
  channel: string;
  header: MessageHeader;
  parent_header: MessageHeader | Record<string, never>;
  metadata: Record<string, unknown>;
  content: Record<string, unknown>;
  buffers?: (ArrayBuffer | ArrayBufferView)[];
}

export const makeHeader = (msgType: string, session: string): MessageHeader => ({
  msg_id: uuidv4(),
  session,
  username: 'mock-kernel',
  date: new Date().toISOString(),
  msg_type: msgType,
  version: PROTOCOL_VERSION,
});

export interface MakeMessageOptions {
  channel: string;
  msgType: string;
  session: string;
  parentHeader?: MessageHeader;
  content?: Record<string, unknown>;
  buffers?: (ArrayBuffer | ArrayBufferView)[];
}

export const makeMessage = (opts: MakeMessageOptions): KernelMessage => ({
  channel: opts.channel,
  header: makeHeader(opts.msgType, opts.session),
  parent_header: opts.parentHeader ?? {},
  metadata: {},
  content: opts.content ?? {},
  buffers: opts.buffers ?? [],
});

export { serialize, deserialize };
