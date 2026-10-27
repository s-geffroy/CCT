"""Journal : une ligne horodatee par evenement, sur la sortie standard."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """`log_file` : lanceur de bureau, journal tournant (5 x 2 Mo) ; la sortie
    standard n'existe pas sous `pythonw` et n'est alors pas utilisee."""
    handlers: list[logging.Handler] = []
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"))
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z")
    for handler in handlers:
        handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(level)
    # Uvicorn configure ses propres handlers (stderr, sans horodatage) avant
    # d'importer l'application : on les ramene au format commun.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    # Pas de journal d'acces : une ligne par sonde de sante toutes les 30 s.
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = []
    access.propagate = False
    # python-chess journalise chaque ligne UCI en DEBUG : bruit inutile.
    logging.getLogger("chess.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"cct.{name}")
