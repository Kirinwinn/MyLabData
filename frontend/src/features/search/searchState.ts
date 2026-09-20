import { z } from "zod";

import type { SearchRequest } from "../../api";

export type SearchOperator = SearchRequest["conditions"][number]["operator"];
export type SearchLogic = SearchRequest["logic"];
export type SearchValueType = "number" | "text" | "boolean";

export interface SearchConditionDraft {
  id: string;
  attributeId: string;
  entryId: string;
  operator: SearchOperator;
  value: string;
  secondValue: string;
}

export const operatorsByValueType: Record<SearchValueType, readonly SearchOperator[]> = {
  number: ["eq", "ne", "lt", "lte", "gt", "gte", "between"],
  text: ["eq", "ne", "contains", "starts_with", "ends_with"],
  boolean: ["eq", "ne"],
};

export const operatorLabels: Record<SearchOperator, string> = {
  eq: "Equals",
  ne: "Does not equal",
  lt: "Less than",
  lte: "Less than or equal",
  gt: "Greater than",
  gte: "Greater than or equal",
  between: "Between",
  contains: "Contains",
  starts_with: "Starts with",
  ends_with: "Ends with",
};

let nextDraftId = 1;

export function emptyConditionDraft(): SearchConditionDraft {
  return {
    id: `condition-${nextDraftId++}`,
    attributeId: "",
    entryId: "",
    operator: "eq",
    value: "",
    secondValue: "",
  };
}

const operatorSchema = z.enum([
  "eq",
  "ne",
  "lt",
  "lte",
  "gt",
  "gte",
  "between",
  "contains",
  "starts_with",
  "ends_with",
]);
const persistedRequestSchema = z.object({
  conditions: z
    .array(
      z.object({
        attribute_id: z.number().int().positive(),
        entry_id: z.number().int().positive(),
        operator: operatorSchema,
        value: z.union([z.number(), z.string(), z.boolean()]),
        second_value: z.union([z.number(), z.string(), z.boolean()]).nullable().optional(),
      }),
    )
    .min(1)
    .max(50),
  logic: z.enum(["and", "or"]),
  limit: z.number().int().min(1).max(1000),
  offset: z.number().int().nonnegative(),
});

export function searchRequestFromUrl(parameters: URLSearchParams): SearchRequest | null {
  const serialized = parameters.get("query");
  if (!serialized) return null;
  try {
    const result = persistedRequestSchema.safeParse(JSON.parse(serialized) as unknown);
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

export function searchRequestToUrl(request: SearchRequest) {
  return new URLSearchParams({ query: JSON.stringify(request) });
}

export function draftsFromRequest(request: SearchRequest | null): SearchConditionDraft[] {
  if (!request) return [emptyConditionDraft()];
  return request.conditions.map((condition) => ({
    id: `condition-${nextDraftId++}`,
    attributeId: String(condition.attribute_id ?? ""),
    entryId: String(condition.entry_id ?? ""),
    operator: condition.operator,
    value: String(condition.value),
    secondValue:
      condition.second_value === null || condition.second_value === undefined
        ? ""
        : String(condition.second_value),
  }));
}
