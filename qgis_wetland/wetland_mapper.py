"""Main QGIS plugin class for Wetland Mapper."""

import os
import re

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolBar, QMessageBox

from .constants import PLUGIN_MENU, PLUGIN_NAME

OPEN_GEOAGENT_PLUGIN_CANDIDATES = ("open_geoagent",)


def _enum_value(cls, enum_name, member_name):
    """Return an enum member from either scoped or legacy Qt APIs."""
    container = getattr(cls, enum_name, cls)
    return getattr(container, member_name)


TOOLBAR_OBJECT_NAME = "WetlandMapperToolbar"
MENU_TITLE = "Wetland Mapper"

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
        self._remove_toolbars_by_object_name()
        self._remove_menus_by_title()
        self.menu = QMenu(PLUGIN_MENU)
        self.iface.mainWindow().menuBar().addMenu(self.menu)

        self.toolbar = QToolBar(f"{PLUGIN_NAME} Toolbar")
        self.toolbar.setObjectName(TOOLBAR_OBJECT_NAME)
        self.iface.addToolBar(self.toolbar)

        icon_base = os.path.join(self.plugin_dir, "icons")
        main_icon = os.path.join(icon_base, "icon.svg")
        if not os.path.exists(main_icon):
            main_icon = ":/images/themes/default/mActionAddLayer.svg"

        settings_icon = os.path.join(icon_base, "settings.svg")
        if not os.path.exists(settings_icon):
            settings_icon = ":/images/themes/default/mActionOptions.svg"

        robot_icon = os.path.join(icon_base, "robot.svg")
        if not os.path.exists(robot_icon):
            robot_icon = ":/images/themes/default/mActionHelpContents.svg"

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
        self.chat_action = self.add_action(
            robot_icon,
            "AI Assistant",
            self.toggle_chat_dock,
            status_tip="Open the OpenGeoAgent chat panel",
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


    def _remove_toolbar(self, toolbar):
        """Detach and schedule deletion of a plugin toolbar widget."""
        if toolbar is None:
            return

        main_window = self.iface.mainWindow()
        actions = []
        try:
            actions = list(toolbar.actions())
        except Exception:
            pass  # nosec B110
        try:
            toolbar.clear()
        except Exception:
            pass  # nosec B110
        for action in actions:
            try:
                action.deleteLater()
            except Exception:
                pass  # nosec B110
        try:
            main_window.removeToolBar(toolbar)
        except Exception:
            pass  # nosec B110
        try:
            toolbar.hide()
        except Exception:
            pass  # nosec B110
        try:
            toolbar.setParent(None)
        except Exception:
            pass  # nosec B110
        try:
            toolbar.deleteLater()
        except Exception:
            pass  # nosec B110

    def _remove_toolbars_by_object_name(self):
        """Remove current or stale plugin toolbars from QGIS."""
        main_window = self.iface.mainWindow()
        for toolbar in main_window.findChildren(QToolBar, TOOLBAR_OBJECT_NAME):
            self._remove_toolbar(toolbar)

    def _plugin_menu_titles(self):
        """Return possible translated and untranslated plugin menu titles."""
        titles = {MENU_TITLE}
        translator = getattr(self, "tr", None)
        if callable(translator):
            try:
                titles.add(translator(MENU_TITLE))
            except Exception:
                pass  # nosec B110
        return titles

    def _remove_menu(self, menu):
        """Detach and schedule deletion of a plugin menu."""
        if menu is None:
            return

        main_window = self.iface.mainWindow()
        try:
            menu.clear()
        except Exception:
            pass  # nosec B110
        try:
            main_window.menuBar().removeAction(menu.menuAction())
        except Exception:
            pass  # nosec B110
        try:
            menu.setParent(None)
        except Exception:
            pass  # nosec B110
        try:
            menu.deleteLater()
        except Exception:
            pass  # nosec B110

    def _remove_menus_by_title(self):
        """Remove current or stale plugin menus from QGIS."""
        menu_bar = self.iface.mainWindow().menuBar()
        titles = self._plugin_menu_titles()
        for action in menu_bar.actions():
            menu = action.menu()
            if menu is not None and menu.title() in titles:
                self._remove_menu(menu)

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

        self._remove_toolbars_by_object_name()
        self._remove_menus_by_title()

    def toggle_wetland_dock(self):
        """Toggle the Wetland Mapper dock widget."""
        if self._wetland_dock is None:
            try:
                from .dialogs.wetland_dock import WetlandDockWidget

                self._wetland_dock = WetlandDockWidget(
                    self.iface, plugin=self, parent=self.iface.mainWindow()
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

    def _on_wetland_visibility_changed(self, _visible):
        self._sync_panel_actions()

    def toggle_chat_dock(self):
        """Show the Wetland Mapper AI tab and open OpenGeoAgent."""
        self._show_ai_assistant_tab()
        self.open_ai_assistant()

    def _show_ai_assistant_tab(self):
        """Create/show the main panel and switch to its AI Assistant tab."""
        if self._wetland_dock is None:
            self.toggle_wetland_dock()
        elif not self._wetland_dock.isVisible():
            self._wetland_dock.show()
            self._wetland_dock.raise_()

        if self._wetland_dock is not None:
            self._wetland_dock.show_ai_assistant_tab()
        self._sync_panel_actions()

    def _sync_panel_actions(self):
        """Synchronize check states for the tabbed Wetland Mapper panel."""
        wetland_visible = bool(
            self._wetland_dock is not None and self._wetland_dock.isVisible()
        )
        if hasattr(self, "wetland_action"):
            self.wetland_action.setChecked(wetland_visible)

        assistant_visible = False
        if wetland_visible and hasattr(self._wetland_dock, "ai_assistant_tab"):
            assistant_visible = (
                self._wetland_dock.tabs.currentWidget()
                == self._wetland_dock.ai_assistant_tab
            )
        if hasattr(self, "chat_action"):
            self.chat_action.setChecked(assistant_visible)

    def open_ai_assistant(self):
        """Open the OpenGeoAgent chat panel, or prompt for installation."""
        plugin = self._get_open_geoagent_plugin()
        if plugin is None:
            self._prompt_open_geoagent_install()
            return

        if not callable(getattr(plugin, "toggle_chat_dock", None)):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "OpenGeoAgent Required",
                "OpenGeoAgent is installed, but this version does not expose "
                "the chat panel launcher expected by Wetland Mapper.\n\n"
                "Please update OpenGeoAgent and try again.",
            )
            return

        try:
            chat_dock = getattr(plugin, "_chat_dock", None)
            if chat_dock is not None and chat_dock.isVisible():
                chat_dock.show()
                chat_dock.raise_()
                return

            plugin.toggle_chat_dock()
        except Exception as exc:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "OpenGeoAgent",
                f"Failed to open the OpenGeoAgent chat panel:\n{exc}",
            )

    def _get_open_geoagent_plugin(self):
        """Return the loaded OpenGeoAgent plugin instance, loading it if possible."""
        try:
            import qgis.utils as qgis_utils
        except Exception as exc:
            QgsMessageLog.logMessage(
                f"Could not import qgis.utils: {exc}",
                PLUGIN_NAME,
                Qgis.MessageLevel.Warning,
            )
            return None

        plugins = getattr(qgis_utils, "plugins", {}) or {}
        for package_name in OPEN_GEOAGENT_PLUGIN_CANDIDATES:
            plugin = plugins.get(package_name)
            if plugin is not None:
                return plugin

        available = set(getattr(qgis_utils, "available_plugins", []) or [])
        for package_name in OPEN_GEOAGENT_PLUGIN_CANDIDATES:
            if package_name not in available:
                continue

            try:
                load_plugin = getattr(qgis_utils, "loadPlugin", None)
                if callable(load_plugin) and package_name not in plugins:
                    load_plugin(package_name)

                start_plugin = getattr(qgis_utils, "startPlugin", None)
                active_plugins = getattr(qgis_utils, "active_plugins", []) or []
                if callable(start_plugin) and package_name not in active_plugins:
                    start_plugin(package_name)

                plugins = getattr(qgis_utils, "plugins", {}) or {}
                plugin = plugins.get(package_name)
                if plugin is not None:
                    return plugin
            except Exception as exc:
                QgsMessageLog.logMessage(
                    f"Failed to load OpenGeoAgent plugin " f"'{package_name}': {exc}",
                    PLUGIN_NAME,
                    Qgis.MessageLevel.Warning,
                )

        return None

    def _prompt_open_geoagent_install(self):
        """Tell the user how to install OpenGeoAgent from the QGIS Plugin Manager."""
        message = (
            "The AI Assistant is provided by the OpenGeoAgent QGIS plugin.\n\n"
            "Install it from the QGIS Plugin Manager:\n"
            "  Plugins > Manage and Install Plugins... > All\n"
            "  Search for 'OpenGeoAgent' and click Install Plugin.\n\n"
            "After installing or enabling OpenGeoAgent, click the AI "
            "Assistant button again."
        )
        box = QMessageBox(self.iface.mainWindow())
        box.setIcon(_enum_value(QMessageBox, "Icon", "Information"))
        box.setWindowTitle("Install OpenGeoAgent")
        box.setText(message)
        manager_button = box.addButton(
            "Open Plugin Manager",
            _enum_value(QMessageBox, "ButtonRole", "ActionRole"),
        )
        box.addButton(_enum_value(QMessageBox, "StandardButton", "Ok"))
        box.exec()

        if box.clickedButton() == manager_button:
            self._open_qgis_plugin_manager()

    def _open_qgis_plugin_manager(self):
        """Open the QGIS Plugin Manager dialog."""
        try:
            action = self.iface.actionManagePlugins()
            if action is not None:
                action.trigger()
                return
        except Exception as exc:
            QgsMessageLog.logMessage(
                f"Could not open QGIS Plugin Manager: {exc}",
                PLUGIN_NAME,
                Qgis.MessageLevel.Warning,
            )

        QMessageBox.information(
            self.iface.mainWindow(),
            "Open Plugin Manager",
            "Open the QGIS Plugin Manager from the menu:\n"
            "Plugins > Manage and Install Plugins...",
        )

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
        # Leave version as "Unknown" if metadata.txt is missing or unreadable.
        try:
            metadata_path = os.path.join(self.plugin_dir, "metadata.txt")
            with open(metadata_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
                version_match = re.search(r"^version=(.+)$", content, re.MULTILINE)
                if version_match:
                    version = version_match.group(1).strip()
        except Exception:  # nosec B110
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
