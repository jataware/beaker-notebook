import type { ISessionAttachment } from '@jataware/beaker-client';
import { fetch } from '@/util/fetch';


const route = (sessionId: string, attachmentId?: string) => {
    const base = `/beaker/attachments/${encodeURIComponent(sessionId)}`;
    return attachmentId ? `${base}/${encodeURIComponent(attachmentId)}` : base;
};

const errorMessage = async (response: Response): Promise<string> => {
    try {
        const payload = await response.json();
        return payload.message || response.statusText;
    } catch {
        return response.statusText || `Request failed with status ${response.status}`;
    }
};

export async function uploadSessionAttachment(
    sessionId: string,
    file: File,
    signal?: AbortSignal,
): Promise<ISessionAttachment> {
    const form = new FormData();
    form.append('file', file, file.name);
    const response = await fetch(route(sessionId), {
        method: 'POST',
        body: form,
        signal,
    });
    if (!response.ok) {
        throw new Error(await errorMessage(response));
    }
    return await response.json() as ISessionAttachment;
}

export async function deleteSessionAttachment(
    sessionId: string,
    attachmentId: string,
): Promise<void> {
    const response = await fetch(route(sessionId, attachmentId), {method: 'DELETE'});
    if (!response.ok && response.status !== 404) {
        throw new Error(await errorMessage(response));
    }
}
