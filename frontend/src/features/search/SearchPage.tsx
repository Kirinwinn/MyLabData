import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { apiClient, ApiError, queryKeys } from "../../api";
import type { AttributesResponse, EntriesResponse, SearchRequest, SearchResponse } from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime } from "../../lib/format";
import {
  draftsFromRequest,
  emptyConditionDraft,
  operatorLabels,
  operatorsByValueType,
  searchRequestFromUrl,
  searchRequestToUrl,
} from "./searchState";
import type {
  SearchConditionDraft,
  SearchLogic,
  SearchOperator,
  SearchValueType,
} from "./searchState";

const PAGE_SIZE = 25;

function errorMessage(error: Error | null) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred while searching.";
}

export function SearchPage() {
  const [parameters, setParameters] = useSearchParams();
  const serialized = parameters.toString();
  const request = useMemo(() => searchRequestFromUrl(parameters), [parameters]);

  return (
    <SearchWorkspace
      initialRequest={request}
      invalidUrl={parameters.has("query") && request === null}
      key={serialized}
      onCommit={(next) => setParameters(searchRequestToUrl(next))}
    />
  );
}

interface SearchWorkspaceProps {
  initialRequest: SearchRequest | null;
  invalidUrl: boolean;
  onCommit(request: SearchRequest): void;
}

