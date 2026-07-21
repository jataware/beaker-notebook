import { ref, toValue, type MaybeRefOrGetter } from 'vue';
import { useRouter } from 'vue-router';

// Module-scoped singleton: a raw upload File handed off from a page that does
// not itself parse skill uploads (e.g. the notebook) to the integrations page,
// which owns the parse/preview flow. Module scope is deliberate — it must
// survive the route navigation that unmounts the originating page.
const pendingUploadFile = ref<File | null>(null);

export interface UseIntegrationUploadOptions {
    /** Session id to forward so the integrations page resolves the same session. */
    sessionId?: MaybeRefOrGetter<string | null | undefined>;
}

export interface UseIntegrationUploadReturn {
    handleUpload: (file: File) => Promise<void>;
    takePendingUpload: () => File | null;
}

/**
 * Bridges the IntegrationPanel `upload` event from pages that cannot handle it
 * in place (currently the notebook) over to the integrations page. The raw
 * File is stashed and the integrations page is opened in "new skill" mode,
 * where the existing upload handler picks the file up and parses it.
 */
export const useIntegrationUpload = (
    options: UseIntegrationUploadOptions = {},
): UseIntegrationUploadReturn => {
    const router = useRouter();

    const handleUpload = async (file: File): Promise<void> => {
        pendingUploadFile.value = file;
        // `selected=upload` is a distinct signal from `selected=new` (a blank
        // new integration): it tells the integrations page to consume the
        // stashed file rather than open an empty editor.
        const query: Record<string, string> = { selected: 'upload' };
        const sessionId = toValue(options.sessionId);
        if (sessionId) {
            query.session = sessionId;
        }
        await router.push({ name: 'integrations', query });
    };

    // Consumed once by the integrations page; clears the stash so a later blank
    // "New → Skill" does not re-trigger a stale import.
    const takePendingUpload = (): File | null => {
        const file = pendingUploadFile.value;
        pendingUploadFile.value = null;
        return file;
    };

    return {
        handleUpload,
        takePendingUpload,
    };
};
