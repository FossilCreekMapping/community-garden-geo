# Woodhaven Gardens

GIS solution for managing the **Woodhaven Living Laboratory** community garden,
the first site for [Econautics](https://econautics.org/)—a Fort Worth-based
501(c)(3) dedicated to conservation, urban agriculture, and hands-on education.

The tooling reads a declarative JSON schema and either creates a local
**GeoPackage** for offline reference or deploys hosted feature layers directly
to **ArcGIS Online**, then assembles a Web Map ready for **Field Maps** mobile
use by garden coordinators, educators, and volunteers.

> For day-to-day map usage by non-technical staff, see
> **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

---

## Architecture

There are two independent paths — use either or both.

```
schemas/schema.json          (authoritative data model)
        │
        ├──► scripts/create_gdb.py     (Python stdlib — sqlite3)
        │            │
        │            ▼
        │    output/WoodhavenGardens.gpkg   (local / QGIS / manual upload)
        │
        └──► scripts/deploy_agol.py    (arcgis Python API — no arcpy)
                     │
                     ▼
             ArcGIS Online  ──►  Web Map  ──►  Field Maps
```

**Primary path** — `deploy_agol.py` creates the feature service, domains,
relationships, and Web Map directly on AGOL from the schema JSON. No
intermediate file upload is needed.

**Local path** — `create_gdb.py` produces a standards-compliant GeoPackage
(`.gpkg`) using only Python's built-in `sqlite3`. The file can be opened in
QGIS, ArcGIS Pro, or zipped and uploaded to AGOL manually.

---

## Prerequisites

| Requirement | Used by | Notes |
|---|---|---|
| **Python 3.9+** | All scripts | Standard library only for `create_gdb.py` and `zip_gdb.py`. |
| **arcgis** package | `deploy_agol.py` | `pip install -r requirements.txt` |
| **ArcGIS Online account** | `deploy_agol.py` | Creator or Publisher role to publish hosted feature layers and create Web Maps. |

No ArcGIS Pro or `arcpy` installation is required.

---

## Quick start

```bash
# 1. Clone the repo
git clone <repo-url> && cd woodhaven-gardens

# 2. Create a venv and install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Set credentials (NEVER commit these)
cp config/agol.env.example .env
#    edit .env with your AGOL_USERNAME / AGOL_PASSWORD

# 4. Deploy directly to ArcGIS Online
python scripts/deploy_agol.py --share-org

# (Optional) Create a local GeoPackage for offline reference
python scripts/create_gdb.py                # outputs output/WoodhavenGardens.gpkg
python scripts/create_gdb.py --overwrite    # recreate from scratch
```

---

## Script reference

| Script | When to run | Inputs | Outputs |
|---|---|---|---|
| `deploy_agol.py` | First deploy or republish | `schemas/schema.json`, env vars | Hosted feature service + Web Map on AGOL |
| `create_gdb.py` | Local reference or manual upload | `schemas/schema.json` | `output/WoodhavenGardens.gpkg` |
| `zip_gdb.py` | Manual AGOL upload via browser | `.gpkg` file | `.gpkg.zip` |

### Common options

- `deploy_agol.py --overwrite` — delete and recreate the existing AGOL service.
- `deploy_agol.py --share-public` — make items publicly visible.
- `deploy_agol.py --title "My Garden" --web-map-title "My Garden Ops"` — custom names.
- `create_gdb.py --overwrite` — delete and recreate the local GeoPackage.
- `create_gdb.py --output /some/path --name MyGarden` — custom location/name.

---

## Data model overview

The authoritative schema is [`schemas/schema.json`](schemas/schema.json). Below
is a summary of each layer.

### Polygon layers

| Layer | Purpose |
|---|---|
| **PropertyBoundary** | Legal or administrative property outline. |
| **ManagementZone** | Functional zones (vegetable, pollinator, outdoor classroom, compost, etc.). |
| **GardenBed** | Individual growing beds with assignee, role (production/education/demo), irrigation, and sun exposure. |
| **PlannedArea** | Future development footprints with priority and status tracking. |
| **GatheringArea** | Picnic, class, workshop, and event spaces. |
| **BuildingFootprint** | Sheds, greenhouses, pavilions, and other structures. |
| **WaterBody** | Ponds, rain gardens, detention basins. |

### Polyline

| Layer | Purpose |
|---|---|
| **Trail** | Walking paths with surface type, width, accessibility, and optional interpretive/general flag. |

### Point layers

| Layer | Purpose |
|---|---|
| **Plant** | Individual plants and notable trees (species, health, source, optional bed link). |
| **Amenity** | Benches, picnic tables, signs, learning stations, spigots, gates, etc. |
| **EquipmentPoint** | Movable or point-located equipment. |
| **PropertyMarker** | Survey pins, corners, wayfinding markers. |

### Non-spatial tables

| Table | Purpose |
|---|---|
| **CropSeason** | Seasonal crop records related many-to-one with GardenBed (crop, variety, yield, pest issues, program notes for education tie-ins). |

All coded-value domains and the `GardenBed <-> CropSeason` relationship class
are defined in the schema JSON. `deploy_agol.py` creates them on the hosted
service automatically; `create_gdb.py` creates the table structures locally
(domains are applied on AGOL).

---

## Publishing and schema changes

**Additive changes** (new field, new domain value): Update `schema.json` and
run `deploy_agol.py --overwrite`.

**Breaking changes** (renamed/removed fields, changed types): Publish as a new
service with a versioned title (e.g. `--title "Woodhaven Gardens v2"`), update
the Web Map to point at the new layers, and retire the old service after
verification.

See Esri's
[Overwrite a hosted feature layer](https://doc.arcgis.com/en/arcgis-online/manage-data/publish-features.htm)
documentation for constraints on overwrite operations.

---

## Configuration

| File | Purpose |
|---|---|
| `config/agol.env.example` | Template for AGOL credentials — copy to `.env` in the repo root. |
| `.gitignore` | Prevents committing `.env`, `output/`, `__pycache__/`, lock files. |

---

## Contributing

- Bump `schema_version` in `schemas/schema.json` when fields or domains change.
- Note whether a change is additive or breaking in your commit message.
- Do not commit credentials, output files, or lock files.
