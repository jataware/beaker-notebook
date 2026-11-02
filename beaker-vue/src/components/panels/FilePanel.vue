<template>
  <div class="file-container pre">
    <div class="file-container-header">
      <span>Contents of: <span class="header-path">{{ displayPath }}</span></span>
      <span style="flex: 1"></span>
      <Button
          @click="openFileSelection"
          v-tooltip.bottom="{value: 'Files to upload', showDelay: 300}"
          icon="pi pi-cloud-upload"
          size="small"
          v-show="!hideUploads"
      />
      <form ref="uploadForm">
        <input
          @change="onSelectFilesForUpload"
          ref="fileInput"
          type="file"
          multiple
          style="display:none;"
          name="uploadfiles"
        />
        <input
          type="hidden"
          name="_xsrf"
          :value="xsrfCookie"
        />
      </form>
      <Button
          @click="refreshFiles"
          v-tooltip.bottom="{value: 'Refresh files ', showDelay: 300}"
          icon="pi pi-refresh"
          size="small"
      />
    </div>

    <DataTable :value="files" size="small" stripedRows class="file-table" removableSort
               @row-dblclick="doubleClick" resizableColumns columnResizeMode="fit" rowHover :loading="tableLoading"
               @dragover="fileDragOver" @drop="fileDrop"
               >
        <Column header="" class="download-column" v-if="!disabledColumns?.includes('downloads')">
          <template #header>
            <span
              class="pi pi-cloud-download"
              style="font-weight: lighter;"
            ></span>
          </template>
          <template #body="slotProps">
            <Button
              v-if="slotProps.data.type === 'file' || slotProps.data.type === 'notebook'"
              icon="pi pi-cloud-download"
              class="download-button"
              @click="downloadFile(slotProps.data)"
              v-tooltip.left="{value: 'Download', showDelay: 0, hideDelay: 0}"
            ></Button>
          </template>
        </Column>
        <Column field="name" header="Name" class="filename-column" v-if="!disabledColumns?.includes('filename')" sortable>
          <template #body="slotProps">
            <span :class="[...getFileIconClass(slotProps.data), 'file-icon', slotProps.data.type]"></span>
            <span
              :id="`file-list::${slotProps.data.path}`"
              class="file-name monospace"
              :class="slotProps.data.type"
            >
              {{ slotProps.data.name }}
            </span>
          </template>
        </Column>
        <Column field="last_modified" header="Last Modified" v-if="!disabledColumns?.includes('timestamp')" sortable style="max-width: 25%;">
          <template #body="slotProps">
            <span v-if="slotProps.data.last_modified" v-tooltip="slotProps.data.last_modified">
              {{ formatDate(slotProps.data.last_modified) }}
            </span>
            <span v-else style="display: flex; justify-content: center;"> - </span>
          </template>
        </Column>
        <Column field="size" header="Size" v-if="!disabledColumns?.includes('filesize')" sortable style="max-width: 25%;">
          <template #body="slotProps">
            <span v-if="slotProps.data.size" v-tooltip="`${slotProps.data.size} bytes`">
              {{ formatSize(slotProps.data.size) }}
            </span>
            <span v-else style="display: flex; justify-content: center;"> - </span>
          </template>
        </Column>
    </DataTable>
  </div>
  <Dialog
    modal
    v-model:visible="largeFilePreviewDialogVisible"
    header="Large File Preview"
    style="width: 30em;"
  >
    <span class="p-text-secondary preview-dialog-text">
      You are attempting to open a file that is <b>{{ largeFileSizeUILabel }}.</b>
    </span>
    <span class="p-text-secondary preview-dialog-text">
      This requires downloading the file over the network.
    </span>
    <div class="preview-dialog-button-container">
        <Button
          type="button"
          label="Cancel"
          outlined
          @click="() => {
            largeFilePreviewDialogVisible = false;
            largeFilePreviewCallback = () => {};
          }"
        />
        <Button
          type="button"
          label="Preview"
          @click="() => {
            largeFilePreviewDialogVisible = false;
            largeFilePreviewCallback();
            largeFilePreviewCallback = () => {};
          }"
          />
    </div>
  </Dialog>
</template>

<script lang="ts" setup>

import { ref, inject, capitalize, onMounted, computed } from "vue";
import Button from 'primevue/button';
import 'vue-json-pretty/lib/styles.css';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dialog from 'primevue/dialog';
import * as cookie from 'cookie';
import { filesize } from 'filesize';
import { Time, URLExt  } from '@jupyterlab/coreutils';
import scroll from 'scroll-into-view-if-needed'

import { ContentsManager, Contents } from '@jupyterlab/services';

const session = inject<any>('session');
const curDir = ref<string>('.');

const emit = defineEmits([
  "open-file",
  "preview-file"
]);

type FilePanelColumn = "downloads" | "timestamp" | "filename" | "filesize"

const props = defineProps<{
  disabledColumns?: FilePanelColumn[],
  hideUploads?: boolean
}>()

const contentManager = new ContentsManager({serverSettings: session.serverSettings});