function SearchWorkspace({ initialRequest, invalidUrl, onCommit }: SearchWorkspaceProps) {
  const queryClient = useQueryClient();
  const [logic, setLogic] = useState<SearchLogic>(initialRequest?.logic ?? "and");
  const [conditions, setConditions] = useState(() => draftsFromRequest(initialRequest));
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const attributes = useQuery({
    queryKey: queryKeys.attributes.all(),
    queryFn: ({ signal }) => apiClient.attributes({ signal }),
  });
  const restoredAttributeIds = useMemo(
    () =>
      Array.from(
        new Set(
          initialRequest?.conditions.flatMap((condition) =>
            condition.attribute_id ? [condition.attribute_id] : [],
          ) ?? [],
        ),
      ),
    [initialRequest],
  );
  const restoredEntries = useQueries({
    queries: restoredAttributeIds.map((attributeId) => ({
      queryKey: queryKeys.attributes.entries(attributeId),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiClient.attributeEntries(attributeId, { signal }),
    })),
  });
  const restoredCatalogReady =
    initialRequest !== null &&
    attributes.data !== undefined &&
    restoredEntries.every((query) => query.data !== undefined);
  const restoredRequestValid = restoredCatalogReady
    ? requestMatchesCatalog(
        initialRequest,
        attributes.data,
        new Map(
          restoredAttributeIds.map((attributeId, index) => [
            attributeId,
            restoredEntries[index].data ?? [],
          ]),
        ),
      )
    : undefined;
  const result = useQuery({
    queryKey: queryKeys.search(initialRequest ?? emptyRequest()),
    queryFn: ({ signal }) => apiClient.search(initialRequest ?? emptyRequest(), { signal }),
    enabled: restoredRequestValid === true,
  });

  const updateCondition = (id: string, update: Partial<SearchConditionDraft>) => {
    setConditions((current) =>
      current.map((condition) => (condition.id === id ? { ...condition, ...update } : condition)),
    );
    setValidationErrors([]);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const built = buildRequest(conditions, logic, attributes.data, queryClient);
    if (!built.ok) {
      setValidationErrors(built.errors);
      return;
    }
    setValidationErrors([]);
    onCommit(built.request);
  };

  const moveCondition = (index: number, direction: -1 | 1) => {
    setConditions((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
  };

  return (
    <div className="search-page">
      <section className="search-filter" aria-labelledby="search-filter-title">
        <div className="section-heading">
          <div>
            <h2 id="search-filter-title">Filter</h2>
          </div>
          <LogicControl logic={logic} onChange={setLogic} />
        </div>
        <div className="search-builder" aria-label="Filter conditions">

        {invalidUrl ? (
          <p className="inline-warning" role="alert">
            The search conditions in the URL are invalid. A blank condition is shown and no request was sent.
          </p>
        ) : null}
        {restoredRequestValid === false ? (
          <p className="inline-warning" role="alert">
            The URL conditions do not match the current catalog or value types, so no request was sent.
          </p>
        ) : null}
        {attributes.error ? (
          <ErrorState
            compact
            title="Failed to load catalog"
            description={errorMessage(attributes.error)}
            onRetry={() => attributes.refetch()}
          />
        ) : (
          <form onSubmit={submit}>
            <footer className="search-builder__footer">
              <button className="button" disabled={attributes.isPending} type="submit">
                Run Search
              </button>
              <button
                className="button button--ghost"
                disabled={conditions.length >= 50}
                onClick={() => setConditions((current) => [...current, emptyConditionDraft()])}
                type="button"
              >
                ＋ Add condition
              </button>
            </footer>
            <div className="search-conditions">
              {conditions.map((condition, index) => (
                <ConditionRow
                  attributes={attributes.data ?? []}
                  condition={condition}
                  index={index}
                  isFirst={index === 0}
                  isLast={index === conditions.length - 1}
                  key={condition.id}
                  logic={logic}
                  onMove={(direction) => moveCondition(index, direction)}
                  onRemove={() =>
                    setConditions((current) =>
                      current.length === 1
                        ? current
                        : current.filter((candidate) => candidate.id !== condition.id),
                    )
                  }
                  onUpdate={(update) => updateCondition(condition.id, update)}
                />
              ))}
            </div>

            {validationErrors.length ? (
              <div className="search-validation" role="alert">
                <strong>Please correct the following conditions:</strong>
                <ul>
                  {validationErrors.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              </div>
            ) : null}

          </form>
        )}
        </div>
      </section>

      <SearchResults
        onPage={(offset) =>
          initialRequest && onCommit({ ...initialRequest, offset, limit: PAGE_SIZE })
        }
        query={result}
        request={restoredRequestValid === false ? null : initialRequest}
      />
    </div>
  );
}

function LogicControl({
  logic,
  onChange,
}: {
  logic: SearchLogic;
  onChange(value: SearchLogic): void;
}) {
  return (
    <fieldset className="logic-control">
      <legend>Condition logic</legend>
      <label className={logic === "and" ? "logic-control--active" : ""}>
        <input
          checked={logic === "and"}
          name="logic"
          onChange={() => onChange("and")}
          type="radio"
        />
        AND
      </label>
      <label className={logic === "or" ? "logic-control--active" : ""}>
        <input checked={logic === "or"} name="logic" onChange={() => onChange("or")} type="radio" />
        OR
      </label>
    </fieldset>
  );
}

interface ConditionRowProps {
  attributes: AttributesResponse;
  condition: SearchConditionDraft;
  index: number;
  isFirst: boolean;
  isLast: boolean;
  logic: SearchLogic;
  onUpdate(update: Partial<SearchConditionDraft>): void;
  onMove(direction: -1 | 1): void;
  onRemove(): void;
}

function ConditionRow({
  attributes,
  condition,
  index,
  isFirst,
  isLast,
  logic,
  onUpdate,
  onMove,
  onRemove,
}: ConditionRowProps) {
  const attributeId = Number(condition.attributeId);
  const attribute = attributes.find((candidate) => candidate.attribute_id === attributeId);
  const valueType = isValueType(attribute?.value_type) ? attribute.value_type : null;
  const entries = useQuery({
    queryKey: queryKeys.attributes.entries(attributeId || 0),
    queryFn: ({ signal }) => apiClient.attributeEntries(attributeId, { signal }),
    enabled: Boolean(attributeId),
  });
  const operators = valueType ? operatorsByValueType[valueType] : operatorsByValueType.number;

  const changeAttribute = (attributeValue: string) => {
    const selected = attributes.find(
      (candidate) => candidate.attribute_id === Number(attributeValue),
    );
    const selectedType = isValueType(selected?.value_type) ? selected.value_type : "number";
    onUpdate({
      attributeId: attributeValue,
      entryId: "",
      operator: operatorsByValueType[selectedType][0],
      value: selectedType === "boolean" ? "true" : "",
      secondValue: "",
    });
  };

  return (
    <article className="search-condition">
      <div className="search-condition__index">
        <span>{index + 1}</span>
        {index > 0 ? <small>{logic.toUpperCase()}</small> : null}
      </div>
      <div className="search-condition__fields">
        <label>
          <span>Attribute</span>
          <select
            aria-label={`Condition ${index + 1} Attribute`}
            onChange={(event) => changeAttribute(event.target.value)}
            value={condition.attributeId}
          >
            <option value="">Select Attribute</option>
            {attributes.map((candidate) => (
              <option key={candidate.attribute_id} value={candidate.attribute_id}>
                {candidate.attribute_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Entry</span>
          <select
            aria-label={`Condition ${index + 1} Entry`}
            disabled={!attribute || entries.isPending || entries.isError}
            onChange={(event) => onUpdate({ entryId: event.target.value })}
            value={condition.entryId}
          >
            <option value="">
              {entries.isPending ? "Loading…" : entries.isError ? "Load failed" : "Select Entry"}
            </option>
            {entries.data?.map((entry) => (
              <option key={entry.entry_id} value={entry.entry_id}>
                {entry.entry_key}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Operator</span>
          <select
            aria-label={`Condition ${index + 1} Operator`}
            disabled={!valueType}
            onChange={(event) =>
              onUpdate({
                operator: event.target.value as SearchOperator,
                secondValue: "",
              })
            }
            value={condition.operator}
          >
            {operators.map((operator) => (
              <option key={operator} value={operator}>
                {operatorLabels[operator]} · {operator}
              </option>
            ))}
          </select>
        </label>
        <ValueInput
          condition={condition}
          index={index}
          unit={attribute?.unit}
          valueType={valueType}
          onUpdate={onUpdate}
        />
      </div>
      <div className="search-condition__actions" aria-label={`Adjust condition ${index + 1}`}>
        <button disabled={isFirst} onClick={() => onMove(-1)} title="Move up" type="button">
          ↑
        </button>
        <button disabled={isLast} onClick={() => onMove(1)} title="Move down" type="button">
          ↓
        </button>
        <button disabled={isFirst && isLast} onClick={onRemove} title="Delete" type="button">
          ×
        </button>
      </div>
    </article>
  );
}

interface ValueInputProps {
  condition: SearchConditionDraft;
  index: number;
  unit: string | null | undefined;
  valueType: SearchValueType | null;
  onUpdate(update: Partial<SearchConditionDraft>): void;
}

function ValueInput({ condition, index, unit, valueType, onUpdate }: ValueInputProps) {
  if (valueType === "boolean") {
    return (
      <label>
        <span>Value</span>
        <select
          aria-label={`Condition ${index + 1} Value`}
          onChange={(event) => onUpdate({ value: event.target.value })}
          value={condition.value || "true"}
        >
          <option value="true">Yes · true</option>
          <option value="false">No · false</option>
        </select>
      </label>
    );
  }

  return (
    <div
      className={`search-value${condition.operator === "between" ? " search-value--range" : ""}`}
    >
      <label>
        <span>{condition.operator === "between" ? "Minimum" : "Value"}</span>
        <input
          aria-label={`Condition ${index + 1} Value`}
          disabled={!valueType}
          onChange={(event) => onUpdate({ value: event.target.value })}
          placeholder={valueType === "number" ? "Enter number" : "Enter text"}
          step={valueType === "number" ? "any" : undefined}
          type={valueType === "number" ? "number" : "text"}
          value={condition.value}
        />
        {unit ? <small>{unit}</small> : null}
      </label>
      {condition.operator === "between" ? (
        <label>
          <span>Maximum</span>
          <input
            aria-label={`Condition ${index + 1} Second Value`}
            onChange={(event) => onUpdate({ secondValue: event.target.value })}
            placeholder="Enter upper bound"
            step="any"
            type="number"
            value={condition.secondValue}
          />
          {unit ? <small>{unit}</small> : null}
        </label>
      ) : null}
    </div>
  );
}

type BuildResult = { ok: true; request: SearchRequest } | { ok: false; errors: string[] };

function buildRequest(
  drafts: SearchConditionDraft[],
  logic: SearchLogic,
  attributes: AttributesResponse | undefined,
  queryClient: ReturnType<typeof useQueryClient>,
): BuildResult {
  if (!attributes) return { ok: false, errors: ["Catalog is still loading."] };
  const errors: string[] = [];
  const conditions: SearchRequest["conditions"] = [];

  drafts.forEach((draft, index) => {
    const label = `Condition ${index + 1}`;
    const attribute = attributes.find(
      (candidate) => candidate.attribute_id === Number(draft.attributeId),
    );
    if (!attribute || !isValueType(attribute.value_type)) {
      errors.push(`${label}: Please select a valid Attribute.`);
      return;
    }
    const entries = queryClient.getQueryData<EntriesResponse>(
      queryKeys.attributes.entries(attribute.attribute_id),
    );
    const entry = entries?.find((candidate) => candidate.entry_id === Number(draft.entryId));
    if (!entry || entry.attribute_id !== attribute.attribute_id) {
      errors.push(`${label}: Please select an Entry belonging to this Attribute.`);
      return;
    }
    if (!operatorsByValueType[attribute.value_type].includes(draft.operator)) {
      errors.push(`${label}: This operator does not apply to the ${attribute.value_type} value type.`);
      return;
    }

    if (attribute.value_type === "number") {
      const value = Number(draft.value);
      if (!draft.value.trim() || !Number.isFinite(value)) {
        errors.push(`${label}: Please enter a valid number.`);
        return;
      }
      if (draft.operator === "between") {
        const second = Number(draft.secondValue);
        if (!draft.secondValue.trim() || !Number.isFinite(second)) {
          errors.push(`${label}: between requires a valid maximum value.`);
          return;
        }
        if (value > second) {
          errors.push(`${label}: Minimum cannot be greater than maximum.`);
          return;
        }
        conditions.push({
          attribute_id: attribute.attribute_id,
          entry_id: entry.entry_id,
          operator: draft.operator,
          value,
          second_value: second,
        });
        return;
      }
      conditions.push({
        attribute_id: attribute.attribute_id,
        entry_id: entry.entry_id,
        operator: draft.operator,
        value,
      });
      return;
    }

    if (attribute.value_type === "boolean") {
      if (draft.value !== "true" && draft.value !== "false") {
        errors.push(`${label}: Please select a boolean value.`);
        return;
      }
      conditions.push({
        attribute_id: attribute.attribute_id,
        entry_id: entry.entry_id,
        operator: draft.operator,
        value: draft.value === "true",
      });
      return;
    }

    if (!draft.value.trim()) {
      errors.push(`${label}: Text value cannot be empty.`);
      return;
    }
    conditions.push({
      attribute_id: attribute.attribute_id,
      entry_id: entry.entry_id,
      operator: draft.operator,
      value: draft.value,
    });
  });

  return errors.length
    ? { ok: false, errors }
    : { ok: true, request: { conditions, logic, limit: PAGE_SIZE, offset: 0 } };
}

interface SearchResultsProps {
  request: SearchRequest | null;
  query: {
    data: SearchResponse | undefined;
    error: Error | null;
    isPending: boolean;
    isFetching: boolean;
    refetch(): unknown;
  };
  onPage(offset: number): void;
}

function SearchResults({ request, query, onPage }: SearchResultsProps) {
  if (!request) {
    return (
      <section className="search-results panel" aria-label="Search results">
        <EmptyState title="Search has not been run" description="Add at least one valid condition, then click “Run Search”." />
      </section>
    );
  }
  if (query.isPending) {
    return (
      <section className="search-results panel" aria-label="Search results">
        <LoadingState title="Running cross-filter search" />
      </section>
    );
  }
  if (query.error || !query.data) {
    return (
      <section className="search-results panel" aria-label="Search results">
        <ErrorState
          title="Search failed"
          description={errorMessage(query.error)}
          onRetry={() => query.refetch()}
        />
      </section>
    );
  }

  const data = query.data;
  return (
    <section className="search-results panel" aria-label="Search results">
      <div className="search-results__toolbar">
        <SearchPageControl
          key={`${data.offset}-${data.total}`}
          limit={data.limit}
          offset={data.offset}
          onPage={onPage}
          total={data.total ?? data.molecules.length}
        />
        <ExportSearchButton disabled={data.molecules.length === 0} request={request} />
      </div>
      {!data.molecules.length ? (
        <EmptyState title="No matching molecules" description="Try broadening the conditions or use OR." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Lab ID</th>
                <th>Canonical SMILES</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.molecules.map((molecule) => (
                <tr key={molecule.molecule_id}>
                  <td>#{molecule.molecule_id}</td>
                  <td>
                    <Link className="table-link" to={`/molecules/${molecule.molecule_id}`}>
                      {molecule.lab_id}
                    </Link>
                  </td>
                  <td><span className="smiles-cell">{molecule.canonical_smiles}</span></td>
                  <td>{formatDateTime(molecule.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ExportSearchButton({
  disabled,
  request,
}: {
  disabled: boolean;
  request: SearchRequest;
}) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportJob = useMutation({
    mutationFn: async (exportRequest: SearchRequest) => {
      const job = await apiClient.searchExport(exportRequest);
      const fileName = job.result?.file_name;
      if (typeof fileName !== "string" || !fileName) {
        throw new ApiError({
          kind: "response",
          message: "The export job completed without a workbook file.",
        });
      }
      return job.job_id;
    },
    onError: (error: Error) => {
      setExportError(
        error instanceof ApiError ? error.message : "The export could not be completed.",
      );
    },
    onSuccess: (jobId) => {
      setExportError(null);
      triggerExportDownload(apiClient.exportDownloadUrl(jobId));
    },
    onSettled: () => setExporting(false),
  });

  return (
    <>
      {exportError ? (
        <span className="search-export__error" role="alert">
          {exportError}
        </span>
      ) : null}
      <button
        className="button search-export"
        disabled={disabled || exporting}
        onClick={() => {
          setExporting(true);
          setExportError(null);
          exportJob.mutate(request);
        }}
        type="button"
      >
        {exporting ? "Exporting…" : "Export XLSX"}
      </button>
    </>
  );
}

function triggerExportDownload(url: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function SearchPageControl({
  limit,
  offset,
  total,
  onPage,
}: {
  limit: number;
  offset: number;
  total: number;
  onPage(offset: number): void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const [editingPage, setEditingPage] = useState(false);
  const [pageDraft, setPageDraft] = useState(String(page));

  const goToPage = () => {
    const requested = Number.parseInt(pageDraft, 10);
    if (!Number.isFinite(requested)) return;
    const nextPage = Math.min(Math.max(1, requested), totalPages);
    setEditingPage(false);
    onPage((nextPage - 1) * limit);
  };

  return (
    <div className="search-page-control section-heading__meta">
      <span>Page</span>
      {editingPage ? (
        <input
          aria-label="Page number"
          autoFocus
          className="page-jump-input"
          inputMode="numeric"
          max={totalPages}
          min={1}
          onBlur={goToPage}
          onChange={(event) => setPageDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") goToPage();
            if (event.key === "Escape") setEditingPage(false);
          }}
          type="text"
          value={pageDraft}
        />
      ) : (
        <button
          aria-label={`Current page ${page}`}
          className="page-jump-button"
          onClick={() => {
            setPageDraft(String(page));
            setEditingPage(true);
          }}
          type="button"
        >
          {page}
        </button>
      )}
      <span>/ {totalPages}</span>
    </div>
  );
}

function isValueType(value: string | undefined): value is SearchValueType {
  return value === "number" || value === "text" || value === "boolean";
}

function requestMatchesCatalog(
  request: SearchRequest,
  attributes: AttributesResponse,
  entriesByAttribute: Map<number, EntriesResponse>,
) {
  return request.conditions.every((condition) => {
    const attribute = attributes.find(
      (candidate) => candidate.attribute_id === condition.attribute_id,
    );
    if (!attribute || !isValueType(attribute.value_type)) return false;
    const entry = entriesByAttribute
      .get(attribute.attribute_id)
      ?.find((candidate) => candidate.entry_id === condition.entry_id);
    if (!entry || entry.attribute_id !== attribute.attribute_id) return false;
    if (!operatorsByValueType[attribute.value_type].includes(condition.operator)) return false;

    if (attribute.value_type === "number") {
      if (typeof condition.value !== "number" || !Number.isFinite(condition.value)) return false;
      if (condition.operator !== "between") return condition.second_value == null;
      return (
        typeof condition.second_value === "number" &&
        Number.isFinite(condition.second_value) &&
        condition.value <= condition.second_value
      );
    }
    if (condition.second_value != null) return false;
    return attribute.value_type === "boolean"
      ? typeof condition.value === "boolean"
      : typeof condition.value === "string" && condition.value.trim().length > 0;
  });
}

function emptyRequest(): SearchRequest {
  return { conditions: [], logic: "and", limit: PAGE_SIZE, offset: 0 };
}
