import { useMutation } from "@tanstack/react-query";
import { ApiError, apiClient, parseJobResult } from "../../api";
import { LoadingState, ErrorState } from "../../components/PageState";
import { transportLabel, useJob } from "../jobs/useJob";
import { isTerminalJob, jobStatusLabels } from "../jobs/jobStatus";
import { MoleculePreviewDetail } from "./MoleculePreviewDetail";
import { AnnotationPreviewDetail } from "./AnnotationPreviewDetail";
import { canConfirmImport, isTokenExpiredError } from "./previewHelpers";
import { formatDateTime } from "../../lib/format";
import { useState } from "react";

interface PreviewConfirmationProps {
  jobId: string;
  onCompleted(): void;
  onReset(): void;
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "An unexpected error occurred while reading the job status.";
}

export function PreviewConfirmation({ jobId, onCompleted, onReset }: PreviewConfirmationProps) {
  const job = useJob(jobId);
  const [importJobId, setImportJobId] = useState<string | null>(null);
  const importJob = useJob(importJobId);
  const [tokenError, setTokenError] = useState(false);

  const confirmImport = useMutation({
    mutationFn: () => {
      const record = job.data;
      if (!record) throw new Error("Job data not available");
      const parsed = parseJobResult(record);
      if (!parsed.ok || !parsed.data) throw new Error("Preview result not available");
      if (
        parsed.data.jobType !== "annotation_preview" &&
        parsed.data.jobType !== "molecule_preview"
      ) {
        throw new Error("Not a preview job");
      }
      const token =
        parsed.data.jobType === "annotation_preview" ? parsed.data.result.preview_token : null;
      const payload = token ? { preview_token: token } : null;
      const packageId = String(record.payload.package_id ?? "");
      return apiClient.importPackage(packageId, payload);
    },
    onSuccess: (response) => {
      setImportJobId(response.job_id);
    },
    onError: (error: unknown) => {
      if (isTokenExpiredError(error)) {
        setTokenError(true);
      }
    },
  });

  if (job.isPending) return <LoadingState title="Loading the preview job" />;
  if (job.error || !job.data) {
    return (
      <ErrorState
        title="Failed to load job status"
        description={errorMessage(job.error)}
        onRetry={() => job.refetch()}
      />
    );
  }

  const record = job.data;
  const parsed = parseJobResult(record);

  if (tokenError) {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__error">
          <p className="section-kicker">Token expired</p>
          <h3>The package has changed</h3>
          <p>The preview token has expired, possibly because the package file in the Incoming directory was modified. Please preview again.</p>
          <button className="button" type="button" onClick={onReset}>
            Choose another package
          </button>
        </div>
      </div>
    );
  }

  if (importJobId && importJob.data) {
    const importRecord = importJob.data;
    const importParsed = parseJobResult(importRecord);

    if (isTerminalJob(importRecord)) {
      return (
        <div className="preview-workflow">
          <div className="preview-workflow__done">
            <p className="section-kicker">Import finished</p>
            <h3>
              {importRecord.status === "completed"
                ? "Import completed"
                : `Import ${jobStatusLabels[importRecord.status]}`}
            </h3>
            {importRecord.status === "completed" && importParsed.ok && importParsed.data ? (
              <div className="preview-workflow__summary">
                {importParsed.data.jobType === "package_import" ? (
                  <p>
                    {importParsed.data.result.inserted_rows.toLocaleString("en-US")} rows written ·
                    Import ID #{importParsed.data.result.import_id}
                  </p>
                ) : null}
              </div>
            ) : null}
            {importRecord.status === "failed" && importRecord.error_message ? (
              <div className="preview-workflow__error">
                <p className="section-kicker">Import failed</p>
                <pre>{importRecord.error_message}</pre>
              </div>
            ) : null}
            <button className="button" type="button" onClick={onCompleted}>
              Back to Incoming
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="preview-workflow">
        <div className="preview-workflow__progress">
          <div>
            <span>{importRecord.message ?? "Writing to the database…"}</span>
            <strong>{Math.round(importRecord.progress * 100)}%</strong>
          </div>
          <div
            className="progress"
            aria-label={`Import progress ${Math.round(importRecord.progress * 100)}%`}
          >
            <span style={{ width: `${importRecord.progress * 100}%` }} />
          </div>
          <small>{transportLabel(importJob.transport, importRecord)}</small>
        </div>
      </div>
    );
  }

  if (
    record.status === "queued" ||
    record.status === "validating" ||
    record.status === "running"
  ) {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__progress">
          <div className="progress" aria-label={`Preview progress ${Math.round(record.progress * 100)}%`}>
            <span style={{ width: `${record.progress * 100}%` }} />
          </div>
        </div>
      </div>
    );
  }

  if (record.status === "importing") {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__progress">
          <div>
            <span>{record.message ?? "Writing to the database…"}</span>
            <strong>{Math.round(record.progress * 100)}%</strong>
          </div>
          <div className="progress" aria-label={`Import progress ${Math.round(record.progress * 100)}%`}>
            <span style={{ width: `${record.progress * 100}%` }} />
          </div>
          <small>{transportLabel(job.transport, record)}</small>
        </div>
      </div>
    );
  }

  if (record.status === "failed") {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__error">
          <p className="section-kicker">Preview failed</p>
          <h3>Preview failed</h3>
          {record.error_message ? <pre>{record.error_message}</pre> : null}
          <p>
            <small>Created: {formatDateTime(record.created_at)}</small>
          </p>
          <button className="button" type="button" onClick={onReset}>
            Choose another package
          </button>
        </div>
      </div>
    );
  }

  if (record.status === "cancelled") {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__error">
          <p className="section-kicker">Cancelled</p>
          <h3>Preview cancelled</h3>
          <button className="button" type="button" onClick={onReset}>
            Choose another package
          </button>
        </div>
      </div>
    );
  }

  if (record.status === "waiting_confirmation" && parsed.ok && parsed.data) {
    const showConfirmButton =
      parsed.data.jobType === "annotation_preview" ? canConfirmImport(parsed.data.result) : true;

    return (
      <div className="preview-workflow">
        <div className="preview-workflow__preview">
          {parsed.data.jobType === "molecule_preview" ? (
            <MoleculePreviewDetail preview={parsed.data.result} />
          ) : parsed.data.jobType === "annotation_preview" ? (
            <AnnotationPreviewDetail preview={parsed.data.result} />
          ) : null}

          <div className="preview-actions">
            {showConfirmButton ? (
              <button
                className="button"
                disabled={confirmImport.isPending}
                onClick={() => confirmImport.mutate()}
                type="button"
              >
                {confirmImport.isPending ? "Submitting import…" : "Confirm import"}
              </button>
            ) : (
              <p className="inline-warning">Conflicts or errors prevent confirming the import. Resolve them and preview again.</p>
            )}
            <button className="button button--ghost" type="button" onClick={onReset}>
              Cancel
            </button>
            {confirmImport.error ? (
              <p className="mutation-error">{errorMessage(confirmImport.error)}</p>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (record.status === "completed" && parsed.ok && parsed.data) {
    return (
      <div className="preview-workflow">
        <div className="preview-workflow__done">
          <p className="section-kicker">Preview completed</p>
          <h3>Preview completed</h3>
          <button className="button" type="button" onClick={onCompleted}>
            Back to Incoming
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-workflow">
      <div className="preview-workflow__error">
        <p className="section-kicker">Unknown state</p>
        <h3>Unknown state</h3>
        <p>Job status: {record.status}</p>
        {!parsed.ok ? <p className="inline-warning">{parsed.error.message}</p> : null}
        <button className="button" type="button" onClick={onReset}>
          Choose another package
        </button>
      </div>
    </div>
  );
}
