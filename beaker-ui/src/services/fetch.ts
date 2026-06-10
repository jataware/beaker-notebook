import { URLExt } from '@jupyterlab/coreutils';

type DefaultHeaders = Record<string, HeadersInit>;

function isRelativeUrl(url: string) {
  if (url.startsWith('.')) {
    return true;
  }
  else if (url.startsWith('/') && !url.startsWith('//')) {
    return true;
  }
  else {
    try {
      const parsedUrl = new URL(url);
      return true;
    }
    catch (e){
      return false;
    }
  }
}

export class FetchClient {
  private defaultHeaders: DefaultHeaders;
  private _baseUrl: string;

  constructor(defaultHeaders: DefaultHeaders = {}) {
    this.defaultHeaders = defaultHeaders;
  }

  setDefaultHeaders(urlRegex: string|RegExp, headers: HeadersInit) {
    this.defaultHeaders[urlRegex.toString()] = headers;
  }

  get baseUrl() {
    return this._baseUrl;
  }

  setBaseUrl(baseUrl) {
    this._baseUrl = baseUrl;
  }

  async fetch(url: string, options?: RequestInit): Promise<Response> {
    // const absUrl = URLExt.parse(url).href;
    const absUrl = ((isRelativeUrl(url) && !url.startsWith(this._baseUrl))
                    ? URLExt.parse(URLExt.join(this.baseUrl, url)).href
                    : URLExt.parse(url).href
    );
    const headers = Object.entries(this.defaultHeaders).reduce<HeadersInit>((prev, [regex, headers]) => {
      if (new RegExp(regex).test(absUrl)) {
        return {...prev, ...headers};
      }
      else {
        return prev;
      }
    }, {});

    return fetch(absUrl, {
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
const fetchMethod: FetchClient["fetch"] = client.fetch.bind(client);
export {fetchMethod as fetch};
