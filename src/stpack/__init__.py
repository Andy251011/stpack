"""stpack -- standardise raw spatial transcriptomics sample folders."""

from .detect import detect_platform
from .keeplists import PLATFORMS
from .package import package_sample, resolve_files

__version__ = "0.1.0"
__all__ = ["package_sample", "detect_platform", "resolve_files", "PLATFORMS"]
