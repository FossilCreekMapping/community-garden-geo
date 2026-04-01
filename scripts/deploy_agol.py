"""
Deploy the Woodhaven Gardens schema to ArcGIS Online.

Creates a hosted feature service directly from schemas/schema.json (no file
upload or arcpy required), then builds a Web Map and prints Field Maps links.

Requires the ``arcgis`` Python package (pip install arcgis).

Configuration via environment variables (or a .env file with python-dotenv):

    AGOL_URL       - Portal URL  (default: https://www.arcgis.com)
    AGOL_USERNAME  - ArcGIS Online username
    AGOL_PASSWORD  - ArcGIS Online password

Usage:
    python deploy_agol.py [options]

Options:
    --schema          Path to schema JSON (default: schemas/schema.json)
    --title           Feature service title
    --web-map-title   Web Map title
    --folder          AGOL content folder
    --tags            Comma-separated tags
    --share-org       Share items with the organization
    --share-public    Share items publicly
    --overwrite       Delete existing service and recreate
"""

import argparse
import json
import os
import re
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS
from arcgis.mapping import WebMap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(SCRIPT_DIR, os.pardir, "schemas", "schema.json")

DEFAULT_TITLE = "Woodhaven Gardens"
DEFAULT_WM_TITLE = "Woodhaven Gardens - Operations"
DEFAULT_TAGS = (
    "community garden,Econautics,Living Laboratory,Woodhaven,urban agriculture"
)
DEFAULT_BASEMAP = "arcgis-imagery-standard"
SERVICE_DESCRIPTION = (
    "Hosted feature layers for the Woodhaven Gardens Living Laboratory "
    "(Econautics). Contains garden beds, management zones, trails, "
    "amenities, plants, property boundaries, and related data."
)

ESRI_FIELD_TYPES = {
    "TEXT": "esriFieldTypeString",
    "SHORT": "esriFieldTypeSmallInteger",
    "LONG": "esriFieldTypeInteger",
    "DOUBLE": "esriFieldTypeDouble",
    "FLOAT": "esriFieldTypeSingle",
    "DATE": "esriFieldTypeDate",
}

ESRI_GEOMETRY_TYPES = {
    "POLYGON": "esriGeometryPolygon",
    "POLYLINE": "esriGeometryPolyline",
    "POINT": "esriGeometryPoint",
}

CARDINALITY_MAP = {
    "ONE_TO_MANY": "esriRelCardinalityOneToMany",
    "ONE_TO_ONE": "esriRelCardinalityOneToOne",
    "MANY_TO_MANY": "esriRelCardinalityManyToMany",
}


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def connect(url, username, password):
    print(f"Connecting to {url} as {username}...")
    gis = GIS(url, username, password)
    print(f"  Authenticated as: {gis.properties.user.username}")
    return gis


# -- Esri REST definition builders -------------------------------------------

def _build_domain(dom_name, dom_def):
    return {
        "type": "codedValue",
        "name": dom_name,
        "codedValues": [
            {"code": code, "name": label}
            for code, label in dom_def["values"].items()
        ],
    }


def _build_field(fld, domains):
    field_def = {
        "name": fld["name"],
        "type": ESRI_FIELD_TYPES[fld["type"]],
        "alias": fld.get("alias", fld["name"]),
        "nullable": True,
        "editable": True,
    }
    if fld["type"] == "TEXT":
        field_def["length"] = fld.get("length", 256)
    if "domain" in fld and fld["domain"] in domains:
        field_def["domain"] = _build_domain(fld["domain"], domains[fld["domain"]])
    return field_def


def _system_fields():
    return [
        {
            "name": "OBJECTID",
            "type": "esriFieldTypeOID",
            "alias": "OBJECTID",
            "nullable": False,
            "editable": False,
        },
        {
            "name": "GlobalID",
            "type": "esriFieldTypeGlobalID",
            "alias": "GlobalID",
            "length": 38,
            "nullable": False,
            "editable": False,
        },
    ]


def _build_layer_def(layer_id, fc_def, domains, wkid):
    fields = _system_fields()
    for fld in fc_def["fields"]:
        fields.append(_build_field(fld, domains))

    return {
        "id": layer_id,
        "name": fc_def["name"],
        "type": "Feature Layer",
        "geometryType": ESRI_GEOMETRY_TYPES[fc_def["geometry_type"]],
        "hasZ": fc_def.get("has_z", False),
        "hasM": fc_def.get("has_m", False),
        "objectIdField": "OBJECTID",
        "globalIdField": "GlobalID",
        "hasAttachments": False,
        "capabilities": "Create,Delete,Query,Update,Editing",
        "extent": {
            "xmin": -20037508.34,
            "ymin": -20037508.34,
            "xmax": 20037508.34,
            "ymax": 20037508.34,
            "spatialReference": {"wkid": wkid},
        },
        "fields": fields,
    }


