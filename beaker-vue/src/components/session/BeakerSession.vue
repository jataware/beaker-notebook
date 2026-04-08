<template>
  <div class="beaker-session-container">
    <slot></slot>
  </div>
</template>

<script lang="ts">
import { reactive, ref, inject, provide, defineComponent } from 'vue';
import type { VNode, PropType, ComponentInternalInstance, DefineComponent } from 'vue';
import CodeEditor from '../misc/CodeEditor.vue';
import { BeakerSession } from '@jataware/beaker-client';
import type { IMimeRenderer, IBeakerCell, BeakerKernelStatus } from '@jataware/beaker-client';
import * as messages from '@jupyterlab/services/lib/kernel/messages';
import type { ConnectionStatus as JupyterConnectionStatus } from '@jupyterlab/services/lib/kernel/kernel';


export interface IBeakerCellComponent {
  [key: string]: any,
  $: ComponentInternalInstance,
  cell: IBeakerCell,
  enter: (position?: "start" | "end" | number) => void,
  exit: () => void,
  execute: () => void,
  clear: () => void,
  editor?: typeof CodeEditor,
  lintAnnotations?: {}[],
}


export const toBeakerCellComponent = (vnode: VNode): IBeakerCellComponent => {
  const component: ComponentInternalInstance = vnode?.component;
  if (component === undefined) {
    return undefined;
  }
  return reactive({
    // @
    ...{
      cell: (component.proxy as unknown as {cell: IBeakerCell}).cell,
    },
    ...{
      enter: component.exposed.enter,
      exit: component.exposed.exit,
      execute: component.exposed.execute,
      clear: component.exposed.clear,
      editor: component.exposed.editor,
      lintAnnotations: component.exposed.lintAnnotations,
    } as {
      enter: (position?: "start" | "end" | number)=>void,
      exit: ()=>void,
      execute: ()=>void,
      clear: ()=>void,
      editor?: typeof CodeEditor,
    },
    $: component,
  });
}

