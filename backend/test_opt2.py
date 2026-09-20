from pathlib import Path
import tempfile

tmp = Path(tempfile.mkdtemp())
db_path = str(tmp / 'DryData.duckdb')

import duckdb
con = duckdb.connect(db_path)
con.execute("""CREATE TABLE Molecules (molecule_id BIGINT, lab_id VARCHAR, canonical_smiles VARCHAR, channel VARCHAR, created_at TIMESTAMP)""")
con.execute("""CREATE TABLE Attributes (attribute_id BIGINT, attribute_key VARCHAR, attribute_name VARCHAR, value_type VARCHAR, unit VARCHAR, description VARCHAR)""")
con.execute("""CREATE TABLE Entries (entry_id BIGINT, attribute_id BIGINT, entry_key VARCHAR, annotation_kind VARCHAR, method_name VARCHAR, method_version VARCHAR, conditions_json JSON, is_mutable BOOLEAN, description VARCHAR)""")
con.execute("""CREATE TABLE Annotations (molecule_id BIGINT, entry_id BIGINT, value_number DOUBLE, value_text VARCHAR, value_boolean BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP)""")
con.execute("""INSERT INTO Attributes VALUES (1, 'abs', 'Abs', 'number', 'nm', NULL)""")
con.execute("""INSERT INTO Entries VALUES (1, 1, 'a', 'calc', 'T', '1', '{}', FALSE, NULL), (2, 1, 'b', 'calc', 'T', '1', '{}', FALSE, NULL)""")
con.execute("""INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, '2026-09-01'), (2, 'L2', 'CCC', NULL, '2026-09-02')""")
con.execute("""INSERT INTO Annotations VALUES (1, 1, 700, NULL, NULL, '2026-09-01', '2026-09-01')""")
con.execute("""INSERT INTO Annotations VALUES (2, 1, 800, NULL, NULL, '2026-09-02', '2026-09-02')""")
con.close()

from access.paths import DryDataPaths
from access.database import DryDataDatabase
from access.cache import CacheStore
from access.catalog import CatalogRepository, STATISTICS_NAMESPACE

paths = DryDataPaths(tmp)
repo = CatalogRepository(DryDataDatabase(paths), CacheStore(paths))

rows = repo.attribute_statistics(1)
print('Rows:', [(r.entry_id, r.count, r.min, r.max, r.mean, r.median, r.std) for r in rows])
cache_files = list((tmp/'Cache').glob(f'{STATISTICS_NAMESPACE}-*.json'))
print('Cache files:', cache_files)
print('SUCCESS: option 2 (GROUP BY) works with cache ①')