const cookies = cookie.parse(document.cookie);
const xsrfCookie = cookies._xsrf;

const showToast = inject<any>('show_toast');

const fileInput = ref<HTMLInputElement|undefined>(undefined);
const uploadForm = ref<HTMLFormElement|undefined>(undefined);
const files = ref<any[]|undefined>(undefined);
const tableLoading = ref<boolean>(false);

const largeFilePreviewCallback = ref<() => void>();
const largeFilePreviewDialogVisible = ref<boolean>()
// in bytes - 10 MB
const largeFileWarningSize = 10 * 1000000;
const largeFileSizeUILabel = ref<string>();

const previewFile = (path, mimetype) => {
  emit("preview-file", URLExt.join(session?.serverSettings?.baseUrl, `files/${path}`), mimetype)
}

const formatDate = (dateString) => {
  return dateString !== null ? Time.formatHuman(dateString) : '-';
}

const formatSize = (size) => {
  return size !== null ? filesize(size, {spacer: ""}) : '-';
}

const openFileSelection = () => {
   fileInput.value?.click();
}

const displayPath = computed(() => {
  const path = curDir.value === '.' ? '' : curDir.value;
  return `/${path}`;
});

const getFileIconClass = (obj) => {
  const classes = [];
  if (obj.type === 'file') {
    classes.push('pi', 'pi-file');
  }
  else if (obj.type === 'directory') {
    classes.push('pi', 'pi-folder');
  }
  else if (obj.type === 'notebook') {
    classes.push('notebook-icon');
  }

  return classes;
}

const doubleClick = ({data}) => {
  if (data.type === 'directory') {
    curDir.value = data.path;
    refreshFiles();
  }
  else if (data.type === 'notebook') {
    if (window.confirm(`Open notebook ${data.name}?\n\nOpening this file will replace your current notebook and reset the session. Proceed?`)) {
      getFileContents(data).then((json) => {
        emit('open-file', json, data.path);
      })
    }
  }
  else if (data.size >= largeFileWarningSize) {
    largeFileSizeUILabel.value = `approximately ${Math.floor(data.size / 1000000)} MB`;
    showLargeFilePreview(() =>
      previewFile(data.path, data.mimetype));
  }
  else {
    previewFile(data.path, data.mimetype)
  }
}

const showLargeFilePreview = (callback: () => void) => {
  largeFilePreviewDialogVisible.value = true;
  largeFilePreviewCallback.value = callback;
}

const getFileContents = async (fileData) => {
  tableLoading.value = true;
  try {
    const fileRecord = await contentManager.get(fileData.path);
    tableLoading.value = false;
    return fileRecord.content;
  } catch(e) {
    tableLoading.value = false;
    showToast({
      title: 'Invalid File',
      detail: 'Unable to load. Please check file contains valid ipynb json data.',
      severity: 'error',
      life: 10000
    });
  }
}

const fileDragOver = (event: DragEvent) => {
  // Prevent default to allow dropping if a file is being dragged. Otherwise don't allow dropping here.
  const hasFile = [...event.dataTransfer.items].filter((i) => (i.kind === 'file')).length > 0;
  if (hasFile) {
    event.preventDefault();
  }
};

const fileDrop = async (event: DragEvent) => {
  // Prevent default behavior (Prevent file from being opened)
  event.preventDefault();
  await uploadFiles(event.dataTransfer.files);
}

const onSelectFilesForUpload = async () => {
  // Fetch files from form element
  const fileList = uploadForm.value['uploadfiles']?.files;
  await uploadFiles(fileList);
}

const uploadFiles = async (files: FileList) => {
  const results = [];
  const promises = Array.from(files).map(async (file) => {
    const fullPath = `${curDir.value}/${file.name}`;
    const bytes = [];
    const reader = file.stream().getReader();
    let chunk = (await reader.read()).value;
    while (chunk?.length > 0) {
      bytes.push(Array.from(chunk, (byte) => String.fromCharCode(byte)).join(""));
      chunk = (await reader.read()).value;
    }
    const type = (file.type !== "" ? file.type : "application/octet-stream");
    const content = btoa(bytes.join(""));
    const format = 'base64';

    const fileObj: Partial<Contents.IModel> = {
      type,
      format,
      content,
    };

    let result;
    try {
      result = await contentManager.save(fullPath, fileObj);
    }
    catch(e) {
      showToast({
        title: 'Upload failed',
        detail: `Unable to upload file "${fullPath}": ${e}`,
        severity: 'error',
        life: 8000
      });
      return;
    }
    if (result && result.created && result.size) {
      showToast({
        title: 'Upload complete',
        detail: `File "${result.path}" (${result.size} bytes) successfully uploaded.`,
        severity: 'success',
        life: 4000
      });
    }
    else {
      showToast({
        title: 'Upload failed',
        detail: `Unable to upload file "${fullPath}".`,
        severity: 'error',
        life: 8000
      });
    }
  });
  // Wait for all uploads to complete, then refresh the file list.
  await Promise.all(promises);
  await refreshFiles();
  return results;
}

