import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { apiClient, ApiError, queryKeys } from "../../api";
import type { EntryIndexEntry, EntryResultFilterInput } from "../../api";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime, formatNumber } from "../../lib/format";

const PAGE_SIZE = 20;

function triggerExportDownload(url: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function message(error: Error | null) {
  return error instanceof ApiError
    ? error.message
    : "An unexpected error occurred while reading molecules.";
}

export function MoleculesPage() {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [editingPage, setEditingPage] = useState(false);
  const [pageDraft, setPageDraft] = useState("1");
  const [entryId, setEntryId] = useState<number | null>(null);
  const [hasResults, setHasResults] = useState(false);
  const stats = useQuery({
    queryKey: queryKeys.stats(),
    queryFn: ({ signal }) => apiClient.stats({ signal }),
  });
  const entriesIndex = useQuery({
    queryKey: queryKeys.entries.index(),
    queryFn: ({ signal }) => apiClient.entriesIndex({ signal }),
  });
  const entryFilter: EntryResultFilterInput | null =
    entryId === null ? null : { entryId, hasResults };
  const molecules = useQuery({
    queryKey: queryKeys.molecules.list(query, PAGE_SIZE, offset, entryFilter),
    queryFn: ({ signal }) =>
      apiClient.molecules({ query, limit: PAGE_SIZE, offset, entryFilter }, { signal }),
  });

  const entriesByAttribute = useMemo(() => {
    const groups = new Map<string, EntryIndexEntry[]>();
    for (const entry of entriesIndex.data ?? []) {
      const list = groups.get(entry.attribute_name) ?? [];
      list.push(entry);
      groups.set(entry.attribute_name, list);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [entriesIndex.data]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setQuery(draft.trim() || null);
    setOffset(0);
  }

  function clear() {
    setDraft("");
    setQuery(null);
    setOffset(0);
  }

  function selectEntry(value: string) {
    setEntryId(value === "" ? null : Number.parseInt(value, 10));
    setOffset(0);
  }

  function setPresence(next: boolean) {
    setHasResults(next);
    setOffset(0);
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalCount = molecules.data?.total ?? stats.data?.molecules ?? PAGE_SIZE;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const exportCount = molecules.data?.total;

  function goToPage() {
    const requested = Number.parseInt(pageDraft, 10);
    if (!Number.isFinite(requested)) return;
    const nextPage = Math.min(Math.max(1, requested), totalPages);
    setOffset((nextPage - 1) * PAGE_SIZE);
    setPageDraft(String(nextPage));
    setEditingPage(false);
  }

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportJob = useMutation({
    mutationFn: async () => {
      const job = await apiClient.smilesExport(entryFilter);
      const fileName = job.result?.file_name;
      if (typeof fileName !== "string" || !fileName) {
        throw new ApiError({
          kind: "response",
          message: "The export job completed without an archive file.",
        });
      }
      return job.job_id;
    },
    onSuccess: (jobId) => {
      setExportError(null);
      triggerExportDownload(apiClient.exportDownloadUrl(jobId));
    },
    onError: (error: Error) => {
      setExportError(error.message || "The export could not be completed.");
    },
    onSettled: () => setExporting(false),
  });

  return (
    <div className="molecules-page">
      <section aria-labelledby="molecule-search-title">
        <div className="section-heading">
          <div>
            <h2 id="molecule-search-title">Search</h2>
          </div>
        </div>
        <div className="molecule-search">
          <form onSubmit={submit}>
            <label>
              <span className="sr-only">Lab ID or SMILES</span>
              <input
                placeholder="e.g. MLD-0001 or CCO"
                type="search"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
            <button className="button button--inline" type="submit">
              Search
            </button>
            {query ? (
              <button className="button button--ghost button--inline" type="button" onClick={clear}>
                Clear
              </button>
            ) : null}
          </form>
        </div>
      </section>

      <div className="molecule-filter">
        <label className="molecule-filter__field">
          <span className="sr-only">Entry</span>
          <select
            value={entryId ?? ""}
            onChange={(event) => selectEntry(event.target.value)}
          >
            <option value="">Any entry (no result filter)</option>
            {entriesByAttribute.map(([attributeName, entries]) => (
              <optgroup key={attributeName} label={attributeName}>
                {entries.map((entry) => (
                  <option key={entry.entry_id} value={entry.entry_id}>
                    {entry.entry_key}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="molecule-filter__presence" role="group" aria-label="Result presence">
          <button
            aria-pressed={entryFilter !== null && !entryFilter.hasResults}
            disabled={entryFilter === null}
            type="button"
            onClick={() => setPresence(false)}
          >
            Missing results
          </button>
          <button
            aria-pressed={entryFilter !== null && entryFilter.hasResults}
            disabled={entryFilter === null}
            type="button"
            onClick={() => setPresence(true)}
          >
            Has results
          </button>
        </div>
        {entryFilter !== null ? (
          <button
            className="button button--ghost button--inline"
            type="button"
            onClick={() => selectEntry("")}
          >
            Clear entry filter
          </button>
        ) : null}
      </div>

      <section className="panel molecule-results" aria-label="Molecule records">
        <div className="panel__heading">
          <div className="molecule-export">
            <button
              className="button button--inline"
              disabled={exporting}
              onClick={() => {
                setExporting(true);
                setExportError(null);
                exportJob.mutate();
              }}
              type="button"
            >
              {exporting ? "Exporting…" : exportCount !== undefined ? `Export (${formatNumber(exportCount)})` : "Export"}
            </button>
            {exportError ? (
              <span className="molecule-export__error" role="alert">
                {exportError}
              </span>
            ) : null}
          </div>
          <span className="section-heading__meta">
            Page{" "}
            {editingPage ? (
              <input
                aria-label="Page number"
                className="page-jump-input"
                min={1}
                max={totalPages}
                type="text"
                inputMode="numeric"
                value={pageDraft}
                onChange={(event) => setPageDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") goToPage();
                  if (event.key === "Escape") setEditingPage(false);
                }}
                onBlur={goToPage}
                autoFocus
              />
            ) : (
              <button
                className="page-jump-button"
                type="button"
                aria-label={`Current page ${page}`}
                onClick={() => {
                  setPageDraft(String(page));
                  setEditingPage(true);
                }}
              >
                {page}
              </button>
            )}{" "}
            / {totalPages}
          </span>
        </div>

        {molecules.isPending ? <LoadingState title="Loading molecule records" /> : null}
        {molecules.error ? (
          <ErrorState
            title="Failed to load molecules"
            description={message(molecules.error)}
            onRetry={() => molecules.refetch()}
          />
        ) : null}
        {molecules.data && !molecules.data.items.length ? (
          <EmptyState
            title={query || entryFilter ? "No matching molecules" : "Molecule registry is empty"}
            description={
              query
                ? "Try another Lab ID or SMILES."
                : entryFilter
                  ? "Try another entry filter."
                  : "Import a molecules file to add records."
            }
          />
        ) : null}
        {molecules.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="molecule-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Lab ID</th>
                    <th>Canonical SMILES</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {molecules.data.items.map((molecule) => (
                    <tr key={molecule.molecule_id}>
                      <td>#{molecule.molecule_id}</td>
                      <td>
                        <Link to={`/molecules/${molecule.molecule_id}`}>{molecule.lab_id}</Link>
                      </td>
                      <td>
                        <code className="smiles-cell">{molecule.canonical_smiles}</code>
                      </td>
                      <td>{formatDateTime(molecule.created_at, { locale: "en-US" })}</td>
                      <td>
                        <div className="table-actions">
                          <CopyButton compact label="SMILES" value={molecule.canonical_smiles} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav className="pagination" aria-label="Molecule pagination">
              <button
                className="button button--ghost button--inline"
                disabled={offset === 0}
                type="button"
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <span>Page {page}</span>
              <button
                className="button button--ghost button--inline"
                disabled={molecules.data.items.length < PAGE_SIZE}
                type="button"
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </nav>
          </>
        ) : null}
      </section>
    </div>
  );
}
