"""Main QGIS plugin class for Wetland Mapper."""

import os
import re

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolBar, QMessageBox

from .constants import PLUGIN_MENU, PLUGIN_NAME


class QgisWetlandPlugin:
    """Wetland Mapper implementation class for QGIS."""

    def __init__(self, iface):
        """Initialize the plugin."""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = None
        self.toolbar = None
        self._wetland_dock = None
        self._settings_dock = None

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        checkable=False,
        parent=None,
    ):
        """Add a QGIS action to the plugin menu and/or toolbar."""
        action = QAction(QIcon(icon_path), text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        action.setCheckable(checkable)

        if status_tip is not None:
            action.setStatusTip(status_tip)
        if add_to_toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.menu.addAction(action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create menu entries and toolbar icons inside QGIS."""
        self.menu = QMenu(PLUGIN_MENU)
        self.iface.mainWindow().menuBar().addMenu(self.menu)

        self.toolbar = QToolBar(f"{PLUGIN_NAME} Toolbar")
        self.toolbar.setObjectName("WetlandMapperToolbar")
        self.iface.addToolBar(self.toolbar)

        icon_base = os.path.join(self.plugin_dir, "icons")
        main_icon = os.path.join(icon_base, "icon.svg")
        if not os.path.exists(main_icon):
            main_icon = ":/images/themes/default/mActionAddLayer.svg"

        settings_icon = os.path.join(icon_base, "settings.svg")
        if not os.path.exists(settings_icon):
            settings_icon = ":/images/themes/default/mActionOptions.svg"

        about_icon = os.path.join(icon_base, "about.svg")
        if not os.path.exists(about_icon):
            about_icon = ":/images/themes/default/mActionHelpContents.svg"

        self.wetland_action = self.add_action(
            main_icon,
            "Wetland Mapper",
            self.toggle_wetland_dock,
            status_tip="Open Wetland Mapper",
            checkable=True,
            parent=self.iface.mainWindow(),
        )
        self.settings_action = self.add_action(
            settings_icon,
            "Settings",
            self.toggle_settings_dock,
            status_tip="Open Wetland Mapper settings",
            checkable=True,
            parent=self.iface.mainWindow(),
        )

        self.menu.addSeparator()
        self.add_action(
            ":/images/themes/default/mActionRefresh.svg",
            "Check for Updates...",
            self.show_update_checker,
            add_to_toolbar=False,
            status_tip="Check for Wetland Mapper updates from GitHub",
            parent=self.iface.mainWindow(),
        )
        self.add_action(
            about_icon,
            "About Wetland Mapper",
            self.show_about,
            add_to_toolbar=False,
            status_tip="About Wetland Mapper",
            parent=self.iface.mainWindow(),
        )

    def unload(self):
        """Remove plugin UI from QGIS."""
        if self._wetland_dock:
            self.iface.removeDockWidget(self._wetland_dock)
            self._wetland_dock.deleteLater()
            self._wetland_dock = None
        if self._settings_dock:
            self.iface.removeDockWidget(self._settings_dock)
            self._settings_dock.deleteLater()
            self._settings_dock = None

        if self.menu is not None:
            for action in list(self.menu.actions()):
                self.menu.removeAction(action)
            menubar = self.iface.mainWindow().menuBar()
            menubar.removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None

        self.actions = []

    def toggle_wetland_dock(self):
        """Toggle the Wetland Mapper dock widget."""
        if self._wetland_dock is None:
            try:
                from .dialogs.wetland_dock import WetlandDockWidget

                self._wetland_dock = WetlandDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._wetland_dock.setObjectName("WetlandMapperDock")
                self._wetland_dock.visibilityChanged.connect(
                    self._on_wetland_visibility_changed
                )
                self.iface.addDockWidget(
                    Qt.DockWidgetArea.RightDockWidgetArea, self._wetland_dock
                )
                self._wetland_dock.show()
                self._wetland_dock.raise_()
                return
            except Exception as exc:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    PLUGIN_NAME,
                    f"Failed to create Wetland Mapper panel:\n{exc}",
                )
                self.wetland_action.setChecked(False)
                return

        if self._wetland_dock.isVisible():
            self._wetland_dock.hide()
        else:
            self._wetland_dock.show()
            self._wetland_dock.raise_()

    def _on_wetland_visibility_changed(self, visible):
        self.wetland_action.setChecked(visible)

    def toggle_settings_dock(self):
        """Toggle the settings dock widget."""
        if self._settings_dock is None:
            try:
                from .dialogs.settings_dock import SettingsDockWidget

                self._settings_dock = SettingsDockWidget(
                    self.iface, self.iface.mainWindow()
                )
                self._settings_dock.setObjectName("WetlandMapperSettingsDock")
                self._settings_dock.visibilityChanged.connect(
                    self._on_settings_visibility_changed
                )
                self.iface.addDockWidget(
                    Qt.DockWidgetArea.RightDockWidgetArea, self._settings_dock
                )
                self._settings_dock.show()
                self._settings_dock.raise_()
                return
            except Exception as exc:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    PLUGIN_NAME,
                    f"Failed to create Settings panel:\n{exc}",
                )
                self.settings_action.setChecked(False)
                return

        if self._settings_dock.isVisible():
            self._settings_dock.hide()
        else:
            self._settings_dock.show()
            self._settings_dock.raise_()

    def _on_settings_visibility_changed(self, visible):
        self.settings_action.setChecked(visible)

    def show_about(self):
        """Display the about dialog."""
        version = "Unknown"
        try:
            metadata_path = os.path.join(self.plugin_dir, "metadata.txt")
            with open(metadata_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
                version_match = re.search(r"^version=(.+)$", content, re.MULTILINE)
                if version_match:
                    version = version_match.group(1).strip()
        except Exception:
            pass

        about_text = f"""
<h2>Wetland Mapper</h2>
<p>Version: {version}</p>
<p>A native QGIS plugin for wetland mapping and water occurrence analysis.</p>
<ul>
<li>Load built-in wetland mapping presets, including Playa Wetlands.</li>
<li>Add custom WMS, XYZ, PMTiles, and local vector sources.</li>
<li>Analyze JRC water occurrence for extents and selected features.</li>
<li>Browse NAIP imagery years and export analysis outputs.</li>
</ul>
<p>Licensed under the MIT License.</p>
"""
        QMessageBox.about(self.iface.mainWindow(), "About Wetland Mapper", about_text)

    def show_update_checker(self):
        """Display the update checker dialog."""
        try:
            from .dialogs.update_checker import UpdateCheckerDialog
        except ImportError as exc:
            QMessageBox.critical(
                self.iface.mainWindow(),
                PLUGIN_NAME,
                f"Failed to import update checker dialog:\n{exc}",
            )
            return

        try:
            dialog = UpdateCheckerDialog(self.plugin_dir, self.iface.mainWindow())
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(
                self.iface.mainWindow(),
                PLUGIN_NAME,
                f"Failed to open update checker:\n{exc}",
            )
