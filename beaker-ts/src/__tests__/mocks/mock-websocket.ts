// A transport-only WebSocket shim that satisfies the subset of the WebSocket
// interface jupyterlab's KernelConnection uses. It carries no protocol
// knowledge — encoding/decoding and message routing live in the host
// (MockJupyterServer), so this class can stay dumb and reusable.
//
// jupyterlab constructs the socket as `new settings.WebSocket(url, protocols)`
// (two args), so the owning server binds itself into a subclass; see
// MockJupyterServer.webSocketClass.

export interface SocketHost {
  /** The subprotocol the "server" reports back on open ('' or the v1 token). */
  readonly negotiatedProtocol: string;
  /** Raw frame (string | ArrayBuffer) sent by the client (jupyterlab). */
  handleClientMessage(data: unknown, socket: MockWebSocket): void;
  attachSocket(socket: MockWebSocket): void;
  detachSocket(socket: MockWebSocket): void;
}

type SocketEvent = { type: string; [key: string]: unknown };
type Listener = (event: SocketEvent) => void;

export class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  url: string;
  protocol = '';
  binaryType: 'blob' | 'arraybuffer' = 'blob';
  readyState: number = MockWebSocket.CONNECTING;

  onopen: Listener | null = null;
  onmessage: Listener | null = null;
  onclose: Listener | null = null;
  onerror: Listener | null = null;

  private _host: SocketHost;
  private _listeners = new Map<string, Set<Listener>>();

  constructor(url: string, _protocols: string | string[] | undefined, host: SocketHost) {
    this.url = url;
    this._host = host;
    this._host.attachSocket(this);
    // Open on a macrotask so the caller has assigned its on* handlers first
    // (jupyterlab assigns them synchronously right after construction).
    setTimeout(() => this._open(), 0);
  }

  private _open(): void {
    if (this.readyState !== MockWebSocket.CONNECTING) {
      return;
    }
    this.protocol = this._host.negotiatedProtocol;
    this.readyState = MockWebSocket.OPEN;
    this._dispatch('open', { type: 'open' });
  }

  /** Client → server. */
  send(data: string | ArrayBufferLike | ArrayBufferView): void {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('MockWebSocket: send() called while socket is not OPEN');
    }
    this._host.handleClientMessage(data, this);
  }

  /** Server → client. `raw` is already serialized for the negotiated protocol. */
  emitMessage(raw: string | ArrayBuffer): void {
    if (this.readyState !== MockWebSocket.OPEN) {
      return;
    }
    this._dispatch('message', { type: 'message', data: raw });
  }

  close(code = 1000, reason = ''): void {
    if (this.readyState === MockWebSocket.CLOSED) {
      return;
    }
    this.readyState = MockWebSocket.CLOSED;
    this._host.detachSocket(this);
    this._dispatch('close', { type: 'close', code, reason, wasClean: true });
  }

  addEventListener(type: string, listener: Listener): void {
    if (!this._listeners.has(type)) {
      this._listeners.set(type, new Set());
    }
    this._listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: Listener): void {
    this._listeners.get(type)?.delete(listener);
  }

  private _dispatch(type: string, event: SocketEvent): void {
    const handler = (this as unknown as Record<string, Listener | null>)[`on${type}`];
    if (typeof handler === 'function') {
      handler.call(this, event);
    }
    this._listeners.get(type)?.forEach((listener) => listener.call(this, event));
  }
}
