"""Reads a PDF and reports what is still inside it that you may not mean to send."""

# Read from the installed package rather than repeated here. A hand-written copy
# drifts the moment a release is cut, and then the tool misreports itself. That
# happened once already on a sibling project: 0.2.0 went out announcing itself as
# 0.1.0, and no test caught it because the string agreed with itself everywhere it
# appeared in the source tree. Only installing the built artefact and asking it
# found the lie.
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _installed_version

    try:
        __version__ = _installed_version("before-you-send")
    except PackageNotFoundError:  # running from a source tree, not installed
        __version__ = "unknown (not installed)"
except ImportError:  # pragma: no cover - Python 3.7 and earlier
    __version__ = "unknown"

from before_you_send.findings import Blindspot, Finding, Level, Report, Unchecked

__all__ = ["Blindspot", "Finding", "Level", "Report", "Unchecked", "__version__"]
