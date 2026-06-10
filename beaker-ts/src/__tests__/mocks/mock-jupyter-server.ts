// An in-memory Jupyter server for tests: it satisfies the REST handshake that
// brings a SessionContext up to a connected kernel, and routes kernel messages
// over a MockWebSocket so that real beaker-ts + real jupyterlab connection code
// runs end-to-end against a scripted "kernel".
//
// Usage:
//   const server = new MockJupyterServer({ wireProtocol: 'v1' });
//   server.onExecute((ctx, count) => {
//     ctx.io('stream', { name: 'stdout', text: 'hi\n' });
//     ctx.reply('execute_reply', { status: 'ok', execution_count: count });
//   });
//   const session = new BeakerSession({ settings: server.serverSettings, ... });
//   await session.sessionReady;
//
// The wire protocol defaults to 'v1' (binary) because that is what Beaker uses
// in production; pass 'json' to exercise the default text codec.
import { ServerConnection } from '@jupyterlab/services/lib/serverconnection';

import {
  KernelMessage,
  MessageHeader,
  WireProtocol,
  deserialize,
  makeMessage,
  serialize,
  wireProtocolHeader,
} from './protocol';
import { MockWebSocket, SocketHost } from './mock-websocket';

const BASE_URL = 'http://localhost:8888/';
const WS_URL = 'ws://localhost:8888/';

/**
 * Passed to each message handler. Replies are auto-correlated to the triggering
 * request (parent_header + session) so handlers describe intent, not plumbing.
 */
export interface HandlerContext {
  /** The decoded request that triggered this handler. */
  readonly request: KernelMessage;
  /** Emit an IOPub message (parent = request). */
  io(msgType: string, content?: Record<string, unknown>, buffers?: (ArrayBuffer | ArrayBufferView)[]): void;
  /** Emit a reply on the request's own channel (e.g. shell execute_reply). */
  reply(msgType: string, content?: Record<string, unknown>, buffers?: (ArrayBuffer | ArrayBufferView)[]): void;
  /** Shorthand for an IOPub `status` message. */
  status(state: 'busy' | 'idle' | 'starting'): void;
  /** Allocate the next monotonic execution count. */
  nextExecutionCount(): number;
}

export type MessageHandler = (ctx: HandlerContext) => void | Promise<void>;
export type ExecuteHandler = (ctx: HandlerContext, executionCount: number) => void | Promise<void>;

export interface MockJupyterServerOptions {
  wireProtocol?: WireProtocol;
}

export class MockJupyterServer implements SocketHost {
  readonly wireProtocol: WireProtocol;

  private readonly handlers = new Map<string, MessageHandler>();
  private readonly sockets = new Set<MockWebSocket>();
  private readonly kernelId = `mock-kernel-${cryptoRandomId()}`;
  private readonly sessionId = `mock-session-${cryptoRandomId()}`;
  private executionCount = 0;
  private session: { id: string; path: string; name: string; type: string; kernel: { id: string; name: string } } | null = null;

  constructor(options: MockJupyterServerOptions = {}) {
    this.wireProtocol = options.wireProtocol ?? 'v1';
    this.installDefaultHandlers();
  }

  // -- handler registration -------------------------------------------------

  /** Register (or replace) a handler for a given client message type. */
  on(msgType: string, handler: MessageHandler): this {
    this.handlers.set(msgType, handler);
    return this;
  }

  /**
   * Convenience wrapper for `execute_request`: emits the standard
   * busy → execute_input → (your outputs/reply) → idle envelope so handlers
   * only have to describe the interesting middle.
   */
  onExecute(handler: ExecuteHandler): this {
    return this.on('execute_request', async (ctx) => {
      const count = ctx.nextExecutionCount();
      ctx.status('busy');
      ctx.io('execute_input', {
        code: (ctx.request.content as { code?: string }).code ?? '',
        execution_count: count,
      });
      await handler(ctx, count);
      ctx.status('idle');
    });
  }

  private installDefaultHandlers(): void {
    // The connection sends kernel_info_request as soon as it connects and will
    // not report "ready" until it receives the reply.
    this.on('kernel_info_request', (ctx) => {
      ctx.status('busy');
      ctx.reply('kernel_info_reply', {
        status: 'ok',
        protocol_version: '5.3',
        implementation: 'mock',
        implementation_version: '1.0.0',
        language_info: {
          name: 'python',
          version: '3.11.0',
          mimetype: 'text/x-python',
          file_extension: '.py',
          pygments_lexer: 'ipython3',
          codemirror_mode: { name: 'ipython', version: 3 },
          nbconvert_exporter: 'python',
        },
        banner: 'Mock Beaker kernel',
        help_links: [],
      });
      ctx.status('idle');
    });
  }

  // -- SocketHost -----------------------------------------------------------

  get negotiatedProtocol(): string {
    return wireProtocolHeader(this.wireProtocol);
  }

  attachSocket(socket: MockWebSocket): void {
    this.sockets.add(socket);
  }

  detachSocket(socket: MockWebSocket): void {
    this.sockets.delete(socket);
  }

  handleClientMessage(data: unknown, socket: MockWebSocket): void {
    const msg = deserialize(data as never, this.negotiatedProtocol) as unknown as KernelMessage;
    const handler = this.handlers.get(msg.header.msg_type);
    if (!handler) {
      // Unhandled request types are ignored; register a handler to script them.
      return;
    }
    const ctx = this.makeContext(msg, socket);
    void Promise.resolve(handler(ctx)).catch((err) => {
      // Surface handler errors loudly rather than hanging the awaiting future.
      console.error(`MockJupyterServer handler for "${msg.header.msg_type}" threw:`, err);
    });
  }

