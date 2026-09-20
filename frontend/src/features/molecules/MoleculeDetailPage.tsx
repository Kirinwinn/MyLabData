import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { apiClient, ApiError, queryKeys } from "../../api";
import type {
  AttributesResponse,
  MoleculeAttributeAnnotationsResponse,
  MoleculeResponse,
} from "../../api";
import { ConditionsList } from "../../components/ConditionsList";
import { CopyButton } from "../../components/CopyButton";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatBoolean, formatDateTime, formatValueWithUnit } from "../../lib/format";
import { PropertyEditor } from "../properties/PropertyEditor";
import { MoleculeRenderer } from "./MoleculeRenderer";

function message(error: Error | null) {
  return error instanceof ApiError
    ? error.message
    : "An unexpected error occurred while reading the molecule.";
}

export function MoleculeDetailPage() {
  const navigate = useNavigate();
  const parameters = useParams();
  const [searchParameters] = useSearchParams();
  const moleculeId = Number(parameters.moleculeId);
  const validId = Number.isSafeInteger(moleculeId) && moleculeId > 0;
  const requestedAttributeId = Number(searchParameters.get("attribute"));
  const selectedAttributeId =
    Number.isSafeInteger(requestedAttributeId) && requestedAttributeId > 0
      ? requestedAttributeId
      : null;

  const molecule = useQuery({
    queryKey: queryKeys.molecules.detail(moleculeId),
    queryFn: ({ signal }) => apiClient.molecule(moleculeId, { signal }),
    enabled: validId,
  });
  const attributes = useQuery({
    queryKey: queryKeys.molecules.attributes(moleculeId),
    queryFn: ({ signal }) => apiClient.moleculeAttributes(moleculeId, { signal }),
    enabled: validId,
  });
  const annotations = useQuery({
    queryKey:
      selectedAttributeId === null
        ? queryKeys.molecules.annotations(moleculeId, 0)
        : queryKeys.molecules.annotations(moleculeId, selectedAttributeId),
    queryFn: ({ signal }) =>
      apiClient.moleculeAttributeAnnotations(moleculeId, selectedAttributeId!, { signal }),
    enabled: validId && selectedAttributeId !== null,
  });

  if (!validId) {
    return (
      <ErrorState title="Invalid molecule ID" description="Select a molecule from the registry." />
    );
  }
  if (molecule.isPending) return <LoadingState title="Loading molecule details" />;
  if (molecule.error) {
    return (
      <ErrorState
        title="Failed to load molecule details"
        description={message(molecule.error)}
        onRetry={() => molecule.refetch()}
      />
    );
  }
  if (!molecule.data) {
    return (
      <EmptyState title="No molecule data" description="The backend returned no molecule record." />
    );
  }

  const selectedAttribute = attributes.data?.find(
    (attribute) => attribute.attribute_id === selectedAttributeId,
  );

  function goBack() {
    const historyIndex = window.history.state?.idx;
    if (typeof historyIndex === "number" && historyIndex > 0) {
      navigate(-1);
      return;
    }
    navigate("/molecules", { replace: true });
  }

  return (
    <div className="molecule-detail-page">
      <button className="back-link" type="button" onClick={goBack}>
        ← Back
      </button>
      <MoleculeHero molecule={molecule.data} />

      <section className="annotation-section" aria-labelledby="annotations-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Linked observations</p>
            <h2 id="annotations-title">Annotations</h2>
          </div>
        </div>
        <AnnotationPanel
          annotations={annotations}
          attributes={attributes}
          moleculeId={molecule.data.molecule_id}
          selectedAttribute={selectedAttribute}
          selectedAttributeId={selectedAttributeId}
        />
      </section>
    </div>
  );
}

