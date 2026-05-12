"""ASPICE Conflict Detector - Detect conflicts between ASPICE levels."""

from .conflict_detector import (
    Conflict,
    ConflictDetector,
    ConflictDetectorError,
    ConflictType,
    Severity,
)

__all__ = [
    "Conflict",
    "ConflictDetector",
    "ConflictDetectorError",
    "ConflictType",
    "Severity",
]

__version__ = "1.0.0"
