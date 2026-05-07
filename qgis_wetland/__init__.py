"""Wetland Mapper QGIS plugin package."""

from .deps_manager import ensure_venv_packages_available

# Add venv site-packages to sys.path so plugin dependencies are importable.
# This is a no-op if the venv has not been created yet.
ensure_venv_packages_available()

from .wetland_mapper import QgisWetlandPlugin


def classFactory(iface):
    """Load the Wetland Mapper plugin class.

    Args:
        iface: A QGIS interface instance.

    Returns:
        QgisWetlandPlugin: The plugin instance.
    """
    return QgisWetlandPlugin(iface)
