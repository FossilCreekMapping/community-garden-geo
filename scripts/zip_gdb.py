"""
Zip a GeoPackage for manual upload to ArcGIS Online.

Usage:
    python zip_gdb.py [--gpkg <path_to.gpkg>] [--output <output.zip>]

If --gpkg is omitted the script looks for output/WoodhavenGardens.gpkg
relative to the repo root.

Note: The primary deployment path (deploy_agol.py) creates the feature
service directly on AGOL from schema.json and does not require this zip.
This script is provided for manual uploads via the AGOL web interface.
"""

import argparse
import os
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GPKG = os.path.join(
    SCRIPT_DIR, os.pardir, "output", "WoodhavenGardens.gpkg"
)


def zip_gpkg(gpkg_path: str, zip_path: str):
    gpkg_path = os.path.abspath(gpkg_path)
    if not os.path.isfile(gpkg_path):
        sys.exit(f"ERROR: GeoPackage not found at {gpkg_path}")

    filename = os.path.basename(gpkg_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(gpkg_path, filename)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Zipped {filename}")
    print(f"Output: {zip_path} ({size_mb:.2f} MB)")


def main():
    parser = argparse.ArgumentParser(
        description="Zip a GeoPackage for AGOL upload"
    )
    parser.add_argument(
        "--gpkg", default=DEFAULT_GPKG,
        help="Path to the .gpkg file",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output .zip path (default: same folder, same base name)",
    )
    args = parser.parse_args()

    gpkg_path = os.path.abspath(args.gpkg)
    if args.output:
        zip_path = os.path.abspath(args.output)
    else:
        zip_path = gpkg_path + ".zip"

    zip_gpkg(gpkg_path, zip_path)


if __name__ == "__main__":
    main()
