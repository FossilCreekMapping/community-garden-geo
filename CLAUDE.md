# Woodhaven Gardens — Developer Context

## Repository layout

```
schemas/schema.json   authoritative data model (single source of truth)
scripts/
  create_gdb.py       builds a local GeoPackage (stdlib only — no ArcPy)
  deploy_agol.py      deploys to ArcGIS Online (requires arcgis package)
  zip_gdb.py          zips a GeoPackage for manual AGOL upload
tests/
  test_create_gdb.py  unit + integration tests for create_gdb.py
output/               generated files — gitignored
config/
  agol.env.example    template for AGOL credentials → copy to .env
```

## Running the application

```bash
# Build a local GeoPackage (no credentials needed)
python scripts/create_gdb.py                  # → output/WoodhavenGardens.gpkg
python scripts/create_gdb.py --overwrite      # recreate from scratch

# Deploy directly to ArcGIS Online
cp config/agol.env.example .env
# edit .env with AGOL_USERNAME / AGOL_PASSWORD
python scripts/deploy_agol.py --share-org
```

## Running tests

```bash
python -m unittest discover -s tests -v
```

Tests cover `create_gdb.py` only — no external services or credentials required.
`deploy_agol.py` requires a live ArcGIS Online account and is not unit-tested.

## Schema changes

- **Additive** (new field, new domain value): edit `schema.json`, bump `schema_version`, rerun scripts.
- **Breaking** (rename/remove field, change type): publish as a new versioned service title.
- Always keep `schema_version` up to date in `schema.json`.

## Credentials

Never commit `.env` or any file containing `AGOL_PASSWORD`. The `.gitignore`
already excludes `.env` and `output/`.

## Dependencies

| Package | Required by |
|---|---|
| Python 3.9+ stdlib only | `create_gdb.py`, `zip_gdb.py` |
| `arcgis>=2.3.0` | `deploy_agol.py` |
| `python-dotenv>=1.0.0` | `deploy_agol.py` |

Install with `pip install -r requirements.txt`.
