<template>
    <BeakerSession
        id="beaker-session-container"
        ref="beakerSession"
        @connection-failure="connectionFailure"
    >
        <div id="page" :class="props.pageClass">
            <header>
                <slot name="header">
                    <BeakerHeader
                        :connectionStatus="connectionStatus"
                        @select-kernel="toggleContextSelection"
                        @context-changed="(contextData) => {beakerSession.setContext(contextData)}"
                        :title="props.title"
                        :title-extra="props.titleExtra"
                        :nav="props.headerNav"
                    />
                </slot>
            </header>

            <main ref="mainRef">
                <slot name="main">
                    <div id="left-panel">
                        <slot name="left-panel">
                        </slot>
                    </div>

                    <div :id="`center-panel${isChat ? '-chat-override': '' }`">
                        <slot>
                        </slot>
                    </div>

                    <div id="right-panel">
                        <slot name="right-panel">
                        </slot>
                    </div>
                </slot>
            </main>

            <footer>
            <slot name="footer">
                <FooterDrawer />
            </slot>
            </footer>

            <!-- Modals, popups and globals -->
            <slot name="context-selection-popup">
                <Dialog
                    ref="contextSelectionDialogRef"
                    v-model:visible="contextSelectionOpen"
                    modal
                    :draggable="true"
                    :maximizable="true"
                    header="Configure Context"
                >
                    <BeakerContextSelection
                        @context-changed="(contextData) => {beakerSession.setContext(contextData)}"
                        @close-context-selection="contextSelectionOpen = false"
                    />
                </Dialog>
            </slot>
            <slot name="toast">
                <Toast position="bottom-right" />
            </slot>
            <slot name="confirmation">
                <ConfirmDialog></ConfirmDialog>
            </slot>
        </div>
        <slot name="login-dialog">
            <Dialog
                ref="loginDialogRef"
                v-model:visible="authDialogVisible"
                modal
                :draggable="false"
                header="Model Provider Configuration"
                @show="providerConfig"
            >
                <div v-if="authMessage" style="margin-bottom: 1rem;">
                    <h3>Message from service:</h3>
                    <span style="font-style: italic;">{{ authMessage }}</span>
                </div>
                <ProviderSelector
                    :config-type="beakerSession?.connectionSettings?.config_type"
                    @set-agent-model="setAgentModel"
                    @close-dialog="authDialogVisible = false"
                />
            </Dialog>
        </slot>
        <DynamicDialog/>
    </BeakerSession>
</template>

<script setup lang="tsx">
import { type ErrorObject, isErrorObject } from '../util';
import { h, useSlots, isVNode, ref, onMounted, provide, onUnmounted, toRaw} from 'vue';
import { type Component, type ComponentInstance } from 'vue';
import Dialog from 'primevue/dialog';
import DynamicDialog from 'primevue/dynamicdialog';
import { useDialog } from 'primevue/usedialog';
import ConfirmDialog from 'primevue/confirmdialog';
import BeakerSession from '../components/session/BeakerSession.vue';
import BeakerHeader from '../components/misc/BeakerHeader.vue';
import Card from 'primevue/card';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import {BeakerSession as Session} from '@jataware/beaker-client'
import InputText from 'primevue/inputtext';
import InputGroup from 'primevue/inputgroup';
import Button from 'primevue/button';
import ProviderSelector from '../components/misc/ProviderSelector.vue';
import { useNotebookSnapshot } from '../composables/useNotebookSnapshot';

import {default as ConfigPanel, getConfigAndSchema, dropUnchangedValues, objectifyTables, tablifyObjects, saveConfig} from '../components/panels/ConfigPanel.vue';
import SideMenu, { type MenuPosition } from '../components/sidemenu/SideMenu.vue';
import BeakerContextSelection from "../components/session/BeakerContextSelection.vue";
import FooterDrawer from '../components/misc/FooterDrawer.vue';
import type { DynamicDialogInstance, DynamicDialogOptions } from 'primevue/dynamicdialogoptions';

const dialog = useDialog();
const toast = useToast();

const mainRef = ref();

// TODO -- WARNING: showToast is only defined locally, but provided/used everywhere. Move to session?
export interface ShowToastOptions {
    title: string;
    detail: string;
    life?: number;
    severity?: 'success' | 'warn' | 'info' | 'error';
}

const showToast = (options: ShowToastOptions) => {
    const {title, detail, life=3000, severity='success'} = options;
    toast.add({
        summary: title,
        detail,
        life,
        severity,
    });
};

const props = defineProps<{
  title: string;
  titleExtra?: string;
  savefile?: string;
  headerNav?: any;
  apiKeyPrompt?: boolean;
  pageClass?: string;
}>();

const emit = defineEmits([
    "notebook-autosaved",
    "open-file",
]);

const connectionStatus = ref('connecting');
const beakerSession = ref<typeof BeakerSession>();
const authDialogVisible = ref<boolean>(props.apiKeyPrompt || false);
const authDialogEntry = ref<string>("");
const authMessage = ref<string>("");
const authRetryCell = ref();
const loginDialogRef = ref();
const overlayRef = ref<DynamicDialogInstance>();

const { loadSnapshot, startAutosave, stopAutosave } = useNotebookSnapshot({
    beakerSession,
    savefile: () => props.savefile,
    onOpenFile: (content, name, openOptions) => emit('open-file', content, name, openOptions),
});

