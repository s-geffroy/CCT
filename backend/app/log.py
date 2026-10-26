"""Journal : une ligne horodatee par evenement, sur la sortie standard."""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
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
