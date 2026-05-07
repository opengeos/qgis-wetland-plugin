"""Layer catalog and persistence helpers for Wetland Mapper."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional

from qgis.PyQt.QtCore import QSettings

from .constants import PLAYA_PRESET_ID, SETTINGS_PREFIX


@dataclass(frozen=True)
class CatalogEntry:
    """A data source that Wetland Mapper can add to a QGIS project."""

    id: str
    name: str
    category: str
    provider: str
    source: str
    layer_name: str = ""
    geometry_type: str = ""
    default_visible: bool = False
    opacity: float = 1.0
    preset_ids: List[str] = field(default_factory=list)
    attribution: str = ""
    style: str = "default"
    description: str = ""

    def to_dict(self) -> Dict:
        """Return a JSON-serializable representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "CatalogEntry":
        """Create an entry from persisted settings data."""
        valid_keys = cls.__dataclass_fields__.keys()
        clean = {key: data.get(key) for key in valid_keys if key in data}
        if not clean.get("preset_ids"):
            clean["preset_ids"] = []
        return cls(**clean)


PLAYA_CATALOG: List[CatalogEntry] = [
    CatalogEntry(
        id="playa_wbdhu8",
        name="WBDHU8 Boundary",
        category="Watersheds",
        provider="ogr",
        source="https://data.source.coop/giswqs/playa/WBDHU8.gpkg",
        layer_name="wbdhu8",
        geometry_type="polygon",
        default_visible=True,
        opacity=1.0,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="Source Cooperative / USGS WBD",
        style="wbd_outline",
        description="HUC8 watershed boundaries for the Playa example catalog.",
    ),
    CatalogEntry(
        id="playa_nwi",
        name="NWI Wetlands",
        category="Wetlands",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/nwi.pmtiles",
        layer_name="playa_nwi__conus_wetlands__conus_wet_poly",
        geometry_type="polygon",
        default_visible=True,
        opacity=0.5,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="USFWS National Wetlands Inventory / Source Cooperative",
        style="nwi_wetland_type",
    ),
    CatalogEntry(
        id="playa_depressions_10m",
        name="Depressions 10m",
        category="Depressions",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/depressions_10m.pmtiles",
        layer_name="merged_layer",
        geometry_type="polygon",
        default_visible=True,
        opacity=0.5,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="Source Cooperative / 3DEP-derived depressions",
        style="depressions",
    ),
    CatalogEntry(
        id="playa_easements",
        name="Easements",
        category="Conservation",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/easements_12_11_2024.pmtiles",
        layer_name="easements_12_11_2024",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.5,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="Source Cooperative",
        style="easements",
    ),
    CatalogEntry(
        id="playa_h3_nwi_count",
        name="H3 NWI Count",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_nwi_count.pmtiles",
        layer_name="h3_res5_nwi_count",
        geometry_type="polygon",
        default_visible=True,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_wetland_count",
    ),
    CatalogEntry(
        id="playa_h3_nwi_acres",
        name="H3 NWI Acres",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_nwi_acres.pmtiles",
        layer_name="h3_res5_nwi_acres",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_wetland_acres",
    ),
    CatalogEntry(
        id="playa_h3_depressions_count",
        name="H3 Depressions Count",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_depressions_count.pmtiles",
        layer_name="h3_res5_depressions_count",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_depression_count",
    ),
    CatalogEntry(
        id="playa_h3_depressions_acres",
        name="H3 Depressions Acres",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_depressions_acres.pmtiles",
        layer_name="h3_res5_depressions_acres",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_depression_acres",
    ),
    CatalogEntry(
        id="playa_h3_conus_nwi_count",
        name="H3 CONUS NWI Count",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_conus_nwi_count.pmtiles",
        layer_name="h3_res5_conus_nwi_count",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_wetland_count",
    ),
    CatalogEntry(
        id="playa_h3_conus_nwi_acres",
        name="H3 CONUS NWI Acres",
        category="Summaries",
        provider="pmtiles",
        source="https://data.source.coop/giswqs/playa/h3_res5_conus_nwi_acres.pmtiles",
        layer_name="h3_res5_conus_nwi_acres",
        geometry_type="polygon",
        default_visible=False,
        opacity=0.85,
        preset_ids=[PLAYA_PRESET_ID],
        style="h3_wetland_acres",
    ),
    CatalogEntry(
        id="jrc_water_occurrence",
        name="JRC Water Occurrence",
        category="Water",
        provider="xyz",
        source="https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png",
        geometry_type="raster",
        default_visible=False,
        opacity=1.0,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="EC JRC / Google",
        style="raster",
    ),
    CatalogEntry(
        id="google_satellite",
        name="Google Satellite",
        category="Imagery",
        provider="xyz",
        source="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        geometry_type="raster",
        default_visible=False,
        opacity=1.0,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="Google",
        style="raster",
    ),
    CatalogEntry(
        id="naip_false_color",
        name="NAIP False Color",
        category="Imagery",
        provider="wms",
        source="https://imagery.nationalmap.gov/arcgis/services/USGSNAIPImagery/ImageServer/WMSServer",
        layer_name="USGSNAIPImagery:FalseColorComposite",
        geometry_type="raster",
        default_visible=False,
        opacity=1.0,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="USGS NAIP",
        style="raster",
    ),
    CatalogEntry(
        id="three_dep_hillshade",
        name="3DEP Hillshade",
        category="Elevation",
        provider="wms",
        source="https://elevation.nationalmap.gov/arcgis/services/3DEPElevation/ImageServer/WMSServer",
        layer_name="3DEPElevation:Hillshade Multidirectional",
        geometry_type="raster",
        default_visible=False,
        opacity=1.0,
        preset_ids=[PLAYA_PRESET_ID],
        attribution="USGS 3DEP",
        style="raster",
    ),
]


