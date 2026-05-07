"""QGIS layer loading and styling helpers."""

from __future__ import annotations

from typing import Iterable, List, Tuple
from urllib.parse import quote, urlencode

from .catalog import CatalogEntry, pmtiles_layer_uri, pmtiles_vsicurl_uri
from .constants import PLUGIN_NAME


def has_gdal_pmtiles_support() -> bool:
    """Return True when the current GDAL build can open PMTiles."""
    try:
        from osgeo import ogr
    except Exception:
        return False
    return ogr.GetDriverByName("PMTiles") is not None


def inspect_pmtiles_layers(url: str) -> List[str]:
    """Return sublayer names available in a PMTiles archive."""
    try:
        from osgeo import ogr
    except Exception as exc:
        raise RuntimeError("GDAL/OGR Python bindings are not available.") from exc

    datasource = ogr.Open(pmtiles_vsicurl_uri(url))
    if datasource is None:
        raise RuntimeError(f"Could not open PMTiles source: {url}")

    names = []
    for index in range(datasource.GetLayerCount()):
        layer = datasource.GetLayerByIndex(index)
        if layer is not None:
            names.append(layer.GetName())
    return names


def add_catalog_entry(entry: CatalogEntry, group_name: str = PLUGIN_NAME):
    """Add a catalog entry to the active QGIS project and return the layer."""
    if entry.provider == "pmtiles":
        layer = _add_pmtiles(entry)
    elif entry.provider == "xyz":
        layer = _add_xyz(entry)
    elif entry.provider == "wms":
        layer = _add_wms(entry)
    elif entry.provider in ("ogr", "local_vector"):
        layer = _add_ogr(entry)
    else:
        raise ValueError(f"Unsupported provider: {entry.provider}")

    _apply_common_metadata(layer, entry)
    _apply_style(layer, entry)
    _add_layer_to_group(layer, group_name)
    return layer


def add_catalog_entries(
    entries: Iterable[CatalogEntry], group_name: str = PLUGIN_NAME
) -> Tuple[List[object], List[Tuple[CatalogEntry, str]]]:
    """Add multiple entries, returning successful layers and failures."""
    layers = []
    failures = []
    for entry in entries:
        try:
            layers.append(add_catalog_entry(entry, group_name=group_name))
        except Exception as exc:
            failures.append((entry, str(exc)))
    return layers, failures


def _add_pmtiles(entry: CatalogEntry):
    from qgis.core import QgsVectorLayer

    if not has_gdal_pmtiles_support():
        raise RuntimeError("This QGIS/GDAL build does not include the PMTiles driver.")

    if entry.layer_name:
        available = inspect_pmtiles_layers(entry.source)
        if available and entry.layer_name not in available:
            raise RuntimeError(
                f"Layer '{entry.layer_name}' not found. Available: {', '.join(available)}"
            )

    layer = QgsVectorLayer(
        pmtiles_layer_uri(entry.source, entry.layer_name), entry.name, "ogr"
    )
    if not layer.isValid():
        raise RuntimeError(f"QGIS could not load PMTiles layer: {entry.name}")
    return layer


def _add_ogr(entry: CatalogEntry):
    from qgis.core import QgsVectorLayer

    uri = entry.source
    if uri.startswith("https://") and not uri.endswith(".pmtiles"):
        uri = f"/vsicurl/{uri}"
    if entry.layer_name:
        uri = f"{uri}|layername={entry.layer_name}"
    layer = QgsVectorLayer(uri, entry.name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"QGIS could not load vector layer: {entry.name}")
    return layer


def _add_xyz(entry: CatalogEntry):
    from qgis.core import QgsRasterLayer

    uri = f"type=xyz&url={quote(entry.source, safe=':/?&={{}}')}"
    layer = QgsRasterLayer(uri, entry.name, "wms")
    if not layer.isValid():
        raise RuntimeError(f"QGIS could not load XYZ layer: {entry.name}")
    return layer


def _add_wms(entry: CatalogEntry):
    from qgis.core import QgsRasterLayer

    uri = wms_layer_uri(entry.source, entry.layer_name)
    layer = QgsRasterLayer(uri, entry.name, "wms")
    if not layer.isValid():
        error = ""
        try:
            error = layer.error().summary()
        except Exception:
            pass
        message = f"QGIS could not load WMS layer: {entry.name}"
        if error:
            message = f"{message}\n{error}"
        raise RuntimeError(message)
    return layer


def wms_layer_uri(source_url: str, layer_name: str, crs: str = "EPSG:3857") -> str:
    """Build a QGIS WMS provider URI."""
    params = {
        "IgnoreGetFeatureInfoUrl": "1",
        "IgnoreGetMapUrl": "1",
        "contextualWMSLegend": "0",
        "crs": crs,
        "dpiMode": "7",
        "format": "image/png",
        "layers": layer_name,
        "styles": "",
        "url": source_url,
        "version": "1.3.0",
    }
    try:
        from qgis.core import QgsDataSourceUri

        uri = QgsDataSourceUri()
        for key, value in params.items():
            uri.setParam(key, value)
        encoded = uri.encodedUri()
        if isinstance(encoded, bytes):
            return encoded.decode("utf-8")
        return str(encoded)
    except Exception:
        return urlencode(params, quote_via=quote)


