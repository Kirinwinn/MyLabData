import type { components } from "../../api/generated/schema";
import {
  countByStatus,
  hasConflicts,
  hasErrors,
  hasWarnings,
  statusColor,
} from "./previewHelpers";

type AnnotationPackagePreview = components["schemas"]["AnnotationPackagePreview"];

interface AnnotationPreviewDetailProps {
  preview: AnnotationPackagePreview;
}

export function AnnotationPreviewDetail({ preview }: AnnotationPreviewDetailProps) {
  const attrCounts = countByStatus(preview.attributes);
  const entryCounts = countByStatus(preview.entries);

  return (
    <div className="preview-detail">
      <div className="preview-stats">
        <div className="stat-card">
          <span className="stat-card__value">
            {preview.annotation_rows.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">Annotation rows</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">
            {preview.linkable_molecules.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">Linkable molecules</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">
            {preview.unlinkable_molecules.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">Unlinkable molecules</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">
            {preview.duplicate_annotations.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">In-file duplicates</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">
            {preview.existing_annotations.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">Already in database</span>
        </div>
        <div className="stat-card stat-card--accent">
          <span className="stat-card__value">
            {preview.expected_inserts.toLocaleString("en-US")}
          </span>
          <span className="stat-card__label">Expected inserts</span>
        </div>
      </div>

      <div className="preview-status-row">
        {hasConflicts(preview) ? (
          <span className="preview-status-badge preview-status-badge--conflict">Conflicts</span>
        ) : null}
        {hasWarnings(preview) ? (
          <span className="preview-status-badge preview-status-badge--warning">Warnings</span>
        ) : null}
        {hasErrors(preview) ? (
          <span className="preview-status-badge preview-status-badge--error">Errors</span>
        ) : null}
      </div>

      <section className="preview-table-section" aria-labelledby="preview-attributes-title">
        <h3 id="preview-attributes-title">
          Attributes
          <span className="count-chip">{preview.attributes.length}</span>
        </h3>
        <p className="preview-table-meta">
          Existing {attrCounts.existing} · New {attrCounts.new} · Conflicts {attrCounts.conflict}
        </p>
        {preview.attributes.length > 0 ? (
          <div className="table-wrap">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Key</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Unit</th>
                  <th>Conflicts</th>
                </tr>
              </thead>
              <tbody>
                {preview.attributes.map((item) => (
                  <tr className={statusColor[item.status]} key={item.definition.attribute_key}>
                    <td>
                      <span
                        className={`preview-dot preview-dot--${item.status}`}
                        aria-hidden="true"
                      />
                      {item.status}
                    </td>
                    <td>
                      <code>{item.definition.attribute_key}</code>
                    </td>
                    <td>{item.definition.attribute_name}</td>
                    <td>{item.definition.value_type}</td>
                    <td>{item.definition.unit ?? "-"}</td>
                    <td>
                      {(item.conflicts?.length ?? 0) > 0 ? (
                        <ul className="preview-conflicts">
                          {item.conflicts?.map((conflict, index) => (
                            <li key={index}>{conflict}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="conditions-empty">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="conditions-empty">No attributes</p>
        )}
      </section>

      <section className="preview-table-section" aria-labelledby="preview-entries-title">
        <h3 id="preview-entries-title">
          Entries
          <span className="count-chip">{preview.entries.length}</span>
        </h3>
        <p className="preview-table-meta">
          Existing {entryCounts.existing} · New {entryCounts.new} · Conflicts {entryCounts.conflict}
        </p>
        {preview.entries.length > 0 ? (
          <div className="table-wrap">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Entry Key</th>
                  <th>Kind</th>
                  <th>Method</th>
                  <th>Mutable</th>
                  <th>Conflicts</th>
                </tr>
              </thead>
              <tbody>
                {preview.entries.map((item) => (
                  <tr className={statusColor[item.status]} key={item.definition.entry_key}>
                    <td>
                      <span
                        className={`preview-dot preview-dot--${item.status}`}
                        aria-hidden="true"
                      />
                      {item.status}
                    </td>
                    <td>
                      <code>{item.definition.entry_key}</code>
                    </td>
                    <td>{item.definition.annotation_kind}</td>
                    <td>
                      {item.definition.method_name}
                      {item.definition.method_version ? ` v${item.definition.method_version}` : ""}
                    </td>
                    <td>{item.definition.is_mutable ? "Yes" : "No"}</td>
                    <td>
                      {(item.conflicts?.length ?? 0) > 0 ? (
                        <ul className="preview-conflicts">
                          {item.conflicts?.map((conflict, index) => (
                            <li key={index}>{conflict}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="conditions-empty">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="conditions-empty">No entries</p>
        )}
      </section>

      {hasWarnings(preview) ? (
        <section className="preview-warnings" aria-labelledby="preview-warnings-title">
          <h3 id="preview-warnings-title">Warnings</h3>
          <ul>
            {preview.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {hasErrors(preview) ? (
        <section className="preview-errors" aria-labelledby="preview-errors-title">
          <h3 id="preview-errors-title">Errors</h3>
          <ul>
            {preview.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
