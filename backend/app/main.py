"""Application FastAPI : API /api/v1 + UI statique, un seul processus."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from . import backup
from .api.analysis import router as analysis_router
from .api.engine import router as engine_router
from .api.desktop import router as desktop_router
from .api.library import router as library_router
from .api.reference import router as reference_router
from .api.settings import router as settings_router
from .api.routes import router
from .api.sessions import router as sessions_router
from .domain.errors import DomainError
from .engine.download import DownloadState
from .engine.scheduler import Scheduler
from .engine.uci import EngineManager
from .persistence.db import Database
from .log import get_logger, setup_logging
from .preferences import Preferences
from .services import AnalysisService, ReferenceService
from .settings import APP_VERSION, Settings, get_settings

log = get_logger("app")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("demarrage %s (donnees %s)", APP_VERSION, settings.data_dir)
        try:
            # Restauration demandee par backup.ps1 / update.ps1 : avant toute migration.
            (settings.data_dir / backup.RESTORE_DIR).mkdir(parents=True, exist_ok=True)
            backup.apply_pending_restore(settings.data_dir, log)
            version = app.state.db.migrate()
            log.info("base prete : schema v%d, journal %s", version, app.state.db.journal_mode)
            with app.state.db.session() as conn:
                app.state.prefs.load(conn)
            app.state.engine.threads = app.state.prefs["engine_threads"]
            app.state.engine.hash_mb = app.state.prefs["engine_hash_mb"]
        except Exception as exc:
            # Le serveur reste joignable : /ready signale la base indisponible.
            log.error("base indisponible : %s: %s", type(exc).__name__, exc)
        if settings.engine_enabled:
            # Lot 7 : moteur choisi par l'utilisateur, impose (Docker), trouve sur la
            # machine ou deja telecharge ; sinon propose au telechargement.
            await app.state.engine.locate(app.state.prefs["engine_path"] or None)
            await app.state.engine.start()
            await app.state.scheduler.start()
        else:
            log.warning("moteur desactive par configuration")
        yield
        # SIGTERM : on arrete la file (le calcul en cours est interrompu) puis Stockfish.
        await app.state.scheduler.stop()
        await app.state.engine.stop()
        log.info("arret")

    app = FastAPI(title="Chess Calculation Trainer", version=APP_VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = EngineManager(settings)
    app.state.engine_download = DownloadState()
    app.state.db = Database(settings.data_dir / "app.sqlite")
    app.state.scheduler = Scheduler(app.state.db, app.state.engine, max_queued=settings.max_queued_jobs)
    app.state.analysis = AnalysisService(settings, app.state.engine, app.state.scheduler)
    app.state.prefs = Preferences(settings)
    app.state.reference = ReferenceService(app.state.db, app.state.analysis, app.state.prefs)
    app.state.scheduler.on_finished.append(app.state.reference.on_job_finished)
    app.state.scheduler.on_idle.append(app.state.reference.on_idle)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Un site tiers ouvert dans le navigateur peut viser 127.0.0.1 : toute
        # mutation portant une Origin etrangere est refusee.
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in _allowed_origins(request, settings):
                return JSONResponse(error_body("FORBIDDEN_ORIGIN", "Origine non autorisee."), status_code=403)
            length = request.headers.get("content-length")
            if length is not None and length.isdigit() and int(length) > settings.max_pgn_bytes + 64 * 1024:
                return JSONResponse(error_body("BODY_TOO_LARGE", "Requete trop volumineuse."), status_code=413)
        return await call_next(request)

    # Ajoute apres `guard` : s'execute donc avant lui (protection DNS rebinding).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        fields = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(error_body("VALIDATION_ERROR", "Requete invalide.", {"fields": fields}), status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # Le detail va au journal, jamais dans la reponse.
        log.exception("erreur interne sur %s %s", request.method, request.url.path)
        return JSONResponse(error_body("INTERNAL_ERROR", "Erreur interne."), status_code=500)

    app.include_router(router)
    app.include_router(library_router)
    app.include_router(sessions_router)
    app.include_router(analysis_router)
    app.include_router(reference_router)
    app.include_router(settings_router)
    app.include_router(engine_router)
    if settings.desktop_token:
        app.include_router(desktop_router)
    _mount_static(app, settings.static_dir)
    return app


def _allowed_origins(request: Request, settings: Settings) -> set[str]:
    # L'origine de la page elle-meme (meme hote/port) est toujours acceptee.
    own = f"{request.url.scheme}://{request.headers.get('host', '')}"
    return {own, *settings.allowed_origins}


def _mount_static(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    if not index.is_file():
        log.warning("UI absente (%s) : API seule", static_dir)
        return
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(error_body("NOT_FOUND", "Ressource inconnue."), status_code=404)
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


_app: FastAPI | None = None


def __getattr__(name: str):
    """`app.main:app` (image Docker) : construit a la premiere demande, pas a
    l'import, pour que le lanceur de bureau (`app.desktop`) importe ce module
    sans creer d'application sur les reglages par defaut (`/data`)."""
    global _app
    if name == "app":
        if _app is None:
            setup_logging()
            _app = create_app()
        return _app
    raise AttributeError(name)
