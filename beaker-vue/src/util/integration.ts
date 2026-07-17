import { fetch } from '@/util/fetch';

export interface IntegrationResource {
    // names must be coherent with python resource class
    resource_type: string
    integration: string
    resource_id: string
}

export interface IntegrationExample extends IntegrationResource {
    resource_type: "example";
    query: string
    code: string
    notes?: string
}

export interface IntegrationAttachedFile extends IntegrationResource {
    resource_type: "file";
    filepath: string
    name: string
    content?: string
}

export interface SkillMetadataResource extends IntegrationResource {
    resource_type: "skill_metadata";
    skill_name: string
    description: string
    license?: string
    compatibility?: string
    allowed_tools?: string
    skill_metadata: Record<string, string>
}

export interface SkillInstructionsResource extends IntegrationResource {
    resource_type: "skill_instructions";
    content: string
}

export interface SkillFileResource extends IntegrationResource {
    resource_type: "skill_file";
    name: string
    relative_path: string
    content?: string
}

export interface SkillExampleResource extends IntegrationResource {
    resource_type: "skill_example";
    filename: string
    title: string
    description: string
    content?: string
}

export interface MCPToolResource extends IntegrationResource {
    resource_type: "mcp_tool";
    tool_name: string
    description?: string
    // JSON Schema for the tool's arguments, as returned by tools/list.
    input_schema?: Record<string, any>
}

export interface MCPResourceResource extends IntegrationResource {
    resource_type: "mcp_resource";
    uri: string
    name: string
    description?: string
    mime_type?: string
    content?: string
}

export interface MCPPromptResource extends IntegrationResource {
    resource_type: "mcp_prompt";
    prompt_name: string
    description?: string
    arguments?: Record<string, any>[]
}

export type IntegrationResourceMap = {
    [id in string]: IntegrationResource
}

export interface Integration {
    description: string
    source: string
    slug: string
    uuid: string
    name: string
    url: string
    provider: string
    datatype?: string
    // Slug of the parent corpus, if declared inside one. MCP servers provided
    // by a context are namespaced under a "context-<slug>" corpus.
    corpus?: string
    // important: resources are loaded via a second API call and may not exist or be filled on the object
    resources?: IntegrationResourceMap;
}

// Connection config for an MCP server. Either stdio (command/args/env) or
// http/sse (url/headers). `transport` may be explicit or left for the backend
// to infer from command/url.
export interface MCPServerConfig {
    name: string
    title?: string
    command?: string
    args?: string[]
    env?: Record<string, string>
    url?: string
    headers?: Record<string, string>
    transport?: "stdio" | "http" | "sse"
    disabled?: boolean
    description?: string
    instructions?: string
    metadata?: Record<string, any>
}

export interface MCPIntegration extends Integration {
    datatype: "mcp";
    server_config?: MCPServerConfig
    // Transient: true only while a live session is open.
    connected?: boolean
    // Whether the tool/resource/prompt catalog has been fetched into resources.
    resources_loaded?: boolean
    server_title?: string
    server_version?: string
    instructions?: string
    capabilities?: Record<string, any>
}

export type IntegrationMap = {[key in string]: Integration};

export type IntegrationProviders = {
    [key in string]: {
        mutable: boolean
        integrations: Integration[]
    }
}

export interface IntegrationInterfaceState {
    selected: string | undefined
    integrations: IntegrationMap
    unsavedChanges: boolean
    finishedInitialLoad: boolean
}

export interface IntegrationAPIRouteDetails {
    sessionId: string,
    integrationId?: string,
    resourceType?: string,
    resourceId?: string,
}

const toRoute = (details: IntegrationAPIRouteDetails) =>
    [details.sessionId, details?.integrationId, details?.resourceType, details?.resourceId]
    .filter((x) => x)
    .join('/')

