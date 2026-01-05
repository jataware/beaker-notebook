<template>
    <Codemirror
        v-model="model"
        :extensions="extensions"
        :disabled="props.disabled"
        :autofocus="props.autofocus"
        @ready="handleReady"
        @update:modelValue="modelUpdate"
    />
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, inject } from "vue";
import { Codemirror } from "vue-codemirror";
import { EditorView, keymap } from "@codemirror/view";
import { EditorState, Prec, type Extension } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import type { LanguageSupport } from "@codemirror/language";
import { autocompletion, completionKeymap, completionStatus, selectedCompletion, acceptCompletion, closeCompletion, startCompletion, completeFromList } from "@codemirror/autocomplete";
import { AnnotationProviderFactory, type AnnotationData } from "../../util/annotations";
import type { IBeakerTheme } from '../../plugins/theme';
import { type BeakerLanguage, LanguageRegistry, getCompletions } from "../../util/autocomplete";
import { BeakerSession } from 'beaker-kernel';

const session: BeakerSession = inject('session');

declare type DisplayMode = "light" | "dark";

type AnnotationProvider = "linter" | "decoration";

export interface CodeEditorProps {
    displayMode?: DisplayMode,
    language?: string,
    languageOptions?: any,
    autocompleteEnabled?: boolean,
    autocompleteOptions?: string[],
    modelValue: string,

    autofocus?: boolean,
    disabled?: boolean,
    readonly?: boolean,
    annotations?: any[],
    annotationProvider?: AnnotationProvider,
}

const props = withDefaults(defineProps<CodeEditorProps>(), {
    displayMode: "light",
    autocompleteEnabled: true,
    autofocus: false,
    disabled: false,
    annotations: () => [],
    annotationProvider: "linter",
});

const model = ref<string>(props.modelValue);

const emit = defineEmits([
        'submit',
        "update:modelValue",
]);
const { theme } = inject<IBeakerTheme>('theme');

const codeMirrorView = shallowRef<EditorView>();
const codeMirrorState = shallowRef();

const handleReady = ({view, state}) => {
    // See vue codemirror api/npm docs: https://codemirror.net/docs/ref/
    codeMirrorView.value = view;
    codeMirrorState.value = state;
};

const modelUpdate = (newValue: string): void => {
    emit("update:modelValue", newValue);
}

const displayMode = computed<DisplayMode>(() => {
    if (theme.mode === 'default') {
        return 'light';
    }
    else {
        return theme.mode;
    }
});

const extensions = computed(() => {
    // Remove tab and esc keybindings from default CM keymapping.
    const filteredCompletionKeymap = completionKeymap.filter(item => !['Tab', 'Escape'].includes(item.key));
    // Override default CM keymapping the keys.
    const overriddenKeymap = [
        ...filteredCompletionKeymap,
        {key: "Tab", run: (editorView: EditorView) => {
            const editorState = editorView.state;
            const selection = editorState.selection.main;

            const startLine = editorState.doc.lineAt(selection.from);
            const firstNonWhitespaceOffset = startLine.text.match(/\S|$/)?.index || 0;
            const inStartingWhitespace = (
                selection.from >= startLine.from
                && selection.from <= startLine.from + firstNonWhitespaceOffset
            );

            // If an autocomplete is active and something is selected, accept the completion.
            if (completionStatus(editorState) === "active" && selectedCompletion(editorState) !== null) {
                return acceptCompletion(editorView);
            }

            // Only indent if cursor or selection is at start of line
            if (inStartingWhitespace) {
                // Returning false allows default action (indentation)
                return false;
            }

            // Default to starting an autocompletion, if possible.
            startCompletion(editorView);

            // Prevent default action
            return true;
        }},
        // Prevent escape key from exiting cell editing if autocomplete is cancelled by pressing exec.
        {
            // Using built-in helper "any" so we have access to the original keyboard event to allow stopping
            // propagation, preventing blurring the node when cancelling an autocompletion via the escape key.
            any(editorView: EditorView, event: KeyboardEvent) {
                if (event.key === "Escape") {
                    const state = editorView.state;
                    if (completionStatus(state) === "active") {
                        event.stopImmediatePropagation();
                        event.stopPropagation();
                        event.preventDefault();
                        closeCompletion(editorView);
                    }
                    return true;
                }
                return false;
            },
        }
    ];

    const enabledExtensions: Extension[] = [
        // Keymapping
        Prec.highest(keymap.of(overriddenKeymap)),
        EditorState.readOnly.of(props.readonly ?? false),
        EditorView.lineWrapping,
        [EditorView.theme({
            '.cm-scroller': {
                fontFamily: "'Ubuntu Mono', 'Courier New', Courier, monospace",
            }
        })],
    ];
    if (displayMode.value === "dark") {
        enabledExtensions.push(oneDark);
    }


    const language: BeakerLanguage = LanguageRegistry.get(props.language);

    if (props.autocompleteEnabled) {
        let autocompleteOptions;
        if (props.autocompleteOptions) {
            autocompleteOptions = autocompletion({
                override: [completeFromList(props.autocompleteOptions)],
                defaultKeymap: false,
                activateOnCompletion: language?.activateOnCompletion,
            });
        }
        else {
            autocompleteOptions = autocompletion({
                override: [(completion) => getCompletions(completion, session)],
                defaultKeymap: false,
                activateOnCompletion: language?.activateOnCompletion,
            });
        }
        enabledExtensions.push(autocompleteOptions);
    }

    if(language !== undefined) {
        const languageSupport: LanguageSupport = language.initializer(props.languageOptions);
        enabledExtensions.push(
            languageSupport,
        )
    }

    if (props.annotations?.length) {
        try {
            const provider = AnnotationProviderFactory.create(props.annotationProvider || "decoration");
            const annotationExtensions = provider.createExtensions(props.annotations as AnnotationData[]);
            enabledExtensions.push(...annotationExtensions);
        } catch (error) {
            console.warn(`Failed to create annotation provider '${props.annotationProvider}':`, error);
            // fallback to linter
            const fallbackProvider = AnnotationProviderFactory.create("linter");
            const annotationExtensions = fallbackProvider.createExtensions(props.annotations as AnnotationData[]);
            enabledExtensions.push(...annotationExtensions);
        }
    }

    return enabledExtensions;
});

