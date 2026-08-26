-- Persistent coordination records for the in-process background job queue.

CREATE TABLE Jobs (
    job_id VARCHAR PRIMARY KEY,
    job_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    progress DOUBLE NOT NULL DEFAULT 0,
    message VARCHAR,
    payload_json JSON NOT NULL,
    result_json JSON,
    error_message VARCHAR,
    cancel_requested BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(job_id)) > 0),
    CHECK (length(trim(job_type)) > 0),
    CHECK (status IN (
        'queued', 'validating', 'waiting_confirmation', 'importing',
        'completed', 'failed', 'cancelled'
    )),
    CHECK (progress >= 0 AND progress <= 1),
    CHECK (finished_at IS NULL OR finished_at >= created_at),
    CHECK (started_at IS NULL OR started_at >= created_at)
);

