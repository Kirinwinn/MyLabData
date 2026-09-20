import type { components } from "./generated/schema";

type SearchRequest = components["schemas"]["SearchRequest"];

export const queryKeys = {
  all: ["mylabdata"] as const,
  health: () => [...queryKeys.all, "health"] as const,
  packages: {
    all: () => [...queryKeys.all, "packages"] as const,
    list: () => [...queryKeys.all, "packages", "list"] as const,
    detail: (packageId: string) => [...queryKeys.all, "packages", "detail", packageId] as const,
  },
  imports: {
    all: () => [...queryKeys.all, "imports"] as const,
    list: (limit: number, offset: number) =>
      [...queryKeys.all, "imports", "list", { limit, offset }] as const,
    detail: (importId: number) => [...queryKeys.all, "imports", "detail", importId] as const,
  },
  jobs: {
    all: () => [...queryKeys.all, "jobs"] as const,
    list: (limit: number) => [...queryKeys.all, "jobs", "list", { limit }] as const,
    detail: (jobId: string) => [...queryKeys.all, "jobs", "detail", jobId] as const,
  },
  molecules: {
    all: () => [...queryKeys.all, "molecules"] as const,
    list: (
      query: string | null,
      limit: number,
      offset: number,
      entryFilter?: { entryId: number; hasResults: boolean } | null,
    ) =>
      [
        ...queryKeys.all,
        "molecules",
        "list",
        {
          query,
          limit,
          offset,
          ...(entryFilter ? { entryFilter } : {}),
        },
      ] as const,
    detail: (moleculeId: number) => [...queryKeys.all, "molecules", "detail", moleculeId] as const,
    structure3d: (moleculeId: number, requestId: number) =>
      [...queryKeys.all, "molecules", moleculeId, "structure-3d", requestId] as const,
    attributes: (moleculeId: number) =>
      [...queryKeys.all, "molecules", moleculeId, "attributes"] as const,
    annotations: (moleculeId: number, attributeId: number) =>
      [
        ...queryKeys.all,
        "molecules",
        moleculeId,
        "attributes",
        attributeId,
        "annotations",
      ] as const,
  },
  attributes: {
    all: () => [...queryKeys.all, "attributes"] as const,
    entries: (attributeId: number) =>
      [...queryKeys.all, "attributes", attributeId, "entries"] as const,
    stats: (attributeId: number) => [...queryKeys.all, "attributes", attributeId, "stats"] as const,
  },
  entries: {
    index: () => [...queryKeys.all, "entries", "index"] as const,
  },
  sourceFiles: {
    all: () => [...queryKeys.all, "source-files"] as const,
    list: () => [...queryKeys.all, "source-files", "list"] as const,
    profile: (name: string) => [...queryKeys.all, "source-files", "profile", name] as const,
  },
  stats: () => [...queryKeys.all, "stats"] as const,
  search: (request: SearchRequest) => [...queryKeys.all, "search", request] as const,
};