const focus = () => {
    codeMirrorView.value?.focus();
}

const blur = () => {
    codeMirrorView.value?.contentDOM?.blur();
}

defineExpose({
    focus,
    blur,
    view: codeMirrorView,
    update: modelUpdate,
    model: model
})

</script>

<style lang="scss">
    .cm-completionIcon-instance {
        &::after {
            content: '𝑥';
        }
    }

li.cm-diagnostic {
    white-space: normal !important;

    p {
        margin: 0.5em 0;
    }
}

// for gutter markers
.cm-gutter-lint {
    width: 1.6em;

    // marker container
    .cm-lint-marker {
        padding: 0.2em 0;
    }

    .cm-lint-marker-error {

        content: ""; /* clear the default content which requires an svg */
        position: relative;

        &::before {
            // content: "\e90b"; /* unicode for pi-times icon */
            // content: "";   // pasting pi-times-circle from website, but below is better
            // content: "\e90c"; /* unicode for pi-times-circle icon */
            content: ""; /* character for pi-exclamation-circle icon */
            font-family: 'PrimeIcons';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: rgb(236, 77, 77);
            font-size: 0.9rem;
        }
    }

    .cm-lint-marker-warning {
        content: ""; /* clear the default content which requires an svg */
        position: relative;

        &::before {
            font-family: 'PrimeIcons';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 0.9rem;
            color: #ff9800;
            content: ""; // exclamation triangle char
        }

    }

    .cm-lint-marker-info {

        content: ""; /* clear the default content which requires an svg */
        position: relative;

        &::before {
            font-family: 'PrimeIcons';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 0.9rem;
            color: #2196f3;
            content: ""; // exclamation triangle char
        }
    }
}

//  z-index > 99 is higher than the sidemenu drag handle, etc
.cm-tooltip-hover {
    z-index: 99 !important;
}
.cm-tooltip {
    max-width: 60vw;
}
.cm-tooltip.cm-tooltip-hover:not(.cm-tooltip-lint) {
    background-color: transparent;
    border: none;
}

/**
All these styles cm-tooltip styles are exactly defined to have the tooltip-wrapper
have a margin-right, so that it doesn't render exactly all the way to the right of the page
(which would happen sometimes and look odd).
Moved the tooltip border/color to the inner element to allow CodeMirror to calc the
tooltip size without any weird re-layout animation. It is a bit specific so be careful when changing.
 */
.cm-tooltip > .cm-tooltip-section, .cm-tooltip.cm-tooltip-lint {
    padding: 1rem !important;
    border-radius: 4px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
    overflow-y: auto;
    border: none;

    background-color: var(--p-surface-0) !important;

    // and override for dark theme/mode
    .beaker-dark & {
        background-color: var(--p-surface-b) !important;
        border: 1px solid var(--p-surface-a);
    }
}
.cm-tooltip > .cm-tooltip-section {
    margin-right: 1rem;
    max-width: 100%;

    ul {
        margin: 0;
        padding: 0;
    }
}

:root {
    --color: 255, 0, 0;
}

.cm-lintRange {
    background-image: none !important;
    text-decoration: underline wavy rgba(var(--color), 0.5) !important;
    text-decoration-skip-ink: none;

    &.category-literal {
        --color: #FFFF00;
        background-color: color-mix(in srgb, var(--color) 20%, transparent);
    }

    &.category-assumptions {
        background-color: rgba(#FFCC22, 0.1);
    }

    &.category-grounding {
        background-color: rgba(#FF0000, 0.1);
    }

    &.category-grounding.category-literal {
        background-color: rgba(#00FF00, 0.1);
    }
}

// some override styles for decoration-based annotations (to match linter styles above)
.annotation-tooltip {
    h4 {
        margin: 0.2rem 0;
    }
    p {
        margin: 0.5em 0;
    }
}

</style>
