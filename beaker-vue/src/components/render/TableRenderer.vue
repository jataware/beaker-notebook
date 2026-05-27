<template>
    <div class="table-renderer">
        <DataTable
            :value="processedData.values"
            paginator
            :rows="20"
            :rowsPerPageOptions="[10, 20, 50]"
            v-if="mimeType.startsWith('text/')"
        >
            <Column
                v-for="column in processedData.columns"
                :field="column"
                :header="column"
                :key="column"
            >

            </Column>
        </DataTable>
        <TabView
            v-if="isExcelDocument(mimeType)"
            :pt="{
                panelContainer: (options) => ({
                    class: 'xlsx-panel-container'
                }),
            }"
        >
            <TabPanel
                v-for="{name, html} in xlsxData"
                :header="name"
                :key="name"
                :value="name"
            >
                <div v-if="!isLoadingXSLX" class="xlsx-table" v-html="html"></div>
            </TabPanel>
        </TabView>
    </div>
</template>

<script setup lang="ts">
import { computed, watch, ref, onMounted } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import TabView from 'primevue/tabview';
import TabPanel from 'primevue/tabpanel';

import * as XLSX from 'xlsx';

const props = defineProps([
    "data",
    "mimeType"
]);

type XLSXRenderedSheetData = {
    name: string,
    html: string
}

type DataTablePayload = {
    columns: string[],
    values: object[]
}

const isExcelDocument = (mimetype) => (
    mimetype === 'application/vnd.ms-excel' ||
    mimetype === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
);

const xlsxData = ref<XLSXRenderedSheetData[] | null>();

const processSeparatedValues = (data, rowSeparator, valueSeparator): DataTablePayload => {
    if (data === undefined || data === "") {
        return {
            columns: [],
            values: [],
        };
    }
    const rows: string[] = data.split(rowSeparator);
    const header: string[] = rows[0].split(valueSeparator);
    const values = rows.slice(1).map((row) =>
        row.split(',').reduce((combined, entry, index) =>
            ({[header[index]]: entry.trim(), ...combined}), {}))
    return {
        columns: header,
        values,
    }
}

const loadXlsx = (data) => {
    const workbook = XLSX.read(data);
    const sheets = workbook.SheetNames.map((sheet) => ({
        name: sheet,
        html: XLSX.utils.sheet_to_html(workbook.Sheets[sheet])
    }));
    return sheets;
}

const processedData = computed<DataTablePayload | null>(() => {
    if (props.mimeType === 'text/csv') {
        return processSeparatedValues(props?.data, '\n', ',');
    }
    else if (props.mimeType === 'text/tsv') {
        return processSeparatedValues(props?.data, '\t', ',');
    }
    return props.data
})

const isLoadingXSLX = ref(false);
onMounted(() => {
    if (props.mimeType.startsWith('application/vnd')) {
        isLoadingXSLX.value = true;
        xlsxData.value = loadXlsx(props.data);
        isLoadingXSLX.value = false;
    }
})


</script>

<style lang="scss">

// https://github.com/mdn/learning-area/blob/main/html/tables/basic/minimal-table.css
// minimal / readable table example used from MDN - colors changed for primevue
.xlsx-table {
    table {
        border-collapse: collapse;
        //border: 2px solid var(--p-surface-d);
        letter-spacing: 1px;
        font-size: 0.8rem;
    }

    td, th {
        border: 1px solid var(--p-surface-f);
        padding: 10px 20px;
    }

    th {
        background-color: var(surface-c);
    }

    td {
        text-align: center;
    }

    tr:nth-child(even) td {
        background-color: var(--p-surface-a);
    }

    tr:nth-child(odd) td {
        background-color: var(--p-surface-b);
    }

    caption {
        padding: 10px;
    }
}

.xlsx-panel-container {
    padding: 0;
}
</style>
