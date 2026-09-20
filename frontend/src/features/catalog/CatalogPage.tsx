import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { apiClient, ApiError, queryKeys } from "../../api";
import type { AttributeStatsResponse, EntriesResponse } from "../../api";
import { ConditionsList } from "../../components/ConditionsList";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatNumber, formatValueWithUnit } from "../../lib/format";

function message(error: Error | null) {
  return error instanceof ApiError
    ? error.message
    : "An unexpected error occurred while reading the catalog.";
}

export function CatalogPage() {
  const [filter, setFilter] = useState("");
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [expandedEntryId, setExpandedEntryId] = useState<number | null>(null);
  const attributes = useQuery({
    queryKey: queryKeys.attributes.all(),
    queryFn: ({ signal }) => apiClient.attributes({ signal }),
  });
  const selectedId = chosenId ?? attributes.data?.[0]?.attribute_id ?? null;
  const selected = attributes.data?.find((item) => item.attribute_id === selectedId);
  const entries = useQuery({
    queryKey: queryKeys.attributes.entries(selectedId ?? 0),
    queryFn: ({ signal }) => apiClient.attributeEntries(selectedId as number, { signal }),
    enabled: selectedId !== null,
  });
  const statistics = useQuery({
    queryKey: queryKeys.attributes.stats(selectedId ?? 0),
    queryFn: ({ signal }) => apiClient.attributeStats(selectedId as number, { signal }),
    enabled: selectedId !== null,
  });

  const visibleAttributes = useMemo(() => {
    const needle = filter.trim().toLocaleLowerCase();
    if (!needle) return attributes.data ?? [];
    return (attributes.data ?? []).filter((item) =>
      `${item.attribute_name} ${item.attribute_key} ${item.value_type}`
        .toLocaleLowerCase()
        .includes(needle),
    );
  }, [attributes.data, filter]);

  if (attributes.isPending) return <LoadingState title="Loading the attribute catalog" />;
  if (attributes.error) {
    return (
      <ErrorState
        title="Failed to load catalog"
        description={message(attributes.error)}
        onRetry={() => attributes.refetch()}
      />
    );
  }
  if (!attributes.data?.length) {
    return (
      <EmptyState
        title="Catalog is empty"
        description="Import an Annotation Package containing Attributes and Entries and the catalog will form here."
      />
    );
  }

  return (
    <div className="catalog-page">
      <section className="catalog-sidebar" aria-label="Attributes">
        <div className="catalog-sidebar__panel">
          <div className="catalog-sidebar__toolbar">
            <span className="catalog-sidebar__count">{attributes.data.length}</span>
            <label className="filter-field">
              <span className="sr-only">Filter attributes</span>
              <input
                placeholder="Filter by name, key, or type"
                type="search"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
              />
            </label>
          </div>
          <div className="attribute-list">
            {visibleAttributes.map((attribute, index) => (
              <button
                aria-pressed={attribute.attribute_id === selectedId}
                className={`attribute-option${attribute.attribute_id === selectedId ? " attribute-option--active" : ""}`}
                key={attribute.attribute_id}
                type="button"
                onClick={() => {
                  setChosenId(attribute.attribute_id);
                  setExpandedEntryId(null);
                }}
              >
                <span className="type-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span>
                  <strong>{attribute.attribute_name}</strong>
                </span>
                <em>{attribute.value_type}</em>
              </button>
            ))}
            {!visibleAttributes.length ? (
              <EmptyState compact title="No matches" description="Try a different attribute filter." />
            ) : null}
          </div>
          <PreheatControl />
        </div>
      </section>

      {selected ? (
        <section className="catalog-detail" aria-labelledby="attribute-detail-title">
          <header className="catalog-detail__hero">
            <div>
              <h2 id="attribute-detail-title">{selected.attribute_name}</h2>
              <div className="identifier-line">
                <code>{selected.attribute_key}</code>
                <CopyButton compact label="Attribute Key" value={selected.attribute_key} />
              </div>
            </div>
          </header>

          <CatalogEntries
            entries={entries.data}
            entriesError={entries.error}
            entriesPending={entries.isPending}
            onRetry={() => entries.refetch()}
            statistics={statistics.data}
            statisticsError={statistics.error}
            unit={selected.unit}
            expandedEntryId={expandedEntryId}
            onToggleEntry={(entryId) =>
              setExpandedEntryId((current) => (current === entryId ? null : entryId))
            }
          />
        </section>
      ) : null}
    </div>
  );
}

interface CatalogEntriesProps {
  entries: EntriesResponse | undefined;
  statistics: AttributeStatsResponse | undefined;
  entriesPending: boolean;
  entriesError: Error | null;
  statisticsError: Error | null;
  unit: string | null;
  onRetry: () => unknown;
  expandedEntryId: number | null;
  onToggleEntry: (entryId: number) => void;
}

