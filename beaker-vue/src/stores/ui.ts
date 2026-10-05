import { defineStore } from 'pinia';
import { ref, watch, type Ref } from 'vue';

import { type SideMenuState, SideMenuStateDefaults } from '@/components/sidemenu/SideMenu.vue';

/**
 *  UI state
 */
const LocalStoragePrefix = "beaker-notebook:ui:";

const uiState = <T>(
    slug: string,
    defaultValue: T,
    migrate?: (value: T) => T,
): Ref<T> => {
    const localStorageKey = (slug: string): string => {
        return `${LocalStoragePrefix}${slug}`;
    }
    const getLocalStoreValue = (key: string, defaultValue: T): T => {
        const rawValue = localStorage.getItem(key);
        if (rawValue === null) {
            return structuredClone(defaultValue);
        }
        else {
            try {
                const value = JSON.parse(rawValue) as T;
                return migrate ? migrate(value) : value;
            }
            catch {
                return structuredClone(defaultValue);
            }
        }
    }
    const setLocalStoreValue = (key: string, value: T): void => {
        const rawValue = JSON.stringify(value);
        localStorage.setItem(key, rawValue);
    }

    const key = localStorageKey(slug);
    const value = getLocalStoreValue(key, defaultValue);
    const internalRef = ref(value) as Ref<T>;

    watch(internalRef, () => {
        setLocalStoreValue(key, internalRef.value);
    }, {deep: true});

    return internalRef;
}


export const useUIStore = defineStore('beaker-ui', () => {
    const leftMenuState = uiState<SideMenuState>("leftMenuState", SideMenuStateDefaults);
    const rightMenuState = uiState<SideMenuState>(
        "rightMenuState",
        SideMenuStateDefaults,
        // Existing saved state reflects a user choice, before userModified was tracked.
        (value) => ({...value, userModified: value.userModified ?? true}),
    );

    return {
        leftMenuState,
        rightMenuState,
    };
});
