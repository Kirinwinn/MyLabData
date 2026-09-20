import type { ReactNode } from "react";

interface PageStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
}

export function LoadingState({ title = "Loading", compact = false }: Partial<PageStateProps>) {
  return (
    <div className={`page-state${compact ? " page-state--compact" : ""}`} role="status">
      <span className="page-state__spinner" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>Reading the latest data from the MyLabData backend.</p>
      </div>
    </div>
  );
}

export function EmptyState({ title, description, action, compact = false }: PageStateProps) {
  return (
    <div className={`page-state${compact ? " page-state--compact" : ""}`}>
      <span className="page-state__symbol" aria-hidden="true">
        ∅
      </span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {action}
      </div>
    </div>
  );
}

interface ErrorStateProps extends Omit<PageStateProps, "action"> {
  onRetry?: () => void;
}

export function ErrorState({ title, description, onRetry, compact = false }: ErrorStateProps) {
  return (
    <div
      className={`page-state page-state--error${compact ? " page-state--compact" : ""}`}
      role="alert"
    >
      <span className="page-state__symbol" aria-hidden="true">
        !
      </span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {onRetry ? (
          <button className="button button--quiet" type="button" onClick={onRetry}>
            Reload
          </button>
        ) : null}
      </div>
    </div>
  );
}
