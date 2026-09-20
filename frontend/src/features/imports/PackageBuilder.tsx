import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient, ApiError, queryKeys } from "../../api";
import type {
  AttributesResponse,
  EntryIndexEntry,
  PackageBuildMapping,
  PackageBuildRequest,
  PackageBuildResult,
  SourceFileColumnProfile,
  SourceFileProfile,
} from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatNumber } from "../../lib/format";
import { formatBytes } from "./previewHelpers";

const ANNOTATION_KINDS = ["prediction", "calculation", "property"] as const;
const VALUE_TYPES = ["number", "text", "boolean"] as const;

type ValueType = (typeof VALUE_TYPES)[number];
type AnnotationKind = (typeof ANNOTATION_KINDS)[number];

interface AttributeDraft {
  mode: "existing" | "new";
  attributeKey: string;
  attributeName: string;
  valueType: ValueType;
  unit: string;
  description: string;
}

interface EntryDraft {
  mode: "existing" | "new";
  entryKey: string;
  annotationKind: AnnotationKind;
  methodName: string;
  methodVersion: string;
  conditionsText: string;
  isMutable: boolean;
  description: string;
}

interface ColumnDraft {
  included: boolean;
  attribute: AttributeDraft;
  entry: EntryDraft;
}

function message(error: Error | null) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred.";
}

function draftForColumn(column: SourceFileColumnProfile): ColumnDraft {
  return {
    included: column.value_type !== "text",
    attribute: {
      mode: "existing",
      attributeKey: "",
      attributeName: "",
      valueType: column.value_type,
      unit: "",
      description: "",
    },
    entry: {
      mode: "existing",
      entryKey: "",
      annotationKind: "prediction",
      methodName: "",
      methodVersion: "",
      conditionsText: "",
      isMutable: false,
      description: "",
    },
  };
}

function defaultDrafts(columns: SourceFileColumnProfile[]): Record<number, ColumnDraft> {
  return Object.fromEntries(columns.map((column) => [column.index, draftForColumn(column)]));
}

function guessIdentifierColumn(columns: SourceFileColumnProfile[]): number {
  const byName = columns.find((column) => /smiles/i.test(column.name));
  const byIdentifier = columns.find((column) => /(^|[^a-z])id([^a-z]|$)/i.test(column.name));
  return byName?.index ?? byIdentifier?.index ?? columns[0]?.index ?? 0;
}

function parseConditions(text: string): { ok: boolean; conditions: Record<string, unknown> } {
  const conditions: Record<string, unknown> = {};
  for (const part of text.split(",")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) return { ok: false, conditions: {} };
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    if (!key || !value) return { ok: false, conditions: {} };
    conditions[key] = value;
  }
  return { ok: true, conditions };
}

function suggestEntryKey(attributeKey: string, methodName: string, conditionsText: string): string {
  const attribute = attributeKey.trim() || "attribute";
  const method = (methodName.trim() || "method").toLowerCase().replace(/[^a-z0-9_]+/g, "_");
  const parsed = parseConditions(conditionsText);
  const first = parsed.ok ? Object.values(parsed.conditions)[0] : undefined;
  const condition = typeof first === "string" ? first.trim() : "";
  return condition ? `${attribute}.${method}.${condition}` : `${attribute}.${method}`;
}

