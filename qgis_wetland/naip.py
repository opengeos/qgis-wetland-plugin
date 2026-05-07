"""NAIP imagery helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict
from urllib.parse import quote

from .constants import DEFAULT_EE_TILE_ENDPOINT, NAIP_ASSET_ID


def naip_payload(year: int) -> Dict:
    """Return the Earth Engine tile request payload for a NAIP year."""
    return {
        "asset_id": NAIP_ASSET_ID,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "vis_params": {"bands": ["N", "R", "G"]},
    }


def fetch_naip_tile_url(
    year: int, endpoint: str = DEFAULT_EE_TILE_ENDPOINT, timeout: int = 120
) -> str:
    """Fetch an XYZ tile URL for a NAIP year."""
    data = json.dumps(naip_payload(year)).encode("utf-8")
    http_request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            http_request, timeout=timeout
        ) as response:  # nosec B310
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"NAIP tile API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"NAIP tile API request failed: {exc.reason}") from exc

    payload = json.loads(body)
    tile_url = payload.get("tile_url")
    if not tile_url:
        raise ValueError("NAIP tile API response did not include tile_url.")
    return tile_url


def add_naip_xyz_layer(tile_url: str, name: str, opacity: float = 0.85):
    """Add a NAIP XYZ raster layer to the QGIS project."""
    from qgis.core import QgsProject, QgsRasterLayer

    uri = f"type=xyz&url={quote(tile_url, safe=':/?&={{}}')}"
    layer = QgsRasterLayer(uri, name, "wms")
    if not layer.isValid():
        raise RuntimeError(f"QGIS could not load NAIP layer: {name}")
    layer.setOpacity(opacity)
    QgsProject.instance().addMapLayer(layer)
    return layer
