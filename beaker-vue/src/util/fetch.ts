import { URLExt } from '@jupyterlab/coreutils';

type DefaultHeaders = Record<string, HeadersInit>;

class FetchClient {
  private defaultHeaders: DefaultHeaders;

  constructor(defaultHeaders: DefaultHeaders = {}) {
    this.defaultHeaders = defaultHeaders;
  }

  setDefaultHeaders(urlRegex: string|RegExp, headers: HeadersInit) {
    this.defaultHeaders[urlRegex.toString()] = headers;
  }

  async fetch(url: string, options?: RequestInit): Promise<Response> {
    const absUrl = URLExt.parse(url).href;
    const headers = Object.entries(this.defaultHeaders).reduce<HeadersInit>((prev, [regex, headers]) => {
      if (new RegExp(regex).test(absUrl)) {
        return {...prev, ...headers};
      }
      else {
        return prev;
      }
    }, {});

    return fetch(url, {
      ...options,
      headers: {
        ...headers,
        ...options?.headers,
      },
    });
  }
}

// Create a default fetch client instance
export const client = new FetchClient();

// Export the fetch method bound to the default instance
const fetchMethod = client.fetch.bind(client);
export {fetchMethod as fetch};
