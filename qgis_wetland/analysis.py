"""JRC water occurrence analysis helpers."""

from __future__ import annotations

import csv
import json
import math
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .constants import DEFAULT_JRC_STATS_ENDPOINT

TARGET_JRC_ESTIMATED_CELLS = 20000


@dataclass
class JrcRequest:
    """Parameters for a JRC water statistics request."""

    bbox: Tuple[float, float, float, float]
    scale: int = 100
    start_month: int = 5
    end_month: int = 10
    frequency: str = "month"

    def validate(self) -> None:
        west, south, east, north = self.bbox
        if not all(math.isfinite(value) for value in self.bbox):
            raise ValueError("Bounding box coordinates must be finite numbers.")
        if west < -180 or east > 180 or south < -90 or north > 90:
            raise ValueError(
                "Bounding box must be in WGS84 longitude/latitude coordinates."
            )
        if east <= west or north <= south:
            raise ValueError("Bounding box coordinates are invalid.")
        if abs(east - west) < 0.001 or abs(north - south) < 0.001:
            raise ValueError("Bounding box is too small.")
        if self.scale < 1:
            raise ValueError("Scale must be a positive meter value.")
        if not 1 <= self.start_month <= 12 or not 1 <= self.end_month <= 12:
            raise ValueError("Month values must be between 1 and 12.")
        if self.start_month > self.end_month:
            raise ValueError("Start month cannot be after end month.")

    def payload(self) -> Dict:
        self.validate()
        return {
            "bbox": list(self.bbox),
            "scale": adjusted_scale_for_bbox(self.bbox, self.scale),
            "start_month": self.start_month,
            "end_month": self.end_month,
            "frequency": self.frequency,
        }


