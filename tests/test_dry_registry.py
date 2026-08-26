from pathlib import Path
import tempfile
import unittest

from Database.Dry.Registry import DryRegistry, RegistryError


class DryRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = DryRegistry(
            db_path=self.root / "DryData" / "Registry" / "DryData.duckdb",
            dry_root=self.root / "DryData",
        )
        self.registry.initialize()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initialization_creates_workflow_and_empty_schema(self) -> None:
        for stage in ("Incoming", "Processed", "Failed"):
            for category in ("Molecules", "Traits", "Predictions", "Annotations"):
                self.assertTrue((self.root / "DryData" / stage / category).is_dir())

        counts = self.registry.status()["counts"]
        self.assertEqual(
            counts,
            {
                "Molecules": 0,
                "Attributes": 0,
                "Sources": 0,
                "Imports": 0,
                "AttributeDistributions": 0,
                "AttributeStats": 0,
            },
        )

    def test_source_attribute_and_cache_upserts(self) -> None:
        source_id = self.registry.register_source(
            "model.test", "Test Model", "derived"
        )
        self.assertEqual(
            source_id,
            self.registry.register_source("model.test", "Test Model v2", "derived"),
        )
        attribute_id = self.registry.register_attribute(
            "prediction.test.score",
            "Score",
            "prediction",
            "float",
            source_id=source_id,
        )
        self.assertGreater(attribute_id, 0)

        distribution_id = self.registry.cache_distribution(
            "prediction.test.score",
            "all",
            "revision-1",
            distribution_type="histogram",
            non_null_count=3,
            null_count=1,
            bin_edges=[0.0, 0.5, 1.0],
            bin_counts=[1, 2],
        )
        self.assertGreater(distribution_id, 0)
        distribution = self.registry.get_distribution(
            "prediction.test.score", "all", "revision-1"
        )
        self.assertIsNotNone(distribution)
        assert distribution is not None
        self.assertEqual(distribution["bin_counts"], [1, 2])
        self.assertEqual(
            distribution_id,
            self.registry.cache_distribution(
                "prediction.test.score",
                "all",
                "revision-1",
                distribution_type="histogram",
                non_null_count=4,
                null_count=0,
                bin_edges=[0.0, 1.0],
                bin_counts=[4],
            ),
        )
        updated_distribution = self.registry.get_distribution(
            "prediction.test.score", "all", "revision-1"
        )
        assert updated_distribution is not None
        self.assertEqual(updated_distribution["bin_counts"], [4])

        stat_id = self.registry.cache_stats(
            "prediction.test.score",
            "all",
            "revision-1",
            row_count=4,
            non_null_count=3,
            null_count=1,
            distinct_count=3,
            min_value=0.1,
            max_value=0.9,
            mean_value=0.5,
        )
        self.assertGreater(stat_id, 0)
        stats = self.registry.get_stats(
            "prediction.test.score", "all", "revision-1"
        )
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["row_count"], 4)
        self.assertEqual(stats["mean_value"], 0.5)
        self.assertEqual(
            stat_id,
            self.registry.cache_stats(
                "prediction.test.score",
                "all",
                "revision-1",
                row_count=5,
                non_null_count=5,
                null_count=0,
                mean_value=0.6,
            ),
        )
        updated_stats = self.registry.get_stats(
            "prediction.test.score", "all", "revision-1"
        )
        assert updated_stats is not None
        self.assertEqual(updated_stats["row_count"], 5)

    def test_molecule_import_deduplicates_and_audits(self) -> None:
        first = self.root / "first.csv"
        first.write_text(
            "SMILES,inchikey\n"
            "CCO,KEY1\n"
            "CCO,KEY1\n"
            "CCC,KEY2\n"
            ",\n"
            "C1CC1,KEY3\n",
            encoding="utf-8",
        )
        result = self.registry.import_molecules(
            first,
            source_key="external.test",
            source_name="External Test",
            source_type="external",
        )
        self.assertEqual(result["total_rows"], 5)
        self.assertEqual(result["accepted_rows"], 3)
        self.assertEqual(result["rejected_rows"], 1)
        self.assertEqual(result["duplicate_rows"], 1)

        second = self.root / "second.csv"
        second.write_text("SMILES,inchikey\nCCO,KEY1\nN,KEY4\n", encoding="utf-8")
        result = self.registry.import_molecules(
            second,
            source_key="external.test",
            source_name="External Test",
            source_type="external",
            calculate_checksum=False,
        )
        self.assertEqual(result["accepted_rows"], 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(self.registry.status()["counts"]["Molecules"], 4)

        molecules = self.registry.search_molecules("KEY4")
        self.assertEqual(len(molecules), 1)
        self.assertEqual(molecules[0]["canonical_smiles"], "N")
        self.assertRegex(molecules[0]["lab_id"], r"^L\d{8}$")
        self.assertEqual(len(self.registry.list_imports()), 2)

    def test_conflicting_molecule_identities_fail_atomically(self) -> None:
        conflicting = self.root / "conflicting.csv"
        conflicting.write_text(
            "SMILES,inchikey\nCCC,KEY1\nC1CC1,KEY1\n",
            encoding="utf-8",
        )

        with self.assertRaises(RegistryError):
            self.registry.import_molecules(
                conflicting,
                source_key="external.conflict",
                source_name="Conflicting Input",
                source_type="external",
                calculate_checksum=False,
            )

        self.assertEqual(self.registry.status()["counts"]["Molecules"], 0)
        self.assertEqual(self.registry.list_imports()[0]["status"], "failed")

    def test_invalid_input_is_recorded_as_failed(self) -> None:
        invalid = self.root / "invalid.csv"
        invalid.write_text("name\nnot-a-molecule-column\n", encoding="utf-8")

        with self.assertRaises(RegistryError):
            self.registry.import_molecules(
                invalid,
                source_key="external.invalid",
                source_name="Invalid Input",
                source_type="external",
            )

        imports = self.registry.list_imports()
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0]["status"], "failed")
        self.assertIn("SMILES column", imports[0]["error_message"])

    def test_attribute_file_registration_catalogs_columns(self) -> None:
        molecules = self.root / "molecules.csv"
        molecules.write_text("SMILES\nCCO\nCCC\n", encoding="utf-8")
        self.registry.import_molecules(
            molecules,
            source_key="external.demo",
            source_name="Demo Molecules",
            source_type="external",
            calculate_checksum=False,
        )
        predictions = self.root / "predictions.csv"
        predictions.write_text(
            "SMILES,score,label\nCCO,0.8,active\nCCC,0.2,inactive\n",
            encoding="utf-8",
        )
        result = self.registry.register_attribute_file(
            predictions,
            source_key="model.demo",
            source_name="Demo Model",
            source_type="derived",
            attribute_category="prediction",
            attribute_prefix="Demo",
            model_name="Demo",
        )

        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(
            result["attribute_keys"],
            ["prediction.Demo.score", "prediction.Demo.label"],
        )
        counts = self.registry.status()["counts"]
        self.assertEqual(counts["Attributes"], 2)
        self.assertEqual(counts["Imports"], 2)
        self.assertEqual(self.registry.list_imports()[0]["data_category"], "predictions")

    def test_attribute_file_requires_registered_identity_and_audits_failure(self) -> None:
        predictions = self.root / "orphan_predictions.csv"
        predictions.write_text("SMILES,score\nCCO,0.8\n", encoding="utf-8")

        with self.assertRaises(RegistryError):
            self.registry.register_attribute_file(
                predictions,
                source_key="model.orphan",
                source_name="Orphan Model",
                source_type="derived",
                attribute_category="prediction",
                attribute_prefix="Orphan",
                calculate_checksum=False,
            )

        self.assertEqual(self.registry.status()["counts"]["Attributes"], 0)
        self.assertEqual(self.registry.list_imports()[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
