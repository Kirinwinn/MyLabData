import type { components } from "../../api/generated/schema";

type MoleculeImportPreview = components["schemas"]["MoleculePackagePreview"];

interface MoleculePreviewDetailProps {
  preview: MoleculeImportPreview;
}

export function MoleculePreviewDetail({ preview }: MoleculePreviewDetailProps) {
  const stats = [
    { label: "Total rows", value: preview.total_rows },
    { label: "Valid molecules", value: preview.valid_rows },
    { label: "New molecules", value: preview.new_rows },
    { label: "Existing molecules", value: preview.existing_rows },
    { label: "In-file duplicates", value: preview.duplicate_rows },
    { label: "Invalid records", value: preview.invalid_rows },
  ];

  return (
    <div className="preview-detail">
      <div className="preview-detail__header">
        <div>
          <p className="section-kicker">Molecules preview</p>
          <h3>{preview.package_name}</h3>
        </div>
        <code className="preview-detail__hash">{preview.package_hash}</code>
      </div>

      <div className="preview-stats">
        {stats.map((stat) => (
          <div className="stat-card" key={stat.label}>
            <span className="stat-card__value">{stat.value.toLocaleString("en-US")}</span>
            <span className="stat-card__label">{stat.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
