import { inject } from 'vue';

interface SiteSessionConfig {
    sessionId?: string;
    sessionInPath?: boolean;
}

export function useSiteSession(fallback: string) {
    const siteConfig = inject<SiteSessionConfig>('siteConfig', {});
    return {
        sessionId: siteConfig.sessionId || new URLSearchParams(window.location.search).get('session') || fallback,
        sessionInPath: siteConfig.sessionInPath ?? false,
    };
}