def fetch_jrc_water_stats(
    request: JrcRequest,
    endpoint: str = DEFAULT_JRC_STATS_ENDPOINT,
    timeout: int = 120,
) -> Dict:
    """Fetch JRC water statistics from the configured API endpoint."""
    data = json.dumps(request.payload()).encode("utf-8")
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
        raise RuntimeError(f"JRC API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"JRC API request failed: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(
            f"JRC API request timed out after {timeout} seconds. "
            "Try again, or use a smaller area if the service remains busy."
        ) from exc
    return parse_jrc_response(json.loads(body))


def estimate_request_cells(
    bbox: Tuple[float, float, float, float], scale: int
) -> float:
    """Estimate raster cells in a WGS84 bbox at a nominal meter scale."""
    west, south, east, north = bbox
    mid_lat = math.radians((south + north) / 2.0)
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = max(1.0, 111_320.0 * math.cos(mid_lat))
    width_m = abs(east - west) * meters_per_degree_lon
    height_m = abs(north - south) * meters_per_degree_lat
    return (width_m * height_m) / float(scale * scale)


def adjusted_scale_for_bbox(
    bbox: Tuple[float, float, float, float],
    requested_scale: int,
    target_cells: int = TARGET_JRC_ESTIMATED_CELLS,
) -> int:
    """Return a coarser scale when needed for interactive JRC requests.

    The Earth Engine endpoint uses bestEffort, so this plugin treats the UI
    scale as the preferred minimum resolution and automatically submits a
    coarser scale for large extents.
    """
    if requested_scale < 1:
        raise ValueError("Scale must be a positive meter value.")
    cells = estimate_request_cells(bbox, requested_scale)
    if cells <= target_cells:
        return int(requested_scale)
    factor = math.sqrt(cells / float(target_cells))
    return int(math.ceil(requested_scale * factor))


def parse_jrc_response(data: Dict) -> Dict:
    """Validate and normalize the JRC API response shape."""
    if "monthly_history" not in data or "water_occurrence" not in data:
        raise ValueError("JRC response is missing expected result sections.")
    monthly = data["monthly_history"].get("data", [])
    histogram = data["water_occurrence"].get("histogram", {})
    stats = data["water_occurrence"].get("stats", {})
    if not isinstance(monthly, list):
        raise ValueError("Monthly history data is not a list.")
    if "bin_edges" not in histogram or "counts" not in histogram:
        raise ValueError("Occurrence histogram is incomplete.")
    for key in ("mean", "min", "max", "stdDev"):
        if key not in stats:
            raise ValueError(f"Occurrence stats missing '{key}'.")
    return data


def monthly_csv_rows(data: Dict) -> List[List[object]]:
    """Return rows for monthly water-area CSV export."""
    rows = [["Month", "Area (hectares)"]]
    for item in data["monthly_history"]["data"]:
        rows.append([item.get("Month", ""), item.get("Area", "")])
    return rows


def histogram_csv_rows(data: Dict) -> List[List[object]]:
    """Return rows for occurrence histogram CSV export."""
    hist = data["water_occurrence"]["histogram"]
    rows = [["Bin Start (%)", "Bin End (%)", "Count (hectares)"]]
    for index, count in enumerate(hist["counts"]):
        rows.append([hist["bin_edges"][index], hist["bin_edges"][index + 1], count])
    return rows


def write_csv(path: str, rows: Iterable[Iterable[object]]) -> None:
    """Write rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerows(rows)


def write_json(path: str, data: Dict) -> None:
    """Write raw analysis JSON."""
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2)


def render_chart_png(path: str, data: Dict, chart_type: str) -> None:
    """Render a chart PNG for monthly area or occurrence histogram."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if chart_type == "monthly":
        monthly = data["monthly_history"]["data"]
        labels = [item.get("Month", "") for item in monthly]
        values = [item.get("Area", 0) for item in monthly]
        ylabel = "Area (hectares)"
        title = "Monthly Water Area"
        color = "#4264fb"
    elif chart_type == "histogram":
        hist = data["water_occurrence"]["histogram"]
        labels = [
            f"{hist['bin_edges'][i]}-{hist['bin_edges'][i + 1]}%"
            for i in range(len(hist["counts"]))
        ]
        values = hist["counts"]
        ylabel = "Count (hectares)"
        title = "Water Occurrence Distribution"
        color = "#28a745"
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    fig, axis = plt.subplots(figsize=(10, 4), dpi=150)
    x_positions = list(range(len(labels)))
    axis.bar(x_positions, values, color=color)
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    tick_positions, tick_labels = sparse_tick_labels(labels, max_ticks=14)
    axis.set_xticks(tick_positions)
    axis.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
    axis.margins(x=0.01)
    fig.tight_layout(pad=1.2)
    fig.savefig(path)
    plt.close(fig)


def sparse_tick_labels(
    labels: List[str], max_ticks: int = 14
) -> Tuple[List[int], List[str]]:
    """Return a readable subset of x-axis tick labels for dense bar charts."""
    if not labels:
        return [], []
    if len(labels) <= max_ticks:
        return list(range(len(labels))), labels

    step = max(1, math.ceil(len(labels) / max_ticks))
    positions = list(range(0, len(labels), step))
    if positions[-1] != len(labels) - 1:
        positions.append(len(labels) - 1)
    return positions, [labels[index] for index in positions]


def create_bbox_layer(name: str, bbox: Tuple[float, float, float, float]):
    """Create a temporary polygon layer for an analysis bounding box."""
    from qgis.core import (
        QgsFeature,
        QgsFillSymbol,
        QgsGeometry,
        QgsPointXY,
        QgsProject,
        QgsVectorLayer,
    )

    west, south, east, north = bbox
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", name, "memory")
    provider = layer.dataProvider()
    feature = QgsFeature()
    feature.setGeometry(
        QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(west, south),
                    QgsPointXY(east, south),
                    QgsPointXY(east, north),
                    QgsPointXY(west, north),
                    QgsPointXY(west, south),
                ]
            ]
        )
    )
    provider.addFeatures([feature])
    layer.updateExtents()
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "255,255,255,0",
            "outline_color": "#4264fb",
            "outline_width": "0.8",
            "outline_style": "dash",
        }
    )
    layer.renderer().setSymbol(symbol)
    QgsProject.instance().addMapLayer(layer)
    return layer


def export_analysis_bundle(
    directory: str, data: Dict, prefix: str = "jrc_water_stats"
) -> Dict[str, str]:
    """Export CSV, JSON, and chart PNG outputs into a directory."""
    os.makedirs(directory, exist_ok=True)
    paths = {
        "monthly_csv": os.path.join(directory, f"{prefix}_monthly.csv"),
        "histogram_csv": os.path.join(directory, f"{prefix}_histogram.csv"),
        "json": os.path.join(directory, f"{prefix}.json"),
        "monthly_png": os.path.join(directory, f"{prefix}_monthly.png"),
        "histogram_png": os.path.join(directory, f"{prefix}_histogram.png"),
    }
    write_csv(paths["monthly_csv"], monthly_csv_rows(data))
    write_csv(paths["histogram_csv"], histogram_csv_rows(data))
    write_json(paths["json"], data)
    render_chart_png(paths["monthly_png"], data, "monthly")
    render_chart_png(paths["histogram_png"], data, "histogram")
    return paths


def make_jrc_task(request: JrcRequest, endpoint: str, timeout: int, callback):
    """Create a QgsTask that fetches JRC stats off the UI thread."""
    from qgis.core import QgsTask

    class JrcWaterStatsTask(QgsTask):
        def __init__(self):
            super().__init__("Fetch JRC water statistics", QgsTask.Flag.CanCancel)
            self.result = None
            self.error = None

        def run(self):
            try:
                self.result = fetch_jrc_water_stats(request, endpoint, timeout)
                return True
            except Exception as exc:
                self.error = str(exc)
                return False

        def finished(self, success):
            callback(success, self.result, self.error)

    return JrcWaterStatsTask()
