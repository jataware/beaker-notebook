import { EditorView as CodeMirrorView } from "@codemirror/view";
import PrimevueTextarea from "primevue/textarea";


/**
 *
 **/
// TODO: Fix this as to be better null safe
export function capitalize(s: string) {
    return s?.charAt(0).toUpperCase() + s.slice(1) || s;
}

/**
 *
 **/
export function getDateTimeString() {
    const t = new Date();
    // convert the local time zone offset from minutes to milliseconds
    const z = t.getTimezoneOffset() * 60 * 1000;
    // subtract the offset from t
    const tLocalNumber = Number(t) - z;
    // create shifted Date object
    const tLocal = new Date(tLocalNumber);
    // convert to ISO format string
    let iso = tLocal.toISOString();
    // drop the milliseconds and zone
    iso = iso.split(".")[0];
    // replace the T and `:` with `_` (`:` characters aren't allowed in filenames)
    iso = iso.replace(/[:T]/g, '_')
    return iso;
}

/**
 *
 **/
export function downloadFileDOM(data: Blob, filename: string, mimeType: string) {
    const nav = (window.navigator as any);

    if (nav.msSaveOrOpenBlob) {
        nav.msSaveBlob(data, filename);
    }
    else {
        const elem = window.document.createElement('a');
        elem.href = window.URL.createObjectURL(data);
        elem.download = filename;
        document.body.appendChild(elem);
        elem.click();
        document.body.removeChild(elem);
    }
}
const isSelectable = (el: HTMLElement): boolean => {
    if (typeof el.getAttribute("tabindex") === "string") {
        return true;
    }
};

export function findSelectableParent(target: HTMLElement): HTMLElement {
    while (target !== undefined && target !== null && target !== document.body) {
        if (isSelectable(target)) {
            return target;
        }
        target = target.parentElement;
    }
    return undefined;
}

export type ErrorObject = {
    ename: string;
    evalue: string;
    traceback?: string[];
}

export function isErrorObject(obj): obj is ErrorObject {
    return Object.hasOwn(obj, "ename") && Object.hasOwn(obj, "evalue");
}

type InputElement = HTMLTextAreaElement | HTMLInputElement | CodeMirrorView | typeof PrimevueTextarea;

export function normalizeInputElement(input: object): InputElement {
    if (Object.hasOwn(input, "view") && Object.hasOwn(input["view"], "viewState")) {
        return input["view"];
    }
    if (input && input["$el"]) {
        return input["$el"] as InputElement;
    }
    else {
        return input as InputElement;
    }
}

export function is_codemirror(input: InputElement): input is CodeMirrorView {
    const result = Object.hasOwn(input, 'viewState') && Object.hasOwn(input, 'dom') && Object.hasOwn(input, 'docView')
    return result;
}

export function is_primevue(input: InputElement): input is typeof PrimevueTextarea {
    return false;
}

export function is_html_textarea(input: InputElement): input is HTMLTextAreaElement {
    return input && input["type"] === "textarea";
}

export function atStartOfInput(input: object) {
    const normalizedInput = normalizeInputElement(input)
    if (is_codemirror(normalizedInput)) {
        return normalizedInput.state.selection.main.to === 0;
    }
    else if (is_primevue(normalizedInput)) {
        return false;
    }
    else if (is_html_textarea(normalizedInput)) {
        return normalizedInput.selectionEnd === 0;
    }
    return false;
}

export function atEndOfInput(input: object) {
    const normalizedInput = normalizeInputElement(input)
    if (is_codemirror(normalizedInput)) {
        return normalizedInput.state.selection.main.from === normalizedInput.state.doc.length;
    }
    else if (is_primevue(normalizedInput)) {
        return false;
    }
    else if (is_html_textarea(normalizedInput)) {
        return normalizedInput.selectionStart === normalizedInput.textLength;
    }
    return false;
}

export * from './annotations';
export * from './autocomplete';
export * from './integration';