def builtin_entries() -> List[CatalogEntry]:
    """Return built-in catalog entries."""
    return list(PLAYA_CATALOG)


def entries_for_preset(preset_id: str) -> List[CatalogEntry]:
    """Return all catalog entries for a preset."""
    return [entry for entry in all_entries() if preset_id in entry.preset_ids]


def all_entries() -> List[CatalogEntry]:
    """Return built-in and user-defined catalog entries."""
    return builtin_entries() + load_custom_entries()


def entry_by_id(entry_id: str) -> Optional[CatalogEntry]:
    """Find a catalog entry by id."""
    for entry in all_entries():
        if entry.id == entry_id:
            return entry
    return None


def load_custom_entries() -> List[CatalogEntry]:
    """Load user-defined catalog entries from QSettings."""
    raw = QSettings().value(f"{SETTINGS_PREFIX}custom_sources", "[]", type=str)
    try:
        items = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    entries = []
    for item in items:
        try:
            entries.append(CatalogEntry.from_dict(item))
        except (TypeError, ValueError):
            continue
    return entries


def save_custom_entries(entries: Iterable[CatalogEntry]) -> None:
    """Persist user-defined catalog entries."""
    payload = json.dumps([entry.to_dict() for entry in entries], indent=2)
    settings = QSettings()
    settings.setValue(f"{SETTINGS_PREFIX}custom_sources", payload)
    settings.sync()


def add_custom_entry(entry: CatalogEntry) -> None:
    """Add or replace a custom catalog entry."""
    entries = [item for item in load_custom_entries() if item.id != entry.id]
    entries.append(entry)
    save_custom_entries(entries)


def make_custom_id(name: str) -> str:
    """Create a stable-ish id for a user-defined source name."""
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"custom_{slug or 'source'}"


def pmtiles_vsicurl_uri(url: str) -> str:
    """Return the GDAL /vsicurl URI for a PMTiles URL."""
    if url.startswith("/vsicurl/"):
        return url
    return f"/vsicurl/{url}"


def pmtiles_layer_uri(url: str, layer_name: str) -> str:
    """Return a QGIS OGR layer URI for a PMTiles sublayer."""
    base = pmtiles_vsicurl_uri(url)
    return f"{base}|layername={layer_name}" if layer_name else base
