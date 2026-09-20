import type { components, operations } from "./generated/schema";
import { ApiError, apiErrorFromResponse, apiErrorFromThrown } from "./errors";

type Schemas = components["schemas"];
type JobAccepted = Schemas["JobAccepted"];

export type HealthResponse =
  operations["health_api_v1_health_get"]["responses"][200]["content"]["application/json"];
export type StatsResponse = Schemas["DatabaseStats"];
export type ImportsResponse = Schemas["ImportRecord"][];
export type JobsResponse =
  operations["get_background_jobs_api_v1_jobs_get"]["responses"][200]["content"]["application/json"];
export type JobResponse =
  operations["get_background_job_api_v1_jobs__job_id__get"]["responses"][200]["content"]["application/json"];
export type AttributesResponse = Schemas["AttributeRecord"][];
export type EntriesResponse = Schemas["EntryRecord"][];
export type AttributeStatsResponse = Schemas["AttributeStatistics"][];
export type MoleculesResponse = Schemas["MoleculeSummary"][];
export type MoleculeResponse = Schemas["MoleculeDetail"];
export type Molecule3DStructureResponse = Schemas["Molecule3DStructure"];
export type MoleculeAttributeAnnotationsResponse = Schemas["MoleculeAttributeAnnotation"][];
export type SearchRequest = Schemas["SearchRequest"];
export type SearchResponse = Schemas["SearchResult"];
export type SearchExportResponse = Schemas["SearchExportResult"];
export type PackagesResponse = Schemas["PackageSummary"][];
export type PackageResponse = Schemas["PackageDetail"];
export type PackagePreviewResponse =
  operations["preview_package_api_v1_packages__package_id__preview_post"]["responses"][202]["content"]["application/json"];
export type PackageImportResponse =
  operations["import_package_api_v1_packages__package_id__imports_post"]["responses"][202]["content"]["application/json"];
export type PackageImportRequest = Schemas["PackageImportRequest"];
export type PropertyUpdateRequest = Schemas["PropertyUpdateRequest"];
export type PropertyUpdateResponse =
  operations["update_property_api_v1_molecules__molecule_id__properties__entry_id__put"]["responses"][202]["content"]["application/json"];
export type PreheatStatsResponse = {
  total: number;
  preheated: number;
  failed: number;
  elapsed_seconds: number;
};
export type EntryResultFilterInput = { entryId: number; hasResults: boolean };
export type EntryIndexEntry = {
  entry_id: number;
  entry_key: string;
  attribute_key: string;
  attribute_name: string;
  annotation_kind: string;
  method_name: string;
  method_version: string | null;
  conditions: Record<string, unknown>;
  is_mutable: boolean;
  description: string | null;
};
export type MoleculesPageResponse = { items: Schemas["MoleculeSummary"][]; total: number };
export type SourceFileSummary = {
  name: string;
  size_bytes: number;
  modified_at: string;
};
export type SourceFileColumnProfile = {
  index: number;
  name: string;
  value_type: "number" | "text" | "boolean";
  filled_rows: number;
  empty_rows: number;
};
export type SourceFileProfile = {
  name: string;
  encoding: string;
  delimiter: string;
  columns: SourceFileColumnProfile[];
  total_rows: number;
  preview_rows: string[][];
};
export type AttributeChoiceInput = {
  mode: "existing" | "new";
  attribute_key: string;
  attribute_name?: string | null;
  value_type?: "number" | "text" | "boolean" | null;
  unit?: string | null;
  description?: string | null;
};
export type EntryChoiceInput = {
  mode: "existing" | "new";
  entry_key: string;
  annotation_kind?: "prediction" | "calculation" | "property" | null;
  method_name?: string | null;
  method_version?: string | null;
  conditions?: Record<string, unknown>;
  is_mutable?: boolean;
  description?: string | null;
};
export type PackageBuildMapping = {
  column_index: number;
  column_name: string;
  attribute: AttributeChoiceInput;
  entry: EntryChoiceInput;
};
export type PackageBuildRequest = {
  package_name: string;
  source_file: string;
  identifier_column_index: number;
  processor_name: string;
  processor_version: string;
  mappings: PackageBuildMapping[];
  dry_run: boolean;
};
export type PackageBuildResult = {
  dry_run: boolean;
  package_name: string;
  attributes_existing: number;
  attributes_new: number;
  entries_existing: number;
  entries_new: number;
  annotation_rows: number;
  linkable_molecules: number;
  unlinkable_molecules: number;
  in_file_duplicates: number;
  already_in_database: number;
  expected_inserts: number;
  rejected_rows: number;
  warnings: string[];
};

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

