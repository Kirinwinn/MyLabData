-- Preserve the complete result of every Molecules import preview.

-- DuckDB cannot add a constrained column with ALTER TABLE. Existing audit
-- records remain NULL; new Molecules imports always write all four values.
ALTER TABLE Imports ADD COLUMN valid_rows BIGINT;
ALTER TABLE Imports ADD COLUMN new_rows BIGINT;
ALTER TABLE Imports ADD COLUMN existing_rows BIGINT;
ALTER TABLE Imports ADD COLUMN duplicate_rows BIGINT;
