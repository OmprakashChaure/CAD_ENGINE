from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf.document import Drawing

from utils.logger import get_logger


logger = get_logger(__name__)


class DXFLoader:
    """
    Production-grade DXF loader.
    """

    def __init__(self, dxf_path: str):
        self.dxf_path = Path(dxf_path)

    def validate(self) -> None:
        """
        Validate DXF file existence.
        """

        if not self.dxf_path.exists():
            raise FileNotFoundError(
                f"DXF file not found: {self.dxf_path}"
            )

        if self.dxf_path.suffix.lower() != ".dxf":
            raise ValueError(
                f"Invalid DXF file: {self.dxf_path}"
            )

    def load(self) -> Drawing:
        """
        Load DXF safely with recovery fallback.
        """

        self.validate()

        logger.info(f"Loading DXF: {self.dxf_path}")

        try:
            document = ezdxf.readfile(str(self.dxf_path))
            logger.info("DXF loaded successfully")
            return document

        except Exception as exc:
            logger.warning(
                f"Normal load failed ({exc}). Attempting recovery..."
            )

            try:
                from ezdxf import recover
                document, auditor = recover.readfile(str(self.dxf_path))
                logger.info("DXF loaded via recovery mode")
                return document

            except Exception as rec_exc:
                logger.error(f"Recovery also failed: {rec_exc}")
                raise RuntimeError(
                    f"DXF loading failed: {exc}"
                ) from exc