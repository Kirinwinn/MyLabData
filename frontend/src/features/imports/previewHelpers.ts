import { ApiError } from "../../api";
import type { components } from "../../api/generated/schema";

type AnnotationPackagePreview = components["schemas"]["AnnotationPackagePreview"];
type AttributePreviewItem = components["schemas"]["AttributePreviewItem"];
type EntryPreviewItem = components["schemas"]["EntryPreviewItem"];

export type PreviewStatus = "existing" | "new" | "conflict";

export const statusColor: Record<PreviewStatus, string> = {
  existing: "preview-row--existing",
  new: "preview-row--new",
  conflict: "preview-row--conflict",
};

export function itemStatus(item: AttributePreviewItem | EntryPreviewItem): PreviewStatus {
  return item.status;
}

export function hasConflicts(preview: AnnotationPackagePreview): boolean {
  return (
    preview.attributes.some((item) => item.status === "conflict") ||
    preview.entries.some((item) => item.status === "conflict")
  );
}

export function hasErrors(preview: AnnotationPackagePreview): boolean {
  return preview.errors.length > 0;
}

export function hasWarnings(preview: AnnotationPackagePreview): boolean {
  return preview.warnings.length > 0;
}

export function canConfirmImport(preview: AnnotationPackagePreview): boolean {
  return preview.can_import && Boolean(preview.preview_token) && !hasConflicts(preview);
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  const formatted =
    exponent === 0
      ? value.toString()
      : value.toLocaleString("zh-CN", {
          maximumFractionDigits: 1,
        });
  return `${formatted} ${units[exponent]}`;
}

export function isTokenExpiredError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status !== 422) return false;
  const detail = error.detail;
  if (typeof detail === "string") {
    return /preview token/i.test(detail);
  }
  return false;
}

export function countByStatus(
  items: (AttributePreviewItem | EntryPreviewItem)[],
): Record<PreviewStatus, number> {
  const counts: Record<PreviewStatus, number> = {
    existing: 0,
    new: 0,
    conflict: 0,
  };
  for (const item of items) {
    counts[item.status] += 1;
  }
  return counts;
}