def _build_table_def(table_id, tbl_def, domains):
    fields = _system_fields()
    for fld in tbl_def["fields"]:
        fields.append(_build_field(fld, domains))

    return {
        "id": table_id,
        "name": tbl_def["name"],
        "type": "Table",
        "objectIdField": "OBJECTID",
        "globalIdField": "GlobalID",
        "hasAttachments": False,
        "capabilities": "Create,Delete,Query,Update,Editing",
        "fields": fields,
    }


# -- Service creation --------------------------------------------------------

def _find_existing(gis, title):
    hits = gis.content.search(
        query=(
            f'title:"{title}" type:"Feature Service"'
            f" owner:{gis.users.me.username}"
        ),
        max_items=5,
    )
    return next((h for h in hits if h.title == title), None)


def create_feature_service(gis, schema, title, tags, folder, overwrite):
    existing = _find_existing(gis, title)
    if existing:
        if overwrite:
            print(f"  Deleting existing service: {existing.id}")
            existing.delete()
        else:
            sys.exit(
                f'ERROR: Service "{title}" already exists ({existing.id}). '
                "Use --overwrite to replace it."
            )

    service_name = re.sub(r"[^a-zA-Z0-9_]", "_", title)
    wkid = schema.get("spatial_reference_wkid", 3857)

    print(f"Creating feature service: {title}")
    item = gis.content.create_service(
        name=service_name,
        create_params={
            "name": service_name,
            "hasStaticData": False,
            "maxRecordCount": 2000,
            "supportedQueryFormats": "JSON",
            "capabilities": "Create,Delete,Query,Update,Editing,Sync",
            "spatialReference": {"wkid": wkid},
            "initialExtent": {
                "xmin": -10850000, "ymin": 3845000,
                "xmax": -10815000, "ymax": 3880000,
                "spatialReference": {"wkid": wkid},
            },
            "allowGeometryUpdates": True,
            "units": "esriMeters",
            "xssPreventionInfo": {
                "xssPreventionEnabled": True,
                "xssPreventionRule": "InputOnly",
                "xssInputRule": "rejectInvalid",
            },
        },
        service_type="featureService",
        folder=folder,
    )

    item.update(item_properties={
        "title": title,
        "tags": tags,
        "description": SERVICE_DESCRIPTION,
    })
    print(f"  Service item: {item.id}")
    return item


def add_layers_and_tables(item, schema):
    """Add all layers and tables from the schema definition."""
    domains = schema.get("domains", {})
    wkid = schema.get("spatial_reference_wkid", 3857)
    name_to_id = {}

    layers = []
    for i, fc_def in enumerate(schema["feature_classes"]):
        layers.append(_build_layer_def(i, fc_def, domains, wkid))
        name_to_id[fc_def["name"]] = i

    tables = []
    table_offset = len(layers)
    for i, tbl_def in enumerate(schema["tables"]):
        tid = table_offset + i
        tables.append(_build_table_def(tid, tbl_def, domains))
        name_to_id[tbl_def["name"]] = tid

    flc = FeatureLayerCollection.fromitem(item)

    definition = {}
    if layers:
        definition["layers"] = layers
    if tables:
        definition["tables"] = tables

    print(f"  Adding {len(layers)} layers and {len(tables)} tables...")
    flc.manager.add_to_definition(json.dumps(definition))

    return name_to_id


def add_relationships(item, schema, name_to_id):
    """Wire up relationship classes between layers/tables."""
    rels = schema.get("relationships", [])
    if not rels:
        return

    flc = FeatureLayerCollection.fromitem(item)

    all_endpoints = {
        lyr.properties.id: lyr for lyr in flc.layers
    }
    for tbl in flc.tables:
        all_endpoints[tbl.properties.id] = tbl

    for rel in rels:
        origin_id = name_to_id[rel["origin_table"]]
        dest_id = name_to_id[rel["destination_table"]]
        cardinality = CARDINALITY_MAP.get(
            rel.get("cardinality", "ONE_TO_MANY"),
            "esriRelCardinalityOneToMany",
        )
        is_composite = rel.get("relationship_type") == "COMPOSITE"

        origin_endpoint = all_endpoints[origin_id]
        origin_endpoint.manager.update_definition({
            "relationships": [{
                "id": 0,
                "name": rel["name"],
                "relatedTableId": dest_id,
                "role": "esriRelRoleOrigin",
                "cardinality": cardinality,
                "keyField": rel["origin_primary_key"],
                "composite": is_composite,
            }],
        })

        dest_endpoint = all_endpoints[dest_id]
        dest_endpoint.manager.update_definition({
            "relationships": [{
                "id": 0,
                "name": rel["name"],
                "relatedTableId": origin_id,
                "role": "esriRelRoleDestination",
                "cardinality": cardinality,
                "keyField": rel["origin_foreign_key"],
                "composite": is_composite,
            }],
        })
        print(f"  Relationship: {rel['name']}")


