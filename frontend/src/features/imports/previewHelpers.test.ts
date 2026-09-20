import { describe, expect, it } from "vitest";

import { ApiError } from "../../api";
import type { components } from "../../api/generated/schema";
import {
  canConfirmImport,
  countByStatus,
  formatBytes,
  hasConflicts,
  hasErrors,
  hasWarnings,
  isTokenExpiredError,
  statusColor,
} from "./previewHelpers";

type AnnotationPackagePreview = components["schemas"]["AnnotationPackagePreview"];
type AttributePreviewItem = components["schemas"]["AttributePreviewItem"];
type EntryPreviewItem = components["schemas"]["EntryPreviewItem"];

function makeAttribute(status: "existing" | "new" | "conflict" = "existing"): AttributePreviewItem {
  return {
    definition: {
      attribute_key: "attr_key",
      attribute_name: "Attribute Name",
      value_type: "number",
      unit: null,
      description: null,
    },
    status,
    conflicts: [],
  };
}

function makeEntry(status: "existing" | "new" | "conflict" = "existing"): EntryPreviewItem {
  return {
    definition: {
      entry_key: "entry_key",
      attribute_key: "attr_key",
      annotation_kind: "property",
      method_name: "method",
      method_version: null,
      conditions: {},
      source_key: null,
      is_mutable: false,
      description: null,
    },
    status,
    conflicts: [],
  };
}

function makePreview(overrides: Partial<AnnotationPackagePreview> = {}): AnnotationPackagePreview {
  return {
    package_name: "test-package",
    package_hash: "abc123",
    preview_token: "token-123",
    annotation_rows: 100,
    attributes: [],
    entries: [],
    linkable_molecules: 80,
    unlinkable_molecules: 5,
    duplicate_annotations: 3,
    existing_annotations: 10,
    expected_inserts: 70,
    warnings: [],
    errors: [],
    can_import: true,
    ...overrides,
  };
}

describe("statusColor", () => {
  it("maps each status to a CSS class", () => {
    expect(statusColor.existing).toBe("preview-row--existing");
    expect(statusColor.new).toBe("preview-row--new");
    expect(statusColor.conflict).toBe("preview-row--conflict");
  });
});

describe("hasConflicts", () => {
  it("returns false when no attributes or entries have conflict status", () => {
    const preview = makePreview({
      attributes: [makeAttribute("existing"), makeAttribute("new")],
      entries: [makeEntry("existing")],
    });
    expect(hasConflicts(preview)).toBe(false);
  });

  it("returns true when an attribute has conflict status", () => {
    const preview = makePreview({
      attributes: [makeAttribute("existing"), makeAttribute("conflict")],
      entries: [],
    });
    expect(hasConflicts(preview)).toBe(true);
  });

  it("returns true when an entry has conflict status", () => {
    const preview = makePreview({
      attributes: [],
      entries: [makeEntry("conflict")],
    });
    expect(hasConflicts(preview)).toBe(true);
  });
});

describe("hasErrors", () => {
  it("returns false when errors array is empty", () => {
    expect(hasErrors(makePreview({ errors: [] }))).toBe(false);
  });

  it("returns true when errors array has items", () => {
    expect(hasErrors(makePreview({ errors: ["something broke"] }))).toBe(true);
  });
});

describe("hasWarnings", () => {
  it("returns false when warnings array is empty", () => {
    expect(hasWarnings(makePreview({ warnings: [] }))).toBe(false);
  });

  it("returns true when warnings array has items", () => {
    expect(hasWarnings(makePreview({ warnings: ["heads up"] }))).toBe(true);
  });
});

describe("canConfirmImport", () => {
  it("returns true when can_import is true, token exists, and no conflicts", () => {
    const preview = makePreview({
      can_import: true,
      preview_token: "token-123",
      attributes: [makeAttribute("existing")],
      entries: [makeEntry("new")],
    });
    expect(canConfirmImport(preview)).toBe(true);
  });

  it("returns false when can_import is false", () => {
    const preview = makePreview({
      can_import: false,
      preview_token: "token-123",
    });
    expect(canConfirmImport(preview)).toBe(false);
  });

  it("returns false when preview_token is empty", () => {
    const preview = makePreview({
      can_import: true,
      preview_token: "",
    });
    expect(canConfirmImport(preview)).toBe(false);
  });

  it("returns false when there are conflicts even if can_import is true", () => {
    const preview = makePreview({
      can_import: true,
      preview_token: "token-123",
      attributes: [makeAttribute("conflict")],
    });
    expect(canConfirmImport(preview)).toBe(false);
  });
});

describe("formatBytes", () => {
  it("formats zero bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("formats bytes", () => {
    expect(formatBytes(500)).toBe("500 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(1048576)).toBe("1 MB");
  });

  it("formats gigabytes", () => {
    expect(formatBytes(1073741824)).toBe("1 GB");
  });
});

describe("isTokenExpiredError", () => {
  it("returns true for a 422 error with preview token detail", () => {
    const error = new ApiError({
      kind: "http",
      status: 422,
      message: "Preview token is invalid or the Annotation Package has changed",
      detail: "Preview token is invalid or the Annotation Package has changed",
    });
    expect(isTokenExpiredError(error)).toBe(true);
  });

  it("returns false for a 422 error without preview token in detail", () => {
    const error = new ApiError({
      kind: "http",
      status: 422,
      message: "some other validation error",
      detail: "some other validation error",
    });
    expect(isTokenExpiredError(error)).toBe(false);
  });

  it("returns false for a non-422 error", () => {
    const error = new ApiError({
      kind: "http",
      status: 500,
      message: "Internal server error",
      detail: "Internal server error",
    });
    expect(isTokenExpiredError(error)).toBe(false);
  });

  it("returns false for non-ApiError", () => {
    expect(isTokenExpiredError(new Error("random"))).toBe(false);
    expect(isTokenExpiredError(null)).toBe(false);
    expect(isTokenExpiredError(undefined)).toBe(false);
  });
});

describe("countByStatus", () => {
  it("counts items by their status", () => {
    const items = [
      makeAttribute("existing"),
      makeAttribute("new"),
      makeAttribute("new"),
      makeAttribute("conflict"),
    ];
    const counts = countByStatus(items);
    expect(counts.existing).toBe(1);
    expect(counts.new).toBe(2);
    expect(counts.conflict).toBe(1);
  });

  it("returns zeros for an empty array", () => {
    const counts = countByStatus([]);
    expect(counts.existing).toBe(0);
    expect(counts.new).toBe(0);
    expect(counts.conflict).toBe(0);
  });
});