  private makeContext(request: KernelMessage, socket: MockWebSocket): HandlerContext {
    const parentHeader = request.header;
    const session = request.header.session;
    const emit = (
      channel: string,
      msgType: string,
      content?: Record<string, unknown>,
      buffers?: (ArrayBuffer | ArrayBufferView)[],
    ): void => {
      const message = makeMessage({ channel, msgType, session, parentHeader, content, buffers });
      socket.emitMessage(serialize(message as never, this.negotiatedProtocol) as string | ArrayBuffer);
    };

    return {
      request,
      io: (msgType, content, buffers) => emit('iopub', msgType, content, buffers),
      reply: (msgType, content, buffers) => emit(request.channel, msgType, content, buffers),
      status: (state) => emit('iopub', 'status', { execution_state: state }),
      nextExecutionCount: () => (this.executionCount += 1),
    };
  }

  // -- server settings ------------------------------------------------------

  /** Settings to hand to `new BeakerSession({ settings })`. */
  get serverSettings(): ServerConnection.ISettings {
    return ServerConnection.makeSettings({
      baseUrl: BASE_URL,
      wsUrl: WS_URL,
      appendToken: false,
      fetch: this.fetch as unknown as ServerConnection.ISettings['fetch'],
      WebSocket: this.webSocketClass as unknown as ServerConnection.ISettings['WebSocket'],
    });
  }

  private get webSocketClass(): typeof MockWebSocket {
    const host: SocketHost = this;
    return class BoundMockWebSocket extends MockWebSocket {
      constructor(url: string, protocols?: string | string[]) {
        super(url, protocols, host);
      }
    };
  }

  // -- REST handshake -------------------------------------------------------

  // `ServerConnection.makeRequest` calls `settings.fetch(request)` with a single
  // Request object, so we read url/method/body off it.
  private fetch = async (input: Request | string, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input.url;
    const method = (typeof input === 'string' ? init?.method : input.method) ?? 'GET';
    const { pathname } = new URL(url);
    const readBody = async (): Promise<Record<string, any>> => {
      try {
        if (typeof input === 'string') {
          return init?.body ? JSON.parse(init.body as string) : {};
        }
        return await input.json();
      } catch {
        return {};
      }
    };

    const json = (data: unknown, status = 200): Response =>
      new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
    const noContent = (): Response => new Response(null, { status: 204 });

    if (pathname.endsWith('/api/kernelspecs')) {
      return json(this.kernelSpecsModel());
    }
    if (pathname.endsWith('/api/me')) {
      return json({
        identity: {
          username: 'mock',
          name: 'Mock User',
          display_name: 'Mock User',
          initials: 'M',
          color: '',
          avatar_url: '',
        },
        permissions: {},
      });
    }
    if (pathname.endsWith('/api/sessions')) {
      if (method === 'POST') {
        // jupyterlab starts a session with a generated UUID path, then shuts it
        // down unless the returned model echoes that exact path. So reflect the
        // request body rather than returning a fixed model.
        const body = await readBody();
        this.session = {
          id: this.sessionId,
          path: body.path ?? 'mock-session',
          name: body.name ?? '',
          type: body.type ?? 'notebook',
          kernel: { id: this.kernelId, name: body.kernel?.name ?? 'python3' },
        };
        return json(this.sessionModel(), 201);
      }
      return json(this.session ? [this.sessionModel()] : []);
    }
    if (pathname.includes('/api/sessions/')) {
      if (method === 'DELETE') {
        this.session = null;
        return noContent();
      }
      if (method === 'PATCH') {
        // setPath / setName during startup — merge and reflect.
        const body = await readBody();
        if (this.session) {
          if (typeof body.path === 'string') this.session.path = body.path;
          if (typeof body.name === 'string') this.session.name = body.name;
        }
        return json(this.sessionModel());
      }
      return this.session ? json(this.sessionModel()) : json({ message: 'No such session' }, 404);
    }
    if (pathname.endsWith('/api/kernels')) {
      return method === 'POST' ? json(this.kernelModel(), 201) : json(this.session ? [this.kernelModel()] : []);
    }
    if (pathname.includes('/api/kernels/')) {
      if (method === 'DELETE') {
        return noContent();
      }
      return json(this.kernelModel());
    }
    return new Response(`MockJupyterServer: unhandled ${method} ${pathname}`, { status: 404 });
  };

  private kernelSpecsModel() {
    return {
      default: 'python3',
      kernelspecs: {
        python3: {
          name: 'python3',
          resources: {},
          spec: {
            language: 'python',
            display_name: 'Python 3 (mock)',
            argv: [],
            env: {},
            interrupt_mode: 'signal',
            metadata: {},
          },
        },
      },
    };
  }

  private kernelModel() {
    return {
      id: this.kernelId,
      name: 'python3',
      last_activity: new Date().toISOString(),
      execution_state: 'idle',
      connections: 1,
    };
  }

  private sessionModel() {
    return {
      id: this.session?.id ?? this.sessionId,
      name: this.session?.name ?? '',
      path: this.session?.path ?? 'mock-session',
      type: this.session?.type ?? 'notebook',
      kernel: this.kernelModel(),
    };
  }
}

/** Small unique-id helper (avoids pulling in uuid where any string will do). */
function cryptoRandomId(): string {
  return Math.abs(Math.floor(performance.now() * 1000)).toString(36) + Math.random().toString(36).slice(2, 8);
}