export class ApiClient {
  constructor(private readonly baseUrl = "") {}

  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    const headers = new Headers(options.headers);
    if (options.body !== undefined && !isFormData && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        headers,
        body:
          options.body === undefined
            ? undefined
            : isFormData
              ? (options.body as FormData)
              : JSON.stringify(options.body),
      });
      const body = await readBody(response);
      if (!response.ok) throw apiErrorFromResponse(response, body);
      return body as T;
    } catch (error) {
      throw apiErrorFromThrown(error);
    }
  }

  health(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<HealthResponse>("/api/v1/health", options);
  }

  stats(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.query<StatsResponse>("/api/v1/stats/query", undefined, options);
  }

  imports(
    parameters: { limit?: number; offset?: number } = {},
    options: Pick<ApiRequestOptions, "signal"> = {},
  ) {
    return this.queryItems<Schemas["ImportRecord"]>(
      "/api/v1/imports/query",
      { limit: parameters.limit ?? 100, offset: parameters.offset ?? 0 },
      options,
    );
  }

  jobs(parameters: { limit?: number } = {}, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<JobsResponse>(
      withQuery("/api/v1/jobs", { limit: parameters.limit }),
      options,
    );
  }

  job(jobId: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<JobResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, options);
  }

  cancelJob(jobId: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<JobResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
      ...options,
      method: "POST",
    });
  }

  attributes(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<Schemas["AttributeRecord"]>(
      "/api/v1/attributes/query",
      undefined,
      options,
    );
  }

  attributeEntries(attributeId: number, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<Schemas["EntryRecord"]>(
      `/api/v1/attributes/${attributeId}/entries/query`,
      undefined,
      options,
    );
  }

  attributeStats(attributeId: number, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<Schemas["AttributeStatistics"]>(
      `/api/v1/attributes/${attributeId}/stats/query`,
      undefined,
      options,
    );
  }

  preheatStats(options: Pick<ApiRequestOptions, "signal"> = {}): Promise<PreheatStatsResponse> {
    return this.query<PreheatStatsResponse>(
      "/api/v1/attributes/stats/preheat",
      undefined,
      options,
    );
  }

  molecules(
    parameters: {
      query?: string | null;
      limit?: number;
      offset?: number;
      entryFilter?: EntryResultFilterInput | null;
    } = {},
    options: Pick<ApiRequestOptions, "signal"> = {},
  ) {
    return this.query<MoleculesPageResponse>(
      "/api/v1/molecules/query",
      {
        query: parameters.query ?? null,
        limit: parameters.limit ?? 100,
        offset: parameters.offset ?? 0,
        ...(parameters.entryFilter
          ? {
              entry_filter: {
                entry_id: parameters.entryFilter.entryId,
                has_results: parameters.entryFilter.hasResults,
              },
            }
          : {}),
      },
      options,
    );
  }

  entriesIndex(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<EntryIndexEntry>("/api/v1/entries/index/query", undefined, options);
  }

  sourceFiles(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<SourceFileSummary[]>("/api/v1/source-files", options);
  }

  sourceFileProfile(name: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<SourceFileProfile>(
      `/api/v1/source-files/${encodeURIComponent(name)}/profile`,
      options,
    );
  }

  uploadSourceFile(file: File, options: Pick<ApiRequestOptions, "signal"> = {}) {
    const body = new FormData();
    body.append("file", file);
    return this.request<SourceFileProfile>("/api/v1/source-files", {
      ...options,
      method: "POST",
      body,
    });
  }

  deleteSourceFile(name: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<void>(`/api/v1/source-files/${encodeURIComponent(name)}`, {
      ...options,
      method: "DELETE",
    });
  }

  buildPackage(
    request: PackageBuildRequest,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ): Promise<JobResponse> {
    return this.queryJob("/api/v1/packages/build", request, options);
  }

  molecule(moleculeId: number, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.query<MoleculeResponse>(
      `/api/v1/molecules/${moleculeId}/query`,
      undefined,
      options,
    );
  }

  molecule3dStructure(moleculeId: number, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.query<Molecule3DStructureResponse>(
      `/api/v1/molecules/${moleculeId}/structure-3d/query`,
      undefined,
      options,
    );
  }

  moleculeAttributes(moleculeId: number, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<Schemas["AttributeRecord"]>(
      `/api/v1/molecules/${moleculeId}/attributes/query`,
      undefined,
      options,
    );
  }

  moleculeAttributeAnnotations(
    moleculeId: number,
    attributeId: number,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ) {
    return this.queryItems<Schemas["MoleculeAttributeAnnotation"]>(
      `/api/v1/molecules/${moleculeId}/attributes/${attributeId}/annotations/query`,
      undefined,
      options,
    );
  }

  search(request: SearchRequest, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.query<SearchResponse>("/api/v1/search", request, options);
  }

  searchExport(
    request: SearchRequest,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ): Promise<JobResponse> {
    return this.queryJob("/api/v1/search/export", request, options);
  }

  smilesExport(
    entryFilter: EntryResultFilterInput | null = null,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ): Promise<JobResponse> {
    const body = entryFilter
      ? { entry_filter: { entry_id: entryFilter.entryId, has_results: entryFilter.hasResults } }
      : {};
    return this.queryJob("/api/v1/molecules/smiles/export", body, options);
  }

  exportDownloadUrl(jobId: string) {
    return `${this.baseUrl}/api/v1/jobs/${encodeURIComponent(jobId)}/export`;
  }

  packages(options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.queryItems<Schemas["PackageSummary"]>("/api/v1/packages/query", undefined, options);
  }

  package(packageId: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.query<PackageResponse>(
      `/api/v1/packages/${encodeURIComponent(packageId)}/query`,
      undefined,
      options,
    );
  }

  previewPackage(packageId: string, options: Pick<ApiRequestOptions, "signal"> = {}) {
    return this.request<PackagePreviewResponse>(
      `/api/v1/packages/${encodeURIComponent(packageId)}/preview`,
      { ...options, method: "POST" },
    );
  }

  importPackage(
    packageId: string,
    body: PackageImportRequest | null,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ) {
    return this.request<PackageImportResponse>(
      `/api/v1/packages/${encodeURIComponent(packageId)}/imports`,
      { ...options, method: "POST", body },
    );
  }

  updateProperty(
    moleculeId: number,
    entryId: number,
    request: PropertyUpdateRequest,
    options: Pick<ApiRequestOptions, "signal"> = {},
  ) {
    return this.request<PropertyUpdateResponse>(
      `/api/v1/molecules/${moleculeId}/properties/${entryId}`,
      { ...options, method: "PUT", body: request },
    );
  }

  private async query<T>(
    path: string,
    body: unknown,
    options: Pick<ApiRequestOptions, "signal">,
  ): Promise<T> {
    const job = await this.queryJob(path, body, options);
    return job.result as T;
  }

  private async queryJob(
    path: string,
    body: unknown,
    options: Pick<ApiRequestOptions, "signal">,
  ): Promise<JobResponse> {
    const accepted = await this.request<JobAccepted>(path, {
      ...options,
      method: "POST",
      body,
    });
    return this.waitForQuery(accepted.job_id, options.signal ?? undefined);
  }

  private async queryItems<T>(
    path: string,
    body: unknown,
    options: Pick<ApiRequestOptions, "signal">,
  ): Promise<T[]> {
    const result = await this.query<{ items: T[] }>(path, body, options);
    if (!result || !Array.isArray(result.items)) {
      throw new ApiError({ kind: "response", message: "Query Job 返回了无效的列表结果" });
    }
    return result.items;
  }

  private async waitForQuery(jobId: string, signal?: AbortSignal): Promise<JobResponse> {
    while (true) {
      const job = await this.job(jobId, { signal });
      if (job.status === "completed") {
        if (job.result === null) {
          throw new ApiError({ kind: "response", message: "Query Job 完成但没有返回结果" });
        }
        return job;
      }
      if (job.status === "failed" || job.status === "cancelled") {
        throw new ApiError({
          kind: "response",
          message: job.error_message ?? job.message ?? `Query Job ${job.status}`,
          detail: job,
        });
      }
      await abortableDelay(75, signal);
    }
  }
}

function withQuery(path: string, parameters: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
}

function abortableDelay(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timeout = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;

  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    if (!response.ok) return text;
    throw new ApiError({
      kind: "response",
      status: response.status,
      message: "后端返回了无法解析的 JSON 响应",
      cause: error,
    });
  }
}

export const apiClient = new ApiClient();
