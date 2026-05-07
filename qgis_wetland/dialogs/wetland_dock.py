"""Main dock widget for Wetland Mapper."""

from __future__ import annotations

import os
from dataclasses import replace

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..analysis import (
    JrcRequest,
    adjusted_scale_for_bbox,
    create_bbox_layer,
    estimate_request_cells,
    export_analysis_bundle,
    make_jrc_task,
)
from ..catalog import (
    CatalogEntry,
    add_custom_entry,
    all_entries,
    entries_for_preset,
    make_custom_id,
)
from ..constants import (
    CACHE_DIR_NAME,
    DEFAULT_EE_TILE_ENDPOINT,
    DEFAULT_JRC_STATS_ENDPOINT,
    NAIP_END_YEAR,
    NAIP_START_YEAR,
    PLAYA_PRESET_ID,
    PLUGIN_NAME,
    SETTINGS_PREFIX,
)
from ..downloads import (
    is_remote_cacheable_ogr,
    make_download_task,
    make_health_check_task,
)
from ..layer_loader import (
    add_catalog_entries,
    add_catalog_entry,
    has_gdal_pmtiles_support,
)
from ..naip import add_naip_xyz_layer, fetch_naip_tile_url


class WetlandDockWidget(QDockWidget):
    """Dockable Wetland Mapper panel."""

    def __init__(self, iface, plugin=None, parent=None):
        super().__init__(PLUGIN_NAME, parent)
        self.iface = iface
        self.plugin = plugin
        self.settings = QSettings()
        self._last_bbox = None
        self._last_result = None
        self._jrc_task = None
        self._download_tasks = []
        self._health_task = None
        self._naip_cache = {}
        self._bbox_tool = None
        self._setup_ui()
        self._populate_catalog()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(8)

        header = QLabel("Wetland Mapper")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(header)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._create_catalog_tab(), "Catalog")
        self.tabs.addTab(self._create_custom_sources_tab(), "Custom")
        self.tabs.addTab(self._create_analysis_tab(), "Analyze")
        self.tabs.addTab(self._create_export_tab(), "Export")
        self.ai_assistant_tab = self._create_ai_assistant_tab()
        self.tabs.addTab(self.ai_assistant_tab, "AI Assistant")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_ai_assistant_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        assistant_group = QGroupBox("OpenGeoAgent")
        assistant_layout = QVBoxLayout(assistant_group)

        open_btn = QPushButton("Open OpenGeoAgent")
        open_btn.clicked.connect(self._open_ai_assistant)
        assistant_layout.addWidget(open_btn)

        self.ai_assistant_status = QLabel("Ready")
        self.ai_assistant_status.setWordWrap(True)
        self.ai_assistant_status.setStyleSheet("font-size: 10px; color: gray;")
        assistant_layout.addWidget(self.ai_assistant_status)

        layout.addWidget(assistant_group)
        layout.addStretch()
        return widget

    def _open_ai_assistant(self):
        plugin = getattr(self, "plugin", None)
        if plugin is None or not hasattr(plugin, "open_ai_assistant"):
            QMessageBox.warning(
                self,
                PLUGIN_NAME,
                "OpenGeoAgent launcher is unavailable from this panel.",
            )
            return

        plugin.open_ai_assistant()
        self.ai_assistant_status.setText("OpenGeoAgent requested")

    def show_ai_assistant_tab(self):
        """Show the AI Assistant tab inside the Wetland Mapper panel."""
        self.tabs.setCurrentWidget(self.ai_assistant_tab)
        self.show()
        self.raise_()

    def _on_tab_changed(self, _index):
        plugin = getattr(self, "plugin", None)
        if plugin is not None and hasattr(plugin, "_sync_panel_actions"):
            plugin._sync_panel_actions()

    def _create_catalog_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        preset_group = QGroupBox("Presets")
        preset_layout = QVBoxLayout(preset_group)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Playa Wetlands", PLAYA_PRESET_ID)
        self.preset_combo.currentIndexChanged.connect(self._populate_catalog)
        preset_layout.addWidget(self.preset_combo)

        self.catalog_tree = QTreeWidget()
        self.catalog_tree.setHeaderLabels(["Layer", "Provider"])
        self.catalog_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        preset_layout.addWidget(self.catalog_tree)

        button_row = QHBoxLayout()
        self.add_selected_btn = QPushButton("Add Selected")
        self.add_selected_btn.clicked.connect(self._add_selected_catalog_layers)
        self.add_preset_btn = QPushButton("Add Preset")
        self.add_preset_btn.clicked.connect(self._add_current_preset)
        button_row.addWidget(self.add_selected_btn)
        button_row.addWidget(self.add_preset_btn)
        preset_layout.addLayout(button_row)

        health_row = QHBoxLayout()
        self.health_btn = QPushButton("Check Sources")
        self.health_btn.clicked.connect(self._check_source_health)
        self.zoom_btn = QPushButton("Zoom to Playa")
        self.zoom_btn.clicked.connect(self._zoom_to_playa)
        health_row.addWidget(self.health_btn)
        health_row.addWidget(self.zoom_btn)
        preset_layout.addLayout(health_row)

        layout.addWidget(preset_group)

        naip_group = QGroupBox("NAIP Imagery")
        naip_layout = QFormLayout(naip_group)
        self.naip_year_combo = QComboBox()
        for year in range(NAIP_START_YEAR, NAIP_END_YEAR + 1):
            self.naip_year_combo.addItem(str(year), year)
        naip_layout.addRow("Year:", self.naip_year_combo)
        self.naip_opacity = QSpinBox()
        self.naip_opacity.setRange(0, 100)
        self.naip_opacity.setValue(85)
        self.naip_opacity.setSuffix("%")
        naip_layout.addRow("Opacity:", self.naip_opacity)

        naip_buttons = QHBoxLayout()
        self.update_naip_btn = QPushButton("Update Layer")
        self.update_naip_btn.clicked.connect(lambda: self._load_naip(False))
        self.persist_naip_btn = QPushButton("Add Year Layer")
        self.persist_naip_btn.clicked.connect(lambda: self._load_naip(True))
        naip_buttons.addWidget(self.update_naip_btn)
        naip_buttons.addWidget(self.persist_naip_btn)
        naip_layout.addRow(naip_buttons)
        layout.addWidget(naip_group)

        layout.addStretch()
        return widget

    def _create_custom_sources_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form_group = QGroupBox("Add Custom Source")
        form = QFormLayout(form_group)
        self.custom_name = QLineEdit()
        self.custom_name.setPlaceholderText("Wetland source name")
        form.addRow("Name:", self.custom_name)

        self.custom_provider = QComboBox()
        self.custom_provider.addItem("PMTiles (OGR)", "pmtiles")
        self.custom_provider.addItem("WMS", "wms")
        self.custom_provider.addItem("XYZ Tiles", "xyz")
        self.custom_provider.addItem("GeoPackage/Shapefile", "ogr")
        form.addRow("Type:", self.custom_provider)

        source_row = QHBoxLayout()
        self.custom_source = QLineEdit()
        self.custom_source.setPlaceholderText("URL or local file path")
        source_row.addWidget(self.custom_source)
        browse_btn = QPushButton("...")
        browse_btn.setMaximumWidth(32)
        browse_btn.clicked.connect(self._browse_custom_source)
        source_row.addWidget(browse_btn)
        form.addRow("Source:", source_row)

        self.custom_layer_name = QLineEdit()
        self.custom_layer_name.setPlaceholderText("Optional OGR/WMS layer name")
        form.addRow("Layer:", self.custom_layer_name)

        self.custom_category = QLineEdit()
        self.custom_category.setText("Custom")
        form.addRow("Category:", self.custom_category)

        source_buttons = QHBoxLayout()
        save_btn = QPushButton("Save Source")
        save_btn.clicked.connect(self._save_custom_source)
        add_now_btn = QPushButton("Add Now")
        add_now_btn.clicked.connect(self._add_custom_source_now)
        source_buttons.addWidget(save_btn)
        source_buttons.addWidget(add_now_btn)
        form.addRow(source_buttons)

        layout.addWidget(form_group)

        self.custom_tree = QTreeWidget()
        self.custom_tree.setHeaderLabels(["Saved Source", "Provider"])
        layout.addWidget(self.custom_tree)

        refresh_btn = QPushButton("Refresh Saved Sources")
        refresh_btn.clicked.connect(self._populate_custom_sources)
        layout.addWidget(refresh_btn)
        return widget

    def _create_analysis_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        inputs = QGroupBox("JRC Water Occurrence")
        form = QFormLayout(inputs)

        self.analysis_source = QComboBox()
        self.analysis_source.addItem("Current map extent", "extent")
        self.analysis_source.addItem("Selected feature extent", "selected")
        self.analysis_source.addItem("Draw bounding box", "drawn")
        form.addRow("Area:", self.analysis_source)

        bbox_buttons = QHBoxLayout()
        draw_btn = QPushButton("Draw BBox")
        draw_btn.clicked.connect(self._start_bbox_draw)
        use_extent_btn = QPushButton("Use Extent")
        use_extent_btn.clicked.connect(self._capture_current_extent)
        bbox_buttons.addWidget(draw_btn)
        bbox_buttons.addWidget(use_extent_btn)
        form.addRow(bbox_buttons)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 10000)
        self.scale_spin.setValue(100)
        self.scale_spin.setSuffix(" m")
        form.addRow("Scale:", self.scale_spin)

        self.start_month_spin = QSpinBox()
        self.start_month_spin.setRange(1, 12)
        self.start_month_spin.setValue(5)
        self.end_month_spin = QSpinBox()
        self.end_month_spin.setRange(1, 12)
        self.end_month_spin.setValue(10)
        month_row = QHBoxLayout()
        month_row.addWidget(self.start_month_spin)
        month_row.addWidget(QLabel("to"))
        month_row.addWidget(self.end_month_spin)
        form.addRow("Months:", month_row)

        run_btn = QPushButton("Run Water Stats")
        run_btn.clicked.connect(self._run_jrc_analysis)
        form.addRow(run_btn)
        layout.addWidget(inputs)

        self.analysis_output = QTextEdit()
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setPlaceholderText("Analysis results will appear here.")
        layout.addWidget(self.analysis_output)

        self.chart_tabs = QTabWidget()
        self.monthly_chart_area = QScrollArea()
        self.monthly_chart_area.setWidgetResizable(True)
        self.monthly_chart_widget = QWidget()
        self.monthly_chart_layout = QVBoxLayout(self.monthly_chart_widget)
        self.monthly_chart_layout.setContentsMargins(4, 4, 4, 4)
        self.monthly_chart_area.setWidget(self.monthly_chart_widget)
        self.chart_tabs.addTab(self.monthly_chart_area, "Monthly")

        self.histogram_chart_area = QScrollArea()
        self.histogram_chart_area.setWidgetResizable(True)
        self.histogram_chart_widget = QWidget()
        self.histogram_chart_layout = QVBoxLayout(self.histogram_chart_widget)
        self.histogram_chart_layout.setContentsMargins(4, 4, 4, 4)
        self.histogram_chart_area.setWidget(self.histogram_chart_widget)
        self.chart_tabs.addTab(self.histogram_chart_area, "Histogram")
        layout.addWidget(self.chart_tabs)
        self._clear_analysis_charts("Run water stats to view charts.")

        export_row = QHBoxLayout()
        export_btn = QPushButton("Export Analysis")
        export_btn.clicked.connect(self._export_analysis)
        bbox_btn = QPushButton("Add BBox Layer")
        bbox_btn.clicked.connect(self._add_bbox_layer)
        export_row.addWidget(export_btn)
        export_row.addWidget(bbox_btn)
        layout.addLayout(export_row)
        return widget

    def _create_export_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        map_btn = QPushButton("Export Current Map Image")
        map_btn.clicked.connect(self._export_map_image)
        layout.addWidget(map_btn)

        selected_btn = QPushButton("Export Selected Features")
        selected_btn.clicked.connect(self._export_selected_features)
        layout.addWidget(selected_btn)

        note = QLabel(
            "Analysis exports are available after running JRC water occurrence."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px;")
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _populate_catalog(self):
        if not hasattr(self, "catalog_tree"):
            return
        preset_id = self.preset_combo.currentData() or PLAYA_PRESET_ID
        self.catalog_tree.clear()
        categories = {}
        for entry in entries_for_preset(preset_id):
            category_item = categories.get(entry.category)
            if category_item is None:
                category_item = QTreeWidgetItem([entry.category, ""])
                category_item.setFlags(
                    category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                )
                self.catalog_tree.addTopLevelItem(category_item)
                categories[entry.category] = category_item
            item = QTreeWidgetItem([entry.name, entry.provider])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.id)
            item.setCheckState(
                0,
                (
                    Qt.CheckState.Checked
                    if entry.default_visible
                    else Qt.CheckState.Unchecked
                ),
            )
            category_item.addChild(item)
        self.catalog_tree.expandAll()
        self._populate_custom_sources()

    def _populate_custom_sources(self):
        if not hasattr(self, "custom_tree"):
            return
        self.custom_tree.clear()
        for entry in [item for item in all_entries() if not item.preset_ids]:
            tree_item = QTreeWidgetItem([entry.name, entry.provider])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, entry.id)
            self.custom_tree.addTopLevelItem(tree_item)

    def _selected_catalog_entries(self):
        entries = []
        for item in self.catalog_tree.selectedItems():
            entry_id = item.data(0, Qt.ItemDataRole.UserRole)
            if entry_id:
                entry = next(
                    (
                        candidate
                        for candidate in all_entries()
                        if candidate.id == entry_id
                    ),
                    None,
                )
                if entry:
                    entries.append(entry)
        if entries:
            return entries
        checked = []
        root_count = self.catalog_tree.topLevelItemCount()
        for root_index in range(root_count):
            root = self.catalog_tree.topLevelItem(root_index)
            for child_index in range(root.childCount()):
                child = root.child(child_index)
                if child.checkState(0) == Qt.CheckState.Checked:
                    entry_id = child.data(0, Qt.ItemDataRole.UserRole)
                    entry = next(
                        (
                            candidate
                            for candidate in all_entries()
                            if candidate.id == entry_id
                        ),
                        None,
                    )
                    if entry:
                        checked.append(entry)
        return checked

    def _add_selected_catalog_layers(self):
        entries = self._selected_catalog_entries()
        if not entries:
            self._set_status("Select or check at least one catalog layer.", "orange")
            return
        self._add_entries(entries)

    def _add_current_preset(self):
        preset_id = self.preset_combo.currentData() or PLAYA_PRESET_ID
        self._add_entries(entries_for_preset(preset_id))

    def _add_entries(self, entries):
        ready_entries, download_entries = self._split_download_entries(entries)
        self._set_status(f"Adding {len(ready_entries)} layer(s)...")
        layers, failures = add_catalog_entries(ready_entries, group_name=PLUGIN_NAME)
        if failures:
            details = "\n".join(
                f"{entry.name}: {message}" for entry, message in failures
            )
            QMessageBox.warning(self, PLUGIN_NAME, f"Some layers failed:\n{details}")
        if download_entries:
            self._start_downloads(download_entries)
            self._set_status(
                f"Added {len(layers)} layer(s). Downloading {len(download_entries)} cached layer(s)..."
            )
        else:
            self._set_status(f"Added {len(layers)} layer(s).", "green")

    def _browse_custom_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Wetland Data Source",
            "",
            "Vector data (*.gpkg *.shp *.geojson);;All files (*)",
        )
        if path:
            self.custom_source.setText(path)

    def _custom_entry_from_form(self):
        name = self.custom_name.text().strip()
        source = self.custom_source.text().strip()
        if not name or not source:
            raise ValueError("Custom source requires a name and source URL/path.")
        return CatalogEntry(
            id=make_custom_id(name),
            name=name,
            category=self.custom_category.text().strip() or "Custom",
            provider=self.custom_provider.currentData(),
            source=source,
            layer_name=self.custom_layer_name.text().strip(),
            geometry_type=(
                "raster"
                if self.custom_provider.currentData() in ("wms", "xyz")
                else "polygon"
            ),
            default_visible=True,
            opacity=1.0,
            preset_ids=[],
            style="default",
        )

    def _save_custom_source(self):
        try:
            entry = self._custom_entry_from_form()
            add_custom_entry(entry)
            self._populate_custom_sources()
            self._set_status(f"Saved custom source: {entry.name}", "green")
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def _add_custom_source_now(self):
        try:
            entry = self._custom_entry_from_form()
            ready_entries, download_entries = self._split_download_entries([entry])
            for ready_entry in ready_entries:
                add_catalog_entry(ready_entry, group_name=PLUGIN_NAME)
                self._set_status(f"Added custom source: {ready_entry.name}", "green")
            if download_entries:
                self._start_downloads(download_entries)
                self._set_status(f"Downloading custom source: {entry.name}")
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def _split_download_entries(self, entries):
        ready_entries = []
        download_entries = []
        for entry in entries:
            if entry.provider in ("ogr", "local_vector") and is_remote_cacheable_ogr(
                entry.source
            ):
                cached_path = self._cached_source_path(entry.source)
                if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                    ready_entries.append(replace(entry, source=cached_path))
                else:
                    download_entries.append(entry)
            else:
                ready_entries.append(entry)
        return ready_entries, download_entries

    def _start_downloads(self, entries):
        from qgis.core import QgsApplication

        cache_dir = self.settings.value(
            f"{SETTINGS_PREFIX}cache_dir",
            os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME),
            type=str,
        )
        data_cache_dir = os.path.join(cache_dir, "data")
        for entry in entries:
            task = make_download_task(entry, data_cache_dir, self._on_download_finished)
            self._download_tasks.append(task)
            QgsApplication.taskManager().addTask(task)

    def _on_download_finished(self, success, entry, path, error):
        if not success:
            QMessageBox.warning(
                self, PLUGIN_NAME, f"Failed to download {entry.name}:\n{error}"
            )
            self._set_status(f"Download failed: {entry.name}")
            return
        try:
            cached_entry = replace(entry, source=path)
            add_catalog_entry(cached_entry, group_name=PLUGIN_NAME)
            self._set_status(f"Downloaded and added {entry.name}.")
        except Exception as exc:
            QMessageBox.warning(
                self, PLUGIN_NAME, f"Downloaded but could not load {entry.name}:\n{exc}"
            )

    def _cached_source_path(self, url):
        from ..downloads import cache_path_for_url

        cache_dir = self.settings.value(
            f"{SETTINGS_PREFIX}cache_dir",
            os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME),
            type=str,
        )
        return cache_path_for_url(url, os.path.join(cache_dir, "data"))

    def _check_source_health(self):
        if self._health_task is not None:
            self._set_status("Source health check already running.")
            return

        entries = self._selected_catalog_entries() or entries_for_preset(
            PLAYA_PRESET_ID
        )

        preflight = []
        remaining = []
        for entry in entries:
            if entry.provider == "pmtiles" and not has_gdal_pmtiles_support():
                preflight.append(
                    f"{entry.name}: failed (GDAL PMTiles driver not available)"
                )
                continue
            remaining.append(entry)

        if preflight:
            self.analysis_output.setPlainText("\n".join(preflight))
            self.tabs.setCurrentIndex(2)

        if not remaining:
            self._set_status("Source health check complete.")
            return

        self._set_status("Checking source health...")
        self.tabs.setCurrentIndex(2)

        task = make_health_check_task(
            remaining,
            lambda success, lines: self._on_health_check_finished(
                success, preflight, lines
            ),
        )
        self._health_task = task
        from qgis.core import QgsApplication

        QgsApplication.taskManager().addTask(task)

    def _on_health_check_finished(self, success, preflight_lines, task_lines):
        self._health_task = None
        all_lines = list(preflight_lines) + list(task_lines)
        self.analysis_output.setPlainText("\n".join(all_lines))
        self.tabs.setCurrentIndex(2)
        if success:
            self._set_status("Source health check complete.")
        else:
            self._set_status("Source health check canceled.")

    def _zoom_to_playa(self):
        canvas = self.iface.mapCanvas()
        try:
            from qgis.core import (
                QgsCoordinateReferenceSystem,
                QgsCoordinateTransform,
                QgsProject,
                QgsRectangle,
            )

            rect = QgsRectangle(-106.5, 31.0, -94.0, 41.5)
            target_crs = canvas.mapSettings().destinationCrs()
            source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            if target_crs.authid() != source_crs.authid():
                transform = QgsCoordinateTransform(
                    source_crs, target_crs, QgsProject.instance()
                )
                rect = transform.transformBoundingBox(rect)
            canvas.setExtent(rect)
            canvas.refresh()
            self._set_status("Zoomed to the Playa example region.", "green")
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, f"Could not zoom map:\n{exc}")

    def _load_naip(self, persistent):
        year = self.naip_year_combo.currentData()
        opacity = self.naip_opacity.value() / 100.0
        endpoint = self.settings.value(
            f"{SETTINGS_PREFIX}ee_tile_endpoint", DEFAULT_EE_TILE_ENDPOINT, type=str
        )
        timeout = self.settings.value(f"{SETTINGS_PREFIX}timeout", 45, type=int)
        self._set_status(f"Loading NAIP {year}...")
        try:
            tile_url = self._naip_cache.get(year)
            if not tile_url:
                tile_url = fetch_naip_tile_url(year, endpoint, timeout)
                self._naip_cache[year] = tile_url
            name = f"NAIP False Color {year}" if persistent else "NAIP False Color"
            if not persistent:
                self._remove_dynamic_naip_layers()
            layer = add_naip_xyz_layer(tile_url, name, opacity)
            if not persistent:
                layer.setCustomProperty("wetland_mapper/naip_dynamic", True)
            self._set_status(f"Loaded NAIP imagery for {year}.")
        except Exception as exc:
            QMessageBox.warning(
                self, PLUGIN_NAME, f"Could not load NAIP imagery:\n{exc}"
            )
            self._set_status("NAIP load failed.")

    def _remove_dynamic_naip_layers(self):
        from qgis.core import QgsProject

        project = QgsProject.instance()
        for layer in list(project.mapLayers().values()):
            if layer.customProperty("wetland_mapper/naip_dynamic", False):
                project.removeMapLayer(layer.id())

    def _capture_current_extent(self):
        try:
            self._last_bbox = self._canvas_extent_as_wgs84()
            self.analysis_source.setCurrentIndex(
                self.analysis_source.findData("extent")
            )
            self._set_status(
                f"Captured extent: {self._format_bbox(self._last_bbox)}", "green"
            )
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, f"Could not capture extent:\n{exc}")

    def _start_bbox_draw(self):
        try:
            from qgis.PyQt.QtGui import QColor
            from qgis.core import Qgis, QgsGeometry, QgsPointXY, QgsRectangle
            from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
        except Exception as exc:
            QMessageBox.warning(
                self,
                PLUGIN_NAME,
                f"Interactive drawing is unavailable in this QGIS environment:\n{exc}",
            )
            return

        dock = self
        canvas = self.iface.mapCanvas()

        class BBoxTool(QgsMapToolEmitPoint):
            def __init__(self, map_canvas):
                super().__init__(map_canvas)
                self.canvas = map_canvas
                self.start = None
                self.rubber_band = QgsRubberBand(map_canvas, Qgis.GeometryType.Polygon)
                self.rubber_band.setColor(QColor(66, 100, 251, 80))
                self.rubber_band.setStrokeColor(QColor(66, 100, 251))
                self.rubber_band.setWidth(2)

            def canvasPressEvent(self, event):
                self.start = self.toMapCoordinates(event.pos())

            def canvasMoveEvent(self, event):
                if not self.start:
                    return
                current = self.toMapCoordinates(event.pos())
                rect = QgsRectangle(self.start, current)
                rect.normalize()
                self.rubber_band.setToGeometry(QgsGeometry.fromRect(rect), None)

            def canvasReleaseEvent(self, event):
                if not self.start:
                    return
                current = self.toMapCoordinates(event.pos())
                rect = QgsRectangle(self.start, current)
                rect.normalize()
                self.rubber_band.reset(Qgis.GeometryType.Polygon)
                dock._last_bbox = dock._rect_to_wgs84_bbox(rect)
                dock.analysis_source.setCurrentIndex(
                    dock.analysis_source.findData("drawn")
                )
                dock._set_status(
                    f"Captured drawn bbox: {dock._format_bbox(dock._last_bbox)}",
                    "green",
                )
                self.canvas.unsetMapTool(self)
                self.start = None

        self._bbox_tool = BBoxTool(canvas)
        canvas.setMapTool(self._bbox_tool)
        self._set_status("Drag on the map canvas to draw an analysis bbox.")

    def _run_jrc_analysis(self):
        try:
            bbox = self._analysis_bbox()
            request = JrcRequest(
                bbox=bbox,
                scale=self.scale_spin.value(),
                start_month=self.start_month_spin.value(),
                end_month=self.end_month_spin.value(),
            )
            endpoint = self.settings.value(
                f"{SETTINGS_PREFIX}jrc_stats_endpoint",
                DEFAULT_JRC_STATS_ENDPOINT,
                type=str,
            )
            timeout = self.settings.value(f"{SETTINGS_PREFIX}timeout", 45, type=int)
            submitted_scale = adjusted_scale_for_bbox(request.bbox, request.scale)
            cells = estimate_request_cells(request.bbox, submitted_scale)
            scale_line = f"Scale: {request.scale} m"
            if submitted_scale != request.scale:
                scale_line += f" (auto-adjusted to {submitted_scale} m)"
            self.analysis_output.setPlainText(
                "Submitting JRC water occurrence request...\n\n"
                f"BBox: {self._format_bbox(request.bbox)}\n"
                f"{scale_line}\n"
                f"Months: {request.start_month} to {request.end_month}\n"
                f"Estimated submitted cells: {cells:,.0f}\n"
                f"Timeout: {timeout} seconds"
            )
            self._set_status("Fetching JRC water statistics...")
            task = make_jrc_task(request, endpoint, timeout, self._on_jrc_finished)
            from qgis.core import QgsApplication

            self._jrc_task = task
            QgsApplication.taskManager().addTask(self._jrc_task)
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def _on_jrc_finished(self, success, result, error):
        self._jrc_task = None
        if not success:
            self._set_status("JRC analysis failed.")
            self.analysis_output.setPlainText(
                "JRC Water Occurrence request failed.\n\n"
                f"{error or 'Unknown JRC analysis error'}"
            )
            QMessageBox.warning(
                self, PLUGIN_NAME, error or "Unknown JRC analysis error"
            )
            return
        self._last_result = result
        stats = result["water_occurrence"]["stats"]
        monthly_count = len(result["monthly_history"]["data"])
        self._render_analysis_charts(result)
        self.analysis_output.setPlainText(
            "JRC Water Occurrence\n\n"
            f"BBox: {self._format_bbox(self._last_bbox)}\n"
            f"Monthly records: {monthly_count}\n"
            f"Mean occurrence: {stats['mean']:.2f}%\n"
            f"Min occurrence: {stats['min']}%\n"
            f"Max occurrence: {stats['max']}%\n"
            f"Std dev: {stats['stdDev']:.2f}%"
        )
        self._set_status("JRC analysis complete.")

    def _clear_analysis_charts(self, message="No chart data."):
        self._clear_layout(self.monthly_chart_layout)
        self._clear_layout(self.histogram_chart_layout)
        self.monthly_chart_layout.addWidget(QLabel(message))
        self.histogram_chart_layout.addWidget(QLabel(message))
        self.monthly_chart_layout.addStretch()
        self.histogram_chart_layout.addStretch()

    def _render_analysis_charts(self, result):
        monthly = result["monthly_history"]["data"]
        hist = result["water_occurrence"]["histogram"]

        monthly_rows = [
            (item.get("Month", ""), float(item.get("Area") or 0.0)) for item in monthly
        ]
        hist_rows = []
        for index, count in enumerate(hist["counts"]):
            label = f"{hist['bin_edges'][index]}-{hist['bin_edges'][index + 1]}%"
            hist_rows.append((label, float(count or 0.0)))

        self._populate_bar_chart(
            self.monthly_chart_layout,
            "Monthly Water Area",
            monthly_rows,
            "hectares",
            "#4264fb",
        )
        self._populate_bar_chart(
            self.histogram_chart_layout,
            "Water Occurrence Distribution",
            hist_rows,
            "hectares",
            "#28a745",
        )

    def _populate_bar_chart(self, layout, title, rows, unit, color):
        self._clear_layout(layout)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(title_label)

        if not rows:
            layout.addWidget(QLabel("No data returned."))
            layout.addStretch()
            return

        max_value = max(value for _label, value in rows) or 1.0
        for label, value in rows:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 1, 0, 1)

            label_widget = QLabel(str(label))
            label_widget.setMinimumWidth(82)
            label_widget.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            row_layout.addWidget(label_widget)

            bar = QLabel()
            bar.setMinimumHeight(14)
            width = max(2, int((value / max_value) * 180))
            bar.setFixedWidth(width)
            bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            row_layout.addWidget(bar)

            value_label = QLabel(f"{value:,.2f} {unit}")
            value_label.setMinimumWidth(90)
            row_layout.addWidget(value_label)
            row_layout.addStretch()
            layout.addWidget(row)

        layout.addStretch()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _analysis_bbox(self):
        mode = self.analysis_source.currentData()
        if mode == "selected":
            self._last_bbox = self._selected_feature_extent_as_wgs84()
        elif mode == "extent" or self._last_bbox is None:
            self._last_bbox = self._canvas_extent_as_wgs84()
        return self._last_bbox

    def _canvas_extent_as_wgs84(self):
        return self._rect_to_wgs84_bbox(self.iface.mapCanvas().extent())

    def _selected_feature_extent_as_wgs84(self):
        layer = self.iface.activeLayer()
        if layer is None or not layer.selectedFeatureCount():
            raise ValueError("Select at least one feature in the active layer.")
        extent = None
        for feature in layer.selectedFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if extent is None:
                extent = geom.boundingBox()
            else:
                extent.combineExtentWith(geom.boundingBox())
        if extent is None:
            raise ValueError("Selected features do not have usable geometry.")
        return self._rect_to_wgs84_bbox(extent, layer.crs())

    def _rect_to_wgs84_bbox(self, rect, source_crs=None):
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsProject,
        )

        source = source_crs or self.iface.mapCanvas().mapSettings().destinationCrs()
        target = QgsCoordinateReferenceSystem("EPSG:4326")
        if source.authid() != target.authid():
            transform = QgsCoordinateTransform(source, target, QgsProject.instance())
            rect = transform.transformBoundingBox(rect)
        return (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())

    def _export_analysis(self):
        if not self._last_result:
            QMessageBox.information(
                self, PLUGIN_NAME, "Run JRC analysis before exporting."
            )
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", ""
        )
        if not directory:
            return
        try:
            paths = export_analysis_bundle(directory, self._last_result)
            QMessageBox.information(
                self,
                PLUGIN_NAME,
                "Exported analysis files:\n" + "\n".join(paths.values()),
            )
            self._set_status("Analysis outputs exported.", "green")
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, f"Export failed:\n{exc}")

    def _add_bbox_layer(self):
        if not self._last_bbox:
            QMessageBox.information(
                self, PLUGIN_NAME, "Capture or analyze a bbox first."
            )
            return
        try:
            create_bbox_layer("Wetland Mapper Analysis BBox", self._last_bbox)
            self._set_status("Added analysis bbox layer.", "green")
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, f"Could not add bbox layer:\n{exc}")

    def _export_map_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Map Image", "wetland_mapper_map.png", "PNG image (*.png)"
        )
        if not path:
            return
        self.iface.mapCanvas().saveAsImage(path)
        self._set_status(f"Exported map image: {path}", "green")

    def _export_selected_features(self):
        layer = self.iface.activeLayer()
        if layer is None or not layer.selectedFeatureCount():
            QMessageBox.information(
                self, PLUGIN_NAME, "Select features in the active layer first."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Features",
            "wetland_mapper_selected.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if not path:
            return
        try:
            from qgis.core import QgsFeatureRequest, QgsVectorFileWriter

            request = QgsFeatureRequest().setFilterFids(layer.selectedFeatureIds())
            selected_layer = layer.materialize(request)
            error = QgsVectorFileWriter.writeAsVectorFormat(
                selected_layer, path, "utf-8", selected_layer.crs(), "GPKG"
            )
            if isinstance(error, tuple):
                error_code = error[0]
            else:
                error_code = error
            if error_code != 0:
                raise RuntimeError(f"QGIS writer returned error code {error_code}")
            self._set_status(f"Exported selected features: {path}", "green")
        except Exception as exc:
            QMessageBox.warning(
                self, PLUGIN_NAME, f"Selected feature export failed:\n{exc}"
            )

    def _format_bbox(self, bbox):
        if not bbox:
            return "None"
        return "[" + ", ".join(f"{value:.5f}" for value in bbox) + "]"

    def _set_status(self, message, color=None):
        self.status_label.setText(message)
        style = "font-size: 10px;"
        if color:
            style += f" color: {color};"
        self.status_label.setStyleSheet(style)
