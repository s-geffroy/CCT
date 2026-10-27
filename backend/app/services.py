"""Services applicatifs partages par les routes et le planificateur.

- `AnalysisService.enqueue` : seul point de creation d'un travail d'analyse
  (moteur disponible, position non terminale, cache, file bornee).
- `ReferenceService` : construit l'arbre de reference d'une seance ou d'une
  etude, noeud par noeud, sous les plafonds de `TreeSettings`. Il avance quand
  un travail se termine, quand la file se vide, a la soumission d'une seance
  et sur demande de reanalyse.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import chess

from .domain import reference_policy as policy
from .domain.errors import DomainError, InvalidInput, NotFound
from .domain.review import node_paths as user_tree_paths
from .log import get_logger
from .persistence import analysis_repo, reference_repo, repo, sessions_repo
from .persistence.db import Database

log = get_logger("reference")

PRIORITY_STUDY = 100             # demande explicite d'etude
PRIORITY_USER_REANALYSIS = 90    # reanalyse demandee d'une branche
PRIORITY_SESSION_REFERENCE = 50  # preparation de fond d'une seance
MIN_NODE_BUDGET_S = 5
MAX_ROUNDS = 400


class EngineUnavailable(DomainError):
    status_code = 503


def default_settings(prefs) -> dict:
    """Analyse racine de la reference d'une seance (reglages courants)."""
    return {"target_depth": prefs["reference_depth"], "multipv_max": 20, "budget_s": prefs["reference_budget_s"]}


def tree_defaults(prefs) -> policy.TreeSettings:
    return policy.TreeSettings(budget_s=prefs["tree_budget_s"], max_nodes=prefs["tree_max_nodes"],
                               node_depth=prefs["tree_node_depth"], node_budget_s=prefs["tree_node_budget_s"],
                               auto_max_ply=prefs["tree_auto_max_ply"])


class AnalysisService:
    def __init__(self, settings, engine, scheduler):
        self.settings = settings
        self.engine = engine
        self.scheduler = scheduler

    def engine_desc(self) -> dict:
        info = self.engine.info
        if info is None:
            raise EngineUnavailable("ENGINE_UNAVAILABLE", "Moteur indisponible : analyse impossible pour l'instant.")
        return {"name": info.name, "build": info.build, "threads": info.threads, "hash_mb": info.hash_mb}

    def enqueue(self, conn: sqlite3.Connection, *, position_id: str, session_id: str | None, purpose: str,
                priority: int, settings: dict, node_path: list[str] | None = None) -> tuple[sqlite3.Row, bool]:
        engine_desc = self.engine_desc()
        position = repo.get_position(conn, position_id)
        if position is None:
            raise NotFound("POSITION_NOT_FOUND", "Position inconnue.")
        if position["outcome"] and not node_path:
            raise DomainError("TERMINAL_POSITION", "Partie terminee dans cette position : aucune variante a calculer.")
        context = conn.execute("SELECT context_key FROM positions WHERE id = ?", (position_id,)).fetchone()[0]
        key = analysis_repo.cache_key(context, engine_desc, settings, node_path)
        job, reused = analysis_repo.create_or_reuse(
            conn, position_id=position_id, session_id=session_id, purpose=purpose, priority=priority,
            settings={**settings, "engine": engine_desc}, key=key, max_queued=self.settings.max_queued_jobs,
            node_path=node_path)
        if not reused:
            self.scheduler.wake()
        return job, reused


