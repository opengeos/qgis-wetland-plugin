# Wetland Mapper

Wetland Mapper is a native QGIS plugin for wetland mapping and water occurrence
analysis. The plugin ships with a **Playa Wetlands** example preset, but it is
designed for broader wetland workflows through custom WMS, XYZ, PMTiles,
GeoPackage, Shapefile, and project-layer sources.

## Features

- **Wetland catalog presets**: Load the bundled Playa Wetlands preset into a
  `Wetland Mapper` layer group.
- **Custom sources**: Save and reload user-defined wetland sources with
  `QSettings`.
- **Native PMTiles support**: Load PMTiles through QGIS/GDAL using OGR
  `/vsicurl/https://...pmtiles` URIs.
- **Wetland styling**: Apply NWI, depression, easement, watershed, and H3
  summary styles.
- **JRC water occurrence**: Analyze current map extent, selected feature
  extent, or a drawn bounding box.
- **NAIP imagery browsing**: Request NAIP false-color XYZ tile layers by year.
- **Exports**: Save analysis CSV/JSON/PNG outputs, map images, selected
  features, and analysis bounding boxes.

## Requirements

- QGIS 3.28 through QGIS 4.x
- Python 3.10+
- QGIS/GDAL with the PMTiles vector driver for PMTiles catalog layers
- `matplotlib` for chart PNG exports

The plugin includes a dependency installer that creates an isolated virtual
environment at `~/.qgis_wetland/`.

## Install for Development

```bash
python install.py
```

or:

```bash
./install.sh
```

Then restart QGIS and enable **Wetland Mapper** from the plugin manager.

## Package

```bash
python package_plugin.py
```

This creates a `qgis_wetland-<version>.zip` package suitable for testing or
upload to a QGIS plugin repository.

## Project Structure

```text
qgis-wetland-plugin/
├── qgis_wetland/
│   ├── __init__.py
│   ├── wetland_mapper.py
│   ├── catalog.py
│   ├── layer_loader.py
│   ├── analysis.py
│   ├── naip.py
│   ├── metadata.txt
│   └── dialogs/
│       ├── wetland_dock.py
│       ├── settings_dock.py
│       └── update_checker.py
├── tests/
├── install.py
└── package_plugin.py
```

## Playa Preset Data

The Playa Wetlands preset includes WBDHU8 boundaries, NWI wetlands, 10 m
depressions, conservation easements, H3 wetland/depression summaries, JRC water
occurrence, 3DEP hillshade, Google Satellite, and NAIP imagery.

Vector preset sources are hosted as PMTiles at:

```text
https://data.source.coop/giswqs/playa/
```

## Testing

```bash
pytest
```

The test suite includes PyQt6 import-smoke coverage so Qt enum/import issues are
caught before packaging.
