"""Focused tests for Wetland Mapper catalog and analysis helpers."""

import pytest

from qgis_wetland.analysis import (
    JrcRequest,
    adjusted_scale_for_bbox,
    estimate_request_cells,
    histogram_csv_rows,
    monthly_csv_rows,
    parse_jrc_response,
    sparse_tick_labels,
)
from qgis_wetland.catalog import (
    CatalogEntry,
    entries_for_preset,
    pmtiles_layer_uri,
    pmtiles_vsicurl_uri,
)
from qgis_wetland.constants import PLAYA_PRESET_ID
from qgis_wetland.naip import naip_payload
from qgis_wetland.downloads import (
    DOWNLOAD_USER_AGENT,
    cache_path_for_url,
    is_remote_cacheable_ogr,
)
from qgis_wetland.layer_loader import wms_layer_uri


def _sample_jrc_response():
    return {
        "monthly_history": {
            "frequency": "month",
            "unit": "hectares",
            "data": [{"Month": "2020-05", "Area": 12.5}],
        },
        "water_occurrence": {
            "stats": {"mean": 33.2, "min": 0, "max": 99, "stdDev": 12.1},
            "histogram": {"bin_edges": [0, 50, 100], "counts": [2.0, 3.5]},
        },
        "parameters": {},
    }


def test_playa_preset_contains_core_wetland_layers():
    entries = entries_for_preset(PLAYA_PRESET_ID)
    names = {entry.name for entry in entries}
    assert "NWI Wetlands" in names
    assert "Depressions 10m" in names
    assert "JRC Water Occurrence" in names
    wbd = next(entry for entry in entries if entry.id == "playa_wbdhu8")
    assert wbd.provider == "ogr"
    assert wbd.source.endswith("/WBDHU8.gpkg")
    assert wbd.layer_name == "wbdhu8"


def test_pmtiles_uri_helpers():
    url = "https://example.com/data.pmtiles"
    assert pmtiles_vsicurl_uri(url) == "/vsicurl/https://example.com/data.pmtiles"
    assert (
        pmtiles_layer_uri(url, "wetlands")
        == "/vsicurl/https://example.com/data.pmtiles|layername=wetlands"
    )


def test_download_cache_helpers():
    url = "https://data.source.coop/giswqs/playa/WBDHU8.gpkg"
    path = cache_path_for_url(url, "/tmp/wetland-cache")
    assert path.startswith("/tmp/wetland-cache/WBDHU8-")
    assert path.endswith(".gpkg")
    assert is_remote_cacheable_ogr(url)
    assert not is_remote_cacheable_ogr("https://example.com/data.pmtiles")
    assert "WetlandMapper" in DOWNLOAD_USER_AGENT


def test_wms_layer_uri_encodes_qgis_provider_params():
    uri = wms_layer_uri(
        "https://elevation.nationalmap.gov/arcgis/services/3DEPElevation/ImageServer/WMSServer",
        "3DEPElevation:Hillshade Multidirectional",
    )
    assert "layers=3DEPElevation%3AHillshade%20Multidirectional" in uri
    assert "url=https%3A%2F%2Felevation.nationalmap.gov" in uri
    assert "version=1.3.0" in uri
    assert "dpiMode=7" in uri
    assert "IgnoreGetMapUrl=1" in uri


def test_catalog_entry_round_trip():
    entry = CatalogEntry(
        id="custom_test",
        name="Custom Wetland",
        category="Custom",
        provider="pmtiles",
        source="https://example.com/wetland.pmtiles",
        layer_name="wetlands",
    )
    assert CatalogEntry.from_dict(entry.to_dict()) == entry


def test_jrc_payload_validation_and_shape():
    request = JrcRequest((-100.0, 35.0, -99.99, 35.01), 100, 5, 10)
    assert request.payload() == {
        "bbox": [-100.0, 35.0, -99.99, 35.01],
        "scale": 100,
        "start_month": 5,
        "end_month": 10,
        "frequency": "month",
    }


def test_jrc_rejects_invalid_month_range():
    with pytest.raises(ValueError, match="Start month"):
        JrcRequest((-100.0, 35.0, -99.99, 35.01), 100, 10, 5).payload()


def test_jrc_auto_adjusts_large_interactive_request_scale():
    payload = JrcRequest((-100.0, 35.0, -99.5, 35.5), 100, 5, 10).payload()
    assert payload["scale"] > 100


def test_jrc_estimated_cells_increases_for_smaller_scale():
    bbox = (-100.0, 35.0, -99.9, 35.1)
    assert estimate_request_cells(bbox, 100) > estimate_request_cells(bbox, 500)


def test_adjusted_scale_preserves_small_request_scale():
    bbox = (-100.0, 35.0, -99.99, 35.01)
    assert adjusted_scale_for_bbox(bbox, 100) == 100


def test_jrc_response_csv_rows():
    data = parse_jrc_response(_sample_jrc_response())
    assert monthly_csv_rows(data) == [["Month", "Area (hectares)"], ["2020-05", 12.5]]
    assert histogram_csv_rows(data) == [
        ["Bin Start (%)", "Bin End (%)", "Count (hectares)"],
        [0, 50, 2.0],
        [50, 100, 3.5],
    ]


def test_histogram_bins_match_web_app_labels():
    data = parse_jrc_response(_sample_jrc_response())
    hist = data["water_occurrence"]["histogram"]
    labels = [
        f"{hist['bin_edges'][i]}-{hist['bin_edges'][i + 1]}%"
        for i in range(len(hist["counts"]))
    ]
    assert labels == ["0-50%", "50-100%"]


def test_sparse_tick_labels_keeps_dense_axis_readable():
    labels = [f"1984_{month:02d}" for month in range(1, 13)] + [
        f"1985_{month:02d}" for month in range(1, 13)
    ]
    positions, tick_labels = sparse_tick_labels(labels, max_ticks=6)
    assert len(tick_labels) <= 7
    assert positions[0] == 0
    assert tick_labels[0] == "1984_01"
    assert positions[-1] == len(labels) - 1
    assert tick_labels[-1] == "1985_12"


def test_jrc_response_requires_stats():
    data = _sample_jrc_response()
    del data["water_occurrence"]["stats"]["mean"]
    with pytest.raises(ValueError, match="mean"):
        parse_jrc_response(data)


def test_naip_payload_uses_false_color_bands():
    payload = naip_payload(2020)
    assert payload["asset_id"] == "USDA/NAIP/DOQQ"
    assert payload["start_date"] == "2020-01-01"
    assert payload["end_date"] == "2020-12-31"
    assert payload["vis_params"]["bands"] == ["N", "R", "G"]
