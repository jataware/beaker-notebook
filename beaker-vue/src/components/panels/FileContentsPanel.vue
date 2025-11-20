<template>
    <div class="preview-container-pre">
        <div
            class="preview-draggable"
            :style="`width: ${dragWidth}px;`"
            @mousedown.left.prevent="hookResize()"
        />
        <div
            class="preview-container-main"
                :style="`max-width: calc(100% - ${dragWidth}px);`"
        >
            <div class="preview-standard-toolbar" v-if="!mimetypeConfig[mime]?.overridesToolbar">
                <Toolbar>
                    <template #center>
                        <span>{{ shortname }}</span>
                    </template>
                    <template #end>
                        <Button
                            v-if="mimetypeConfig[mime]?.hasRawToggle"
                            class="preview-raw"
                            @click="isRaw = !isRaw"
                            :label="!isRaw ? 'Raw View' : 'Rich View'"
                        />
                    </template>
                </Toolbar>
            </div>
            <div class="preview-under-toolbar">
                <div v-if="showPreviewInterrupt && contents.isLoading">
                    <Button
                        class="preview-cancel"
                        @click="previewAborter.abort()"
                        severity="danger"
                        label="Cancel Preview"
                    />
                    <span>File is {{ contents.contentLength / 1000000 }} MB</span>
                </div>
                <div class="preview-payload"
                    v-if="!contents.isLoading"
                >
                    <div class="pdf-preview" v-if="mimeCategory(mime) === 'pdf'">
                        <PDFPreview ref="pdfPreviewRef" :url="url"/>
                    </div>
                    <div class="text-preview" v-if="mimeCategory(mime) === 'plaintext'">
                        <CodeEditor
                            :readonly="true"
                            display-mode="dark"
                            :modelValue="contentsWrapper"
                            ref="codeEditorRef"
                            placeholder="Loading..."
                            :language="mime === 'text/x-python' ? 'python' : undefined"
                        />
                    </div>
                    <div class="image-preview" v-if="mimeCategory(mime) === 'image'">
                        <img :src="url"/>
                    </div>
                    <div class="csv-preview" v-if="
                        ['csv', 'tsv', 'excel'].includes(mimeCategory(mime))
                    ">
                        <BeakerMimeBundle
                            v-if="(!isRaw && !contents.isLoading)"
                            :mimeBundle="{[mime]: contentsWrapper}"
                        />
                        <CodeEditor
                            v-if="isRaw"
                            display-mode="dark"
                            :modelValue="contentsWrapper"
                            ref="codeEditorRef"
                            placeholder="Loading..."
                        />
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>
import { ref, watch, computed, reactive } from "vue";

import PDFPreview from "../render/pdf/PDFPreview.vue";
import Toolbar from "primevue/toolbar";
import Button from "primevue/button";
import CodeEditor from "../misc/CodeEditor.vue";
import BeakerMimeBundle from "../render/BeakerMimeBundle.vue";
import { fetch } from '@/util/fetch';

const codeEditorRef = ref();
const pdfPreviewRef = ref();

// dynamically updates with result of async watch
const fallbackMime = ref("");

// should nice-looking renderers show raw instead - see config
const isRaw = ref(false);

const hookResize = () => {
    const resize = event => {
        const target = window.innerWidth - (event.x - dragWidth.value / 2);
        width.value = Math.min(Math.max(target, minWidth), window.innerWidth * 0.9);
    };
    const unhookResize = () => {
        document.querySelector('body').removeEventListener('mousemove', resize);
        document.querySelector('body').removeEventListener('mouseup', this);
    };
    document.querySelector('body').addEventListener('mousemove', resize);
    document.querySelector('body').addEventListener('mouseup', unhookResize);
}

type PreviewCategory =
    | 'image'
    | 'csv'
    | 'tsv'
    | 'plaintext'
    | 'pdf'
    | 'excel'

