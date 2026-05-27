<template>
    <div class="beaker-notebook">
        <slot></slot>
    </div>
</template>

<script lang="tsx">
import { defineComponent, ref, computed, nextTick, provide, inject, type DefineComponent } from "vue";
import { BeakerSession, BeakerNotebook, BeakerCodeCell, BeakerBaseCell } from '@jataware/beaker-client';
import type { IBeakerCell } from '@jataware/beaker-client';
import type { IBeakerCellComponent, BeakerSessionComponentType } from "../session/BeakerSession.vue";
import scrollIntoView from 'scroll-into-view-if-needed';

export const BeakerNotebookComponent: DefineComponent<any, any, any>  = defineComponent({
    props: [
        "cellMap",
        "noEmptyStartingCell"
    ],

    setup(props) {
        const session: BeakerSession = inject('session');
        const beakerSession = inject<BeakerSessionComponentType>('beakerSession');
        const notebook = ref<BeakerNotebook>(session.notebook);

        // TODO: Clear up session/beakerSession confusion. sessionContext? sessionController?
        const selectedCellId = ref<string | null>(null);
        provide('cell-component-mapping', props.cellMap);

        const cellCount = computed(() => session?.notebook?.cells?.length || 0);

        return {
            session,
            beakerSession,
            notebook,
            selectedCellId,
            cellCount,
        }
    },

    methods: {
        selectCell(cell: string | {id: string} | IBeakerCellComponent, enter=false, cursorPos=undefined): string {
            if (cell === undefined) {
                return "";
            }

            let newCellId;
            if (typeof cell === 'string') {
                newCellId = cell;
            }
            else if (Object.hasOwn(cell, "cell")) {
                newCellId = (cell as IBeakerCellComponent).cell.id;
            }
            else {
                newCellId = cell.id;
            }
            if (this.selectedCellId !== newCellId) {
                this.selectedCellId = newCellId
            }

            nextTick(() => {
                this.scrollCellIntoView(this.selectedCell());
                if (enter) {
                    this.selectedCell().enter(cursorPos);
                }
            })

            return this.selectedCellId;
        },

        scrollCellIntoView(cell: IBeakerCellComponent): void {
            const el = cell?.$?.vnode?.el;
            if (!el) {
                return;
            }
            const target = el.closest('.beaker-cell') ?? el;
            scrollIntoView(target, {
                scrollMode: "if-needed",
                block: "nearest",
                inline: "nearest",
            })
        },

        // This can't/shouldn't be a computed property because it information about the selected cell can change
        // without the dependencies in the function changing.
        selectedCell(): IBeakerCellComponent  {
            const selectedCell = this.beakerSession.findNotebookCellById(this.selectedCellId);
            if (selectedCell) {
                return selectedCell;
            }
            if (this.notebook.cells.length > 0) {
                this.selectedCellId = this.notebook.cells[0].id;
                return this.beakerSession.findNotebookCellById(this.selectedCellId);
            }
        },

        nextCell(referenceCell?: IBeakerCell): IBeakerCellComponent | null {
            let cellIndex: number;
            if (referenceCell === undefined) {
                cellIndex = this.notebook.cells.indexOf(this.selectedCell().cell);
            }
            else {
                cellIndex = this.notebook.cells.indexOf(referenceCell);
            }
            if (cellIndex >= 0 && cellIndex < this.cellCount - 1) {
                const nextCell: IBeakerCell = this.notebook.cells[cellIndex+1];
                const nextCellId = nextCell.id;
                return this.beakerSession.findNotebookCellById(nextCellId);
            }
            return null;
        },

        prevCell(referenceCell?: IBeakerCell): IBeakerCellComponent | null {
            let cellIndex: number;
            if (referenceCell === undefined) {
                cellIndex = this.notebook.cells.indexOf(this.selectedCell().cell);
            }
            else {
                cellIndex = this.notebook.cells.indexOf(referenceCell);
            }
            if (cellIndex > 0) {
                const prevCell: IBeakerCell = this.notebook.cells[cellIndex-1];
                const prevCellId = prevCell.id;
                return this.beakerSession.findNotebookCellById(prevCellId);
            }
            return null;
        },

        selectNextCell(referenceCell?: IBeakerCell, enter=false): IBeakerCell | null {
            const nextCell: IBeakerCell | null = this.nextCell(referenceCell);
            if (nextCell) {
                return this.selectCell(nextCell, enter);
            }
            else {
                for (const notebookCell of this.notebook.cells) {
                    if (notebookCell.children) {
                        const childIndex = notebookCell.children.indexOf(referenceCell);
                        if (childIndex === -1) {
                            continue;
                        }
                        // If trying to go past last child cell
                        if (childIndex <= notebookCell.children.length-1) {
                            // Select the next outer cell, if it exists
                            return this.selectNextCell(notebookCell);
                        }
                        else {
                            //
                            return this.selectCell(notebookCell.children[childIndex+1], enter);
                        }
                    }
                }
            }
            return null;
        },

        selectPrevCell(referenceCell?: IBeakerCell, enter=false): IBeakerCell | null {
            const prevCell: IBeakerCell | null = this.prevCell(referenceCell);
            if (prevCell) {
                return this.selectCell(prevCell, enter);
            }
            return null;
        },

        insertCellBefore(referenceCell?: IBeakerCell, newCell?: IBeakerCell, enter=false) {
            if (referenceCell === undefined) {
                referenceCell = this.selectedCell();
            }
            if (newCell === undefined) {
                newCell = new this.defaultCellModel({source: ""})
            }
            const index = (referenceCell === undefined ? this.notebook.cells.length-1 : this.notebook.cells.findIndex((cell) => cell === referenceCell.cell));
            this.notebook.cells.splice(index, 0, newCell);
            nextTick(() => this.selectCell(newCell, enter));
            return newCell;
        },

        insertCellAfter(referenceCell?: IBeakerCell, newCell?: IBeakerCell, enter=false) {
            if (referenceCell === undefined) {
                referenceCell = this.selectedCell();
            }
            if (newCell === undefined) {
                newCell = new this.defaultCellModel({source: ""})
            }
            const index = (referenceCell === undefined ? this.notebook.cells.length-1 : this.notebook.cells.findIndex((cell) => cell === referenceCell.cell));
            this.notebook.cells.splice(index + 1, 0, newCell);
            nextTick(() => this.selectCell(newCell, enter));
            return newCell;
        },

        removeCell(cell?: IBeakerCell): void {
            if (cell === undefined) {
                cell = this.selectedCell();
            }
            const index = this.notebook.cells.findIndex((cellModel) => cellModel === cell.cell);
            if (index > -1) {
                if (cell.cell.id === this.selectedCellId) {
                    if (!this.selectNextCell()) {
                        this.selectPrevCell();
                    }
                }
                return this.notebook.cutCell(index);
            }
        },

        convertCellType(cell: IBeakerCell, cellType: string) {
            const cellIndex = this.notebook.cells.indexOf(cell);
            if (cellIndex === -1) {
                console.warn("attempted to convert cell not found in parent cell in place; cell not found");
                return;
            }
            const cellMap = typeof this.cellMap === 'function' ? this.cellMap(null) : this.cellMap;
            const availableConversions = Object.keys(cellMap);
            if (!availableConversions.includes(cellType)) {
                console.warn("invalid cell type provided for conversion target");
                return;
            }
            const newCell = new cellMap[cellType].modelClass({...cell});
            newCell.cell_type = cellType;
            this.notebook.cells.splice(cellIndex, 1, newCell);
        }
    },

    computed: {
        defaultCellModel(): typeof BeakerBaseCell {
            const cellMap = typeof this.cellMap === 'function' ? this.cellMap(null) : this.cellMap;
            if (cellMap && Object.keys(cellMap).length > 0) {
                const modelClass = (Object.values(cellMap)[0] as any).modelClass;
                return modelClass as typeof modelClass;
            }
            else {
                return BeakerCodeCell;
            }
        },
    },

    beforeMount() {
        provide('notebook', this);
        this.beakerSession.notebookComponent = this;
        if (this.cellCount === 0) {
            if (this.noEmptyStartingCell) {
                return;
            }
            const newCell = this.session.addCodeCell("");
        }
    },

    mounted() {
        if (this.noEmptyStartingCell) {
            return;
        }
        if (!this.selectedCell()) {
            nextTick(() => {
                if (this.notebook.cells.length > 0) {
                    this.selectCell(this.notebook.cells[0].id);
                }
            });
        }
    }
});

export type BeakerNotebookComponentType = InstanceType<typeof BeakerNotebookComponent>;

export default BeakerNotebookComponent;

</script>


<style lang="scss">
.beaker-notebook {
    display: flex;
    flex: 1;
    flex-direction: column;
    height: 100%;
}

.welcome-placeholder  {
    position: absolute;
    top: 7rem;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: -1;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 90%;
}

</style>