function PreheatControl() {
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const preheat = useMutation({
    mutationFn: ({ signal }: { signal: AbortSignal }) => apiClient.preheatStats({ signal }),
    onSuccess: (result) => {
      setError(null);
      const elapsed = Math.max(1, Math.round(result.elapsed_seconds));
      setNotice(
        result.failed
          ? `Statistics cached for ${result.preheated} of ${result.total} attributes (${result.failed} failed) in ${elapsed}s.`
          : `Statistics cached for all ${result.preheated} attributes in ${elapsed}s.`,
      );
    },
    onError: (cause: Error) => {
      setNotice(null);
      setError(
        cause instanceof ApiError ? cause.message : "Preheating the statistics cache failed.",
      );
    },
  });

  return (
    <div className="catalog-preheat">
      <button
        className="button catalog-preheat__button"
        disabled={preheat.isPending}
        type="button"
        onClick={() => preheat.mutate({ signal: new AbortController().signal })}
      >
        {preheat.isPending ? "Caching all statistics…" : "Cache all statistics"}
      </button>
      {notice ? (
        <p className="catalog-preheat__status" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="catalog-preheat__status catalog-preheat__status--error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function CatalogEntries({
  entries,
  statistics,
  entriesPending,
  entriesError,
  statisticsError,
  unit,
  onRetry,
  expandedEntryId,
  onToggleEntry,
}: CatalogEntriesProps) {
  if (entriesPending) return <LoadingState title="Loading entries" />;
  if (entriesError) {
    return (
      <ErrorState title="Failed to load entries" description={message(entriesError)} onRetry={onRetry} />
    );
  }
  if (!entries?.length) {
    return <EmptyState title="No entries" description="This attribute has no entries yet." />;
  }

  const statsByEntry = new Map(statistics?.map((item) => [item.entry_id, item]));

  return (
    <div className="entry-section">
      <div className="section-heading">
        <div>
          <h2>Entries</h2>
        </div>
        <span className="section-heading__meta">{entries.length} definitions</span>
      </div>
      {statisticsError ? (
        <p className="inline-warning">Statistics temporarily unavailable: {message(statisticsError)}</p>
      ) : null}
      <div className="entry-list">
        {entries.map((entry) => (
          <EntryCard
            entry={entry}
            key={entry.entry_id}
            stats={statsByEntry.get(entry.entry_id)}
            unit={unit}
            expanded={expandedEntryId === entry.entry_id}
            onToggle={() => onToggleEntry(entry.entry_id)}
          />
        ))}
      </div>
    </div>
  );
}

function EntryCard({
  entry,
  stats,
  unit,
  expanded,
  onToggle,
}: {
  entry: EntriesResponse[number];
  stats: AttributeStatsResponse[number] | undefined;
  unit: string | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <article className={`entry-card${expanded ? " entry-card--open" : ""}`}>
      <div className="entry-card__summary">
        <button
          aria-expanded={expanded}
          className="entry-card__toggle"
          type="button"
          onClick={onToggle}
        >
          <span className="entry-card__chevron" aria-hidden="true">
            {expanded ? "▾" : "▸"}
          </span>
          <span className="entry-card__id">#{entry.entry_id}</span>
          <code>{entry.entry_key}</code>
          <span className="entry-card__summary-method">{entry.method_name}</span>
          <span className="entry-card__summary-count">
            {stats ? `${formatNumber(stats.count)} values` : "…"}
          </span>
        </button>
        <CopyButton compact label="Entry Key" value={entry.entry_key} />
      </div>
      {expanded ? (
        <div className="entry-card__body">
          <div className="entry-card__body-header">
            <div className="entry-card__badges">
              <span className={`kind-badge kind-badge--${entry.annotation_kind}`}>
                {entry.annotation_kind}
              </span>
              <span>{entry.is_mutable ? "Mutable" : "Read-only"}</span>
            </div>
          </div>
          <div className="entry-card__grid">
            <div>
              <span>Method</span>
              <strong>{entry.method_name}</strong>
              <small>{entry.method_version ? `Version ${entry.method_version}` : "No version"}</small>
            </div>
            <div>
              <span>Mutability</span>
              <strong>{entry.is_mutable ? "Editable" : "Read-only"}</strong>
              <small>{entry.description ?? "No entry description"}</small>
            </div>
          </div>
          <div className="entry-card__conditions">
            <span>Condition</span>
            <ConditionsList conditions={entry.conditions} />
          </div>
          <EntryStatistics stats={stats} unit={unit} />
        </div>
      ) : null}
    </article>
  );
}

function EntryStatistics({
  stats,
  unit,
}: {
  stats: AttributeStatsResponse[number] | undefined;
  unit: string | null;
}) {
  if (!stats) return <div className="entry-stats entry-stats--empty">Statistics not returned yet</div>;

  const values =
    stats.value_type === "number"
      ? [
          ["Count", formatNumber(stats.count)],
          ["Min", formatValueWithUnit(stats.min, unit)],
          ["Max", formatValueWithUnit(stats.max, unit)],
          ["Mean", formatValueWithUnit(stats.mean, unit)],
          ["Median", formatValueWithUnit(stats.median, unit)],
        ]
      : stats.value_type === "boolean"
        ? [
            ["Count", formatNumber(stats.count)],
            ["True", formatNumber(stats.true_count)],
            ["False", formatNumber(stats.false_count)],
          ]
        : [
            ["Count", formatNumber(stats.count)],
            ["Distinct", formatNumber(stats.distinct_count)],
          ];

  return (
    <dl className="entry-stats">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