const downloadFile = async (file) => {
  let url = await contentManager.getDownloadUrl(file.path);
  // Ensure we are downloading. Add the download query param
  if (!/download=/.test(url)) {
    if (/\?/.test(url)) {
      url = url + "&download=1"
    }
    else {
      url = url + "?download=1"
    }
  }
  window.location.href = url;
};

const refreshFiles = async () => {
  tableLoading.value = true;
  const contents = await contentManager.get(curDir.value);
  const records = contents.content;
  records.sort((a, b) => {
    // Sort directories to the top
    if(a.type === 'directory' && b.type !== 'directory') {
      return -1;
    }
    else if (b.type === 'directory' && a.type !== 'directory') {
      return 1;
    }
    // Then sort by name
    return a.name.localeCompare(b.name)
  });
  if (curDir.value !== ".") {
    const parentDir = contentManager.normalize(`${curDir.value}/..`);
    records.splice(0, 0,
      {
        "name": "..",
        "path": parentDir,
        "last_modified": null,
        "created": null,
        "content": null,
        "format": null,
        "mimetype": null,
        "size": null,
        "writable": true,
        "hash": null,
        "hash_algorithm": null,
        "type": "directory"
      }
    );
  }
  files.value = records;
  tableLoading.value = false;
};

const flashFile = async (path: string) => {
  const nameSpan = document.getElementById(`file-list::${path}`)
  if (!nameSpan) {
    // File panel isn't populated, or is in some other directory.
    return;
  }
  const row = nameSpan.closest('tr');
  if (!row) {
    // If namespan exists, this should exist, but just in case err on the side of gracefully not flashing if it can't be
    // found.
    return;
  }
  scroll(row, {behavior: "smooth"});
  row.classList.add("flash");
  row.addEventListener("animationend", () => row.classList.remove("flash"), {once: true});
  row.style.backgroundColor = 'rgba(255, 0, 0, 0)';

}

onMounted(async () => {
  await refreshFiles();
});

defineExpose({
  refresh: refreshFiles,
  flashFile,
  directory: curDir
});

</script>

<style lang="scss">

  .file-container {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    --font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
    font-size: 14pt;
  }

  .file-table {
    font-size: smaller;
    border: 1px solid var(--p-surface-border);
    flex: 1;
    overflow: auto;
    display:flex;

    .p-datatable-table-container {
      flex: 1;
    }

    td {
      padding: 0.25rem;
    }

    .filename-column {
      max-width: 18em;
      cursor: pointer;
      .pi {
        font-size: 16px;
      }
    }

    tr:hover {
      .download-button {
        opacity: 1;
        animation-name: download-fade-in;
        animation-duration: 200ms;
      }
    }

    tr.flash {
      animation-name: fade-out-background;
      animation-duration: 4000ms;
      background-color: rgba(255, 33, 78, 0.8);
    }
  }

.preview-dialog-text {
  margin-bottom: 5px;
  display: block;
}

.preview-dialog-button-container {
  display: flex;
  justify-content: end;
  margin-top: 0.75rem;
  button {
    margin-left: 0.25rem;
  }
}

@keyframes fade-out-background {
  0% {
    background-color: rgba(255, 33, 78, 0.8);
  }

  40% {
    background-color: rgba(255, 33, 78, 0.4);
  }

  50% {
    background-color: rgba(255, 33, 78, 0.6);
  }

  100% {
    background-color: rgba(255, 33, 78, 0);
  }
}

@keyframes download-fade-in {
  0% {
    opacity: 0.0;
  }

  100% {
    opacity: 1.0;
  }
}

  .download-column {
    width: unset;
    padding: 1px;
    aspect-ratio: 1/1;
    text-align: center;

    > .p-datatable-column-header-content {
      justify-content: center;
    }
  }


  .notebook-icon {
    display: inline-flex;
    align-items: center;
    width: 16px;
    height: 16px;
    &:before {
      display: inline-block;
      position: relative;
      top: 2px;
      text-align: center;
      flex: 1;
      content: url("../../assets/notebook-icon.svg");
      height: 16px;
      width: 16px;
    }
  }

  .file-icon {
    &.directory {
      color: var(--p-primary-600);
      font-weight: bold;
    }
  }

  .file-name {
    word-break: keep-all;
    margin-left: 0.25rem;
    &.directory {
      text-decoration: underline ;
      text-underline-offset: 0.25rem;
      // color: var(--p-primary-500);
    }
  }

  .download-button {
    padding: 2px;
    margin: 0 2px;
    width: unset;
    aspect-ratio: 1/1;
    opacity: 0;
  }

  .file-container-header {
    display: flex;
    flex-direction: row;
    align-items: center;
    border: 3px solid var(--p-surface-border);
    background-color: var(--p-surface-d);
    padding-left: 1em;

    > button {
      padding: unset;
      margin: unset;
      margin-left: 3px;
      width: 2em;
      aspect-ratio: 1/1;
    }

    .header-path {
      font-family: var(--font-family);
    }
  }

</style>
