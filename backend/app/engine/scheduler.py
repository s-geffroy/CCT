"""Planificateur d'analyses : une boucle asyncio, un Stockfish, une file persistante.

- Les travaux sont pris par priorite puis anciennete (`analysis_repo.claim_next`).
- Chaque palier atteste est enregistre (point stable) ; les infos intermediaires
  restent en memoire (`live`) et sont diffusees au plus une fois par seconde.
- Annulation : `stop_event` du travail en cours, ou annulation directe en file.
- Panne du moteur : le travail passe `failed`, le moteur est redemarre, la file
  continue. Au demarrage, un travail reste `running` devient `interrupted`.

Les routes FastAPI synchrones tournent dans des threads : elles reveillent la
boucle par `call_soon_threadsafe`, jamais en touchant ses objets directement.
"""
from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import chess
import chess.engine

from ..log import get_logger
from ..persistence import analysis_repo, repo
from ..persistence.db import Database
from .analysis import RootAnalysis, analyse_root
from .uci import EngineManager

log = get_logger("scheduler")

PROGRESS_INTERVAL_S = 1.0


class Broker:
    """Notifie les flux SSE abonnes qu'un travail a change (sans contenu : le flux
    reconstruit l'evenement lui-meme, avec le controle de visibilite)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id)
        if subs:
            subs.discard(queue)
            if not subs:
                del self._subscribers[job_id]

    def notify(self, job_id: str) -> None:
        for queue in list(self._subscribers.get(job_id, ())):
            if queue.empty():  # coalescence : un seul signal en attente suffit
                queue.put_nowait(True)


class Scheduler:
    def __init__(self, db: Database, engine: EngineManager, *, max_queued: int = 20):
        self.db = db
        self.engine = engine
        self.max_queued = max_queued
        self.broker = Broker()
        self.live: dict[str, RootAnalysis] = {}
        self.running_job_id: str | None = None
        self._stop_event: asyncio.Event | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Un seul thread d'ecriture : les instantanes d'un travail sont enregistres
        # dans l'ordre ou ils sont produits.
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis-writer")
        # Abonnes appeles dans le thread d'ecriture : fin d'un travail (id), puis
        # file vide. L'arbre de reference avance ainsi sans dependance circulaire.
        self.on_finished: list = []
        self.on_idle: list = []
        self._idle_pending = True

    # ---------------------------------------------------------- cycle de vie

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        interrupted = await asyncio.to_thread(self._with_conn, analysis_repo.mark_interrupted_on_startup)
        if interrupted:
            log.warning("%d travail(aux) interrompu(s) par l'arret precedent", interrupted)
        self._task = asyncio.create_task(self._run(), name="analysis-scheduler")

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._writer.shutdown(wait=True)

    def wake(self) -> None:
        """Appelable depuis n'importe quel thread."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    def cancel_running(self, job_id: str) -> None:
        def _cancel() -> None:
            if self.running_job_id == job_id and self._stop_event is not None:
                self._stop_event.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(_cancel)

    def notify_threadsafe(self, job_id: str) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.broker.notify, job_id)

    # ------------------------------------------------------------- boucle

    def _with_conn(self, fn, *args, **kwargs):
        with self.db.session() as conn:
            return fn(conn, *args, **kwargs)

    def _notify(self, listeners: list, *args) -> None:
        """Appelle les abonnes ; une erreur d'abonne n'arrete jamais la file."""
        for listener in listeners:
            try:
                listener(*args)
            except Exception:
                log.exception("abonne du planificateur en echec")

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                job = await asyncio.to_thread(self._with_conn, analysis_repo.claim_next)
            except Exception:
                log.exception("lecture de la file impossible")
                job = None
            if job is None:
                if self._idle_pending and self.on_idle:
                    # File vide : les abonnes peuvent relancer des travaux en attente.
                    self._idle_pending = False
                    await loop.run_in_executor(self._writer, self._notify, self.on_idle)
                    continue
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=30)
                except TimeoutError:
                    pass
                continue
            self._idle_pending = True
            try:
                await self._execute(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Un travail qui echoue ne doit jamais arreter la file : on le
                # journalise, on tente de le marquer en echec, et on continue.
                log.exception("analyse %s : erreur inattendue du planificateur", job["id"][:8])
                try:
                    await asyncio.to_thread(self._with_conn, analysis_repo.finish, job["id"], None,
                                            error="erreur interne du planificateur")
                except Exception:
                    log.exception("analyse %s : impossible de marquer l'echec", job["id"][:8])
                self.live.pop(job["id"], None)
                self.broker.notify(job["id"])
            await loop.run_in_executor(self._writer, self._notify, self.on_finished, job["id"])

    def _board(self, job) -> chess.Board:
        with self.db.session() as conn:
            position = repo.get_position(conn, job["position_id"])
        return analysis_repo.job_board(position, analysis_repo.node_path(job))

    async def _guarded(self, search):
        """Recherche surveillee : si le processus Stockfish meurt avant que
        python-chess ne l'ait signale a la commande en cours (mort juste avant
        le debut de la recherche), on ne reste pas bloque indefiniment."""
        task = asyncio.ensure_future(search)
        died = self.engine.engine.returncode
        try:
            await asyncio.wait({task, died}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:  # arret du serveur : la recherche s'arrete avec nous
            task.cancel()
            raise
        if task.done():
            return task.result()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, chess.engine.EngineError):
            pass
        raise chess.engine.EngineTerminatedError(f"processus du moteur termine (code {died.result()})")

    async def _execute(self, job) -> None:
        job_id = job["id"]
        settings = json.loads(job["settings_json"])
        self.running_job_id = job_id
        self._stop_event = asyncio.Event()
        self.broker.notify(job_id)
        log.info("analyse %s : debut (profondeur %d, MultiPV <= %d, budget %d s)", job_id[:8],
                 settings["target_depth"], settings["multipv_max"], settings["budget_s"])
        last_push = 0.0
        pending: list[asyncio.Future] = []  # ecritures de paliers, a terminer avant le resultat final

        def on_progress(kind: str, partial: RootAnalysis) -> None:
            nonlocal last_push
            self.live[job_id] = partial
            if kind == "stage":
                stage = max(partial.stages_reached_s)
                log.info("analyse %s : palier %d atteste a %.1f s", job_id[:8], stage, partial.stages_reached_s[stage])
                pending.append(asyncio.get_running_loop().run_in_executor(
                    self._writer, self._with_conn, analysis_repo.save_stage, job_id, stage, partial))
                self.broker.notify(job_id)
                last_push = time.monotonic()
            elif time.monotonic() - last_push >= PROGRESS_INTERVAL_S:
                self.broker.notify(job_id)
                last_push = time.monotonic()

        result: RootAnalysis | None = None
        error: str | None = None
        try:
            board = await asyncio.to_thread(self._board, job)
            if self.engine.info is None:
                await self.engine.restart()
            if self.engine.info is None:
                raise RuntimeError("moteur indisponible")
            async with self.engine.lock:
                result = await self._guarded(analyse_root(
                    self.engine.engine, board, target_depth=settings["target_depth"],
                    multipv_max=settings["multipv_max"], budget_s=settings["budget_s"],
                    on_progress=on_progress, stop_event=self._stop_event,
                ))
        except (chess.engine.EngineTerminatedError, chess.engine.EngineError) as exc:
            error = "le moteur s'est arrete pendant le calcul"
            log.error("analyse %s : %s (%r) ; redemarrage du moteur", job_id[:8], error, exc)
            await self.engine.restart()
        except asyncio.CancelledError:
            # Arret du serveur : le travail sera marque 'interrupted' au prochain demarrage.
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.exception("analyse %s : echec", job_id[:8])
        finally:
            self.running_job_id = None
            self._stop_event = None

        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.get_running_loop().run_in_executor(
            self._writer, lambda: self._with_conn(analysis_repo.finish, job_id, result, error=error))
        self.live.pop(job_id, None)
        self.broker.notify(job_id)
        if result is not None:
            log.info("analyse %s : fin, %s, %d ligne(s), %.1f s", job_id[:8], result.status, len(result.lines), result.elapsed_s)
