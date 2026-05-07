"""Settings dock for Wetland Mapper."""

import os

from qgis.PyQt.QtCore import Qt, QSettings, QTimer
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    CACHE_DIR_NAME,
    DEFAULT_EE_TILE_ENDPOINT,
    DEFAULT_JRC_STATS_ENDPOINT,
    PLUGIN_NAME,
    SETTINGS_PREFIX,
)
from ..layer_loader import has_gdal_pmtiles_support


class SettingsDockWidget(QDockWidget):
    """Wetland Mapper configuration panel."""

    def __init__(self, iface, parent=None):
        super().__init__("Wetland Mapper Settings", parent)
        self.iface = iface
        self.settings = QSettings()
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(8)

        header = QLabel("Wetland Mapper Settings")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        header.setFont(font)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_services_tab(), "Services")
        self.tabs.addTab(self._create_data_tab(), "Data")
        self.tabs.addTab(self._create_dependencies_tab(), "Dependencies")
        layout.addWidget(self.tabs)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        buttons.addWidget(save_btn)
        buttons.addWidget(reset_btn)
        layout.addLayout(buttons)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_services_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Analysis Services")
        form = QFormLayout(group)

        self.jrc_endpoint = QLineEdit()
        form.addRow("JRC stats endpoint:", self.jrc_endpoint)

        self.ee_endpoint = QLineEdit()
        form.addRow("Earth Engine tile endpoint:", self.ee_endpoint)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 120)
        self.timeout_spin.setSuffix(" sec")
        form.addRow("Network timeout:", self.timeout_spin)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_data_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        group = QGroupBox("Local Data")
        form = QFormLayout(group)

        cache_row = QHBoxLayout()
        self.cache_dir = QLineEdit()
        cache_row.addWidget(self.cache_dir)
        browse_btn = QPushButton("...")
        browse_btn.setMaximumWidth(32)
        browse_btn.clicked.connect(self._browse_cache_dir)
        cache_row.addWidget(browse_btn)
        form.addRow("Cache/export directory:", cache_row)

        self.default_opacity = QSpinBox()
        self.default_opacity.setRange(0, 100)
        self.default_opacity.setSuffix("%")
        form.addRow("Default opacity:", self.default_opacity)

        self.auto_group_check = QCheckBox(
            "Create Wetland Mapper group when adding layers"
        )
        form.addRow("", self.auto_group_check)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _create_dependencies_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.pmtiles_status = QLabel("Checking PMTiles support...")
        self.pmtiles_status.setWordWrap(True)
        layout.addWidget(self.pmtiles_status)

        dependency_group = QGroupBox("Optional Python Packages")
        dep_layout = QVBoxLayout(dependency_group)
        self.matplotlib_status = QLabel("Checking matplotlib...")
        dep_layout.addWidget(self.matplotlib_status)

        install_btn = QPushButton("Install Missing Dependencies")
        install_btn.clicked.connect(self._install_dependencies)
        dep_layout.addWidget(install_btn)

        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self._refresh_dependency_status)
        dep_layout.addWidget(refresh_btn)
        layout.addWidget(dependency_group)

        note = QLabel(
            "PMTiles support comes from the GDAL build bundled with QGIS. "
            "If PMTiles is unavailable, update QGIS/GDAL rather than installing "
            "a Python package."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px;")
        layout.addWidget(note)
        layout.addStretch()

        QTimer.singleShot(100, self._refresh_dependency_status)
        return widget

    def _browse_cache_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Cache Directory", self.cache_dir.text() or ""
        )
        if path:
            self.cache_dir.setText(path)

    def _load_settings(self):
        default_cache = os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME)
        self.jrc_endpoint.setText(
            self.settings.value(
                f"{SETTINGS_PREFIX}jrc_stats_endpoint",
                DEFAULT_JRC_STATS_ENDPOINT,
                type=str,
            )
        )
        self.ee_endpoint.setText(
            self.settings.value(
                f"{SETTINGS_PREFIX}ee_tile_endpoint",
                DEFAULT_EE_TILE_ENDPOINT,
                type=str,
            )
        )
        self.timeout_spin.setValue(
            self.settings.value(f"{SETTINGS_PREFIX}timeout", 45, type=int)
        )
        self.cache_dir.setText(
            self.settings.value(f"{SETTINGS_PREFIX}cache_dir", default_cache, type=str)
        )
        self.default_opacity.setValue(
            self.settings.value(f"{SETTINGS_PREFIX}default_opacity", 85, type=int)
        )
        self.auto_group_check.setChecked(
            self.settings.value(f"{SETTINGS_PREFIX}auto_group", True, type=bool)
        )
        self.status_label.setText("Settings loaded")

    def _save_settings(self):
        self.settings.setValue(
            f"{SETTINGS_PREFIX}jrc_stats_endpoint", self.jrc_endpoint.text().strip()
        )
        self.settings.setValue(
            f"{SETTINGS_PREFIX}ee_tile_endpoint", self.ee_endpoint.text().strip()
        )
        self.settings.setValue(f"{SETTINGS_PREFIX}timeout", self.timeout_spin.value())
        self.settings.setValue(f"{SETTINGS_PREFIX}cache_dir", self.cache_dir.text())
        self.settings.setValue(
            f"{SETTINGS_PREFIX}default_opacity", self.default_opacity.value()
        )
        self.settings.setValue(
            f"{SETTINGS_PREFIX}auto_group", self.auto_group_check.isChecked()
        )
        self.settings.sync()
        self.status_label.setText("Settings saved")
        self.status_label.setStyleSheet("font-size: 10px;")
        self.iface.messageBar().pushSuccess(PLUGIN_NAME, "Settings saved successfully.")

    def _reset_defaults(self):
        default_cache = os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME)
        self.jrc_endpoint.setText(DEFAULT_JRC_STATS_ENDPOINT)
        self.ee_endpoint.setText(DEFAULT_EE_TILE_ENDPOINT)
        self.timeout_spin.setValue(45)
        self.cache_dir.setText(default_cache)
        self.default_opacity.setValue(85)
        self.auto_group_check.setChecked(True)
        self.status_label.setText("Defaults restored; click Save to persist")
        self.status_label.setStyleSheet("font-size: 10px;")

    def _refresh_dependency_status(self):
        if has_gdal_pmtiles_support():
            self.pmtiles_status.setText("GDAL PMTiles support: available")
            self.pmtiles_status.setStyleSheet("color: green; font-weight: 600;")
        else:
            self.pmtiles_status.setText(
                "GDAL PMTiles support: unavailable in this QGIS build"
            )
            self.pmtiles_status.setStyleSheet("color: red; font-weight: 600;")

        try:
            import matplotlib  # noqa: F401

            self.matplotlib_status.setText("matplotlib: installed")
            self.matplotlib_status.setStyleSheet("color: green;")
        except Exception:
            self.matplotlib_status.setText("matplotlib: not installed")
            self.matplotlib_status.setStyleSheet("color: red;")

    def _install_dependencies(self):
        try:
            from ..deps_manager import DepsInstallWorker
        except Exception as exc:
            QMessageBox.warning(
                self, PLUGIN_NAME, f"Dependency installer unavailable:\n{exc}"
            )
            return

        self.status_label.setText("Installing dependencies...")
        self._deps_worker = DepsInstallWorker()
        self._deps_worker.finished.connect(self._on_deps_install_finished)
        self._deps_worker.start()

    def _on_deps_install_finished(self, success, message):
        if success:
            QMessageBox.information(self, PLUGIN_NAME, message)
        else:
            QMessageBox.warning(self, PLUGIN_NAME, message)
        self._refresh_dependency_status()
        self.status_label.setText("Dependency check complete")
        self._deps_worker = None
