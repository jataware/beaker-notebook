import { MimeModel, RenderMimeRegistry} from '@jupyterlab/rendermime';
import { Sanitizer } from '@jupyterlab/apputils';
import { standardRendererFactories, IRenderMime } from '@jupyterlab/rendermime';
import { PartialJSONObject } from '@lumino/coreutils';


export interface IBeakerRendererOptions {
    renderers: ReadonlyArray<IMimeRenderer>;
}

export type MimetypeString = "text/plain" | "text/html" | string;

/**
 *
 */
export interface IMimeBundle {
    [mimetype: MimetypeString]: PartialJSONObject;
}

export interface IMimeRenderer<OutputType = HTMLElement> {
    rank: number;
    mimetypes: MimetypeString[];
    render: (mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject) => OutputType;
}

export class MimeRenderer implements IMimeRenderer<HTMLElement> {

    public rank: number = 100;
    public mimetypes: string[] = [];

    public render(mimeType: MimetypeString, data: PartialJSONObject, metadata: PartialJSONObject): HTMLElement {

        return new HTMLElement();
    };

}

export class JupyterMimeRenderer extends MimeRenderer {

    constructor(factory: IRenderMime.IRendererFactory) {
        super();
        this._factory = factory
        this.rank = factory.defaultRank || 100;
        this.mimetypes = [...factory.mimeTypes];
    }

    public render(mimeType: MimetypeString, data: PartialJSONObject, metadata?: PartialJSONObject): HTMLElement {
        const renderer = this._factory.createRenderer({
            mimeType,
            resolver: null,
            sanitizer: new Sanitizer(),
            linkHandler: null,
            latexTypesetter: null,
            markdownParser: null,
            translator: undefined,

        });
        const model = new MimeModel({
            trusted: true,
            data: {[mimeType]: data},
            metadata: metadata,
        });
        renderer.renderModel(model);
        return renderer.node;
    }
    private _factory: IRenderMime.IRendererFactory;
}

interface TaggedRenderer {
    renderer: IMimeRenderer;
    tag?: string;
}

export class BeakerRenderer {

    constructor(options?: IBeakerRendererOptions) {
        this._renderers = {};
        this._tagged = {};
        for (const factory of standardRendererFactories) {
            const renderer = new JupyterMimeRenderer(factory);
            this.addRenderer(renderer);
        }
        for (const renderer of options?.renderers || []) {
            this.addRenderer(renderer);
        }
    }

    /**
     * Register a renderer. If a tag is provided, the renderer can later be
     * removed as a group via {@link removeRenderersByTag}.
     */
    public addRenderer(renderer: IMimeRenderer, tag?: string) {
        for (const mimetype of renderer.mimetypes) {
            const existing = this._tagged[mimetype];
            if (!existing) {
                this._renderers[mimetype] = renderer;
                this._tagged[mimetype] = { renderer, tag };
            }
            else if (renderer.rank <= existing.renderer.rank) {
                this._renderers[mimetype] = renderer;
                this._tagged[mimetype] = { renderer, tag };
            }
        }
    }

    /**
     * Remove all renderers that were registered with the given tag.
     * For any mimetype left empty after removal, falls back to the
     * next-best renderer if one was previously shadowed — but in practice
     * this just removes the entry since we don't keep a priority queue.
     */
    public removeRenderersByTag(tag: string) {
        for (const [mimetype, entry] of Object.entries(this._tagged)) {
            if (entry.tag === tag) {
                delete this._renderers[mimetype];
                delete this._tagged[mimetype];
            }
        }
    }

    public get rankedMimetypes(): MimetypeString[] {
        const mimetypes = Object.keys(this._renderers);
        mimetypes.sort((a, b) => this._renderers[a].rank - this._renderers[b].rank);
        return mimetypes;
    }

    public render(mimeType: MimetypeString, data: PartialJSONObject, metadata?: PartialJSONObject): any {
        const renderer = this._renderers[mimeType];
        if (renderer) {
            return renderer.render(mimeType, data, metadata || {});
        }
    }

    public renderMimeBundle(bundle: IMimeBundle, metadata?: PartialJSONObject): {[key: MimetypeString]: HTMLElement} {
        return Object.fromEntries(Object.entries(bundle).map(([mimeType, content]) => {
            return [mimeType, this.render(mimeType, content, metadata)];
        }));
    }

    public rankedMimetypesInBundle(bundle: IMimeBundle): MimetypeString[] {
        const result = this.rankedMimetypes.filter((mime) => bundle && Object.keys(bundle).includes(mime))
        return result;
    }

    private _renderers: {[key: string]: IMimeRenderer};
    private _tagged: {[key: string]: TaggedRenderer};
}
