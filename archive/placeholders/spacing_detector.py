"""
Equal Spacing Detector — identifies evenly-spaced patterns.

Detects groups of circles/holes with equal spacing along an axis.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class EqualSpacingDetector:
    """Detect equal-spacing patterns among circles."""

    def detect(self, circles: list[dict]) -> list[dict]:
        """Return list of equal-spacing group descriptors."""
        raise NotImplementedError("Spacing detection to be implemented")