const contextSelectionOpen = ref(false);

const toggleContextSelection = () => {
    contextSelectionOpen.value = !contextSelectionOpen.value;
};

const setMaximized = (maximized: boolean) => {
    const main: HTMLDivElement = mainRef.value;
    if (maximized) {
        main.classList.add("maximized");
    }
    else {
        main.classList.remove("maximized");
    }
}

const showOverlay = (contents: string | Component | HTMLElement | ErrorObject, title?: string) => {
    var contentComponent;
    if (typeof(contents) === "string") {
        contents = h("div", {innerHTML: contents})
    }
    if (isErrorObject(contents)) {
        contents = <div>
            <h3>Error:</h3>
            <div style="font-weight: bold">{contents.ename}</div>
            <div>{ contents.evalue }</div>
            { contents.traceback
                ? <div>
                    <h3>Traceback:</h3>
                    <div class="traceback">{contents.traceback.join("")}</div>
                  </div>
                : undefined }
        </div>
    }
    contentComponent = <div id="overlay">
        <div id="overlay-content">{contents}</div>
        <div id="overlay-footer" >
            <Button label="Close" onClick={() => {
                overlayRef.value.close();
            }} /></div>
    </div>

    if (contentComponent) {
        overlayRef.value = dialog.open(
            contentComponent,
            {
                props: {
                    style: {minWidth: '75vw', minHeight: '75vh'},
                    modal: true,
                    draggable: false,
                    header: title || "Alert",
                    contentStyle: {flex: 1},
                    contentClass: "overlay-dialog"
                },
            }
        );
    }
}

provide('show_toast', showToast);
provide('show_overlay', showOverlay);

const isChat = ref(true);

const connectionFailure = (error: Error) => {
    let errorName = error.name;
    let errorMessage = error.message;

    // Handle worst-case bad error to make it more humane.
    if (errorName === 'TypeError' && errorMessage === "Failed to fetch") {
        errorName = "ConnectionError";
        errorMessage = "Unable to reach server."
    }

    showToast({
        title: `Error connecting - ${errorName}`,
        detail: `${errorMessage}`,
        severity: "error",
        life: 5000,
    });
}

onMounted(async () => {
    const session: Session = beakerSession.value.session;
    await session.sessionReady;  // Ensure content service is up

    // Actions to perform only after session is connected.
    session.session.ready.then(() => {
        // Connect listener for authentication message
        const sessionContext = toRaw(session.session.session)
        sessionContext.iopubMessage.connect(iopubMessage);
        // Start periodic autosave
        startAutosave();
    });

    await loadSnapshot();
});


const iopubMessage = (_sessionConn, msg) => {
    if (msg.header.msg_type === "llm_auth_failure") {
        authDialogVisible.value = true;
        authMessage.value = msg.content.msg;
        if (msg.cell !== undefined) {
            authRetryCell.value = msg.cell;
        }
    }
};

const setAgentModel = async (modelConfig = null, rerunLastCommand = false) => {
    const session = beakerSession.value.session;
    const resetFuture = session.sendBeakerMessage(
        "set_agent_model",
        modelConfig,
    )
    await resetFuture.done;
    if (rerunLastCommand && authRetryCell.value) {
        authRetryCell.value.execute(session);
    }
}

onUnmounted(() => {
    stopAutosave();
});

const providerConfig = () => {
}

defineExpose({
    beakerSession,
    showToast,
    setMaximized,
    getSession: () => beakerSession.value.getSession()
});

</script>

<style lang="scss">
#beaker-session-container {
    height: 100vh;
    width: 100vw;
    display: flex;
    flex-direction: column;
}

#page {
    margin: 0;
    padding: 0;
    overflow: visible hidden;
    height: 100vh;
    width: 100vw;
    display: grid;
    grid-template:
        "header" max-content
        "main" 1fr
        "footer" max-content /
        100%;
}

header {
    grid-area: header;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

main {
    --columns: 1fr minmax(30%, 50%) 1fr;
    grid-area: main;
    position: relative;
    display: grid;
    grid-template: "left-panel center-panel right-panel";
    grid-template-columns: var(--columns);
    grid-template-rows: 100%;
    background-color: var(--p-content-background);
    max-width: 100%;
    max-height: 100%;
    overflow: hidden;

    &.maximized {
        --columns: 1fr minmax(30%, 100%) 1fr;
    }
}

footer {
    grid-area: footer;
}

#left-panel {
    grid-area: left-panel;
}

#center-panel {
    grid-area: center-panel;
    border: 1px solid;
    border-color: var(--p-surface-border);
}

#center-panel-chat-override {
    grid-area: center-panel;
}

#right-panel {
    grid-area: right-panel;
}

.p-confirm-dialog {
    white-space: pre-line;
}

#overlay {
    flex: 1;
    display: flex;
    flex-direction: column;
}

#overlay-content {
    flex: 1;
}

.overlay-dialog {
    padding: 1em 2em 2em 2em;
    white-space: pre-wrap;
    display: flex;
}

#overlay-footer {
    text-align: end;
    min-height: "5em";
    width: "100%"
}

#overlay-content .traceback {
    padding: 0.5rem;
    background-color: var(--p-surface-b);
}

</style>
