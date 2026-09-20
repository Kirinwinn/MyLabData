export type ApiErrorKind = "http" | "network" | "response" | "aborted";

export interface ValidationIssue {
  location: string;
  message: string;
  type?: string;
}

interface ApiErrorOptions {
  kind: ApiErrorKind;
  message: string;
  status?: number;
  detail?: unknown;
  validationIssues?: ValidationIssue[];
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly detail?: unknown;
  readonly validationIssues: ValidationIssue[];

  constructor(options: ApiErrorOptions) {
    super(options.message, { cause: options.cause });
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status;
    this.detail = options.detail;
    this.validationIssues = options.validationIssues ?? [];
  }

  get isRetryable() {
    return (
      this.kind === "network" ||
      this.status === 408 ||
      this.status === 429 ||
      (this.status !== undefined && this.status >= 500)
    );
  }
}

interface FastApiValidationItem {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function extractValidationIssues(detail: unknown): ValidationIssue[] {
  if (!Array.isArray(detail)) return [];

  return detail.flatMap((item) => {
    if (!isRecord(item)) return [];
    const candidate: FastApiValidationItem = item;
    if (typeof candidate.msg !== "string") return [];
    const location = Array.isArray(candidate.loc) ? candidate.loc.map(String).join(".") : "request";
    return [
      {
        location,
        message: candidate.msg,
        type: typeof candidate.type === "string" ? candidate.type : undefined,
      },
    ];
  });
}

function statusFallback(status: number, statusText: string) {
  return statusText ? `Request failed (${status} ${statusText})` : `Request failed (${status})`;
}

export function apiErrorFromResponse(response: Response, body: unknown) {
  const detail = isRecord(body) ? body.detail : undefined;
  const validationIssues = extractValidationIssues(detail);
  const message =
    typeof detail === "string"
      ? detail
      : validationIssues.length > 0
        ? validationIssues.map((issue) => `${issue.location}: ${issue.message}`).join("；")
        : statusFallback(response.status, response.statusText);

  return new ApiError({
    kind: "http",
    status: response.status,
    message,
    detail,
    validationIssues,
  });
}

export function apiErrorFromThrown(error: unknown) {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError({ kind: "aborted", message: "Request cancelled", cause: error });
  }
  if (error instanceof TypeError) {
    return new ApiError({
      kind: "network",
      message: "Unable to connect to the MyLabData backend. Check that the service is running.",
      cause: error,
    });
  }
  return new ApiError({
    kind: "response",
    message: "An unknown API error occurred.",
    cause: error,
  });
}
