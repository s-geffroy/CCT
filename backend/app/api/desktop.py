"""Routes du lanceur de bureau (Lot 7), montees seulement hors Docker.

GET  /api/v1/desktop/ping      l'instance est-elle bien la notre ? (jeton)
POST /api/v1/desktop/shutdown  arret propre demande par `python -m app.desktop --stop`

Le jeton est aleatoire a chaque lancement et ne vit que dans le dossier de
donnees de l'utilisateur : une page web ne peut pas arreter l'application.
"""
from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, Header, Request

from ..domain.errors import DomainError
from ..log import get_logger

router = APIRouter(prefix="/api/v1/desktop")
log = get_logger("desktop")


class BadToken(DomainError):
    status_code = 403


def _check(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.desktop_token
    if not token or not hmac.compare_digest(token, expected):
        raise BadToken("FORBIDDEN_TOKEN", "Jeton du lanceur absent ou invalide.")


@router.get("/ping")
def ping(request: Request, x_cct_token: str | None = Header(default=None)) -> dict:
    _check(request, x_cct_token)
    return {"ok": True}


@router.post("/shutdown", status_code=202)
async def shutdown(request: Request, x_cct_token: str | None = Header(default=None)) -> dict:
    _check(request, x_cct_token)
    log.info("arret demande par le lanceur")
    stop = getattr(request.app.state, "request_shutdown", None)
    if stop is not None:
        # Apres la reponse : uvicorn termine la requete puis passe par le lifespan.
        asyncio.get_running_loop().call_later(0.1, stop)
    return {"stopping": True}