class ReferenceService:
    def __init__(self, db: Database, analysis: AnalysisService, prefs):
        self.db = db
        self.analysis = analysis
        self.prefs = prefs  # reglages lus a chaque nouvel arbre
        # Un seul processus : un verrou suffit a serialiser les avancees d'arbre
        # (routes et planificateur les declenchent depuis des threads differents).
        self._lock = threading.RLock()

    # ------------------------------------------------------------ creation

    def create(self, conn: sqlite3.Connection, *, position_id: str, session_id: str | None, root_job: sqlite3.Row,
               settings: policy.TreeSettings | None = None) -> str:
        position = repo.get_position(conn, position_id)
        tree_id = reference_repo.create_tree(
            conn, position_id=position_id, session_id=session_id, root_job=root_job, root_fen=position["fen"],
            settings=(settings or tree_defaults(self.prefs)).to_dict())
        self.advance(tree_id)
        return tree_id

    # ------------------------------------------------------------- avancee

    def on_job_finished(self, job_id: str) -> None:
        with self.db.session() as conn:
            trees = reference_repo.trees_for_job(conn, job_id)
        for tree_id in trees:
            self.advance(tree_id)

    def on_idle(self) -> None:
        """File vide : reprendre les arbres en attente (file pleine, redemarrage)."""
        with self.db.session() as conn:
            trees = reference_repo.building_trees(conn)
        for tree_id in trees:
            self.advance(tree_id)

    def advance(self, tree_id: str) -> None:
        with self._lock, self.db.session() as conn:
            for _ in range(MAX_ROUNDS):
                try:
                    if not self._round(conn, tree_id):
                        return
                except DomainError as exc:
                    log.warning("arbre %s : avancee suspendue (%s)", tree_id[:8], exc.code)
                    return
            log.warning("arbre %s : trop d'etapes en un appel, reprise plus tard", tree_id[:8])

    def _round(self, conn: sqlite3.Connection, tree_id: str) -> bool:
        """Une etape ; True s'il faut recommencer (un noeud a ete cree ou change)."""
        reference_repo.refresh_statuses(conn, tree_id)
        tree = reference_repo.get_tree(conn, tree_id)
        settings = policy.TreeSettings.from_dict(json.loads(tree["settings_json"]))
        position = repo.get_position(conn, tree["position_id"])
        rows = reference_repo.nodes(conn, tree_id)
        by_path = {reference_repo.path_of(r): r for r in rows}

        if self._restart_interrupted(conn, tree, rows):
            return True
        root = by_path[()]
        if root["status"] in reference_repo.PENDING:
            reference_repo.set_state(conn, tree_id, "building")
            return False
        if root["status"] == "failed":
            reference_repo.set_state(conn, tree_id, "failed")
            return False

        plan_nodes = {
            path: policy.PlanNode(path, r["status"], reference_repo.raw_lines(conn, reference_repo.lines_job_id(conn, r)),
                                  analysed=r["status"] in reference_repo.ANALYSED or bool(r["previous_job_id"]))
            for path, r in by_path.items()
        }
        root_white = position["turn"] == "white"
        cands = policy.candidates(settings, plan_nodes, self._user_paths(conn, tree), root_white)
        def envelope(reason: str) -> str:
            return "user" if reason in reference_repo.USER_REASONS else "auto"

        live = {"auto": 0, "user": 0}  # la racine compte dans l'enveloppe automatique
        for r in rows:
            if r["status"] != "pruned_by_policy" and r["selection_reason"] != "user_requested_reanalysis":
                live[envelope(r["selection_reason"])] += 1
        remaining = {e: settings.budget_s - reference_repo.spent_seconds(conn, tree_id, e) for e in live}
        inflight = sum(1 for r in rows if r["ply"] > 0 and r["status"] in reference_repo.PENDING)
        pruned, by_nodes, pending = 0, False, False
        for cand in cands:
            parent = by_path.get(cand.path[:-1])
            if parent is None:
                continue  # le parent sera cree a une etape suivante
            env = envelope(cand.reason)
            if live[env] >= settings.max_nodes or remaining[env] < MIN_NODE_BUDGET_S:
                pruned += 1
                by_nodes = by_nodes or live[env] >= settings.max_nodes
                if env == "user":
                    # Branche du joueur non analysee : le debriefing doit pouvoir le dire.
                    self._insert(conn, tree, parent, cand, position, job=None, status="pruned_by_policy")
                    return True
                continue
            if inflight >= settings.inflight:
                pending = True
                break
            board = reference_repo.board_at(position, cand.path)
            if board.is_game_over(claim_draw=False):
                self._insert(conn, tree, parent, cand, position, job=None, status="terminal")
                return True
            try:
                job, _ = self.analysis.enqueue(
                    conn, position_id=tree["position_id"], session_id=tree["session_id"],
                    purpose="initial_reference" if tree["session_id"] else "study", priority=cand.priority,
                    settings={"target_depth": settings.node_depth, "multipv_max": settings.max_children,
                              "budget_s": int(min(settings.node_budget_s, remaining[env]))},
                    node_path=list(cand.path))
            except analysis_repo.TooManyJobs:
                pending = True  # file pleine : on reprendra quand elle se videra
                break
            except EngineUnavailable:
                self._insert(conn, tree, parent, cand, position, job=None, status="failed")
                return True
            self._insert(conn, tree, parent, cand, position, job=job, status=reference_repo.NODE_STATUS[job["state"]])
            return True

        if inflight or pending:
            reference_repo.set_state(conn, tree_id, "building")
            return False
        user_pruned = sum(1 for r in rows if r["status"] == "pruned_by_policy")
        by_nodes = by_nodes or any(r["status"] == "pruned_by_policy" for r in rows) and live["user"] >= settings.max_nodes
        state = "complete" if not (pruned or user_pruned) else "node_limit" if by_nodes else "budget_exhausted"
        reference_repo.set_state(conn, tree_id, state, pruned=pruned + user_pruned)
        return False

    def _insert(self, conn, tree, parent, cand: policy.Candidate, position: dict, *, job, status: str) -> None:
        before = reference_repo.board_at(position, cand.path[:-1])
        move = chess.Move.from_uci(cand.path[-1])
        san = before.san(move)
        before.push(move)
        reference_repo.insert_node(
            conn, tree_id=tree["id"], parent_id=parent["id"], path=cand.path, move_uci=move.uci(), move_san=san,
            fen=before.fen(), job_id=job["id"] if job is not None else None, status=status, reason=cand.reason)

    def _restart_interrupted(self, conn, tree, rows) -> bool:
        """Un travail interrompu par un arret du serveur est relance une fois."""
        restarted = False
        for node in rows:
            if node["job_id"] is None or node["previous_job_id"] is not None:
                continue
            job = analysis_repo.get(conn, node["job_id"])
            if job["state"] != "interrupted":
                continue
            settings = {k: v for k, v in json.loads(job["settings_json"]).items() if k != "engine"}
            try:
                new_job, _ = self.analysis.enqueue(
                    conn, position_id=job["position_id"], session_id=job["session_id"], purpose=job["purpose"],
                    priority=job["priority"], settings=settings, node_path=analysis_repo.node_path(job) or None)
            except DomainError:
                continue
            reference_repo.replace_job(conn, node, new_job, reanalysed=False)
            if node["ply"] == 0 and tree["session_id"]:
                conn.execute("UPDATE sessions SET reference_job_id = ? WHERE id = ? AND reference_job_id = ?",
                             (new_job["id"], tree["session_id"], job["id"]))
            log.info("arbre %s : analyse interrompue relancee (%s)", tree["id"][:8], new_job["id"][:8])
            restarted = True
        return restarted

    def _user_paths(self, conn, tree) -> list[tuple[str, ...]]:
        """Branches de la tentative soumise (jamais l'arbre en cours d'edition)."""
        if tree["session_id"] is None:
            return []
        attempt = sessions_repo.get_attempt(conn, tree["session_id"])
        if attempt is None:
            return []
        return sorted(user_tree_paths(attempt.get("tree") or {}).values(), key=lambda p: (len(p), p))

    # ----------------------------------------------------------- reanalyse

    def expand(self, conn: sqlite3.Connection, tree_id: str, path: list[str]) -> None:
        """Reanalyse d'un noeud existant (plus profond), ou analyse d'un coup
        depuis un noeud existant. Hors budget automatique : c'est une demande."""
        tree = reference_repo.get_tree(conn, tree_id)
        position = repo.get_position(conn, tree["position_id"])
        try:
            board = reference_repo.board_at(position, tuple(path))
        except (ValueError, AssertionError):
            raise InvalidInput("ILLEGAL_PATH", "Suite de coups illegale depuis la position de l'arbre.")
        if board.is_game_over(claim_draw=False):
            raise DomainError("TERMINAL_POSITION", "Position terminale : rien a analyser.")
        settings = policy.TreeSettings.from_dict(json.loads(tree["settings_json"]))
        by_path = {reference_repo.path_of(r): r for r in reference_repo.nodes(conn, tree_id)}
        node = by_path.get(tuple(path))
        if node is None and tuple(path[:-1]) not in by_path:
            raise InvalidInput("PARENT_NOT_IN_TREE", "Le coup doit prolonger un noeud de l'arbre.")
        depth = settings.node_depth
        if node is not None and node["job_id"]:
            current = json.loads(analysis_repo.get(conn, node["job_id"])["settings_json"])["target_depth"]
            depth = min(32, max(depth, current) + 4)
        job_settings = {"target_depth": depth,
                        "multipv_max": 20 if not path else settings.max_children,
                        "budget_s": 120}
        job, _ = self.analysis.enqueue(
            conn, position_id=tree["position_id"], session_id=tree["session_id"],
            purpose="initial_reference" if tree["session_id"] else "study", priority=PRIORITY_USER_REANALYSIS,
            settings=job_settings, node_path=list(path) or None)
        with self._lock:
            if node is not None:
                reference_repo.replace_job(conn, node, job, reanalysed=True)
            else:
                cand = policy.Candidate(tuple(path), "user_requested_reanalysis", PRIORITY_USER_REANALYSIS)
                self._insert(conn, tree, by_path[tuple(path[:-1])], cand, position, job=job,
                             status=reference_repo.NODE_STATUS[job["state"]])
            reference_repo.set_state(conn, tree_id, "building")
        self.advance(tree_id)
