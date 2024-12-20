"""Package initializer module."""

from importlib.metadata import version, PackageNotFoundError

PACKAGE_NAME = __name__

try:
    # Read version from installed package.
    __version__ = version(PACKAGE_NAME)
except PackageNotFoundError:
    __version__ = "(uninstalled version)"