export const BeakerSessionComponent: DefineComponent<any, any, any> = defineComponent({
  props: {
      connectionSettings: Object,
      sessionName: {
        type: String,
        required: false,
      },
      sessionId: String,
      defaultKernel: String,
      renderers: (Object as any as PropType<IMimeRenderer<HTMLElement>[]>),
      context: {
        type: Object as PropType<{
          slug: string,
          payload: any,
        }>,
        required: false,
      },
  },

  emits: [
      "iopub-msg",
      "unhandled-msg",
      "any-msg",
      "session-status-changed",
      "context-changed",
      "connection-failure",
  ],

  setup(props, { emit }) {

    const status = ref<BeakerKernelStatus>("unknown");

    const cellRegistry = ref<({[key: string]: VNode})>({});

    const activeContext = ref();
    const notebookComponent = ref();
    const customRendererMimetypes = ref<Set<string>>(new Set());

    const sessionName = props.sessionName ?? props.sessionId;
    const rawSession: BeakerSession = new BeakerSession(
      {
        settings: props.connectionSettings,
        name: sessionName,
        sessionId: props.sessionId,
        kernelName: props.defaultKernel,
        rendererOptions: {
          renderers: props.renderers || [],
        },
        context: props.context,
      }
    );

    status.value = "connecting";

    rawSession.services.connectionFailure.connect((serviceManager, error) => {
      emit('connection-failure', error);
      console.log("Error connecting to kernel/api", error);
    })

    const setSignalHandlers = async (session) => {
        session.iopubMessage.connect(async (session, msg) => {
          emit("iopub-msg", msg);
          if (messages.isStatusMsg(msg)) {
            const newStatus = msg?.content?.execution_state || 'unknown';
            status.value = rawSession.status;
            emit("session-status-changed", newStatus);
          }
          if (msg.header.msg_type === "context_info_response") {
            // Load custom renderers from package and context asset URLs.
            // On context switch, clear context-level renderers (they're scoped to the
            // previous context) but keep package-level renderers.
            const assetUrls = msg.content.info?.asset_urls;
            rawSession.renderer.removeRenderersByTag("context");

            if (assetUrls) {
              // Load package-level renderers (idempotent — addRenderer only replaces
              // if new renderer has equal or better rank)
              if (assetUrls.package) {
                try {
                  const mod = await import(/* @vite-ignore */ assetUrls.package + "renderers.js");
                  if (Array.isArray(mod.default)) {
                    mod.default.forEach((r: any) => rawSession.renderer.addRenderer(r, "package"));
                    console.debug(`Loaded ${mod.default.length} package renderer(s)`);
                  }
                } catch (err) {
                  console.debug(`No package renderer module at ${assetUrls.package}renderers.js`);
                }
              }

              // Load context-level renderers
              if (assetUrls.context) {
                try {
                  const mod = await import(/* @vite-ignore */ assetUrls.context + "renderers.js");
                  if (Array.isArray(mod.default)) {
                    mod.default.forEach((r: any) => rawSession.renderer.addRenderer(r, "context"));
                    console.debug(`Loaded ${mod.default.length} context renderer(s)`);
                  }
                } catch (err) {
                  console.debug(`No context renderer module at ${assetUrls.context}renderers.js`);
                }
              }
            }
          }
        });
        session.session.anyMessage.connect((_: unknown, {msg, direction}) => {
          emit("any-msg", msg, direction);
        });
        session.unhandledMessage.connect((session, msg) => {
          emit("unhandled-msg", msg);
        });
        session.connectionStatusChanged.connect((session, connectionStatus: JupyterConnectionStatus) => {
          status.value = rawSession.status;
        });
      }

      rawSession?.sessionReady.then(async () => {
        await setSignalHandlers(rawSession.session);
      });

    const beakerSession = reactive(rawSession);



    return {
      activeContext,
      session: beakerSession,
      status,
      cellRegistry,
      notebookComponent,
      setSignalHandlers,
    }
  },

  methods: {
    findNotebookCell(predicate: ((cell: IBeakerCellComponent) => boolean)): IBeakerCellComponent {
      for (const cellVnode of this.cellRegistry) {
        if (predicate(cellVnode)) {
          return toBeakerCellComponent(cellVnode)
        }
      }
    },

    findNotebookCellById(id: string): IBeakerCellComponent {
      const cellVnode = this.cellRegistry[id];
      if (cellVnode !== undefined) {
        return toBeakerCellComponent(cellVnode);
      }
    },

    async updateContextInfo() {
      const activeContextInfo = await this.session.activeContext();
      this.activeContext = activeContextInfo;
      this.$emit("context-changed", this.activeContext);
    },

    setContext(contextPayload: any) {
        const showToast: (...args) => void = inject('show_toast');
        this.activeContext = { loading: true };

        const future = this.session.setContext(contextPayload);
        future.then((result: any) => {

            if (result?.status === 'error') {
                let formatted = result?.content?.evalue;
                if (formatted) {
                    const endsWithPeriod = /\.$/.test(formatted);
                    if (!endsWithPeriod) {
                        formatted += '.';
                    }
                }
                showToast({
                    title: 'Context Setup Failed',
                    severity: 'error',
                    detail: `${formatted} Please try again or contact us.`,
                    life: 0
                });
                return;
            }

            if (result?.status === 'abort') {
                showToast({
                    title: 'Context Setup Aborted',
                    severity: 'warning',
                    detail: result?.content?.evalue,
                    life: 6000
                });
                return;
            }

            // Close the context dialog
            // contextSelectionOpen.value = false;
            // Update the context info in the sidebar
            // TODO: Is this even needed? Could maybe be fed/triggered by existing events?
            this.updateContextInfo();
        });
        return future;
    },

    async reconnect() {
      const newSession = await this.session.reconnect();
      await this.setSignalHandlers(newSession);
      this.setContext({
        context: this.activeContext.slug,
        context_info: this.activeContext.config,
        language: this.activeContext.language.slug,
        debug: this.activeContext.info.debug,
        verbose: this.activeContext.info.verbose,
      });
    },

    // to be usable from a pages/ToplevelInterface.vue page, since
    // inject/provide goes NotebookInteface < BaseInterface < BeakerSession
    getSession() {
      return this.session;
    }
  },

  beforeMount() {
    // Register session dependencies for injection (Must be in beforeMount to be available to children)
    provide('beakerSession', reactive(this));
    provide('session', this.session);
  },

  mounted() {
    this.updateContextInfo();
  },
});

export type BeakerSessionComponentType = InstanceType<typeof BeakerSessionComponent>;

export default BeakerSessionComponent;

</script>

<style lang="scss">
</style>
