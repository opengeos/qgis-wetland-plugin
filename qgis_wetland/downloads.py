"""Asynchronous download helpers for cached vector sources."""

from __future__ import annotations

import hashlib
import os
import urllib.parse
import urllib.request

from .constants import CACHE_DIR_NAME

DOWNLOAD_USER_AGENT = (
    "WetlandMapper/0.1 (+https://github.com/opengeos/qgis-wetland-plugin)"
)


def default_data_cache_dir() -> str:
    """Return the default on-disk data cache directory."""
    return os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME, "data")


def cache_path_for_url(url: str, cache_dir: str | None = None) -> str:
    """Return a stable cache path for a URL."""
    if cache_dir is None:
        cache_dir = default_data_cache_dir()
    parsed = urllib.parse.urlparse(url)
    basename = os.path.basename(parsed.path) or "download.dat"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    stem, ext = os.path.splitext(basename)
    return os.path.join(cache_dir, f"{stem}-{digest}{ext}")


def is_remote_cacheable_ogr(url: str) -> bool:
    """Return True for remote OGR files that should be cached locally."""
    lowered = url.lower()
    return lowered.startswith("https://") and not lowered.endswith(".pmtiles")


def download_to_cache(url: str, cache_dir: str | None = None) -> str:
    """Download a URL into cache if needed and return the local path."""
    path = cache_path_for_url(url, cache_dir)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.part"
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DOWNLOAD_USER_AGENT,
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
            with open(temp_path, "wb") as file_obj:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    file_obj.write(chunk)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
    return path


def make_download_task(entry, cache_dir: str, callback):
    """Create a QgsTask that downloads an entry source to cache."""
    from qgis.core import QgsTask

    class DownloadTask(QgsTask):
        def __init__(self):
            super().__init__(f"Download {entry.name}", QgsTask.Flag.CanCancel)
            self.path = None
            self.error = None

        def run(self):
            try:
                self.path = download_to_cache(entry.source, cache_dir)
                return True
            except Exception as exc:
                self.error = str(exc)
                return False

        def finished(self, success):
            callback(success, entry, self.path, self.error)

    return DownloadTask()


def probe_source(entry, timeout: int = 10) -> str:
    """Return a one-line status string for a catalog entry source.

    Performs a HEAD request for HTTP(S) sources and an `os.path.exists` check
    for local paths. Intended to run inside a background `QgsTask` so the UI
    stays responsive while several entries are checked.

    Args:
        entry: Catalog entry exposing ``name``, ``provider``, and ``source``.
        timeout: Per-request timeout in seconds for HTTP HEAD checks.

    Returns:
        A one-line human-readable status suitable for display.
    """
    try:
        if entry.provider == "pmtiles":
            request = urllib.request.Request(entry.source, method="HEAD")
            with urllib.request.urlopen(
                request, timeout=timeout
            ) as response:  # nosec B310
                size = response.headers.get("content-length", "unknown")
            return f"{entry.name}: reachable ({size} bytes)"
        if entry.source.startswith("http"):
            request = urllib.request.Request(entry.source, method="HEAD")
            with urllib.request.urlopen(
                request, timeout=timeout
            ) as response:  # nosec B310
                return f"{entry.name}: HTTP {response.status}"
        found = os.path.exists(entry.source)
        return f"{entry.name}: {'found' if found else 'missing'}"
    except Exception as exc:
        return f"{entry.name}: failed ({exc})"


def make_health_check_task(entries, callback, timeout: int = 10):
    """Create a QgsTask that probes each entry off the UI thread.

    Args:
        entries: Iterable of catalog entries to probe.
        callback: Callable invoked with ``(success: bool, lines: list[str])``
            on the UI thread once the task finishes.
        timeout: Per-request timeout in seconds.
    """
    from qgis.core import QgsTask

    snapshot = list(entries)

    class HealthCheckTask(QgsTask):
        def __init__(self):
            super().__init__(
                "Check Wetland Mapper source health", QgsTask.Flag.CanCancel
            )
            self.lines: list[str] = []

        def run(self):
            for entry in snapshot:
                if self.isCanceled():
                    return False
                self.lines.append(probe_source(entry, timeout=timeout))
            return True

        def finished(self, success):
            callback(success, self.lines)

    return HealthCheckTask()
