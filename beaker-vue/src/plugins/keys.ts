import type { InjectionKey, Ref } from 'vue';
import type { BeakerSession } from 'beaker-kernel';
import type { BeakerWorkspace } from '../types/workspace';
import type { IFetchClient } from '../types/fetch';
import type { IBeakerContextService } from '../types/context';

// Inject keys for host-provided services.
//
// The host (beaker-ui) sets these up via installBeakerHostPlugins.
// Library components and extensions inject from these keys instead of
// importing module-level singletons.

export const BeakerFetchClientKey: InjectionKey<IFetchClient> =
    Symbol('BeakerFetchClient');

export const BeakerContextServiceKey: InjectionKey<IBeakerContextService> =
    Symbol('BeakerContextService');

export const BeakerWorkspaceKey: InjectionKey<Ref<BeakerWorkspace>> =
    Symbol('BeakerWorkspace');

/**
 * Provides the underlying beaker-ts BeakerSession client
 * (i.e., workspace.client). For most components, injecting the workspace
 * itself is preferred; this key is for code that explicitly wants
 * transport-level access.
 */
export const BeakerSessionKey: InjectionKey<Ref<BeakerSession>> =
    Symbol('BeakerSession');
