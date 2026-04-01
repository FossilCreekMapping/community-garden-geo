"""
Create a GeoPackage (.gpkg) from the schema definition in schemas/schema.json.

Uses only the Python standard library (sqlite3).  No arcpy or ArcGIS Pro
required.  The resulting GeoPackage can be opened in QGIS, ArcGIS Pro, or
uploaded to ArcGIS Online.

Usage:
    python create_gdb.py [--output <folder>] [--name <name>] [--overwrite]

Defaults are read from the schema JSON (geodatabase_name, spatial_reference_wkid).
"""

import argparse
import json
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(SCRIPT_DIR, os.pardir, "schemas", "schema.json")

FIELD_TYPE_MAP = {
    "TEXT": "TEXT",
    "SHORT": "INTEGER",
    "LONG": "INTEGER",
    "DOUBLE": "REAL",
    "FLOAT": "REAL",
    "DATE": "TEXT",
}

GEOMETRY_TYPE_MAP = {
    "POLYGON": "POLYGON",
    "POLYLINE": "LINESTRING",
    "POINT": "POINT",
}

SRS_DEFINITIONS = {
    4326: (
        "WGS 84",
        "EPSG",
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,'
        '298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],'
        'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",'
        '0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]',
    ),
    3857: (
        "WGS 84 / Pseudo-Mercator",
        "EPSG",
        'PROJCS["WGS 84 / Pseudo-Mercator",GEOGCS["WGS 84",DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
        'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
        'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
        'AUTHORITY["EPSG","4326"]],PROJECTION["Mercator_1SP"],'
        'PARAMETER["central_meridian",0],PARAMETER["scale_factor",1],'
        'PARAMETER["false_easting",0],PARAMETER["false_northing",0],'
        'UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],'
        'AXIS["Northing",NORTH],AUTHORITY["EPSG","3857"]]',
    ),
}


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _init_gpkg(conn, srs_wkid):
    """Create required GeoPackage metadata tables and seed SRS rows."""
    conn.execute("PRAGMA application_id = 0x47504B47")
    conn.execute("PRAGMA user_version = 10300")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
            srs_name     TEXT    NOT NULL,
            srs_id       INTEGER NOT NULL PRIMARY KEY,
            organization TEXT    NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition   TEXT    NOT NULL,
            description  TEXT
        );
        CREATE TABLE IF NOT EXISTS gpkg_contents (
            table_name  TEXT NOT NULL PRIMARY KEY,
            data_type   TEXT NOT NULL,
            identifier  TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            min_x DOUBLE, min_y DOUBLE,
            max_x DOUBLE, max_y DOUBLE,
            srs_id INTEGER,
            CONSTRAINT fk_gc_r_srs_id
                FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );
        CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
            table_name         TEXT    NOT NULL,
            column_name        TEXT    NOT NULL,
            geometry_type_name TEXT    NOT NULL,
            srs_id             INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            CONSTRAINT pk_geom_cols
                PRIMARY KEY (table_name, column_name),
            CONSTRAINT fk_gc_tn
                FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
            CONSTRAINT fk_gc_srs
                FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        );
    """)

    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys VALUES"
        " ('Undefined Cartesian', -1, 'NONE', -1, 'undefined', NULL)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_spatial_ref_sys VALUES"
        " ('Undefined Geographic', 0, 'NONE', 0, 'undefined', NULL)"
    )

    for wkid, (srs_name, org, definition) in SRS_DEFINITIONS.items():
        conn.execute(
            "INSERT OR IGNORE INTO gpkg_spatial_ref_sys"
            " VALUES (?,?,?,?,?,NULL)",
            (srs_name, wkid, org, wkid, definition),
        )

    conn.commit()


def _create_feature_table(conn, fc_def, srs_wkid):
    name = fc_def["name"]
    geom_type = GEOMETRY_TYPE_MAP.get(
        fc_def["geometry_type"], fc_def["geometry_type"]
    )
    has_z = 1 if fc_def.get("has_z") else 0
    has_m = 1 if fc_def.get("has_m") else 0

    cols = ["fid INTEGER PRIMARY KEY AUTOINCREMENT", "geom BLOB"]
    for fld in fc_def["fields"]:
        col_type = FIELD_TYPE_MAP.get(fld["type"], "TEXT")
        cols.append(f'"{fld["name"]}" {col_type}')

    conn.execute(f'CREATE TABLE "{name}" ({", ".join(cols)})')

    conn.execute(
        "INSERT INTO gpkg_contents VALUES"
        " (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),NULL,NULL,NULL,NULL,?)",
        (name, "features", name, "", srs_wkid),
    )
    conn.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
        (name, "geom", geom_type, srs_wkid, has_z, has_m),
    )
    conn.commit()
    print(f"  Feature class: {name} ({geom_type}, {len(fc_def['fields'])} fields)")


def _create_attribute_table(conn, tbl_def):
    name = tbl_def["name"]
    cols = ["fid INTEGER PRIMARY KEY AUTOINCREMENT"]
    for fld in tbl_def["fields"]:
        col_type = FIELD_TYPE_MAP.get(fld["type"], "TEXT")
        cols.append(f'"{fld["name"]}" {col_type}')

    conn.execute(f'CREATE TABLE "{name}" ({", ".join(cols)})')

    conn.execute(
        "INSERT INTO gpkg_contents VALUES"
        " (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),NULL,NULL,NULL,NULL,NULL)",
        (name, "attributes", name, ""),
    )
    conn.commit()
    print(f"  Table: {name} ({len(tbl_def['fields'])} fields)")


def main():
    parser = argparse.ArgumentParser(
        description="Create a GeoPackage from schema.json"
    )
    parser.add_argument(
        "--schema", default=DEFAULT_SCHEMA,
        help="Path to schema JSON (default: schemas/schema.json)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output folder (default: output/ in repo root)",
    )
    parser.add_argument(
        "--name", default=None,
        help="Output file name (default: derived from schema JSON, .gpkg extension)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Delete existing file before creating",
    )
    args = parser.parse_args()

    schema = load_schema(args.schema)

    raw_name = args.name or schema.get("geodatabase_name", "WoodhavenGardens")
    base = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
    gpkg_name = f"{base}.gpkg"

    output_folder = args.output or os.path.join(SCRIPT_DIR, os.pardir, "output")
    output_folder = os.path.abspath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    gpkg_path = os.path.join(output_folder, gpkg_name)

    if os.path.exists(gpkg_path):
        if args.overwrite:
            print(f"Removing existing file: {gpkg_path}")
            os.remove(gpkg_path)
        else:
            sys.exit(
                f"ERROR: File already exists at {gpkg_path}. "
                "Use --overwrite to replace it."
            )

    wkid = schema.get("spatial_reference_wkid", 3857)

    print(f"Creating GeoPackage: {gpkg_path}")
    conn = sqlite3.connect(gpkg_path)
    try:
        _init_gpkg(conn, wkid)

        print("Creating feature classes...")
        for fc_def in schema.get("feature_classes", []):
            _create_feature_table(conn, fc_def, wkid)

        print("Creating tables...")
        for tbl_def in schema.get("tables", []):
            _create_attribute_table(conn, tbl_def)
    finally:
        conn.close()

    print(f"\nDone. GeoPackage ready at:\n  {gpkg_path}")
    print(
        "\nNote: Coded-value domains and relationship classes are applied\n"
        "during AGOL deployment (deploy_agol.py).  The GeoPackage contains\n"
        "the table schemas for local reference, QGIS, or manual AGOL upload."
    )


if __name__ == "__main__":
    main()
