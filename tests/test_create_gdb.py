"""
Tests for scripts/create_gdb.py using only the Python standard library.
Run with: python -m pytest tests/ -v
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import create_gdb  # noqa: E402

SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "schema.json")


def _open(path):
    return sqlite3.connect(path)


class TestLoadSchema(unittest.TestCase):
    def test_loads_real_schema(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        self.assertEqual(schema["schema_version"], "1.0.0")
        self.assertIn("feature_classes", schema)
        self.assertIn("tables", schema)
        self.assertIn("domains", schema)

    def test_feature_class_count(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        self.assertEqual(len(schema["feature_classes"]), 12)

    def test_table_count(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        self.assertEqual(len(schema["tables"]), 1)

    def test_domain_count(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        self.assertEqual(len(schema["domains"]), 19)


class TestGeoPackageCreation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gpkg = os.path.join(self.tmp.name, "test.gpkg")
        self.schema = create_gdb.load_schema(SCHEMA_PATH)
        conn = sqlite3.connect(self.gpkg)
        create_gdb._init_gpkg(conn, 3857)
        conn.close()
        self.conn = sqlite3.connect(self.gpkg)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _tables(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {r[0] for r in rows}

    def test_gpkg_metadata_tables_exist(self):
        tables = self._tables()
        self.assertIn("gpkg_spatial_ref_sys", tables)
        self.assertIn("gpkg_contents", tables)
        self.assertIn("gpkg_geometry_columns", tables)

    def test_srs_rows_seeded(self):
        rows = self.conn.execute(
            "SELECT srs_id FROM gpkg_spatial_ref_sys"
        ).fetchall()
        srs_ids = {r[0] for r in rows}
        self.assertIn(3857, srs_ids)
        self.assertIn(4326, srs_ids)
        self.assertIn(-1, srs_ids)
        self.assertIn(0, srs_ids)

    def test_create_feature_table(self):
        fc = {
            "name": "TestPolygon",
            "geometry_type": "POLYGON",
            "has_z": False,
            "has_m": False,
            "fields": [
                {"name": "label", "type": "TEXT", "length": 100, "alias": "Label"},
                {"name": "area",  "type": "DOUBLE", "alias": "Area"},
            ],
        }
        create_gdb._create_feature_table(self.conn, fc, 3857)

        tables = self._tables()
        self.assertIn("TestPolygon", tables)

        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(TestPolygon)")}
        self.assertIn("fid", cols)
        self.assertIn("geom", cols)
        self.assertIn("label", cols)
        self.assertIn("area", cols)

    def test_feature_table_registered_in_contents(self):
        fc = {
            "name": "TestLine",
            "geometry_type": "POLYLINE",
            "has_z": False,
            "has_m": False,
            "fields": [{"name": "name", "type": "TEXT", "length": 50, "alias": "Name"}],
        }
        create_gdb._create_feature_table(self.conn, fc, 3857)

        row = self.conn.execute(
            "SELECT data_type, srs_id FROM gpkg_contents WHERE table_name='TestLine'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "features")
        self.assertEqual(row[1], 3857)

    def test_geometry_columns_entry(self):
        fc = {
            "name": "TestPoint",
            "geometry_type": "POINT",
            "has_z": False,
            "has_m": False,
            "fields": [],
        }
        create_gdb._create_feature_table(self.conn, fc, 3857)

        row = self.conn.execute(
            "SELECT geometry_type_name FROM gpkg_geometry_columns"
            " WHERE table_name='TestPoint'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "POINT")

    def test_create_attribute_table(self):
        tbl = {
            "name": "TestTable",
            "fields": [
                {"name": "season", "type": "SHORT",  "alias": "Season"},
                {"name": "notes",  "type": "TEXT",   "length": 500, "alias": "Notes"},
            ],
        }
        create_gdb._create_attribute_table(self.conn, tbl)

        tables = self._tables()
        self.assertIn("TestTable", tables)

        row = self.conn.execute(
            "SELECT data_type FROM gpkg_contents WHERE table_name='TestTable'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "attributes")


class TestFullBuild(unittest.TestCase):
    """End-to-end: run main() against the real schema and verify output."""

    def test_full_gpkg_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            gpkg = os.path.join(tmp, "WoodhavenGardens.gpkg")
            sys.argv = ["create_gdb.py", "--output", tmp]
            create_gdb.main()

            self.assertTrue(os.path.isfile(gpkg))

            conn = sqlite3.connect(gpkg)
            try:
                user_tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                        " AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                expected = {
                    "PropertyBoundary", "ManagementZone", "GardenBed",
                    "PlannedArea", "GatheringArea", "BuildingFootprint",
                    "WaterBody", "Trail", "Plant", "Amenity",
                    "EquipmentPoint", "PropertyMarker", "CropSeason",
                }
                self.assertEqual(user_tables, expected)

                # GardenBed should have bed_id field
                cols = {
                    r[1]
                    for r in conn.execute("PRAGMA table_info(GardenBed)")
                }
                self.assertIn("bed_id", cols)
                self.assertIn("assignee", cols)
                self.assertIn("bed_role", cols)

                # CropSeason should have the relationship key
                crop_cols = {
                    r[1]
                    for r in conn.execute("PRAGMA table_info(CropSeason)")
                }
                self.assertIn("bed_id", crop_cols)
                self.assertIn("season_year", crop_cols)
            finally:
                conn.close()

    def test_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys.argv = ["create_gdb.py", "--output", tmp]
            create_gdb.main()

            sys.argv = ["create_gdb.py", "--output", tmp, "--overwrite"]
            create_gdb.main()

            gpkg = os.path.join(tmp, "WoodhavenGardens.gpkg")
            self.assertTrue(os.path.isfile(gpkg))

    def test_no_overwrite_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys.argv = ["create_gdb.py", "--output", tmp]
            create_gdb.main()

            sys.argv = ["create_gdb.py", "--output", tmp]
            with self.assertRaises(SystemExit):
                create_gdb.main()


class TestFieldTypeMap(unittest.TestCase):
    def test_all_schema_types_mapped(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        used_types = set()
        for fc in schema.get("feature_classes", []):
            for fld in fc["fields"]:
                used_types.add(fld["type"])
        for tbl in schema.get("tables", []):
            for fld in tbl["fields"]:
                used_types.add(fld["type"])

        for t in used_types:
            self.assertIn(
                t, create_gdb.FIELD_TYPE_MAP,
                f"Field type '{t}' used in schema but not in FIELD_TYPE_MAP",
            )

    def test_all_geometry_types_mapped(self):
        schema = create_gdb.load_schema(SCHEMA_PATH)
        used = {fc["geometry_type"] for fc in schema.get("feature_classes", [])}
        for g in used:
            self.assertIn(
                g, create_gdb.GEOMETRY_TYPE_MAP,
                f"Geometry type '{g}' used in schema but not in GEOMETRY_TYPE_MAP",
            )


if __name__ == "__main__":
    unittest.main()
