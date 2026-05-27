import { defineComponent, ref, computed, nextTick, provide, inject, type DefineComponent } from "vue";
import type { IBeakerCell, BeakerSession, BeakerNotebook, BeakerMarkdownCell, BeakerCodeCell, BeakerQueryCell, BeakerRawCell } from '@jataware/beaker-client';

declare const BeakerNotebookComponent: DefineComponent<any, any, any, any>;

export type BeakerNotebookComponentType = InstanceType<typeof BeakerNotebookComponent>;

export default BeakerNotebookComponent;
