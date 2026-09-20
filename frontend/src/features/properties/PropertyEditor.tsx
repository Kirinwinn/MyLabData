import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { ApiError, apiClient, parseJobResult, queryKeys } from "../../api";
import type { PropertyUpdateRequest } from "../../api";
import { isTerminalJob, jobStatusLabels } from "../jobs/jobStatus";
import { transportLabel, useJob } from "../jobs/useJob";

export type PropertyValueType = "number" | "text" | "boolean";

interface PropertyEditorProps {
  moleculeId: number;
  entryId: number;
  entryKey: string;
  valueType: PropertyValueType;
  currentValue: number | string | boolean;
  unit?: string | null;
}

function displayError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "An unexpected error occurred while updating the property.";
}

function initialValue(valueType: PropertyValueType, value: number | string | boolean) {
  if (valueType === "boolean") return value === true ? "true" : "false";
  return String(value);
}

export function PropertyEditor({
  moleculeId,
  entryId,
  entryKey,
  valueType,
  currentValue,
  unit,
}: PropertyEditorProps) {
  const queryClient = useQueryClient();
  const valueId = useId();
  const sourceId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [value, setValue] = useState(() => initialValue(valueType, currentValue));
  const [source, setSource] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  const update = useMutation({
    mutationFn: (request: PropertyUpdateRequest) =>
      apiClient.updateProperty(moleculeId, entryId, request),
    onSuccess: (accepted) => {
      setJobId(accepted.job_id);
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() });
    },
  });

  function closeEditor() {
    setIsOpen(false);
    setValidationError(null);
    setValue(initialValue(valueType, currentValue));
    setSource("");
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedSource = source.trim();
    if (!normalizedSource) {
      setValidationError("Enter the source for this update.");
      return;
    }

    let request: PropertyUpdateRequest;
    if (valueType === "number") {
      const parsed = Number(value);
      if (!value.trim() || !Number.isFinite(parsed)) {
        setValidationError("Enter a valid number.");
        return;
      }
      request = { value_number: parsed, source: normalizedSource };
    } else if (valueType === "boolean") {
      request = { value_boolean: value === "true", source: normalizedSource };
    } else {
      request = { value_text: value, source: normalizedSource };
    }

    setValidationError(null);
    update.mutate(request);
  }

  const completed = job.data?.status === "completed";
  const failed = job.data?.status === "failed";
  const parsedResult = job.data ? parseJobResult(job.data) : null;

  return (
    <div className="property-editor">
      <button
        className="button button--ghost button--inline"
        onClick={() => setIsOpen(true)}
        type="button"
      >
        Edit property
      </button>

      {isOpen ? (
        <form className="property-editor__form" onSubmit={submit}>
          <p className="property-editor__entry">
            Update <code>{entryKey}</code>
          </p>
          <label htmlFor={valueId}>
            <span>New value{unit ? ` (${unit})` : ""}</span>
            {valueType === "boolean" ? (
              <select id={valueId} onChange={(event) => setValue(event.target.value)} value={value}>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            ) : valueType === "text" ? (
              <textarea
                id={valueId}
                onChange={(event) => setValue(event.target.value)}
                rows={3}
                value={value}
              />
            ) : (
              <input
                id={valueId}
                inputMode="decimal"
                onChange={(event) => setValue(event.target.value)}
                type="number"
                value={value}
              />
            )}
          </label>
          <label htmlFor={sourceId}>
            <span>Update source</span>
            <input
              id={sourceId}
              onChange={(event) => setSource(event.target.value)}
              placeholder="e.g. experiment review 2026-08-27"
              required
              value={source}
            />
          </label>
          {validationError ? (
            <p className="mutation-error" role="alert">
              {validationError}
            </p>
          ) : null}
          {update.error ? (
            <p className="mutation-error" role="alert">
              {displayError(update.error)}
            </p>
          ) : null}
          <div className="property-editor__actions">
            <button className="button button--inline" disabled={update.isPending} type="submit">
              {update.isPending ? "Submitting…" : "Submit update"}
            </button>
            <button
              className="button button--ghost button--inline"
              onClick={closeEditor}
              type="button"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {jobId && job.isPending ? (
        <p aria-live="polite" className="property-editor__status">
          Loading update job…
        </p>
      ) : null}
      {job.data && !isTerminalJob(job.data) ? (
        <p aria-live="polite" className="property-editor__status">
          {jobStatusLabels[job.data.status]} · {job.data.message ?? "Updating property"} ·{" "}
          {transportLabel(job.transport, job.data)}
        </p>
      ) : null}
      {completed ? (
        <p aria-live="polite" className="property-editor__success">
          Property updated.
          {parsedResult?.ok && parsedResult.data?.jobType === "property_update"
            ? `Source: ${parsedResult.data.result.source}`
            : ""}
        </p>
      ) : null}
      {failed ? (
        <pre aria-live="assertive" className="property-editor__failure">
          {job.data?.error_message ?? "Property update failed."}
        </pre>
      ) : null}
    </div>
  );
}