async function integrationApiWrapper<T>(
    method: "GET" | "POST" | "DELETE",
    route: IntegrationAPIRouteDetails,
    body?: object
): Promise<T> {
    const path = `/beaker/integrations/${toRoute(route)}`
    console.log(path)
    const response = await fetch(path, {
        method,
        headers: {
            "Content-Type": "application/json"
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    const json = await response.json() as T;
    return json
}

export const getIntegrationProviderType = (integration: Integration) => integration.provider.split(":")[0];

// MCP servers provided by a context are read-only and namespaced under a
// "context-<slug>" corpus; locally-configured servers are user-editable.
export const isContextProvidedIntegration = (integration: Integration): boolean =>
    (integration?.corpus ?? "").startsWith("context-");

export const getIntegrationProviderSlug = (integration: Integration) => integration.provider.split(":")[1]

// Per-datatype display metadata. Single source of truth for how each
// integration datatype is presented in the UI; extend this interface as more
// per-type presentation data is needed.
export interface DatatypeDisplay {
    // Human-readable name for the datatype (e.g. surfaced as an icon tooltip).
    label: string;
    // Bare filename of a bundled icon in public/icons/. Omit for datatypes
    // that have no associated icon.
    icon?: string;
}

const DATATYPE_DISPLAY: {[datatype in string]: DatatypeDisplay} = {
    api: { label: "API" },
    database: { label: "Database" },
    dataset: { label: "Dataset" },
    mcp: { label: "MCP Server", icon: "mcp.png" },
    skill: { label: "Agent Skill", icon: "skill.png" },
};

// Resolves the displayable icon URL for an integration based on its datatype,
// or undefined if that datatype has no associated icon. Uses BASE_URL so the
// path is correct under a non-root deployment base.
export const getIntegrationIcon = (integration: Integration): string | undefined => {
    const filename = integration?.datatype ? DATATYPE_DISPLAY[integration.datatype]?.icon : undefined;
    return filename ? `${import.meta.env.BASE_URL}icons/${filename}` : undefined;
};

// Returns a human-readable label for an integration's datatype, falling back to
// the raw datatype string (or undefined if unset).
export const getIntegrationTypeLabel = (integration: Integration): string | undefined => {
    if (!integration?.datatype) {
        return undefined;
    }
    return DATATYPE_DISPLAY[integration.datatype]?.label ?? integration.datatype;
};

export const listIntegrations = async (sessionId: string): Promise<IntegrationMap> => {
    return (await integrationApiWrapper<{"integrations": IntegrationMap}>("GET", {sessionId})).integrations;
}

export const addIntegration = async (sessionId: string, body: object): Promise<Integration> => {
    return await integrationApiWrapper<Integration>("POST", {sessionId}, body);
}

export const updateIntegration = async (sessionId: string, integrationId: string, body: object): Promise<Integration> => {
    return await integrationApiWrapper<Integration>("POST", {sessionId, integrationId}, body);
}

export const getResource = async (sessionId: string, integrationId: string, resourceType: string, resourceId: string): Promise<IntegrationResource> => {
    return await integrationApiWrapper<IntegrationResource>("GET", {sessionId, integrationId, resourceType, resourceId});
}

export const listResources = async (sessionId: string, integrationId: string) => {
    const routeDetails = {
        sessionId,
        integrationId,
        resourceType: "all"
    }
    return (await integrationApiWrapper<{resources: IntegrationResource[]}>("GET", routeDetails)).resources;
}

export const addResource = async (sessionId: string, integrationId: string, body: object) => {
    return await integrationApiWrapper<IntegrationResource>("POST", {sessionId, integrationId, resourceType: "new"}, body)
}

export const updateResource = async (sessionId: string, integrationId: string, resourceId: string, body: object) => {
    return await integrationApiWrapper<IntegrationResource>("POST", {sessionId, integrationId, resourceType: "new", resourceId}, body)
}

export const deleteResource = async (sessionId: string, integrationId: string, resourceId: string) => {
    return await integrationApiWrapper<{}>("DELETE", {sessionId, integrationId, resourceType: "any", resourceId})
}

export function filterByResourceType<T>(resources: IntegrationResourceMap | undefined, resource_type: string): {[key in string]: T} {
    return Object.fromEntries(Object.entries(resources ?? {})
        .filter(([_, resource]) => resource.resource_type === resource_type)) as {[key in string]: T};
}