function MoleculeHero({ molecule }: { molecule: MoleculeResponse }) {
  return (
    <section className="molecule-hero" aria-labelledby="molecule-title">
      <MoleculeRenderer canonicalSmiles={molecule.canonical_smiles} moleculeId={molecule.molecule_id} />
      <div className="molecule-hero__content">
        <p className="section-kicker">Molecule #{molecule.molecule_id}</p>
        <h2 id="molecule-title">{molecule.lab_id}</h2>
        <div className="molecule-fields">
          <div>
            <span>Lab ID</span>
            <code>{molecule.lab_id}</code>
            <CopyButton compact label="Lab ID" value={molecule.lab_id} />
          </div>
          <div>
            <span>Canonical SMILES</span>
            <code>{molecule.canonical_smiles}</code>
            <CopyButton compact label="SMILES" value={molecule.canonical_smiles} />
          </div>
          <div>
            <span>Created</span>
            <strong>{formatDateTime(molecule.created_at, { locale: "en-US" })}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}

function AnnotationPanel({
  annotations,
  attributes,
  moleculeId,
  selectedAttribute,
  selectedAttributeId,
}: {
  annotations: UseQueryResult<MoleculeAttributeAnnotationsResponse, Error>;
  attributes: UseQueryResult<AttributesResponse, Error>;
  moleculeId: number;
  selectedAttribute: { attribute_id: number; unit: string | null; value_type: string } | undefined;
  selectedAttributeId: number | null;
}) {
  if (attributes.isPending) return <LoadingState title="Loading attributes" />;
  if (attributes.error) {
    return (
      <ErrorState
        title="Failed to load attributes"
        description={message(attributes.error)}
        onRetry={() => attributes.refetch()}
      />
    );
  }
  if (!attributes.data?.length) {
    return <EmptyState title="No attributes" description="This molecule has no annotations." />;
  }
  if (selectedAttributeId === null) {
    return <p className="annotation-selection-prompt">Select an attribute to view annotations.</p>;
  }
  if (!selectedAttribute) {
    return (
      <EmptyState
        title="Attribute unavailable"
        description="Select an attribute from the directory."
      />
    );
  }
  if (annotations.isPending) return <LoadingState title="Loading annotations" />;
  if (annotations.error) {
    return (
      <ErrorState
        title="Failed to load annotations"
        description={message(annotations.error)}
        onRetry={() => annotations.refetch()}
      />
    );
  }
  if (!annotations.data?.length) {
    return <EmptyState title="No annotations" description="This attribute has no records." />;
  }

  return (
    <div className="annotation-cards">
      {annotations.data.map((annotation) => (
        <AnnotationCard
          annotation={annotation}
          key={annotation.entry_id}
          moleculeId={moleculeId}
          unit={selectedAttribute.unit}
          valueType={selectedAttribute.value_type}
        />
      ))}
    </div>
  );
}

function AnnotationCard({
  annotation,
  moleculeId,
  unit,
  valueType,
}: {
  annotation: MoleculeAttributeAnnotationsResponse[number];
  moleculeId: number;
  unit: string | null;
  valueType: string;
}) {
  const value =
    typeof annotation.value === "number"
      ? formatValueWithUnit(annotation.value, unit)
      : typeof annotation.value === "boolean"
        ? formatBoolean(annotation.value)
        : annotation.value;
  const editable =
    annotation.annotation_kind === "property" &&
    annotation.is_mutable &&
    (valueType === "number" || valueType === "text" || valueType === "boolean");

  return (
    <details className="annotation-card">
      <summary>
        <strong>{value}</strong>
        <code className="annotation-card__summary-entry">{annotation.entry_key}</code>
        <span>{formatDateTime(annotation.updated_at, { locale: "en-US" })}</span>
      </summary>
      <div className="annotation-card__content">
        <div>
          <span>Entry key</span>
          <div className="identifier-line">
            <code>{annotation.entry_key}</code>
            <CopyButton compact label="Entry Key" value={annotation.entry_key} />
          </div>
        </div>
        <div>
          <span>Method</span>
          <p>
            {annotation.method_name}
            {annotation.method_version ? ` · ${annotation.method_version}` : ""}
          </p>
        </div>
        <div>
          <span>Conditions</span>
          <ConditionsList conditions={annotation.conditions} />
        </div>
        <div className="annotation-card__meta">
          <span>Description</span>
          <small className="annotation-card__description">
            {annotation.description ?? "No entry description"}
          </small>
          {editable ? (
            <PropertyEditor
              currentValue={annotation.value}
              entryId={annotation.entry_id}
              entryKey={annotation.entry_key}
              moleculeId={moleculeId}
              unit={unit}
              valueType={valueType}
            />
          ) : null}
        </div>
      </div>
    </details>
  );
}
