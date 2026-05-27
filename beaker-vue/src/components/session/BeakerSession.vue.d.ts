import { reactive, ref, inject, provide, VNode, defineComponent, PropType, ComponentInternalInstance, DefineComponent } from 'vue';
import { BeakerSession, IBeakerRendererOptions, JupyterMimeRenderer, IBeakerCell } from '@jataware/beaker-client';
import * as messages from '@jupyterlab/services/lib/kernel/messages';


export interface ICellRepr {
  [key: string]: any,
  $: ComponentInternalInstance,
  cell: IBeakerCell,
  enter: () => void,
  exit: () => void,
  execute: () => void,
  clear: () => void,
}


declare const BeakerSessionComponent: DefineComponent<any, any, any, any>;

export type BeakerSessionComponentType = InstanceType<typeof BeakerSessionComponent>;

export default BeakerSessionComponent;