def _apply_common_metadata(layer, entry: CatalogEntry) -> None:
    layer.setOpacity(entry.opacity)
    layer.setCustomProperty("wetland_mapper/id", entry.id)
    layer.setCustomProperty("wetland_mapper/category", entry.category)
    layer.setCustomProperty("wetland_mapper/attribution", entry.attribution)
    if not entry.default_visible:
        layer.setCustomProperty("wetland_mapper/default_hidden", True)


def _add_layer_to_group(layer, group_name: str) -> None:
    from qgis.core import QgsProject

    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup(group_name)
    if group is None:
        group = root.insertGroup(0, group_name)
    else:
        group_index = root.children().index(group)
        if group_index != 0:
            group_clone = group.clone()
            root.insertChildNode(0, group_clone)
            root.removeChildNode(group)
            group = group_clone

    project.addMapLayer(layer, False)
    node = group.insertLayer(0, layer)
    hidden = layer.customProperty("wetland_mapper/default_hidden", False)
    if hidden:
        node.setItemVisibilityChecked(False)


def _apply_style(layer, entry: CatalogEntry) -> None:
    if entry.geometry_type == "raster":
        return
    if entry.style == "nwi_wetland_type":
        _style_nwi(layer)
    elif entry.style == "depressions":
        _style_simple_fill(layer, "#ff7043", "#bf360c", entry.opacity)
    elif entry.style == "easements":
        _style_simple_fill(layer, "#8bc34a", "#33691e", entry.opacity)
    elif entry.style == "wbd_outline":
        _style_outline(layer, "#3388ff")
    elif entry.style.startswith("h3_"):
        field = _h3_style_field(entry.style)
        _style_graduated(layer, field, entry.opacity)


def _style_simple_fill(
    layer, fill_color: str, stroke_color: str, opacity: float
) -> None:
    try:
        from qgis.core import QgsFillSymbol
    except Exception:
        return
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill_color,
            "outline_color": "255,255,255,0",
            "outline_width": "0",
        }
    )
    symbol.setOpacity(max(0.0, min(1.0, opacity)))
    layer.renderer().setSymbol(symbol)
    layer.triggerRepaint()


def _style_outline(layer, stroke_color: str) -> None:
    try:
        from qgis.core import QgsFillSymbol
    except Exception:
        return
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "255,255,255,0",
            "outline_color": stroke_color,
            "outline_width": "0.5",
        }
    )
    layer.renderer().setSymbol(symbol)
    layer.triggerRepaint()


def _style_nwi(layer) -> None:
    try:
        from qgis.core import (
            QgsCategorizedSymbolRenderer,
            QgsFillSymbol,
            QgsRendererCategory,
        )
    except Exception:
        return

    colors = {
        "Freshwater Forested/Shrub Wetland": "#008837",
        "Freshwater Emergent Wetland": "#7fc31c",
        "Freshwater Pond": "#688cc0",
        "Estuarine and Marine Wetland": "#66c2a5",
        "Riverine": "#0190bf",
        "Lake": "#13007c",
        "Estuarine and Marine Deepwater": "#007c88",
    }
    categories = []
    for value, color in colors.items():
        symbol = QgsFillSymbol.createSimple(
            {"color": color, "outline_color": "255,255,255,0", "outline_width": "0"}
        )
        symbol.setOpacity(0.5)
        categories.append(QgsRendererCategory(value, symbol, value))
    renderer = QgsCategorizedSymbolRenderer("WETLAND_TYPE", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def _style_graduated(layer, field_name: str, opacity: float) -> None:
    try:
        from qgis.core import (
            QgsFillSymbol,
            QgsGraduatedSymbolRenderer,
            QgsRendererRange,
        )
    except Exception:
        return
    if not field_name:
        return

    ranges = [
        (0, 1, "#000004", "0 - 9"),
        (1, 2, "#1b0c41", "10 - 99"),
        (2, 3, "#4a0c6b", "100 - 999"),
        (3, 4, "#a52c60", "1,000 - 9,999"),
        (4, 5, "#ed6925", "10,000 - 99,999"),
        (5, 10, "#fcffa4", "100,000+"),
    ]
    renderer_ranges = []
    for lower, upper, color, label in ranges:
        symbol = QgsFillSymbol.createSimple(
            {"color": color, "outline_color": "255,255,255,0", "outline_width": "0"}
        )
        symbol.setOpacity(opacity)
        renderer_ranges.append(QgsRendererRange(lower, upper, symbol, label))
    renderer = QgsGraduatedSymbolRenderer(f'log10("{field_name}" + 1)', renderer_ranges)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def _h3_style_field(style: str) -> str:
    if "wetland_count" in style:
        return "wetland_count"
    if "wetland_acres" in style:
        return "wetland_acres"
    if "depression_count" in style:
        return "depression_count"
    if "depression_acres" in style:
        return "depression_acres"
    return ""