export function PackageBuilder() {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [draftsByFile, setDraftsByFile] = useState<Record<string, Record<number, ColumnDraft>>>({});
  const [identifierByFile, setIdentifierByFile] = useState<Record<string, number>>({});
  const [packageName, setPackageName] = useState("");
  const [processorName, setProcessorName] = useState("");
  const [processorVersion, setProcessorVersion] = useState("1.0");
  const [formError, setFormError] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<PackageBuildResult | null>(null);
  const [built, setBuilt] = useState<PackageBuildResult | null>(null);

  const files = useQuery({
    queryKey: queryKeys.sourceFiles.list(),
    queryFn: ({ signal }) => apiClient.sourceFiles({ signal }),
  });
  const attributes = useQuery({
    queryKey: queryKeys.attributes.all(),
    queryFn: ({ signal }) => apiClient.attributes({ signal }),
  });
  const entries = useQuery({
    queryKey: queryKeys.entries.index(),
    queryFn: ({ signal }) => apiClient.entriesIndex({ signal }),
  });
  const profile = useQuery({
    queryKey: queryKeys.sourceFiles.profile(selectedFile ?? ""),
    queryFn: ({ signal }) => apiClient.sourceFileProfile(selectedFile as string, { signal }),
    enabled: selectedFile !== null,
  });

  const loaded: SourceFileProfile | undefined = profile.data;
  const drafts: Record<number, ColumnDraft> = loaded
    ? draftsByFile[loaded.name] ?? defaultDrafts(loaded.columns)
    : {};
  const identifierIndex = loaded
    ? identifierByFile[loaded.name] ?? guessIdentifierColumn(loaded.columns)
    : 0;

  function resetOutcome() {
    setPreflight(null);
    setBuilt(null);
    setFormError(null);
  }

  function selectFile(name: string) {
    setSelectedFile(name);
    setFileError(null);
    resetOutcome();
  }

  function updateDraft(columnIndex: number, next: ColumnDraft) {
    if (!loaded) return;
    setDraftsByFile((current) => ({
      ...current,
      [loaded.name]: {
        ...(current[loaded.name] ?? defaultDrafts(loaded.columns)),
        [columnIndex]: next,
      },
    }));
    setPreflight(null);
    setBuilt(null);
  }

  function selectIdentifier(index: number) {
    if (!loaded) return;
    setIdentifierByFile((current) => ({ ...current, [loaded.name]: index }));
    resetOutcome();
  }

  const upload = useMutation({
    mutationFn: (file: File) => apiClient.uploadSourceFile(file),
    onSuccess: (uploaded) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sourceFiles.all() });
      selectFile(uploaded.name);
    },
    onError: (error: Error) => {
      setFileError(error instanceof ApiError ? error.message : "The file could not be uploaded.");
    },
  });

  const remove = useMutation({
    mutationFn: (name: string) => apiClient.deleteSourceFile(name),
    onSuccess: (_data, name) => {
      setFileError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.sourceFiles.all() });
      if (selectedFile === name) {
        setSelectedFile(null);
        resetOutcome();
      }
    },
    onError: (error: Error) => {
      setFileError(error instanceof ApiError ? error.message : "The file could not be deleted.");
    },
  });

  const build = useMutation({
    mutationFn: (request: PackageBuildRequest) => apiClient.buildPackage(request),
    onSuccess: (job, request) => {
      const result = job.result as unknown as PackageBuildResult;
      setFormError(null);
      if (request.dry_run) {
        setPreflight(result);
      } else {
        setBuilt(result);
        setPreflight(null);
      }
    },
    onError: (error: Error) => {
      setFormError(
        error instanceof ApiError ? error.message : "The package could not be built.",
      );
    },
  });

  function buildRequest(dryRun: boolean): PackageBuildRequest | null {
    const loaded = profile.data;
    if (!loaded) {
      setFormError("Choose a source file first.");
      return null;
    }
    if (!packageName.trim()) {
      setFormError("Enter a package name.");
      return null;
    }
    if (!processorName.trim()) {
      setFormError("Enter a processor name.");
      return null;
    }
    const mappings: PackageBuildMapping[] = [];
    for (const column of loaded.columns) {
      if (column.index === identifierIndex) continue;
      const draft = drafts[column.index];
      if (!draft?.included) continue;
      const attribute = draft.attribute;
      if (!attribute.attributeKey.trim()) {
        setFormError(`Column “${column.name}”: choose or name an Attribute.`);
        return null;
      }
      if (attribute.mode === "new" && !attribute.attributeName.trim()) {
        setFormError(`Column “${column.name}”: a new Attribute needs a name.`);
        return null;
      }
      const entry = draft.entry;
      if (!entry.entryKey.trim()) {
        setFormError(`Column “${column.name}”: choose or name an Entry.`);
        return null;
      }
      if (entry.mode === "new" && !entry.methodName.trim()) {
        setFormError(`Column “${column.name}”: a new Entry needs a method name.`);
        return null;
      }
      let conditions: Record<string, unknown> = {};
      if (entry.mode === "new") {
        const parsed = parseConditions(entry.conditionsText);
        if (!parsed.ok) {
          setFormError(`Column “${column.name}”: conditions must use key=value pairs.`);
          return null;
        }
        conditions = parsed.conditions;
      }
      mappings.push({
        column_index: column.index,
        column_name: column.name,
        attribute:
          attribute.mode === "existing"
            ? { mode: "existing", attribute_key: attribute.attributeKey.trim() }
            : {
                mode: "new",
                attribute_key: attribute.attributeKey.trim(),
                attribute_name: attribute.attributeName.trim(),
                value_type: attribute.valueType,
                unit: attribute.unit.trim() || null,
                description: attribute.description.trim() || null,
              },
        entry:
          entry.mode === "existing"
            ? { mode: "existing", entry_key: entry.entryKey.trim() }
            : {
                mode: "new",
                entry_key: entry.entryKey.trim(),
                annotation_kind: entry.annotationKind,
                method_name: entry.methodName.trim(),
                method_version: entry.methodVersion.trim() || null,
                conditions,
                is_mutable: entry.annotationKind === "property" ? entry.isMutable : false,
                description: entry.description.trim() || null,
              },
      });
    }
    if (!mappings.length) {
      setFormError("Include at least one value column.");
      return null;
    }
    setFormError(null);
    return {
      package_name: packageName.trim(),
      source_file: loaded.name,
      identifier_column_index: identifierIndex,
      processor_name: processorName.trim(),
      processor_version: processorVersion.trim() || "1.0",
      mappings,
      dry_run: dryRun,
    };
  }

  const valueColumns = (profile.data?.columns ?? []).filter(
    (column) => column.index !== identifierIndex,
  );

  return (
    <div className="package-builder">
      <section className="package-builder__step">
        <h3>1 · Source file</h3>
        <div className="package-builder__row">
          <label className="button button--inline">
            Upload CSV
            <input
              accept=".csv,.tsv,.txt"
              className="sr-only"
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
                event.target.value = "";
              }}
            />
          </label>
          {upload.isPending ? <span className="package-builder__hint">Uploading…</span> : null}
        </div>
        {fileError ? (
          <p className="inline-warning" role="alert">
            {fileError}
          </p>
        ) : null}
        {files.isPending ? <LoadingState compact title="Loading source files" /> : null}
        {files.error ? (
          <ErrorState
            compact
            title="Failed to load source files"
            description={message(files.error)}
            onRetry={() => files.refetch()}
          />
        ) : null}
        {files.data?.length ? (
          <ul className="package-builder__file-list">
            {files.data.map((item) => (
              <li key={item.name}>
                <button
                  aria-pressed={selectedFile === item.name}
                  className={`package-builder__file${
                    selectedFile === item.name ? " package-builder__file--active" : ""
                  }`}
                  type="button"
                  onClick={() => selectFile(item.name)}
                >
                  <strong>{item.name}</strong>
                  <small>{formatBytes(item.size_bytes)}</small>
                </button>
                <button
                  aria-label={`Delete ${item.name}`}
                  className="button button--ghost button--inline"
                  disabled={remove.isPending}
                  type="button"
                  onClick={() => remove.mutate(item.name)}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        ) : !files.isPending && !files.error ? (
          <EmptyState
            compact
            title="No source files yet"
            description="Upload a CSV of molecule values to start building a package."
          />
        ) : null}
        {selectedFile && profile.isPending ? (
          <LoadingState compact title="Reading the source file" />
        ) : null}
        {profile.error ? (
          <ErrorState
            compact
            title="Failed to read the source file"
            description={message(profile.error)}
            onRetry={() => profile.refetch()}
          />
        ) : null}
        {profile.data ? <SourceFilePreview profile={profile.data} /> : null}
      </section>

      {profile.data ? (
        <section className="package-builder__step">
          <h3>2 · Molecule identifier column</h3>
          <label className="package-builder__field">
            <span className="sr-only">Molecule identifier column</span>
            <select
              value={identifierIndex}
              onChange={(event) => selectIdentifier(Number(event.target.value))}
            >
              {profile.data.columns.map((column) => (
                <option key={column.index} value={column.index}>
                  {column.name}
                </option>
              ))}
            </select>
          </label>
        </section>
      ) : null}

      {profile.data ? (
        <section className="package-builder__step">
          <h3>3 · Column mappings</h3>
          <p className="package-builder__hint">
            Map each value column onto an Attribute and an Entry. Existing keys reuse the
            registered definition.
          </p>
          {valueColumns.map((column) => {
            const draft = drafts[column.index];
            if (!draft) return null;
            return (
              <ColumnMappingEditor
                attributes={attributes.data ?? []}
                column={column}
                draft={draft}
                entries={entries.data ?? []}
                key={column.index}
                onChange={(next) => updateDraft(column.index, next)}
              />
            );
          })}
        </section>
      ) : null}

      {profile.data ? (
        <section className="package-builder__step">
          <h3>4 · Package details</h3>
          <div className="package-builder__row">
            <label className="package-builder__field">
              <span>Package name</span>
              <input
                type="text"
                value={packageName}
                onChange={(event) => setPackageName(event.target.value)}
              />
            </label>
            <label className="package-builder__field">
              <span>Processor name</span>
              <input
                type="text"
                value={processorName}
                onChange={(event) => setProcessorName(event.target.value)}
              />
            </label>
            <label className="package-builder__field">
              <span>Processor version</span>
              <input
                type="text"
                value={processorVersion}
                onChange={(event) => setProcessorVersion(event.target.value)}
              />
            </label>
          </div>
        </section>
      ) : null}

      {profile.data ? (
        <section className="package-builder__step">
          <h3>5 · Preflight and build</h3>
          <div className="package-builder__row">
            <button
              className="button button--inline"
              disabled={build.isPending}
              type="button"
              onClick={() => {
                const request = buildRequest(true);
                if (request) build.mutate(request);
              }}
            >
              {build.isPending && build.variables?.dry_run ? "Checking…" : "Preflight"}
            </button>
            <button
              className="button button--inline"
              disabled={build.isPending}
              type="button"
              onClick={() => {
                const request = buildRequest(false);
                if (request) build.mutate(request);
              }}
            >
              {build.isPending && build.variables && !build.variables.dry_run
                ? "Building…"
                : "Build package"}
            </button>
          </div>
          {formError ? (
            <p className="inline-warning" role="alert">
              {formError}
            </p>
          ) : null}
          {preflight ? <BuildSummary result={preflight} title="Preflight result" /> : null}
          {built ? (
            <div className="package-builder__done">
              <p className="section-kicker">Package built</p>
              <p>
                “{built.package_name}” is waiting in Incoming. Open the Incoming tab to preview
                and confirm it.
              </p>
              <BuildSummary result={built} title="Build result" />
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function SourceFilePreview({ profile }: { profile: SourceFileProfile }) {
  return (
    <div className="package-builder__profile">
      <p className="package-builder__hint">
        {formatNumber(profile.total_rows)} rows · {profile.columns.length} columns · encoding{" "}
        {profile.encoding} · delimiter “{profile.delimiter}”
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {profile.columns.map((column) => (
                <th key={column.index}>
                  {column.name}
                  <small>{column.value_type}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {profile.preview_rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface ColumnMappingEditorProps {
  column: SourceFileColumnProfile;
  draft: ColumnDraft;
  attributes: AttributesResponse;
  entries: EntryIndexEntry[];
  onChange: (next: ColumnDraft) => void;
}

function ColumnMappingEditor({
  column,
  draft,
  attributes,
  entries,
  onChange,
}: ColumnMappingEditorProps) {
  const attribute = draft.attribute;
  const entry = draft.entry;
  const registeredAttribute = attributes.find(
    (item) => item.attribute_key === attribute.attributeKey,
  );
  const registeredEntry = entries.find((item) => item.entry_key === entry.entryKey);
  const entryOptions = entries.filter((item) => item.attribute_key === attribute.attributeKey);

  function updateAttribute(next: Partial<AttributeDraft>) {
    onChange({ ...draft, attribute: { ...attribute, ...next } });
  }

  function updateEntry(next: Partial<EntryDraft>) {
    onChange({ ...draft, entry: { ...entry, ...next } });
  }

  return (
    <article className="package-builder__mapping">
      <header>
        <label className="package-builder__include">
          <input
            checked={draft.included}
            type="checkbox"
            onChange={(event) => onChange({ ...draft, included: event.target.checked })}
          />
          <span>
            <strong>{column.name}</strong>
            <small>
              {column.value_type} · {formatNumber(column.filled_rows)} values ·{" "}
              {formatNumber(column.empty_rows)} empty
            </small>
          </span>
        </label>
      </header>

      <div className="package-builder__choice">
        <div className="package-builder__row">
          <span className="package-builder__label">Attribute</span>
          <label>
            <input
              checked={attribute.mode === "existing"}
              name={`attribute-mode-${column.index}`}
              type="radio"
              onChange={() => updateAttribute({ mode: "existing" })}
            />
            Reuse existing
          </label>
          <label>
            <input
              checked={attribute.mode === "new"}
              name={`attribute-mode-${column.index}`}
              type="radio"
              onChange={() => updateAttribute({ mode: "new" })}
            />
            Create new
          </label>
        </div>
        {attribute.mode === "existing" ? (
          <>
            <label className="package-builder__field">
              <span className="sr-only">Existing Attribute</span>
              <select
                value={attribute.attributeKey}
                onChange={(event) => updateAttribute({ attributeKey: event.target.value })}
              >
                <option value="">Select an Attribute…</option>
                {attributes.map((item) => (
                  <option key={item.attribute_key} value={item.attribute_key}>
                    {item.attribute_name} ({item.attribute_key})
                  </option>
                ))}
              </select>
            </label>
            {registeredAttribute ? (
              <p className="package-builder__definition">
                Registered: {registeredAttribute.attribute_name} ·{" "}
                {registeredAttribute.value_type}
                {registeredAttribute.unit ? ` · ${registeredAttribute.unit}` : ""}
                {registeredAttribute.description ? ` — ${registeredAttribute.description}` : ""}
              </p>
            ) : null}
          </>
        ) : (
          <div className="package-builder__row">
            <label className="package-builder__field">
              <span>Key</span>
              <input
                type="text"
                value={attribute.attributeKey}
                onChange={(event) => updateAttribute({ attributeKey: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Name</span>
              <input
                type="text"
                value={attribute.attributeName}
                onChange={(event) => updateAttribute({ attributeName: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Type</span>
              <select
                value={attribute.valueType}
                onChange={(event) =>
                  updateAttribute({ valueType: event.target.value as ValueType })
                }
              >
                {VALUE_TYPES.map((valueType) => (
                  <option key={valueType} value={valueType}>
                    {valueType}
                  </option>
                ))}
              </select>
            </label>
            <label className="package-builder__field">
              <span>Unit</span>
              <input
                type="text"
                value={attribute.unit}
                onChange={(event) => updateAttribute({ unit: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Description</span>
              <input
                type="text"
                value={attribute.description}
                onChange={(event) => updateAttribute({ description: event.target.value })}
              />
            </label>
          </div>
        )}
      </div>

      <div className="package-builder__choice">
        <div className="package-builder__row">
          <span className="package-builder__label">Entry</span>
          <label>
            <input
              checked={entry.mode === "existing"}
              name={`entry-mode-${column.index}`}
              type="radio"
              onChange={() => updateEntry({ mode: "existing" })}
            />
            Reuse existing
          </label>
          <label>
            <input
              checked={entry.mode === "new"}
              name={`entry-mode-${column.index}`}
              type="radio"
              onChange={() =>
                updateEntry({
                  mode: "new",
                  entryKey:
                    entry.entryKey.trim() ||
                    suggestEntryKey(attribute.attributeKey, entry.methodName, entry.conditionsText),
                })
              }
            />
            Create new
          </label>
        </div>
        {entry.mode === "existing" ? (
          <>
            <label className="package-builder__field">
              <span className="sr-only">Existing Entry</span>
              <select
                disabled={!attribute.attributeKey}
                value={entry.entryKey}
                onChange={(event) => updateEntry({ entryKey: event.target.value })}
              >
                <option value="">
                  {attribute.attributeKey
                    ? "Select an Entry…"
                    : "Select an Attribute first…"}
                </option>
                {entryOptions.map((item) => (
                  <option key={item.entry_key} value={item.entry_key}>
                    {item.entry_key}
                  </option>
                ))}
              </select>
            </label>
            {registeredEntry ? (
              <p className="package-builder__definition">
                Registered: {registeredEntry.annotation_kind} · {registeredEntry.method_name}
                {registeredEntry.method_version ? ` v${registeredEntry.method_version}` : ""} ·{" "}
                {JSON.stringify(registeredEntry.conditions)}
                {registeredEntry.description ? ` — ${registeredEntry.description}` : ""}
              </p>
            ) : null}
          </>
        ) : (
          <div className="package-builder__row">
            <label className="package-builder__field">
              <span>Key</span>
              <input
                type="text"
                value={entry.entryKey}
                onChange={(event) => updateEntry({ entryKey: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Kind</span>
              <select
                value={entry.annotationKind}
                onChange={(event) =>
                  updateEntry({ annotationKind: event.target.value as AnnotationKind })
                }
              >
                {ANNOTATION_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label className="package-builder__field">
              <span>Method</span>
              <input
                type="text"
                value={entry.methodName}
                onChange={(event) => updateEntry({ methodName: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Version</span>
              <input
                type="text"
                value={entry.methodVersion}
                onChange={(event) => updateEntry({ methodVersion: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Conditions</span>
              <input
                placeholder="solvent_smiles=CS(C)=O"
                type="text"
                value={entry.conditionsText}
                onChange={(event) => updateEntry({ conditionsText: event.target.value })}
              />
            </label>
            <label className="package-builder__field">
              <span>Description</span>
              <input
                type="text"
                value={entry.description}
                onChange={(event) => updateEntry({ description: event.target.value })}
              />
            </label>
            {entry.annotationKind === "property" ? (
              <label className="package-builder__include">
                <input
                  checked={entry.isMutable}
                  type="checkbox"
                  onChange={(event) => updateEntry({ isMutable: event.target.checked })}
                />
                <span>Mutable property</span>
              </label>
            ) : null}
          </div>
        )}
      </div>
    </article>
  );
}

function BuildSummary({ result, title }: { result: PackageBuildResult; title: string }) {
  const rows: Array<[string, string]> = [
    ["Attributes", `${result.attributes_existing} existing · ${result.attributes_new} new`],
    ["Entries", `${result.entries_existing} existing · ${result.entries_new} new`],
    ["Annotation rows", formatNumber(result.annotation_rows)],
    ["Linkable molecules", formatNumber(result.linkable_molecules)],
    ["Unlinkable molecules", formatNumber(result.unlinkable_molecules)],
    ["In-file duplicates", formatNumber(result.in_file_duplicates)],
    ["Already in database", formatNumber(result.already_in_database)],
    ["Expected inserts", formatNumber(result.expected_inserts)],
    ["Skipped rows or values", formatNumber(result.rejected_rows)],
  ];
  return (
    <div className="package-builder__summary">
      <h4>{title}</h4>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {result.warnings.length ? (
        <ul className="package-builder__warnings">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
