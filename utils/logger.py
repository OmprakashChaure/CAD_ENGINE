from pathlib import Path
from loguru import logger
import sys


LOG_DIR = Path("outputs/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "pipeline.log"


logger.remove()

logger.add(
    sys.stdout,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "{message}"
    ),
    level="INFO",
)

logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="10 days",
    compression="zip",
    level="DEBUG",
)


def get_logger(name: str):
    """
    Return configured logger instance.
    """
    return logger.bind(module=name)

def log_quarantine(entity_handle: str, reason: str):

    logger.warning(
        f"[QUARANTINE] "
        f"Entity={entity_handle} "
        f"Reason={reason}"
    )