"""Reglages modifiables depuis l'interface (doc 08 : `GET`/`PUT /api/v1/settings`).

Les valeurs par defaut viennent de l'environnement (`Settings`) ; la base ne
garde que ce que l'utilisateur a change (table `settings`). Toute valeur est
bornee : une valeur hors bornes est refusee a l'ecriture et ignoree a la
lecture (base editee a la main, bornes resserrees par une mise a jour).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .domain.errors import InvalidInput
from .persistence.db import transaction, utc_now
from .settings import Settings


def max_threads() -> int:
    """Quota CPU effectif du conteneur (cgroups), sinon nombre de coeurs."""
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            return max(1, int(int(quota) / int(period)))
    except (OSError, ValueError):
        pass
    return max(1, os.cpu_count() or 1)


def max_hash_mb() -> int:
    """Un quart de la memoire allouee au conteneur, entre 16 et 4096 Mo."""
    try:
        raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if raw != "max":
            return max(16, min(4096, int(raw) // (4 * 1024 * 1024)))
    except (OSError, ValueError):
        pass
    return 1024


@dataclass(frozen=True)
class Field:
    key: str
    group: str
    label: str
    default: int | str
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] | None = None
    unit: str | None = None

    def check(self, value) -> int | str:
        if self.choices is not None:
            if value not in self.choices:
                raise InvalidInput("SETTING_INVALID", f"« {self.label} » : valeur inconnue.",
                                   {"key": self.key, "choices": list(self.choices)})
            return value
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidInput("SETTING_INVALID", f"« {self.label} » : nombre entier attendu.", {"key": self.key})
        if not self.minimum <= value <= self.maximum:
            raise InvalidInput("SETTING_OUT_OF_RANGE",
                               f"« {self.label} » doit etre compris entre {self.minimum} et {self.maximum}.",
                               {"key": self.key, "minimum": self.minimum, "maximum": self.maximum})
        return value

    def describe(self) -> dict:
        out = {"key": self.key, "group": self.group, "label": self.label, "default": self.default}
        if self.choices is not None:
            out["choices"] = list(self.choices)
        else:
            out.update({"minimum": self.minimum, "maximum": self.maximum, "unit": self.unit})
        return out


def build_fields(s: Settings) -> list[Field]:
    threads_max = max_threads()
    hash_max = max_hash_mb()
    return [
        Field("engine_threads", "moteur", "Threads Stockfish", min(s.engine_threads, threads_max), 1, threads_max),
        Field("engine_hash_mb", "moteur", "Table de hachage", min(s.engine_hash_mb, hash_max), 16, hash_max, unit="Mo"),
        Field("study_depth", "etude", "Profondeur cible (etude libre)", 21, 8, 32),
        Field("study_multipv", "etude", "Variantes affichees (MultiPV)", 20, 1, 20),
        Field("study_budget_s", "etude", "Budget d'une analyse", 300, 5, 1800, unit="s"),
        Field("reference_depth", "seance", "Profondeur de la reference", s.reference_depth, 8, 32),
        Field("reference_budget_s", "seance", "Budget de l'analyse racine", s.reference_budget_s, 5, 3600, unit="s"),
        Field("tree_budget_s", "arbre", "Budget de l'arbre (par enveloppe)", s.tree_budget_s, 0, 3600, unit="s"),
        Field("tree_max_nodes", "arbre", "Noeuds maximum (par enveloppe)", s.tree_max_nodes, 1, 500),
        Field("tree_node_depth", "arbre", "Profondeur visee a chaque noeud", s.tree_node_depth, 8, 32),
        Field("tree_node_budget_s", "arbre", "Budget par noeud", s.tree_node_budget_s, 5, 600, unit="s"),
        Field("tree_auto_max_ply", "arbre", "Demi-coups explores automatiquement", s.tree_auto_max_ply, 0, 12),
        Field("score_perspective", "affichage", "Point de vue des evaluations", "white",
              choices=("white", "side_to_move")),
    ]


class Preferences:
    def __init__(self, settings: Settings):
        self.fields = {f.key: f for f in build_fields(settings)}
        self._values = {k: f.default for k, f in self.fields.items()}
        self._lock = threading.Lock()

    def load(self, conn: sqlite3.Connection) -> None:
        values = {k: f.default for k, f in self.fields.items()}
        for row in conn.execute("SELECT key, value_json FROM settings").fetchall():
            field = self.fields.get(row["key"])
            if field is None:
                continue
            try:
                values[row["key"]] = field.check(json.loads(row["value_json"]))
            except (InvalidInput, ValueError):
                continue  # valeur devenue invalide : on garde le defaut
        with self._lock:
            self._values = values

    @property
    def values(self) -> dict:
        with self._lock:
            return dict(self._values)

    def __getitem__(self, key: str):
        with self._lock:
            return self._values[key]

    def update(self, conn: sqlite3.Connection, patch: dict) -> dict:
        unknown = sorted(set(patch) - set(self.fields))
        if unknown:
            raise InvalidInput("SETTING_UNKNOWN", "Reglage inconnu.", {"keys": unknown})
        checked = {k: self.fields[k].check(v) for k, v in patch.items()}
        with transaction(conn):
            for key, value in checked.items():
                if value == self.fields[key].default:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)"
                        " ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                        (key, json.dumps(value), utc_now()))
        with self._lock:
            self._values.update(checked)
            return dict(self._values)

    def reset(self, conn: sqlite3.Connection) -> dict:
        with transaction(conn):
            conn.execute("DELETE FROM settings")
        with self._lock:
            self._values = {k: f.default for k, f in self.fields.items()}
            return dict(self._values)

    def describe(self) -> list[dict]:
        return [f.describe() for f in self.fields.values()]