// text/csv should have more priority than text/?? or octet-stream for rich matching.
const mimeCategory = (mimetype: string): PreviewCategory => {
    if (mimetype.startsWith('image/')) {
        return 'image'
    }
    if (mimetype === 'application/pdf') {
        return 'pdf'
    }
    if (mimetype === 'text/csv') {
        return 'csv'
    }
    if (mimetype === 'text/tsv') {
        return 'tsv'
    }
    // todo: is this comprehensive?
    if (mimetype === 'application/vnd.ms-excel' ||
        mimetype === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    {
        return 'excel'
    }
    // application/octet-stream is a common plaintext unknown
    return 'plaintext'
}

type PreviewConfig = {
    overridesToolbar?: boolean;
    // for files that have rich and raw view, like csv
    hasRawToggle?: boolean;
    // for files loaded via delegation to library operating on URLs;
    //   e.x. we aren't passing raw data to PDFJS, just the url.
    //   also applies for <img>
    skipContents?: boolean;
}
const mimetypeConfig: {[key in string]: PreviewConfig} = {
    "application/pdf": {
        overridesToolbar: true,
        skipContents: true
    },
    "image/png": {
        skipContents: true
    },
    "text/csv": {
        hasRawToggle: true
    },
    "text/tsv": {
        hasRawToggle: true
    }
}

type PreviewContents = {
    isLoading: boolean;
    contents?: any;
    contentLength: number;
}
const contents = ref<PreviewContents>({
    isLoading: false,
    contentLength: -1,
});
// should be in sync with isLoading, with false->true state change delayed by 500ms
// (500ms being a dummy value for "when would a user want to interrupt a preview operation")
const showPreviewInterrupt = ref(false);
const previewInterruptTime = 500;

const decoder = new TextDecoder()

// drag bar width in px
const dragWidth = ref(5);
// default pdfjs canvas plus dragbar size
const width = ref(614 + dragWidth.value);
const minWidth = 260;

const props = defineProps([
    'url',
    'mimetype'
])

const mime = computed(() => props.mimetype ?? fallbackMime.value ?? '')

const previewAborter = ref<AbortController>();

// contents as what is most useful by guessing at typing
const contentsWrapper = computed(() => {
    const data = contents.value?.contents;
    const category = mimeCategory(mime.value)
    if (category === 'image' || category === 'pdf') {
        return "<loaded elsewhere via url>";
    }
    if (!data) {
        return "";
    }
    // even if data exists, handle 0-byte files.
    if (data.length === 0) {
        return "<file is 0 bytes>"
    }

    // sheetJS can injest Uint8Array without decoding or re-encoding
    if (category === 'excel') {
        return data
    }

    // default to handling as UTF8 (csv, tsv, plaintext, octet)
    return decoder.decode(data)
});

// not sure why manually refreshing this matters with reactive refs:
// {{ contentsWrapper }} updates live, as a model of codemirror it doesn't.
watch(() => [contentsWrapper.value], (current, old) => {
    if (codeEditorRef.value) {
        codeEditorRef.value.model = current[0];
    }
})

const shortname = computed(() => {
    const parts = props.url?.split('/');
    if (parts === undefined) {
        return 'No file selected.'
    }
    return parts.length > 0 ? parts[parts.length - 1] : "";
});

const getInfoFromURL = async (url: string): Promise<string[]> => {
    const response = await fetch(url, {method: 'HEAD'})
    return ['Content-Type', 'Content-Length'].map((key) => response.headers.get(key))
}


const getContents = async (url: string) => {
    previewAborter.value = new AbortController();
    const response = await fetch(url, {signal: previewAborter.value.signal});
    // const reader = response.body.getReader();
    const fullContents = [];
    for await (const chunk of response.body) {
        fullContents.push(chunk);
    }

    // file is empty
    if (fullContents.length === 0) {
        return [];
    }

    // merge uint8arrays without spread syntax. 50x speedup as according to SO
    // create a new uint8array the size of sum(chunks.length)
    const mergedArray = new Uint8Array(
        fullContents
            .map((chunk) => chunk.length)
            .reduce((a, b) => a + b));
    // set each chunk data at the offset to effectively concatenate them by chunk, not element
    fullContents.reduce((offset, chunk) => {
        mergedArray.set(chunk, offset);
        return offset + chunk.length;
    }, 0)
    return mergedArray;
}


watch(() => [props.url, props.mimetype], async (current, previous) => {
    // if no associated mimetype, find a fallback
    if (previous.length >= 2 && previous[1] === 'application/pdf') {
        // handler for cases where pdf rendering gets interrupted.
        // the pdf renderer checks for a missing canvas and aborts,
        // but the task may need to be handled here later as well.
        console.log('interrupted pdf rendering for another preview');
    }

    contents.value = {
        isLoading: true,
        contentLength: 0,
    };
    const timeout = setTimeout(() => {
        showPreviewInterrupt.value = true;
    }, previewInterruptTime)
    const [mimetype, length] = await getInfoFromURL(props.url);

    if (props.mimetype === undefined || props.mimetype == null) {
        fallbackMime.value = mimetype;
    } else {
        fallbackMime.value = undefined;
    }

    contents.value.contentLength = parseInt(length, 10);
    if (!(mimetypeConfig[props.mimetype] ?? {})?.skipContents) {
        contents.value.contents = await getContents(props.url);
    }
    // reset both flags, because showPreviewInterrupt delays behind isLoading to
    // avoid screen flashes and repainting on fast previews.
    contents.value.isLoading = false;
    showPreviewInterrupt.value = false;
    clearTimeout(timeout);
})

</script>

<style lang="scss">
.preview-container-pre {
    display: flex;
    flex-direction: row;
    height: 100%;
}
.preview-draggable {
    width: 3px;
    min-height: 100%;
    z-index: 100;
    background-color: var(--p-surface-b);
}
.preview-draggable:hover {
    cursor: col-resize;
}
.preview-container-main {
    display: flex;
    flex-direction: column;
    flex: 1;
    // if pdf controls are integrated here, remove border, but don't change default control bar styling
    .pdf-preview .controls-container div.p-toolbar {
        border: none;
        border-radius: 0;
        flex-wrap: nowrap;
        .p-toolbar-group-start button.pdf-ui-close {
            margin-left: 0;
        }
    }
    overflow: hidden;
}

.preview-under-toolbar {
    display: flex;
    flex: 1;
    overflow: auto;
    // csv renderer -- hide mimetypes but don't change this for notebook
    .preview-payload div.csv-preview div div.mime-select-container {
        display: none;
    }
}

div.preview-standard-toolbar {
    div.p-toolbar {
        padding: 0.5rem;
        padding-left: 0.25rem;
        border: none;
        border-radius: 0;
        flex-wrap: nowrap;
        background-color: var(--p-surface-d);
        .p-toolbar-group-start button.pdf-ui-close {
            margin-left: 0;
        }
    }
}
button.preview-close {
    width: 2rem;
    height: 2rem;
}
button.preview-raw {
    height: 2rem;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
    span.p-button-label {
        font-weight: 400;
        text-wrap: nowrap;
    }
}

.preview-payload {
    flex: 1;
    max-height: 100%;
    max-width: 100%;
}
.pdf-preview {
    flex: 1;
    max-height: 100%;
    display: flex;
    flex-direction: column;
}
</style>
