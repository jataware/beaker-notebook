/** Minimal interface the host must satisfy for the BeakerFetchClientKey inject. */
export interface IFetchClient {
    fetch(url: string, options?: RequestInit): Promise<Response>;
    setBaseUrl(baseUrl: string): void;
    setDefaultHeaders(urlRegex: string | RegExp, headers: HeadersInit): void;
    readonly baseUrl: string;
}
