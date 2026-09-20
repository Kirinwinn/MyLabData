import { z } from "zod";

import type { components } from "./generated/schema";

type Schemas = components["schemas"];
type JobRecord = Schemas["JobRecord"];

const nonNegativeInteger = z.number().int().nonnegative();
const positiveInteger = z.number().int().positive();
const nullableString = z.string().nullable();

const moleculePreviewSchema: z.ZodType<Schemas["MoleculePackagePreview"]> = z.object({
  package_name: z.string(),
  package_hash: z.string(),
  total_rows: nonNegativeInteger,
  valid_rows: nonNegativeInteger,
  new_rows: nonNegativeInteger,
  existing_rows: nonNegativeInteger,
  duplicate_rows: nonNegativeInteger,
  invalid_rows: nonNegativeInteger,
});

const attributeDefinitionSchema = z.object({
  attribute_key: z.string(),
  attribute_name: z.string(),
  value_type: z.enum(["number", "text", "boolean"]),
  unit: nullableString,
  description: nullableString,
});

const entryDefinitionSchema = z.object({
  entry_key: z.string(),
  attribute_key: z.string(),
  annotation_kind: z.enum(["prediction", "calculation", "property"]),
  method_name: z.string(),
  method_version: nullableString,
  conditions: z.record(z.string(), z.unknown()).default({}),
  source_key: nullableString,
  is_mutable: z.boolean(),
  description: nullableString,
});

const annotationPreviewSchema: z.ZodType<Schemas["AnnotationPackagePreview"]> = z.object({
  package_name: z.string(),
  package_hash: z.string(),
  preview_token: z.string(),
  annotation_rows: nonNegativeInteger,
  attributes: z.array(
    z.object({
      definition: attributeDefinitionSchema,
      status: z.enum(["existing", "new", "conflict"]),
      conflicts: z.array(z.string()).default([]),
    }),
  ),
  entries: z.array(
    z.object({
      definition: entryDefinitionSchema,
      status: z.enum(["existing", "new", "conflict"]),
      conflicts: z.array(z.string()).default([]),
    }),
  ),
  linkable_molecules: nonNegativeInteger,
  unlinkable_molecules: nonNegativeInteger,
  duplicate_annotations: nonNegativeInteger,
  existing_annotations: nonNegativeInteger,
  expected_inserts: nonNegativeInteger,
  warnings: z.array(z.string()),
  errors: z.array(z.string()),
  can_import: z.boolean(),
});

const packageImportSchema: z.ZodType<Schemas["PackageImportResult"]> = z.object({
  import_id: positiveInteger,
  package_name: z.string(),
  package_hash: z.string(),
  total_rows: nonNegativeInteger,
  inserted_rows: nonNegativeInteger,
  existing_rows: nonNegativeInteger,
  duplicate_rows: nonNegativeInteger,
  invalid_rows: nonNegativeInteger,
  created_attributes: nonNegativeInteger,
  created_entries: nonNegativeInteger,
  created_sources: nonNegativeInteger,
  archived: z.boolean(),
});

const propertyUpdateSchema: z.ZodType<Schemas["PropertyUpdateResult"]> = z.object({
  molecule_id: positiveInteger,
  entry_id: positiveInteger,
  value_number: z.number().nullable(),
  value_text: nullableString,
  value_boolean: z.boolean().nullable(),
  source: z.string(),
  created: z.boolean(),
  updated_at: z.iso.datetime(),
});

type ParsedByJobType =
  | { jobType: "molecule_preview"; result: Schemas["MoleculePackagePreview"] }
  | { jobType: "annotation_preview"; result: Schemas["AnnotationPackagePreview"] }
  | { jobType: "package_import"; result: Schemas["PackageImportResult"] }
  | { jobType: "property_update"; result: Schemas["PropertyUpdateResult"] };

export type JobResultParseResult =
  { ok: true; data: ParsedByJobType | null } | { ok: false; error: JobResultParseError };

export class JobResultParseError extends Error {
  constructor(
    message: string,
    readonly jobType: string,
    readonly issues: z.core.$ZodIssue[] = [],
  ) {
    super(message);
    this.name = "JobResultParseError";
  }
}

export function parseJobResult(job: Pick<JobRecord, "job_type" | "result">): JobResultParseResult {
  if (job.result === null || job.job_type.endsWith("_query")) {
    return { ok: true, data: null };
  }

  if (job.job_type === "package_preview") {
    const molecule = moleculePreviewSchema.safeParse(job.result);
    if (molecule.success) {
      return { ok: true, data: { jobType: "molecule_preview", result: molecule.data } };
    }
    const annotation = annotationPreviewSchema.safeParse(job.result);
    if (annotation.success) {
      return { ok: true, data: { jobType: "annotation_preview", result: annotation.data } };
    }
    return invalidResult(job.job_type, [...molecule.error.issues, ...annotation.error.issues]);
  }

  if (job.job_type === "package_import") {
    return parsedResult(job.job_type, "package_import", packageImportSchema.safeParse(job.result));
  }
  if (job.job_type === "property_update") {
    return parsedResult(
      job.job_type,
      "property_update",
      propertyUpdateSchema.safeParse(job.result),
    );
  }
  return {
    ok: false,
    error: new JobResultParseError(`不支持的任务类型：${job.job_type}`, job.job_type),
  };
}

function parsedResult<K extends "package_import" | "property_update", T>(
  sourceType: string,
  jobType: K,
  parsed: z.ZodSafeParseResult<T>,
): JobResultParseResult {
  if (!parsed.success) return invalidResult(sourceType, parsed.error.issues);
  return { ok: true, data: { jobType, result: parsed.data } as ParsedByJobType };
}

function invalidResult(jobType: string, issues: z.core.$ZodIssue[]): JobResultParseResult {
  return {
    ok: false,
    error: new JobResultParseError("任务结果与任务类型不匹配", jobType, issues),
  };
}