def enable_editor_tracking(item):
    flc = FeatureLayerCollection.fromitem(item)
    flc.manager.update_definition({
        "editorTrackingInfo": {
            "enableEditorTracking": True,
            "enableOwnershipAccessControl": False,
            "allowOthersToQuery": True,
            "allowOthersToUpdate": True,
            "allowOthersToDelete": True,
        },
    })
    print("  Editor tracking enabled")


# -- Web Map ------------------------------------------------------------------

def create_web_map(gis, fs_item, title, tags, folder):
    print("Creating Web Map...")
    wm = WebMap()
    wm.basemap = DEFAULT_BASEMAP

    flc = FeatureLayerCollection.fromitem(fs_item)
    for lyr in flc.layers:
        wm.add_layer(lyr)
    for tbl in flc.tables:
        wm.add_layer(tbl)

    wm_item = wm.save(
        item_properties={
            "title": title,
            "tags": tags,
            "snippet": (
                "Operations map for the Woodhaven Gardens Living Laboratory. "
                "Includes garden beds, zones, trails, plants, amenities, and "
                "property features."
            ),
        },
        folder=folder,
    )
    print(f"  Web Map item: {wm_item.id}")
    return wm_item


# -- Sharing & summary -------------------------------------------------------

def share_items(items, org, public):
    for item in items:
        item.share(org=org, everyone=public)
        vis = []
        if org:
            vis.append("org")
        if public:
            vis.append("public")
        print(f"  Shared {item.title}: {', '.join(vis) or 'private'}")


def print_summary(gis, fs_item, wm_item):
    portal = gis.url.rstrip("/")
    print("\n" + "=" * 60)
    print("DEPLOYMENT SUMMARY")
    print("=" * 60)
    print(f"Feature Service : {fs_item.title}")
    print(f"  Item ID       : {fs_item.id}")
    print(f"  Item page     : {portal}/home/item.html?id={fs_item.id}")
    print(f"Web Map         : {wm_item.title}")
    print(f"  Item ID       : {wm_item.id}")
    print(f"  Item page     : {portal}/home/item.html?id={wm_item.id}")
    print(f"  Map Viewer    : {portal}/apps/mapviewer/index.html?webmap={wm_item.id}")
    print(f"Field Maps link : arcgis-fieldmaps://?itemID={wm_item.id}")
    print("=" * 60)


# -- CLI ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Deploy Woodhaven Gardens schema to ArcGIS Online"
    )
    parser.add_argument(
        "--schema", default=DEFAULT_SCHEMA,
        help="Path to schema JSON (default: schemas/schema.json)",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--web-map-title", default=DEFAULT_WM_TITLE)
    parser.add_argument("--tags", default=DEFAULT_TAGS)
    parser.add_argument(
        "--folder", default=None,
        help="AGOL content folder (created if needed)",
    )
    parser.add_argument("--share-org", action="store_true")
    parser.add_argument("--share-public", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    url = os.environ.get("AGOL_URL", "https://www.arcgis.com")
    username = os.environ.get("AGOL_USERNAME")
    password = os.environ.get("AGOL_PASSWORD")
    if not username or not password:
        sys.exit(
            "ERROR: Set AGOL_USERNAME and AGOL_PASSWORD environment variables "
            "(or place them in a .env file)."
        )

    schema = load_schema(args.schema)
    gis = connect(url, username, password)

    fs_item = create_feature_service(
        gis, schema, args.title, args.tags, args.folder, args.overwrite,
    )

    name_to_id = add_layers_and_tables(fs_item, schema)
    add_relationships(fs_item, schema, name_to_id)
    enable_editor_tracking(fs_item)

    wm_item = create_web_map(
        gis, fs_item, args.web_map_title, args.tags, args.folder,
    )

    if args.share_org or args.share_public:
        share_items([fs_item, wm_item], args.share_org, args.share_public)

    print_summary(gis, fs_item, wm_item)


if __name__ == "__main__":
    main()
