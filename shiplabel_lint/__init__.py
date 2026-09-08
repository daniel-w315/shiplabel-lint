"""Line-by-line checker for shipping label manifest CSVs."""

from .linter import Finding, lint_stream, load_carrier_patterns

__version__ = "0.1.0"
__all__ = ["Finding", "lint_stream", "load_carrier_patterns", "__version__"]
