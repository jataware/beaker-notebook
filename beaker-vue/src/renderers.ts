import { type Component, defineComponent, h } from 'vue';

import type { IMimeRenderer, MimetypeString } from 'beaker-kernel';
import type { PartialJSONObject } from '@lumino/coreutils';
import VueJsonPretty from 'vue-json-pretty';
import { marked } from 'marked';
import TableRenderer from './components/render/TableRenderer.vue';

export interface BeakerRenderOutput {
    component: Component;
    bindMapping: {[key: string]: any};
}

export type BeakerMimeRenderer = IMimeRenderer<BeakerRenderOutput>;

export const JSONRenderer: BeakerMimeRenderer = {
    rank: 60,
    mimetypes: ["application/json", "text/json"],
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {
        return {
            component: VueJsonPretty,
            bindMapping: {
                data: data,
                deep: "2",
                showLength: true,
                showIcon: true,
                showDoubleQuotes: "isQuotes",
                showLineNumber: "linenum",
                style: {
                    whiteSpace: "pre",
                },
            }
        };
    }
}

export const MarkdownRenderer: BeakerMimeRenderer = {
    rank: 40,
    mimetypes: ["text/markdown", "text/x-markdown"],
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {
        const html = marked.parse(data.toString())
        return {
            component: defineComponent(
                (props) => {
                    return () => {
                        return h('div', {innerHTML: props.html});
                    }
                    },
                    {
                    props: ["html"]
                    }
            ),
            bindMapping: {
                'html': html,
            }
        }
    },
}


export const LatexRenderer: BeakerMimeRenderer = {
    rank: 40,
    mimetypes: ["text/latex", "application/latex"],
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {

        // const mathJaxTypsetter = new MathJaxTypesetter();
        // const mathJaxDocument = await mathJaxTypsetter.mathDocument();

        const input = data.toString();
        // const output = mathJaxDocument.convert(input, {display: false}).outerHTML;
        const output = "DEBUG TESTING DEADBEEF";
        return {
            component: defineComponent(
                (props) => {
                    return () => {
                        return h('div', {class: "beaker-latex", innerHTML: props.html, style: {fontSize: "1.5rem"}});
                    }
                    },
                    {
                        props: ["html"]
                    },
            ),
            bindMapping: {
                'html': output,
            }
        }
    }
}

export const TableRenderer: BeakerMimeRenderer = {
    rank: 40,
    mimetypes: [
        "text/csv",
        "text/tsv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ],
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {
        return {
            component: TableRenderer,
            bindMapping: {
                data: data,
                mimeType: mimeType
            }
        }
    }
}

export const JavascriptRenderer: BeakerMimeRenderer = {
    rank: 45,
    mimetypes: [
        "text/javascript",
        "application/javascript",
    ],
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {
        return {
            component: defineComponent(
                (props) => {
                        return () => {
                            return h(
                                'script',
                                {innerHTML: props.html}
                            );
                        }
                }
            ),
            bindMapping: {
                html: data,
                mimeType: mimeType
            }
        }
    }
}

export function wrapJupyterRenderer(jupyterRenderer: IMimeRenderer<HTMLElement>): BeakerMimeRenderer {
    return {
        rank: jupyterRenderer.rank - 10,
        mimetypes: jupyterRenderer.mimetypes,
        render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => {
            const rawHtmlElement: HTMLElement = jupyterRenderer.render(mimeType, data, metadata);
            return {
                component: defineComponent(
                    () => {
                        return () => {
                            return h(
                                'div',
                                {
                                    onVnodeBeforeMount: (vnode) => {
                                        vnode.el.appendChild(rawHtmlElement);
                                    },
                                }
                            );
                        }
                    },
                ),
                bindMapping: {}
            }

        }
    }
}
